"""主力选股 AI 分析：三位分析师整体分析 + 资深研究员精选。

对齐参考项目 main_force_analysis.py：
资金流向 / 行业板块 / 财务基本面三位分析师先出整体报告，再由资深研究员精选 3-5 只。
"""

import asyncio
from collections import Counter
from collections.abc import Awaitable, Callable
from datetime import datetime
from zoneinfo import ZoneInfo

from redis.asyncio import Redis

from app.core.config import settings
from app.core.logging import get_logger
from app.llm.client import (
    LLMClient,
    LLMError,
    LLMNotConfiguredError,
    LLMRequestError,
    LLMResponseError,
    is_llm_configured,
)
from app.llm.main_force_prompts import (
    FINAL_SYSTEM_PROMPT,
    SYSTEM_PROMPTS,
    build_analyst_prompt,
    build_final_prompt,
)
from app.providers.fund_flow_rank import flow_window_label, flow_window_source
from app.providers.performance import EastmoneyPerformanceProvider
from app.providers.symbols import parse_symbol
from app.schemas.screener import (
    LowPriceBullAnalysisRequest,
    MainForceAnalysisRequest,
    MainForceAnalysisResponse,
    MainForceRecommendation,
    PerformanceRow,
    ProfitGrowthAnalysisRequest,
    SmallCapAnalysisRequest,
)
from app.services.ai_analysis_service import (
    QuotaExceededError,
    quota_key,
    read_quota_used,
    seconds_to_midnight,
)
from app.services.screener_service import (
    LowPriceCandidateSet,
    ProfitGrowthCandidateSet,
    SmallCapCandidateSet,
    collect_low_price_candidates,
    collect_profit_growth_candidates,
    collect_small_cap_candidates,
    fetch_quotes,
    filter_main_force,
    load_fund_flow_rank,
)

logger = get_logger(__name__)
TZ_SHANGHAI = ZoneInfo("Asia/Shanghai")

MAX_ANALYSIS_CANDIDATES = 40
# 主力追踪对齐参考项目：候选池取区间净流入前 100
MAIN_FORCE_CANDIDATES = 100
ANALYST_MAX_TOKENS = settings.llm_analyst_max_tokens
FINAL_MAX_TOKENS = settings.llm_final_max_tokens
ANALYST_CALL_TIMEOUT = float(settings.llm_analyst_timeout_seconds)
FINAL_CALL_TIMEOUT = float(settings.llm_timeout_seconds)

PhaseCallback = Callable[[str], Awaitable[None]]

ANALYST_LABELS = {
    "fund_flow": "资金流向",
    "industry": "行业板块",
    "fundamental": "财务基本面",
}


class MainForceEmptyError(Exception):
    pass


def _yi(value: float | None) -> float | None:
    return round(value / 1e8, 2) if value is not None else None


def build_candidate_rows(
    items: list,
    quotes: dict,
    performance: dict[str, PerformanceRow],
) -> list[dict]:
    rows: list[dict] = []
    for item in items:
        quote = quotes.get(item.symbol)
        perf = performance.get(item.symbol)
        rows.append(
            {
                "symbol": item.symbol,
                "name": item.name,
                "price": item.price,
                "change_pct": item.change_pct,
                "main_net_yi": _yi(item.main_net),
                "main_net_pct": item.main_net_pct,
                "amount_yi": _yi(item.amount),
                "pe": quote.pe if quote else None,
                "pb": quote.pb if quote else None,
                "market_cap_yi": _yi(
                    quote.total_market_cap if quote else item.market_cap
                ),
                "industry": perf.industry if perf else "",
                "revenue_growth": perf.revenue_growth if perf else None,
                "profit_growth": perf.profit_growth if perf else None,
                "report_date": perf.report_date if perf else "",
            }
        )
    return rows


def build_summary(rows: list[dict], window_label: str = "") -> str:
    total = len(rows)
    total_net = sum(row["main_net_yi"] or 0 for row in rows)
    avg_change = sum(row["change_pct"] or 0 for row in rows) / total if total else 0
    lines = []
    if window_label:
        lines.append(f"统计区间: {window_label}")
    lines += [
        f"候选股票总数: {total}只",
        f"主力资金合计净流入: {total_net:.2f}亿",
        f"平均区间涨跌幅: {avg_change:.2f}%",
    ]
    industries = Counter(
        row["industry"] for row in rows if row.get("industry")
    )
    if industries:
        lines.append(
            "主要行业分布: "
            + "、".join(f"{name} {count}只" for name, count in industries.most_common(8))
        )
    return "\n".join(lines)


