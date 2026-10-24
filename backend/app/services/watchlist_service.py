"""自选股：增删查与列表行情。"""

import asyncio

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import distinct_on, insert

from app.core.logging import get_logger
from app.db.models.analysis_report import AnalysisReport
from app.db.models.position_change_log import PositionChangeLog
from app.db.models.stock import Stock
from app.db.models.watchlist import WatchlistItem
from app.db.session import SessionLocal
from app.llm.client import LLMNotConfiguredError
from app.providers.symbols import InvalidSymbolError, StockSymbol, parse_symbol
from app.schemas.watchlist import (
    LatestAnalysis,
    PositionChangeEntry,
    WatchlistBatchResult,
    WatchlistEntry,
)
from app.services.ai_job_service import AIWorkerUnavailableError, start_ai_job
from app.services.market_service import MarketDataService
from app.services.quote_batch import fetch_quotes

logger = get_logger(__name__)

MAX_WATCHLIST = 50
# 批量报价缺个别时，最多用单只链路补这么多只，避免请求量反弹
QUOTE_FALLBACK_MAX = 5


class WatchlistLimitError(Exception):
    pass


async def add_watchlist(
    user_id: object,
    raw_symbol: str,
    *,
    note: str = "",
    cost_price: float | None = None,
    quantity: int | None = None,
) -> tuple[str, bool]:
    """幂等加入；返回（归一化代码, 是否新增）。"""
    symbol = parse_symbol(raw_symbol).code
    async with SessionLocal() as session:
        existing = (
            await session.scalars(
                select(WatchlistItem).where(WatchlistItem.user_id == user_id)
            )
        ).all()
        if len(existing) >= MAX_WATCHLIST:
            raise WatchlistLimitError(f"自选股最多 {MAX_WATCHLIST} 只")

        result = await session.execute(
            insert(WatchlistItem)
            .values(
                user_id=user_id,
                symbol=symbol,
                note=note.strip()[:120],
                cost_price=cost_price,
                quantity=quantity,
            )
            .on_conflict_do_nothing(constraint="uq_watchlist_user_symbol")
        )
        await session.commit()
        return symbol, bool(result.rowcount)


async def update_watchlist(user_id: object, raw_symbol: str, changes: dict) -> bool:
    """只更新传入的字段（备注 / 成本价 / 数量）；成本价或数量变化时写调仓记录。"""
    if not changes:
        return False
    symbol = parse_symbol(raw_symbol).code
    async with SessionLocal() as session:
        row = await session.scalar(
            select(WatchlistItem).where(
                WatchlistItem.user_id == user_id, WatchlistItem.symbol == symbol
            )
        )
        if row is None:
            return False

        cost_changed = (
            "cost_price" in changes and changes["cost_price"] != row.cost_price
        )
        qty_changed = "quantity" in changes and changes["quantity"] != row.quantity
        if cost_changed or qty_changed:
            session.add(
                PositionChangeLog(
                    user_id=user_id,
                    symbol=symbol,
                    old_cost_price=row.cost_price,
                    new_cost_price=changes.get("cost_price", row.cost_price),
                    old_quantity=row.quantity,
                    new_quantity=changes.get("quantity", row.quantity),
                )
            )
        for field, value in changes.items():
            setattr(row, field, value)
        await session.commit()
        return True


async def list_position_history(
    user_id: object,
    raw_symbol: str,
    *,
    limit: int = 30,
) -> list[PositionChangeEntry]:
    symbol = parse_symbol(raw_symbol).code
    async with SessionLocal() as session:
        rows = (
            await session.scalars(
                select(PositionChangeLog)
                .where(
                    PositionChangeLog.user_id == user_id,
                    PositionChangeLog.symbol == symbol,
                )
                .order_by(PositionChangeLog.created_at.desc())
                .limit(limit)
            )
        ).all()
    return [
        PositionChangeEntry(
            id=str(row.id),
            symbol=row.symbol,
            old_cost_price=float(row.old_cost_price) if row.old_cost_price is not None else None,
            new_cost_price=float(row.new_cost_price) if row.new_cost_price is not None else None,
            old_quantity=row.old_quantity,
            new_quantity=row.new_quantity,
            created_at=row.created_at,
        )
        for row in rows
    ]


async def remove_watchlist(user_id: object, raw_symbol: str) -> bool:
    symbol = parse_symbol(raw_symbol).code
    async with SessionLocal() as session:
        result = await session.execute(
            delete(WatchlistItem).where(
                WatchlistItem.user_id == user_id,
                WatchlistItem.symbol == symbol,
            )
        )
        await session.commit()
        return bool(result.rowcount)


async def is_watchlisted(user_id: object, raw_symbol: str) -> bool:
    symbol = parse_symbol(raw_symbol).code
    async with SessionLocal() as session:
        row = await session.scalar(
            select(WatchlistItem.id)
            .where(WatchlistItem.user_id == user_id, WatchlistItem.symbol == symbol)
            .limit(1)
        )
        return row is not None


