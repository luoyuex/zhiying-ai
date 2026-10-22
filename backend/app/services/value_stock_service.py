"""低估值策略：估值/股息/负债候选收集与 AI 选股。"""

from collections import Counter
from dataclasses import dataclass

from redis.asyncio import Redis

from app.core.logging import get_logger
from app.providers.base import safe_float
from app.providers.performance import EastmoneyPerformanceProvider
from app.providers.symbols import InvalidSymbolError, parse_symbol
from app.providers.value_stock import (
    fetch_debt_ratios,
    fetch_dividend_yields,
    fetch_valuation_snapshot,
)
from app.schemas.screener import (
    MainForceAnalysisResponse,
    PerformanceRow,
    ValueStockAnalysisRequest,
    ValueStockItem,
)
from app.services.main_force_analysis_service import (
    MAX_ANALYSIS_CANDIDATES,
    MainForceEmptyError,
    _ensure_client,
    _ensure_quota,
    _phase,
    _run_ai_selection,
)
from app.services.screener_service import fetch_quotes

logger = get_logger(__name__)


@dataclass
class ValueStockCandidateSet:
    items: list[ValueStockItem]
    quotes: dict
    performance: dict[str, PerformanceRow]
    report_date: str
    scanned_count: int
    candidate_count: int


def filter_value_snapshot(
    rows: list[dict],
    request: ValueStockAnalysisRequest,
) -> list[dict]:
    """PE/PB/板块/ST 过滤，保留流通市值升序。"""
    result: list[dict] = []
    for row in rows:
        code = str(row.get("SECURITY_CODE") or "").strip()
        name = str(row.get("SECURITY_NAME_ABBR") or "").strip()
        if len(code) != 6 or code[0] not in {"0", "3", "6"}:
            continue
        if request.exclude_st and "ST" in name.upper():
            continue
        if request.exclude_gem and code.startswith(("300", "301")):
            continue
        if request.exclude_star and code.startswith(("688", "689")):
            continue
        if request.exclude_bj and code.startswith(("43", "83", "87", "88", "92")):
            continue
        pe = safe_float(row.get("PE_TTM"))
        pb = safe_float(row.get("PB_MRQ"))
        price = safe_float(row.get("CLOSE_PRICE"))
        float_cap = safe_float(row.get("NOTLIMITED_MARKETCAP_A"))
        total_cap = safe_float(row.get("TOTAL_MARKET_CAP"))
        if pe is None or pb is None or price is None or price <= 0 or float_cap is None:
            continue
        if pe <= 0 or pe > request.max_pe or pb <= 0 or pb > request.max_pb:
            continue
        result.append(
            {
                "symbol": code,
                "name": name,
                "industry": str(row.get("BOARD_NAME") or "").strip(),
                "price": price,
                "change_pct": safe_float(row.get("CHANGE_RATE")),
                "pe": pe,
                "pb": pb,
                "float_market_cap": float_cap,
                "total_market_cap": total_cap,
            }
        )
    result.sort(key=lambda item: item["float_market_cap"] or 0)
    return result


async def collect_value_candidates(
    request: ValueStockAnalysisRequest,
    *,
    performance_provider: EastmoneyPerformanceProvider | None = None,
    limit: int = MAX_ANALYSIS_CANDIDATES,
    trade_date: str | None = None,
    finance_report_date: str | None = None,
    dividend_cutoff: str | None = None,
) -> ValueStockCandidateSet:
    rows = await fetch_valuation_snapshot(
        request.max_pe,
        request.max_pb,
        trade_date=trade_date,
    )
    filtered = filter_value_snapshot(rows, request)
    if not filtered:
        raise MainForceEmptyError("当前条件下没有可分析的候选标的")

    codes = [row["symbol"] for row in filtered]
    prices = {row["symbol"]: row["price"] for row in filtered}
    debt_ratios = await fetch_debt_ratios(codes, report_date=finance_report_date)
    dividend_yields = await fetch_dividend_yields(
        codes,
        prices,
        cutoff=dividend_cutoff,
    )

    qualified: list[dict] = []
    for row in filtered:
        debt_ratio = debt_ratios.get(row["symbol"])
        dividend_yield = dividend_yields.get(row["symbol"], 0.0)
        if debt_ratio is None or debt_ratio > request.max_debt_ratio:
            continue
        if dividend_yield < request.min_dividend_yield:
            continue
        row["debt_ratio"] = debt_ratio
        row["dividend_yield"] = dividend_yield
        qualified.append(row)

    if not qualified:
        raise MainForceEmptyError("当前条件下没有可分析的候选标的")
    qualified.sort(key=lambda item: item["float_market_cap"] or 0)
    selected = qualified[:limit]

    symbols = []
    for row in selected:
        try:
            symbols.append(parse_symbol(row["symbol"]))
        except InvalidSymbolError:
            continue
    quotes = await fetch_quotes(symbols)

    provider = performance_provider or EastmoneyPerformanceProvider()
    try:
        performance = await provider.fetch_latest_by_codes(
            [row["symbol"] for row in selected]
        )
    except Exception as exc:  # noqa: BLE001 - 行业/业绩缺失时仍可分析
        logger.warning("低估值补充业绩数据失败: %s", exc)
        performance = {}

    items: list[ValueStockItem] = []
    for row in selected:
        quote = quotes.get(row["symbol"])
        perf = performance.get(row["symbol"])
        price = quote.price if quote and quote.price else row["price"]
        items.append(
            ValueStockItem(
                symbol=row["symbol"],
                name=row["name"],
                industry=(perf.industry if perf else "") or row["industry"],
                price=price,
                change_pct=quote.change_pct if quote else row["change_pct"],
                amount=quote.amount if quote else None,
                pe=row["pe"],
                pb=row["pb"],
                dividend_yield=row["dividend_yield"],
                debt_ratio=row["debt_ratio"],
                float_market_cap=row["float_market_cap"],
                total_market_cap=row["total_market_cap"],
                profit_growth=perf.profit_growth if perf else None,
                revenue_growth=perf.revenue_growth if perf else None,
                report_date=perf.report_date if perf else "",
            )
        )

    report_date = next(
        (item.report_date for item in items if item.report_date),
        "",
    )
    return ValueStockCandidateSet(
        items=items,
        quotes=quotes,
        performance=performance,
        report_date=report_date,
        scanned_count=len(rows),
        candidate_count=len(qualified),
    )