def _num(value: float | None, digits: int) -> str:
    return f"{value:.{digits}f}" if value is not None else "-"


def build_candidate_table(rows: list[dict], window_label: str = "") -> str:
    """紧凑表格，避免长 JSON 把提示词撑到上万 token。"""
    change_header = f"{window_label}涨幅% " if window_label else "区间涨幅% "
    header = (
        "代码 名称 行业 价格 "
        + change_header
        + f"{window_label or '区间'}主力净额(亿) 净占比% 成交额(亿) "
        "PE PB 总市值(亿) 营收同比% 净利同比% 报告期"
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
                    _num(row.get("main_net_yi"), 2),
                    _num(row.get("main_net_pct"), 2),
                    _num(row.get("amount_yi"), 1),
                    _num(row.get("pe"), 1),
                    _num(row.get("pb"), 2),
                    _num(row.get("market_cap_yi"), 1),
                    _num(row.get("revenue_growth"), 1),
                    _num(row.get("profit_growth"), 1),
                    row.get("report_date") or "-",
                ]
            )
        )
    return "\n".join(lines)


def normalize_recommendations(
    data: dict,
    rows: list[dict],
    final_n: int,
) -> list[MainForceRecommendation]:
    by_symbol = {row["symbol"]: row for row in rows}
    seen: set[str] = set()
    recommendations: list[MainForceRecommendation] = []
    for raw in data.get("recommendations") or []:
        if not isinstance(raw, dict):
            continue
        symbol = str(raw.get("symbol") or "").strip()
        row = by_symbol.get(symbol)
        if row is None or symbol in seen:
            continue
        seen.add(symbol)
        recommendations.append(
            MainForceRecommendation.model_validate(
                {**raw, "symbol": symbol, "name": row["name"]}
            )
        )

    recommendations.sort(key=lambda item: item.rank)
    recommendations = recommendations[:final_n]
    for index, item in enumerate(recommendations, 1):
        item.rank = index
    return recommendations


async def _phase(callback: PhaseCallback | None, text: str) -> None:
    if callback is None:
        return
    try:
        await callback(text)
    except Exception as exc:  # noqa: BLE001 - 阶段更新失败不影响分析
        logger.warning("更新选股任务阶段失败: %s", exc)


async def _run_analyst(
    llm_client: LLMClient,
    kind: str,
    summary: str,
    table: str,
    strategy: str = "main_force",
) -> str:
    try:
        return await llm_client.generate_text(
            SYSTEM_PROMPTS[kind],
            build_analyst_prompt(kind, summary, table, strategy),
            max_tokens=ANALYST_MAX_TOKENS,
            timeout=ANALYST_CALL_TIMEOUT,
        )
    except Exception as exc:  # noqa: BLE001 - 单维度失败不拖垮整份分析
        logger.warning("%s %s 分析失败: %s", strategy, kind, exc)
        return f"（{ANALYST_LABELS[kind]}分析暂不可用，请稍后重试）"


async def _generate_final(
    llm_client: LLMClient,
    prompt: str,
) -> dict:
    for attempt in (1, 2):
        try:
            return await llm_client.generate_json(
                FINAL_SYSTEM_PROMPT,
                prompt,
                max_tokens=FINAL_MAX_TOKENS,
                timeout=FINAL_CALL_TIMEOUT,
                # 结构化 JSON 默认关闭/压低思考，避免 reasoning 吃光正文额度
                reasoning_effort=settings.llm_final_reasoning_effort,
            )
        except (LLMRequestError, LLMResponseError) as exc:
            if attempt == 2:
                raise
            logger.warning("资深研究员精选请求失败，重试一次: %s", exc)
            await asyncio.sleep(2)
    raise AssertionError("unreachable")


