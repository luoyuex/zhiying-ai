"""六位分析师的 LLM 提示词与上下文裁剪。

每位分析师只拿到自己维度的原始数据 + 代码初稿，避免把整份报告塞进 prompt。
提示词变更会改变 digest，使报告缓存自动失效。
"""

import hashlib
import json
from typing import Any

from app.providers.models import KlineBar, Quote
from app.schemas.analysis import TechnicalAnalysis
from app.schemas.analyst import AnalystReport
from app.schemas.company import FinancialData, FundFlowData, SentimentData
from app.schemas.search import WebSearchResult

# key → (角色, 职责, 评级取值)
ANALYST_SPECS: dict[str, tuple[str, str, str]] = {
    "technical": (
        "技术面分析师",
        "根据均线、MACD、RSI、BOLL、ATR、量比与近期 K 线判断趋势强弱、关键支撑压力，"
        "并指出信号之间的矛盾。价位已由代码计算，只能引用，不得修改。",
        "乐观 | 中性 | 谨慎",
    ),
    "fundamental": (
        "基本面分析师",
        "根据最新财报的营收/净利增速、ROE、毛利率、净利率、负债率、流动比率与当前估值，"
        "判断盈利质量与估值匹配度。",
        "乐观 | 中性 | 谨慎",
    ),
    "fund_flow": (
        "资金面分析师",
        "根据近 10 日主力、超大单、大单、中单、小单净流入与占比，判断主力行为、"
        "资金持续性以及价格与资金是否背离。",
        "乐观 | 中性 | 谨慎",
    ),
    "risk": (
        "风险管理分析师",
        "从波动率、回撤、超买超卖、交易拥挤度与公开信息中的事件线索评估风险，"
        "并明确指出哪些风险缺少结构化数据。",
        "低风险 | 中等风险 | 高风险",
    ),
    "sentiment": (
        "市场情绪分析师",
        "根据 AR/BR、换手率、RSI、量比、主要指数表现与公开信息的情绪关键词，"
        "判断短线情绪温度与拥挤度。",
        "乐观 | 中性 | 谨慎",
    ),
    "news": (
        "新闻舆情分析师",
        "只基于检索到的公开网页，提炼与该公司相关的事件、公告与报道倾向，"
        "必须标注日期与站点，不能把网页内容当作已核实事实。",
        "乐观 | 中性 | 谨慎",
    ),
}

SYSTEM_TEMPLATE = """你是智盈 AI 的{role}。
职责：{duty}

规则：
1. 只使用输入 JSON 中的数据，不得编造财务、资金、新闻或价位；数据缺失时在 risks 中注明。
2. 结论要具体到数字或条件，避免「可能」「或许」这类空转表述。
3. 公开网页信息只作事件背景，必须核对发布日期，不能当作确定事实。
4. 不承诺收益，不写交易指令。
5. 输入中的 rule_draft 是代码基于同一批数据生成的初稿，可参考、可修正，但不得无视数据。
6. 所有文字使用简体中文，只输出一个 JSON 对象，不要 Markdown 或解释文字。字段：
{{
  "score": 0 到 100 的整数（越高越积极）,
  "rating": "{ratings}",
  "summary": "不超过 120 字的本维度结论",
  "points": ["2-4 条依据，尽量带数字"],
  "risks": ["1-4 条风险或数据缺口"]
}}"""

USER_TEMPLATE = """请分析以下数据并按要求输出 JSON。输入：
{context}"""


def system_prompt_for(key: str) -> str:
    role, duty, ratings = ANALYST_SPECS[key]
    return SYSTEM_TEMPLATE.format(role=role, duty=duty, ratings=ratings)


def _rule_draft(rule: AnalystReport) -> dict[str, Any]:
    return {
        "score": rule.score,
        "rating": rule.rating,
        "summary": rule.summary,
        "points": rule.points,
        "risks": rule.risks,
    }


