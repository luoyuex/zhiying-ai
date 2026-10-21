"""团队讨论提示词：把六份报告的差异整理成可读的时间线。

不重新分析，只做交叉回应；讨论结果会进入首席决策的输入。
"""

import hashlib
import json
from typing import Any

from app.providers.models import Quote
from app.schemas.analysis import TechnicalAnalysis
from app.schemas.analyst import AnalystReport

SYSTEM_PROMPT = """你是智赢 AI 投资圆桌的主持人。
你会收到六位分析师的结构化报告、当前行情与代码计算的关键价位。
你的任务是把他们的分歧整理成一段讨论纪要，而不是重新分析或编造新数据。

规则：
1. 只能引用输入中的结论、数字与数据缺口；不得新增财务、资金、新闻或价位。
2. 输出 4-6 轮发言，必须覆盖至少 3 位不同分析师；优先讨论评分差异最大的两位。
3. 每轮 40-100 字，必须点名回应另一位分析师（target 填对方名字）。
4. stance 只能是：同意 / 补充 / 质疑。
5. 发言顺序按逻辑推进：先指出分歧，再补充证据，最后收敛；不承诺收益，不写交易指令。
6. 所有文字使用简体中文，只输出一个 JSON 对象，不要 Markdown 或解释文字。字段：
{
  "turns": [
    {"speaker": "技术面", "target": "资金面", "stance": "质疑", "content": "..."}
  ],
  "summary": "不超过 80 字的讨论结论"
}"""

USER_TEMPLATE = """请整理以下分析师团队的讨论。输入：
{context}"""


def _analyst_brief(analyst: AnalystReport) -> dict[str, Any]:
    return {
        "name": analyst.name,
        "score": analyst.score,
        "rating": analyst.rating,
        "summary": analyst.summary,
        "points": analyst.points[:2],
        "risks": analyst.risks[:1],
        "engine": analyst.engine,
        "missing": analyst.missing,
    }


def build_discussion_context(
    quote: Quote,
    technical: TechnicalAnalysis,
    analysts: list[AnalystReport],
) -> dict[str, Any]:
    return {
        "stock": {
            "symbol": quote.symbol,
            "name": quote.name,
            "price": quote.price,
            "change_pct": quote.change_pct,
        },
        "levels": technical.levels.model_dump(),
        "analysts": [_analyst_brief(analyst) for analyst in analysts],
        "data_gaps": sorted({gap for analyst in analysts for gap in analyst.missing}),
    }


def build_discussion_user_prompt(context: dict[str, Any]) -> str:
    return USER_TEMPLATE.format(
        context=json.dumps(context, ensure_ascii=False, separators=(",", ":"), default=str)
    )


_DIGEST_SOURCE = SYSTEM_PROMPT + USER_TEMPLATE
DISCUSSION_PROMPT_DIGEST = hashlib.sha256(_DIGEST_SOURCE.encode("utf-8")).hexdigest()[:12]
DISCUSSION_PROMPT_VERSION = f"discussion.v1:{DISCUSSION_PROMPT_DIGEST}"