def _ensure_client(llm_client: LLMClient | None) -> LLMClient:
    if llm_client is not None:
        return llm_client
    if not is_llm_configured():
        raise LLMNotConfiguredError("尚未配置 LLM")
    return LLMClient()


async def _ensure_quota(redis: Redis, user_id: object, daily_quota: int) -> int:
    quota_used = await read_quota_used(redis, user_id, strict=True)
    if quota_used >= daily_quota:
        raise QuotaExceededError(daily_quota, seconds_to_midnight())
    return quota_used


async def _increment_quota(redis: Redis, user_id: object, quota_used: int) -> int:
    new_used = quota_used + 1
    try:
        new_used = await redis.incr(quota_key(user_id))
        if new_used == 1:
            await redis.expire(quota_key(user_id), seconds_to_midnight())
    except Exception as exc:  # noqa: BLE001
        logger.warning("写入选股额度失败: %s", exc)
    return new_used


async def _run_ai_selection(
    redis: Redis,
    user_id: object,
    daily_quota: int,
    quota_used: int,
    *,
    strategy: str,
    rows: list[dict],
    summary: str,
    table: str,
    final_n: int,
    llm_client: LLMClient,
    on_phase: PhaseCallback | None,
    source: str,
    disclaimer: str,
) -> MainForceAnalysisResponse:
    await _phase(on_phase, "三位分析师整体分析中")
    fund_flow, industry, fundamental = await asyncio.gather(
        _run_analyst(llm_client, "fund_flow", summary, table, strategy),
        _run_analyst(llm_client, "industry", summary, table, strategy),
        _run_analyst(llm_client, "fundamental", summary, table, strategy),
    )

    await _phase(on_phase, "资深研究员精选中")
    try:
        data = await _generate_final(
            llm_client,
            build_final_prompt(
                table,
                fund_flow,
                industry,
                fundamental,
                final_n,
                strategy,
            ),
        )
        recommendations = normalize_recommendations(data, rows, final_n)
    except LLMError:
        raise
    except Exception as exc:  # noqa: BLE001 - 结构化结果异常不应变成 500
        logger.warning("%s 最终精选结果解析失败: %s", strategy, exc)
        raise LLMResponseError("AI 精选结果解析失败") from exc

    new_used = await _increment_quota(redis, user_id, quota_used)
    return MainForceAnalysisResponse(
        strategy=strategy,
        fund_flow=fund_flow,
        industry=industry,
        fundamental=fundamental,
        recommendations=recommendations,
        generated_at=datetime.now(TZ_SHANGHAI),
        model=settings.llm_model,
        quota_used=new_used,
        quota_limit=daily_quota,
        analyzed_count=len(rows),
        source=source,
        disclaimer=disclaimer,
    )


def build_low_price_rows(candidates: LowPriceCandidateSet) -> list[dict]:
    rows: list[dict] = []
    for item in candidates.items:
        quote = candidates.quotes.get(item.symbol)
        perf = candidates.performance.get(item.symbol)
        rows.append(
            {
                "symbol": item.symbol,
                "name": item.name,
                "industry": perf.industry if perf else "",
                "price": item.price,
                "change_pct": item.change_pct,
                "amount_yi": _yi(item.amount),
                "market_cap_yi": _yi(quote.total_market_cap) if quote else None,
                "pe": quote.pe if quote else None,
                "pb": quote.pb if quote else None,
                "revenue_growth": item.revenue_growth,
                "profit_growth": item.profit_growth,
                "report_date": item.report_date,
            }
        )
    return rows


def build_small_cap_rows(candidates: SmallCapCandidateSet) -> list[dict]:
    rows: list[dict] = []
    for item in candidates.items:
        quote = candidates.quotes.get(item.symbol)
        perf = candidates.performance.get(item.symbol)
        rows.append(
            {
                "symbol": item.symbol,
                "name": item.name,
                "industry": perf.industry if perf else "",
                "price": item.price,
                "change_pct": item.change_pct,
                "amount_yi": _yi(quote.amount) if quote else None,
                "market_cap_yi": _yi(item.total_market_cap),
                "pe": quote.pe if quote else None,
                "pb": quote.pb if quote else None,
                "revenue_growth": item.revenue_growth,
                "profit_growth": item.profit_growth,
                "report_date": item.report_date,
            }
        )
    return rows