def _yi(value: float | None) -> float | None:
    return round(value / 1e8, 2) if value is not None else None


def _num(value: float | None, digits: int) -> str:
    return f"{value:.{digits}f}" if value is not None else "-"


def build_value_rows(items: list[ValueStockItem]) -> list[dict]:
    return [
        {
            "symbol": item.symbol,
            "name": item.name,
            "industry": item.industry,
            "price": item.price,
            "change_pct": item.change_pct,
            "amount_yi": _yi(item.amount),
            "pe": item.pe,
            "pb": item.pb,
            "dividend_yield": item.dividend_yield,
            "debt_ratio": item.debt_ratio,
            "float_market_cap_yi": _yi(item.float_market_cap),
            "total_market_cap_yi": _yi(item.total_market_cap),
            "revenue_growth": item.revenue_growth,
            "profit_growth": item.profit_growth,
        }
        for item in items
    ]


def build_value_summary(rows: list[dict]) -> str:
    total = len(rows)
    avg_pe = sum(row["pe"] or 0 for row in rows) / total if total else 0
    avg_pb = sum(row["pb"] or 0 for row in rows) / total if total else 0
    avg_dividend = sum(row["dividend_yield"] or 0 for row in rows) / total if total else 0
    avg_debt = sum(row["debt_ratio"] or 0 for row in rows) / total if total else 0
    avg_cap = sum(row["float_market_cap_yi"] or 0 for row in rows) / total if total else 0
    lines = [
        f"候选股票总数: {total}只",
        f"平均 PE: {avg_pe:.1f}",
        f"平均 PB: {avg_pb:.2f}",
        f"平均股息率: {avg_dividend:.2f}%",
        f"平均资产负债率: {avg_debt:.1f}%",
        f"平均流通市值: {avg_cap:.1f}亿",
    ]
    industries = Counter(row["industry"] for row in rows if row.get("industry"))
    if industries:
        lines.append(
            "主要行业分布: "
            + "、".join(f"{name} {count}只" for name, count in industries.most_common(8))
        )
    return "\n".join(lines)


def build_value_table(rows: list[dict]) -> str:
    header = (
        "代码 名称 行业 价格 涨幅% 成交额(亿) PE PB 股息率% 资产负债率% "
        "流通市值(亿) 总市值(亿) 营收同比% 净利同比%"
    )
    lines = [header]
    for row in rows:
        lines.append(
            " ".join(
                [
                    row["symbol"],
                    row["name"],
                    row.get("industry") or "-",
                    _num(row.get("price"), 2),
                    _num(row.get("change_pct"), 2),
                    _num(row.get("amount_yi"), 2),
                    _num(row.get("pe"), 1),
                    _num(row.get("pb"), 2),
                    _num(row.get("dividend_yield"), 2),
                    _num(row.get("debt_ratio"), 1),
                    _num(row.get("float_market_cap_yi"), 1),
                    _num(row.get("total_market_cap_yi"), 1),
                    _num(row.get("revenue_growth"), 1),
                    _num(row.get("profit_growth"), 1),
                ]
            )
        )
    return "\n".join(lines)


async def analyze_value_stock(
    redis: Redis,
    user_id: object,
    daily_quota: int,
    request: ValueStockAnalysisRequest,
    *,
    llm_client=None,
    performance_provider: EastmoneyPerformanceProvider | None = None,
    on_phase=None,
) -> MainForceAnalysisResponse:
    llm_client = _ensure_client(llm_client)
    quota_used = await _ensure_quota(redis, user_id, daily_quota)

    await _phase(on_phase, "读取估值、股息与负债数据")
    candidates = await collect_value_candidates(
        request,
        performance_provider=performance_provider,
    )
    rows = build_value_rows(candidates.items)
    return await _run_ai_selection(
        redis,
        user_id,
        daily_quota,
        quota_used,
        strategy="value_stock",
        rows=rows,
        summary=build_value_summary(rows),
        table=build_value_table(rows),
        final_n=request.final_n,
        llm_client=llm_client,
        on_phase=on_phase,
        source="eastmoney_valuation+dividend+tencent",
        disclaimer="AI 分析基于公开估值、分红、财务与行情数据，仅供研究参考，不构成投资建议。",
    )