def _stock_snapshot(quote: Quote) -> dict[str, Any]:
    return {
        "symbol": quote.symbol,
        "name": quote.name,
        "price": quote.price,
        "change_pct": quote.change_pct,
        "turnover_pct": quote.turnover_pct,
        "pe": quote.pe,
        "pb": quote.pb,
        "as_of": quote.fetched_at.isoformat(),
    }


def _web_pages(web: WebSearchResult | None) -> list[dict[str, Any]]:
    if web is None or not web.success:
        return []
    return [
        {
            "title": page.title,
            "site": page.site,
            "date": page.date,
            "summary": page.summary[:200],
        }
        for page in web.pages[:6]
    ]


def _drawdown_pct(quote: Quote, bars: list[KlineBar]) -> float | None:
    if len(bars) < 20 or not quote.price:
        return None
    recent_high = max(bar.high for bar in bars[-60:])
    if not recent_high:
        return None
    return round((recent_high - quote.price) / recent_high * 100, 2)


def build_analyst_context(
    key: str,
    rule: AnalystReport,
    quote: Quote,
    technical: TechnicalAnalysis,
    bars: list[KlineBar],
    financial: FinancialData | None,
    fund_flow: FundFlowData | None,
    sentiment: SentimentData | None,
    web: WebSearchResult | None,
) -> dict[str, Any]:
    context: dict[str, Any] = {
        "stock": _stock_snapshot(quote),
        "rule_draft": _rule_draft(rule),
        "data_gaps": rule.missing,
    }

    if key == "technical":
        context["technical"] = {
            "score": technical.score,
            "rating": technical.rating,
            "trend": technical.trend,
            "signals": [signal.model_dump() for signal in technical.signals],
            "indicators": technical.indicators.model_dump(),
            "levels": technical.levels.model_dump(),
            "recent_bars": [
                {
                    "date": bar.time.date().isoformat(),
                    "close": bar.close,
                    "volume": bar.volume,
                }
                for bar in bars[-10:]
            ],
        }
    elif key == "fundamental":
        context["financial_periods"] = (
            [period.model_dump() for period in financial.periods[:3]] if financial else []
        )
        context["valuation"] = {
            "pe": quote.pe,
            "pb": quote.pb,
            "total_market_cap": quote.total_market_cap,
            "float_market_cap": quote.float_market_cap,
        }
    elif key == "fund_flow":
        context["fund_flow_days"] = (
            [day.model_dump() for day in fund_flow.days[-10:]] if fund_flow else []
        )
    elif key == "sentiment":
        context["sentiment"] = sentiment.model_dump() if sentiment else None
    elif key == "risk":
        context["risk_inputs"] = {
            "atr14": technical.indicators.atr14,
            "rsi14": technical.indicators.rsi14,
            "ma20": technical.indicators.ma20,
            "price": quote.price,
            "drawdown_60d_pct": _drawdown_pct(quote, bars),
            "turnover_pct": quote.turnover_pct,
        }
        context["public_web_info"] = _web_pages(web)
    elif key == "news":
        context["public_web_info"] = _web_pages(web)

    return context


def build_user_prompt(context: dict[str, Any]) -> str:
    # 财报日期、情绪抓取时间等可能是 date/datetime，统一转字符串
    return USER_TEMPLATE.format(
        context=json.dumps(context, ensure_ascii=False, separators=(",", ":"), default=str)
    )


_DIGEST_SOURCE = "".join(
    [
        SYSTEM_TEMPLATE,
        USER_TEMPLATE,
        *[f"{key}:{role}:{duty}:{ratings}" for key, (role, duty, ratings) in ANALYST_SPECS.items()],
    ]
)
ANALYST_PROMPT_DIGEST = hashlib.sha256(_DIGEST_SOURCE.encode("utf-8")).hexdigest()[:12]
ANALYST_PROMPT_VERSION = f"analyst.v1:{ANALYST_PROMPT_DIGEST}"