def build_profit_growth_rows(candidates: ProfitGrowthCandidateSet) -> list[dict]:
    rows: list[dict] = []
    for item in candidates.items:
        quote = candidates.quotes.get(item.symbol)
        perf = candidates.performance.get(item.symbol)
        rows.append(
            {
                "symbol": item.symbol,
                "name": item.name,
                "industry": perf.industry if perf else "",
                "price": item.price,
                "change_pct": item.change_pct,
                "amount_yi": _yi(item.amount),
                "market_cap_yi": _yi(quote.total_market_cap) if quote else None,
                "pe": quote.pe if quote else None,
                "pb": quote.pb if quote else None,
                "revenue_growth": item.revenue_growth,
                "profit_growth": item.profit_growth,
                "report_date": item.report_date,
            }
        )
    return rows


def build_growth_summary(rows: list[dict]) -> str:
    total = len(rows)
    avg_profit = sum(row["profit_growth"] or 0 for row in rows) / total if total else 0
    avg_revenue = sum(row["revenue_growth"] or 0 for row in rows) / total if total else 0
    avg_amount = sum(row["amount_yi"] or 0 for row in rows) / total if total else 0
    avg_cap = sum(row["market_cap_yi"] or 0 for row in rows) / total if total else 0
    lines = [
        f"候选股票总数: {total}只",
        f"平均营收同比: {avg_revenue:.1f}%",
        f"平均净利同比: {avg_profit:.1f}%",
        f"平均成交额: {avg_amount:.2f}亿",
        f"平均总市值: {avg_cap:.1f}亿",
    ]
    industries = Counter(row["industry"] for row in rows if row.get("industry"))
    if industries:
        lines.append(
            "主要行业分布: "
            + "、".join(f"{name} {count}只" for name, count in industries.most_common(8))
        )
    return "\n".join(lines)


def build_growth_table(rows: list[dict]) -> str:
    header = (
        "代码 名称 行业 价格 涨幅% 成交额(亿) 总市值(亿) PE PB "
        "营收同比% 净利同比% 报告期"
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
                    _num(row.get("market_cap_yi"), 1),
                    _num(row.get("pe"), 1),
                    _num(row.get("pb"), 2),
                    _num(row.get("revenue_growth"), 1),
                    _num(row.get("profit_growth"), 1),
                    row.get("report_date") or "-",
                ]
            )
        )
    return "\n".join(lines)


async def analyze_main_force(
    redis: Redis,
    user_id: object,
    daily_quota: int,
    request: MainForceAnalysisRequest,
    *,
    llm_client: LLMClient | None = None,
    performance_provider: EastmoneyPerformanceProvider | None = None,
    on_phase: PhaseCallback | None = None,
) -> MainForceAnalysisResponse:
    llm_client = _ensure_client(llm_client)
    quota_used = await _ensure_quota(redis, user_id, daily_quota)

    window_label = flow_window_label(request.window)
    await _phase(on_phase, f"获取{window_label}主力资金排行")
    items = await load_fund_flow_rank(redis, request.window)
    filtered = filter_main_force(items, request)
    if not filtered:
        raise MainForceEmptyError("当前条件下没有可分析的候选标的")
    candidates = filtered[:MAIN_FORCE_CANDIDATES]

    await _phase(on_phase, "补充行情与业绩数据")
    quotes = await fetch_quotes([parse_symbol(item.symbol) for item in candidates])
    provider = performance_provider or EastmoneyPerformanceProvider()
    try:
        performance = await provider.fetch_latest_by_codes(
            [item.symbol for item in candidates]
        )
    except Exception as exc:  # noqa: BLE001 - 行业/财务缺失时仍可分析
        logger.warning("主力选股补充业绩数据失败: %s", exc)
        performance = {}

    rows = build_candidate_rows(candidates, quotes, performance)
    summary = build_summary(rows, window_label)
    table = build_candidate_table(rows, window_label)

    return await _run_ai_selection(
        redis,
        user_id,
        daily_quota,
        quota_used,
        strategy="main_force",
        rows=rows,
        summary=summary,
        table=table,
        final_n=request.final_n,
        llm_client=llm_client,
        on_phase=on_phase,
        source=f"{flow_window_source(request.window)}+eastmoney_performance+tencent",
        disclaimer="AI 分析基于公开资金流、行业与财务数据，仅供研究参考，不构成投资建议。",
    )


