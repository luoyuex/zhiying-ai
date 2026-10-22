"""选股服务：主力资金排行筛选。"""

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from zoneinfo import ZoneInfo

from redis.asyncio import Redis

from app.core.logging import get_logger
from app.providers.base import ProviderUnavailable
from app.providers.fund_flow_rank import SinaFundFlowRankProvider
from app.providers.http import fetch, provider_slot
from app.providers.models import Quote
from app.providers.performance import EastmoneyPerformanceProvider
from app.providers.symbols import (
    InvalidSymbolError,
    StockSymbol,
    parse_symbol,
)
from app.providers.tencent import TencentProvider
from app.schemas.screener import (
    FundFlowRankItem,
    LowPriceBullItem,
    LowPriceBullRequest,
    LowPriceBullResponse,
    MainForceScreenRequest,
    MainForceScreenResponse,
    PerformanceRow,
    ProfitGrowthAnalysisRequest,
    ProfitGrowthItem,
    ScreenerStrategy,
    SmallCapItem,
    SmallCapRequest,
    SmallCapResponse,
)

logger = get_logger(__name__)
TZ_SHANGHAI = ZoneInfo("Asia/Shanghai")

RANK_CACHE_KEY = "mkt:screener:fundflow_rank"
RANK_CACHE_TTL = 60
RANK_LIMIT = 300

STRATEGIES = [
    ScreenerStrategy(
        id="main_force",
        name="主力追踪",
        description=(
            "AI 三位分析师（资金流向 / 行业板块 / 财务基本面）分析主力资金靠前标的，"
            "由资深研究员精选最终结果。"
        ),
    ),
    ScreenerStrategy(
        id="low_price_bull",
        name="低价寻宝",
        description=(
            "AI 三位分析师（资金与流动性 / 行业板块 / 业绩成长）分析低价、高净利增长标的，"
            "由资深研究员精选最终结果。"
        ),
    ),
    ScreenerStrategy(
        id="small_cap",
        name="小盘精选",
        description=(
            "AI 三位分析师（资金与流动性 / 行业板块 / 成长与估值）分析小市值、高增长标的，"
            "由资深研究员精选最终结果。"
        ),
    ),
    ScreenerStrategy(
        id="profit_growth",
        name="业绩高增",
        description=(
            "AI 三位分析师（资金与流动性 / 行业板块 / 成长质量）分析高净利增长标的，"
            "由资深研究员精选最终结果。"
        ),
    ),
    ScreenerStrategy(
        id="value_stock",
        name="价值洼地",
        description=(
            "AI 三位分析师（资金与流动性 / 行业板块 / 估值质量）分析低 PE/PB、"
            "近 12 个月高股息、最新报告期低负债标的，由资深研究员精选最终结果。"
        ),
    ),
]