async def list_watchlist(
    user_id: object,
    market: MarketDataService,
) -> list[WatchlistEntry]:
    async with SessionLocal() as session:
        rows = (
            await session.scalars(
                select(WatchlistItem)
                .where(WatchlistItem.user_id == user_id)
                .order_by(WatchlistItem.created_at.desc())
            )
        ).all()
        if not rows:
            return []

        symbols = [row.symbol for row in rows]
        name_rows = (
            await session.execute(select(Stock.code, Stock.name).where(Stock.code.in_(symbols)))
        ).all()
        names = dict(name_rows)

        latest_rows = (
            await session.scalars(
                select(AnalysisReport)
                .where(
                    AnalysisReport.user_id == user_id,
                    AnalysisReport.symbol.in_(symbols),
                )
                .order_by(AnalysisReport.symbol, AnalysisReport.created_at.desc())
                .ext(distinct_on(AnalysisReport.symbol))
            )
        ).all()
        latest_by_symbol = {row.symbol: row for row in latest_rows}

    def latest_entry(symbol: str) -> LatestAnalysis | None:
        row = latest_by_symbol.get(symbol)
        if row is None:
            return None
        decision = (row.report or {}).get("decision") or {}
        return LatestAnalysis(
            report_id=str(row.id),
            rating=row.rating,
            confidence=row.confidence,
            decision_source=str(decision.get("decision_source") or ""),
            position_action=decision.get("position_action"),
            summary=str(decision.get("summary") or "")[:200],
            rating_change=row.rating_change,
            prev_rating=row.prev_rating,
            created_at=row.created_at,
        )

    # 腾讯批量报价：50 只以内只需 1 个请求，避免逐只请求打满令牌桶
    parsed: list[StockSymbol] = []
    for code in symbols:
        try:
            parsed.append(parse_symbol(code))
        except InvalidSymbolError:
            logger.info("自选股代码无效，跳过行情 %s", code)

    quotes = await fetch_quotes(parsed)

    # 批量缺个别（停牌/新股/解析失败）时，少量股票再走单只链路兜底；
    # 缺太多说明批量接口本身异常，逐只补会把请求量放大回去，直接跳过。
    missing = [item for item in parsed if item.code not in quotes]
    if missing and len(missing) <= QUOTE_FALLBACK_MAX:
        fallback = await asyncio.gather(
            *(market.get_quote(item.code) for item in missing),
            return_exceptions=True,
        )
        for item, quote in zip(missing, fallback, strict=True):
            if not isinstance(quote, BaseException):
                quotes[item.code] = quote

    await market.prime_quotes(quotes)

    entries: list[WatchlistEntry] = []
    for row in rows:
        quote = quotes.get(row.symbol)
        if quote is None:
            logger.info("自选股行情获取失败 %s", row.symbol)
            entries.append(
                WatchlistEntry(
                    symbol=row.symbol,
                    name=names.get(row.symbol, row.symbol),
                    added_at=row.created_at,
                    note=row.note,
                    cost_price=float(row.cost_price) if row.cost_price is not None else None,
                    quantity=row.quantity,
                    latest=latest_entry(row.symbol),
                )
            )
            continue
        entries.append(
            WatchlistEntry(
                symbol=quote.symbol,
                name=names.get(quote.symbol) or quote.name,
                price=quote.price,
                change_pct=quote.change_pct,
                source=quote.source,
                fetched_at=quote.fetched_at,
                delayed=quote.delayed,
                added_at=row.created_at,
                note=row.note,
                cost_price=float(row.cost_price) if row.cost_price is not None else None,
                quantity=row.quantity,
                latest=latest_entry(row.symbol),
            )
        )
    return entries


async def batch_analyze(
    user_id: object,
    daily_quota: int,
    raw_symbols: list[str],
    redis: object,
    *,
    force: bool = False,
) -> list[WatchlistBatchResult]:
    """逐只提交现有分析任务；单只失败不影响其余股票。"""
    results: list[WatchlistBatchResult] = []
    for raw in raw_symbols[:20]:
        try:
            state = await start_ai_job(redis, user_id, daily_quota, raw, force)
            results.append(
                WatchlistBatchResult(
                    symbol=state.symbol,
                    job_id=state.job_id,
                    status=state.status.value,
                )
            )
        except InvalidSymbolError as exc:
            results.append(
                WatchlistBatchResult(
                    symbol=raw,
                    status="failed",
                    error_code="INVALID_SYMBOL",
                    error_message=str(exc),
                )
            )
        except LLMNotConfiguredError as exc:
            results.append(
                WatchlistBatchResult(
                    symbol=raw,
                    status="failed",
                    error_code="LLM_NOT_CONFIGURED",
                    error_message=str(exc),
                )
            )
        except AIWorkerUnavailableError as exc:
            results.append(
                WatchlistBatchResult(
                    symbol=raw,
                    status="failed",
                    error_code="AI_SERVICE_UNAVAILABLE",
                    error_message=str(exc),
                )
            )
        except Exception as exc:  # noqa: BLE001 - 批量提交要逐只报错
            logger.warning("自选批量提交失败 %s: %s", raw, exc)
            results.append(
                WatchlistBatchResult(
                    symbol=raw,
                    status="failed",
                    error_code="AI_SERVICE_UNAVAILABLE",
                    error_message="提交分析任务失败",
                )
            )
    return results