async def analyze_low_price_bull(
    redis: Redis,
    user_id: object,
    daily_quota: int,
    request: LowPriceBullAnalysisRequest,
    *,
    llm_client: LLMClient | None = None,
    performance_provider: EastmoneyPerformanceProvider | None = None,
    on_phase: PhaseCallback | None = None,
) -> MainForceAnalysisResponse:
    llm_client = _ensure_client(llm_client)
    quota_used = await _ensure_quota(redis, user_id, daily_quota)

    await _phase(on_phase, "读取最新业绩报表与行情")
    candidates = await collect_low_price_candidates(
        request,
        provider=performance_provider,
        limit=MAX_ANALYSIS_CANDIDATES,
    )
    if not candidates.items:
        raise MainForceEmptyError("当前条件下没有可分析的候选标的")

    rows = build_low_price_rows(candidates)
    return await _run_ai_selection(
        redis,
        user_id,
        daily_quota,
        quota_used,
        strategy="low_price_bull",
        rows=rows,
        summary=build_growth_summary(rows),
        table=build_growth_table(rows),
        final_n=request.final_n,
        llm_client=llm_client,
        on_phase=on_phase,
        source="eastmoney_performance+tencent",
        disclaimer="AI 分析基于公开业绩、行情与财务数据，仅供研究参考，不构成投资建议。",
    )


async def analyze_small_cap(
    redis: Redis,
    user_id: object,
    daily_quota: int,
    request: SmallCapAnalysisRequest,
    *,
    llm_client: LLMClient | None = None,
    performance_provider: EastmoneyPerformanceProvider | None = None,
    on_phase: PhaseCallback | None = None,
) -> MainForceAnalysisResponse:
    llm_client = _ensure_client(llm_client)
    quota_used = await _ensure_quota(redis, user_id, daily_quota)

    await _phase(on_phase, "读取最新业绩报表与行情")
    candidates = await collect_small_cap_candidates(
        request,
        provider=performance_provider,
        limit=MAX_ANALYSIS_CANDIDATES,
    )
    if not candidates.items:
        raise MainForceEmptyError("当前条件下没有可分析的候选标的")

    rows = build_small_cap_rows(candidates)
    return await _run_ai_selection(
        redis,
        user_id,
        daily_quota,
        quota_used,
        strategy="small_cap",
        rows=rows,
        summary=build_growth_summary(rows),
        table=build_growth_table(rows),
        final_n=request.final_n,
        llm_client=llm_client,
        on_phase=on_phase,
        source="eastmoney_performance+tencent",
        disclaimer="AI 分析基于公开业绩、行情与财务数据，仅供研究参考，不构成投资建议。",
    )


async def analyze_profit_growth(
    redis: Redis,
    user_id: object,
    daily_quota: int,
    request: ProfitGrowthAnalysisRequest,
    *,
    llm_client: LLMClient | None = None,
    performance_provider: EastmoneyPerformanceProvider | None = None,
    on_phase: PhaseCallback | None = None,
) -> MainForceAnalysisResponse:
    llm_client = _ensure_client(llm_client)
    quota_used = await _ensure_quota(redis, user_id, daily_quota)

    await _phase(on_phase, "读取最新业绩报表与行情")
    candidates = await collect_profit_growth_candidates(
        request,
        provider=performance_provider,
        limit=MAX_ANALYSIS_CANDIDATES,
    )
    if not candidates.items:
        raise MainForceEmptyError("当前条件下没有可分析的候选标的")

    rows = build_profit_growth_rows(candidates)
    return await _run_ai_selection(
        redis,
        user_id,
        daily_quota,
        quota_used,
        strategy="profit_growth",
        rows=rows,
        summary=build_growth_summary(rows),
        table=build_growth_table(rows),
        final_n=request.final_n,
        llm_client=llm_client,
        on_phase=on_phase,
        source="eastmoney_performance+tencent",
        disclaimer="AI 分析基于公开业绩、行情与财务数据，仅供研究参考，不构成投资建议。",
    )