async def load_fund_flow_rank(redis: Redis) -> list[FundFlowRankItem]:
    try:
        cached = await redis.get(RANK_CACHE_KEY)
        if cached:
            return [FundFlowRankItem.model_validate(item) for item in json.loads(cached)]
    except Exception as exc:  # noqa: BLE001
        logger.warning("读取资金流排行缓存失败: %s", exc)

    items = await SinaFundFlowRankProvider().fetch(limit=RANK_LIMIT)
    try:
        await redis.set(
            RANK_CACHE_KEY,
            json.dumps([item.model_dump() for item in items], ensure_ascii=False),
            ex=RANK_CACHE_TTL,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("写入资金流排行缓存失败: %s", exc)
    return items


def _is_gem(symbol: str) -> bool:
    return symbol.startswith(("300", "301"))


def _is_star(symbol: str) -> bool:
    return symbol.startswith(("688", "689"))


def _is_bj(symbol: str) -> bool:
    return symbol.startswith(("43", "83", "87", "88", "92"))


def filter_main_force(
    items: list[FundFlowRankItem],
    request: MainForceScreenRequest,
) -> list[FundFlowRankItem]:
    result: list[FundFlowRankItem] = []
    for item in items:
        if request.exclude_st and "ST" in item.name.upper():
            continue
        if request.exclude_gem and _is_gem(item.symbol):
            continue
        if request.exclude_star and _is_star(item.symbol):
            continue
        if request.exclude_bj and _is_bj(item.symbol):
            continue
        if request.max_change_pct is not None:
            if item.change_pct is None or item.change_pct > request.max_change_pct:
                continue
        if request.min_price is not None:
            if item.price is None or item.price < request.min_price:
                continue
        if request.max_price is not None:
            if item.price is None or item.price > request.max_price:
                continue
        result.append(item)
    return result


async def screen_main_force(
    redis: Redis,
    request: MainForceScreenRequest,
) -> MainForceScreenResponse:
    items = await load_fund_flow_rank(redis)
    filtered = filter_main_force(items, request)
    return MainForceScreenResponse(
        items=filtered[: request.top_n],
        scanned_count=len(items),
        candidate_count=len(filtered),
        fetched_at=datetime.now(TZ_SHANGHAI),
        filters={
            "top_n": request.top_n,
            "max_change_pct": request.max_change_pct,
            "min_price": request.min_price,
            "max_price": request.max_price,
            "exclude_st": request.exclude_st,
            "exclude_gem": request.exclude_gem,
            "exclude_star": request.exclude_star,
            "exclude_bj": request.exclude_bj,
        },
    )


QUOTE_BATCH_URL = "https://qt.gtimg.cn/q={}"
QUOTE_BATCH_SIZE = 50


async def fetch_quotes(symbols: list[StockSymbol]) -> dict[str, Quote]:
    """腾讯批量报价：一次最多 50 只，单只失败不影响整批。"""
    quotes: dict[str, Quote] = {}
    for start in range(0, len(symbols), QUOTE_BATCH_SIZE):
        chunk = symbols[start : start + QUOTE_BATCH_SIZE]
        query = ",".join(item.prefixed for item in chunk)
        try:
            async with provider_slot():
                response = await fetch(QUOTE_BATCH_URL.format(query))
        except ProviderUnavailable as exc:
            logger.warning("批量报价失败: %s", exc)
            continue
        for symbol in chunk:
            try:
                quotes[symbol.code] = TencentProvider.parse_quote(symbol, response.content)
            except Exception as exc:  # noqa: BLE001 - 停牌/无报价的股票跳过
                logger.info("批量报价解析失败 %s: %s", symbol.code, exc)
    return quotes


class _ExcludeOptions(Protocol):
    exclude_st: bool
    exclude_gem: bool
    exclude_star: bool
    exclude_bj: bool


def _eligible_performance_symbols(
    rows: list[PerformanceRow],
    options: _ExcludeOptions,
) -> list[tuple[PerformanceRow, StockSymbol]]:
    selected: list[tuple[PerformanceRow, StockSymbol]] = []
    for row in rows:
        if options.exclude_st and "ST" in row.name.upper():
            continue
        try:
            symbol = parse_symbol(row.symbol)
        except InvalidSymbolError:
            continue
        if options.exclude_gem and symbol.code.startswith(("300", "301")):
            continue
        if options.exclude_star and symbol.code.startswith(("688", "689")):
            continue
        if options.exclude_bj and symbol.exchange == "BJ":
            continue
        selected.append((row, symbol))
    return selected


async def screen_low_price_bull(
    request: LowPriceBullRequest,
    *,
    provider: EastmoneyPerformanceProvider | None = None,
) -> LowPriceBullResponse:
    """低价擒牛：股价上限 + 净利同比下限，剔除板块/ST，按成交额升序。"""
    candidates = await collect_low_price_candidates(
        request,
        provider=provider,
        limit=request.top_n,
    )
    return LowPriceBullResponse(
        items=candidates.items,
        scanned_count=candidates.scanned_count,
        candidate_count=candidates.candidate_count,
        fetched_at=datetime.now(TZ_SHANGHAI),
        source="eastmoney_performance+tencent",
        filters={
            "top_n": request.top_n,
            "max_price": request.max_price,
            "min_profit_growth": request.min_profit_growth,
            "max_change_pct": request.max_change_pct,
            "exclude_st": request.exclude_st,
            "exclude_gem": request.exclude_gem,
            "exclude_star": request.exclude_star,
            "exclude_bj": request.exclude_bj,
            "report_date": candidates.report_date,
        },
    )


@dataclass
class LowPriceCandidateSet:
    items: list[LowPriceBullItem]
    quotes: dict[str, Quote]
    performance: dict[str, PerformanceRow]
    report_date: str
    scanned_count: int
    candidate_count: int


async def collect_low_price_candidates(
    request: LowPriceBullRequest,
    *,
    provider: EastmoneyPerformanceProvider | None = None,
    limit: int = 40,
) -> LowPriceCandidateSet:
    provider = provider or EastmoneyPerformanceProvider()
    report_date, rows = await provider.fetch(request.min_profit_growth)
    selected = _eligible_performance_symbols(rows, request)
    quotes = await fetch_quotes([symbol for _, symbol in selected])

    items: list[LowPriceBullItem] = []
    performance: dict[str, PerformanceRow] = {}
    for row, symbol in selected:
        if row.profit_growth is None or row.profit_growth < request.min_profit_growth:
            continue
        quote = quotes.get(symbol.code)
        if quote is None or quote.price is None or quote.amount is None:
            continue
        if quote.price >= request.max_price:
            continue
        if (
            request.max_change_pct is not None
            and quote.change_pct is not None
            and quote.change_pct > request.max_change_pct
        ):
            continue
        performance[symbol.code] = row
        items.append(
            LowPriceBullItem(
                symbol=symbol.code,
                name=row.name,
                price=quote.price,
                change_pct=quote.change_pct,
                amount=quote.amount,
                profit_growth=row.profit_growth,
                revenue_growth=row.revenue_growth,
                report_date=row.report_date or report_date,
            )
        )

    # 参考项目按成交额由小到大排名
    items.sort(key=lambda item: item.amount or 0)
    return LowPriceCandidateSet(
        items=items[:limit],
        quotes=quotes,
        performance=performance,
        report_date=report_date,
        scanned_count=len(rows),
        candidate_count=len(items),
    )


async def screen_small_cap(
    request: SmallCapRequest,
    *,
    provider: EastmoneyPerformanceProvider | None = None,
) -> SmallCapResponse:
    """小市值：总市值上限 + 营收/净利增速下限，按总市值升序。"""
    candidates = await collect_small_cap_candidates(
        request,
        provider=provider,
        limit=request.top_n,
    )
    return SmallCapResponse(
        items=candidates.items,
        scanned_count=candidates.scanned_count,
        candidate_count=candidates.candidate_count,
        fetched_at=datetime.now(TZ_SHANGHAI),
        source="eastmoney_performance+tencent",
        filters={
            "top_n": request.top_n,
            "max_market_cap": request.max_market_cap,
            "min_profit_growth": request.min_profit_growth,
            "min_revenue_growth": request.min_revenue_growth,
            "max_change_pct": request.max_change_pct,
            "exclude_st": request.exclude_st,
            "exclude_gem": request.exclude_gem,
            "exclude_star": request.exclude_star,
            "exclude_bj": request.exclude_bj,
            "report_date": candidates.report_date,
        },
    )


@dataclass
class SmallCapCandidateSet:
    items: list[SmallCapItem]
    quotes: dict[str, Quote]
    performance: dict[str, PerformanceRow]
    report_date: str
    scanned_count: int
    candidate_count: int


async def collect_small_cap_candidates(
    request: SmallCapRequest,
    *,
    provider: EastmoneyPerformanceProvider | None = None,
    limit: int = 40,
) -> SmallCapCandidateSet:
    provider = provider or EastmoneyPerformanceProvider()
    report_date, rows = await provider.fetch(
        request.min_profit_growth,
        request.min_revenue_growth,
    )
    selected = _eligible_performance_symbols(rows, request)
    quotes = await fetch_quotes([symbol for _, symbol in selected])
    max_cap = request.max_market_cap * 1e8

    items: list[SmallCapItem] = []
    performance: dict[str, PerformanceRow] = {}
    for row, symbol in selected:
        if row.profit_growth is None or row.profit_growth < request.min_profit_growth:
            continue
        if row.revenue_growth is None or row.revenue_growth < request.min_revenue_growth:
            continue
        quote = quotes.get(symbol.code)
        if quote is None or quote.price is None or quote.total_market_cap is None:
            continue
        if quote.total_market_cap > max_cap:
            continue
        if (
            request.max_change_pct is not None
            and quote.change_pct is not None
            and quote.change_pct > request.max_change_pct
        ):
            continue
        performance[symbol.code] = row
        items.append(
            SmallCapItem(
                symbol=symbol.code,
                name=row.name,
                price=quote.price,
                change_pct=quote.change_pct,
                total_market_cap=quote.total_market_cap,
                profit_growth=row.profit_growth,
                revenue_growth=row.revenue_growth,
                report_date=row.report_date or report_date,
            )
        )

    # 参考项目按总市值由小到大排名
    items.sort(key=lambda item: item.total_market_cap or 0)
    return SmallCapCandidateSet(
        items=items[:limit],
        quotes=quotes,
        performance=performance,
        report_date=report_date,
        scanned_count=len(rows),
        candidate_count=len(items),
    )


@dataclass
class ProfitGrowthCandidateSet:
    items: list[ProfitGrowthItem]
    quotes: dict[str, Quote]
    performance: dict[str, PerformanceRow]
    report_date: str
    scanned_count: int
    candidate_count: int


async def collect_profit_growth_candidates(
    request: ProfitGrowthAnalysisRequest,
    *,
    provider: EastmoneyPerformanceProvider | None = None,
    limit: int = 40,
) -> ProfitGrowthCandidateSet:
    """净利增长：最新报告期净利同比达到阈值，按成交额由小到大排名。"""
    provider = provider or EastmoneyPerformanceProvider()
    report_date, rows = await provider.fetch(request.min_profit_growth)
    selected = _eligible_performance_symbols(rows, request)
    quotes = await fetch_quotes([symbol for _, symbol in selected])

    items: list[ProfitGrowthItem] = []
    performance: dict[str, PerformanceRow] = {}
    for row, symbol in selected:
        if row.profit_growth is None or row.profit_growth < request.min_profit_growth:
            continue
        quote = quotes.get(symbol.code)
        if quote is None or quote.price is None or quote.amount is None:
            continue
        if (
            request.max_change_pct is not None
            and quote.change_pct is not None
            and quote.change_pct > request.max_change_pct
        ):
            continue
        performance[symbol.code] = row
        items.append(
            ProfitGrowthItem(
                symbol=symbol.code,
                name=row.name,
                price=quote.price,
                change_pct=quote.change_pct,
                amount=quote.amount,
                profit_growth=row.profit_growth,
                revenue_growth=row.revenue_growth,
                report_date=row.report_date or report_date,
            )
        )

    items.sort(key=lambda item: item.amount or 0)
    return ProfitGrowthCandidateSet(
        items=items[:limit],
        quotes=quotes,
        performance=performance,
        report_date=report_date,
        scanned_count=len(rows),
        candidate_count=len(items),
    )
