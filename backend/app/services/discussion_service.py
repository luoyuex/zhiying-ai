"""团队讨论：一次 LLM 整理分歧，失败时按评分生成规则版时间线。"""

import asyncio

from app.core.config import settings
from app.core.logging import get_logger
from app.llm.client import LLMClient
from app.llm.discussion_prompts import (
    SYSTEM_PROMPT,
    build_discussion_context,
    build_discussion_user_prompt,
)
from app.providers.models import Quote
from app.schemas.analysis import TechnicalAnalysis
from app.schemas.analyst import AnalystReport, DiscussionTurn, TeamDiscussion

logger = get_logger(__name__)


def build_rule_discussion(analysts: list[AnalystReport]) -> TeamDiscussion:
    """没有 LLM 时也给出可读的分歧摘要，保证报告结构完整。"""
    if not analysts:
        return TeamDiscussion(turns=[], summary="暂无分析师报告，无法形成讨论。")

    ordered = sorted(analysts, key=lambda item: item.score, reverse=True)
    top, low = ordered[0], ordered[-1]
    top_point = top.points[0] if top.points else top.summary
    turns = [
        DiscussionTurn(
            speaker=low.name,
            target=top.name,
            stance="质疑",
            content=(
                f"我的评分是 {low.score}（{low.rating}）：{low.summary[:80]}。"
                f"这与{top.name} {top.score} 分的判断存在差异。"
            ),
        ),
        DiscussionTurn(
            speaker=top.name,
            target=low.name,
            stance="补充",
            content=f"我的评分是 {top.score}，主要依据：{top_point[:90]}；数据缺口仍需保留。",
        ),
    ]

    risk = next((item for item in analysts if item.key == "risk"), None)
    if risk is not None and risk.key not in {top.key, low.key}:
        risk_point = risk.risks[0] if risk.risks else risk.summary
        turns.append(
            DiscussionTurn(
                speaker=risk.name,
                stance="补充",
                content=f"从风险维度看：{risk_point[:90]}。",
            )
        )

    gaps = sorted({gap for item in analysts for gap in item.missing})
    summary = f"六维评分 {low.score}–{top.score}，分歧集中在{low.name}与{top.name}"
    summary += f"；缺口：{'、'.join(gaps)}。" if gaps else "；数据覆盖较完整。"
    return TeamDiscussion(turns=turns, summary=summary, source="rule")


async def build_discussion(
    llm_client: LLMClient,
    quote: Quote,
    technical: TechnicalAnalysis,
    analysts: list[AnalystReport],
) -> TeamDiscussion:
    valid_names = {analyst.name for analyst in analysts}
    context = build_discussion_context(quote, technical, analysts)

    try:
        async with asyncio.timeout(settings.llm_analyst_timeout_seconds):
            data = await llm_client.generate_json(
                SYSTEM_PROMPT,
                build_discussion_user_prompt(context),
            )
        draft = TeamDiscussion.model_validate({**data, "source": "llm"})
        turns = [
            turn.model_copy(update={"target": turn.target if turn.target in valid_names else ""})
            for turn in draft.turns
            if turn.speaker in valid_names and turn.content
        ]
        if not turns:
            raise ValueError("讨论发言为空或分析师名字无法匹配")
        return draft.model_copy(update={"turns": turns[:6], "source": "llm"})
    except Exception as exc:  # noqa: BLE001 - 讨论失败不能拖垮报告
        logger.exception("团队讨论 LLM 失败，使用规则版时间线: %s", exc)
        return build_rule_discussion(analysts)
