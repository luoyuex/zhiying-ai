"""AI 多分析师服务测试：缓存、额度、决策兜底与公开信息。"""

import uuid

import pytest

from app.db.models.user import User
from app.llm.client import LLMResponseError
from app.providers.base import now_shanghai
from app.schemas.analysis import TechnicalAnalysis
from app.schemas.position import UserPosition
from app.schemas.search import WebSearchResult, WebSource
from app.services.ai_analysis_service import (
    QuotaExceededError,
    generate_ai_analysis,
    quota_key,
)
from app.services.technical_analysis import analyze_technicals
from tests.test_technical_analysis import make_bars, make_quote


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str | int] = {}

    async def get(self, key: str):
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.store[key] = value

    async def incr(self, key: str) -> int:
        value = int(self.store.get(key, 0)) + 1
        self.store[key] = value
        return value

    async def expire(self, key: str, seconds: int) -> None:
        return None


_ANALYST_MARKERS = {
    "技术面分析师": "technical",
    "基本面分析师": "fundamental",
    "资金面分析师": "fund_flow",
    "风险管理分析师": "risk",
    "市场情绪分析师": "sentiment",
    "新闻舆情分析师": "news",
}


class FakeLLM:
    """首席决策与六位分析师共用：默认分析师调用失败以保留规则稿。"""

    def __init__(
        self,
        replies: list[dict | Exception],
        *,
        analyst_reply: dict | None = None,
        discussion_reply: dict | None = None,
        fail_keys: tuple[str, ...] = (),
    ) -> None:
        self.replies = replies
        self.analyst_reply = analyst_reply
        self.discussion_reply = discussion_reply
        self.fail_keys = set(fail_keys)
        self.calls = 0
        self.decision_calls = 0
        self.analyst_calls = 0
        self.discussion_calls = 0
        self.prompts: list[str] = []

    async def generate_json(self, system_prompt: str, user_prompt: str) -> dict:
        self.calls += 1
        self.prompts.append(user_prompt)

        if "首席策略官" in system_prompt:
            reply = self.replies[min(self.decision_calls, len(self.replies) - 1)]
            self.decision_calls += 1
            if isinstance(reply, Exception):
                raise reply
            return reply

        if "投资圆桌" in system_prompt:
            self.discussion_calls += 1
            if self.discussion_reply is None:
                raise LLMResponseError("mock discussion failure")
            return self.discussion_reply

        key = next(
            (value for marker, value in _ANALYST_MARKERS.items() if marker in system_prompt),
            None,
        )
        self.analyst_calls += 1
        if key is None or key in self.fail_keys or self.analyst_reply is None:
            raise LLMResponseError(f"mock analyst failure: {key}")
        return self.analyst_reply


def make_user(quota: int = 2) -> User:
    return User(
        id=uuid.uuid4(),
        email=f"ai-{uuid.uuid4().hex[:8]}@example.com",
        nickname="AI Test",
        daily_analysis_quota=quota,
    )


def make_analysis(symbol: str = "600000") -> tuple[User, object, TechnicalAnalysis, list]:
    bars = make_bars(up=True)
    quote = make_quote(bars)
    quote.symbol = symbol
    quote.name = "测试股份"
    technical = analyze_technicals(quote, bars, "fake-kline")
    return make_user(), quote, technical, bars


def decision_reply() -> dict:
    return {
        "rating": "买入",
        "confidence": 72,
        "summary": "技术面偏强，资金与情绪未出现明显背离，给出买入评级。",
        "operation_advice": "等待回踩 MA20 附近分批建仓，避免追高。",
        "holding_period": "10–20 个交易日",
        "position_size": "中等仓位（不超过 5 成）",
        "key_reasons": ["价格站上 MA20", "MACD 红柱延续", "量能平稳"],
        "risks": ["RSI 接近偏热区间", "财务与资金流数据缺失"],
        "risk_warning": "短线涨幅较大，注意回撤风险。",
        "consensus": ["技术面与情绪面偏多"],
        "dissent": ["基本面数据缺失"],
    }


async def test_generate_caches_six_analysts_and_counts_quota():
    redis = FakeRedis()
    user, quote, technical, bars = make_analysis("600010")
    llm = FakeLLM([decision_reply()])

    first = await generate_ai_analysis(
        redis, user.id, user.daily_analysis_quota, quote, technical, bars, llm_client=llm
    )
    second = await generate_ai_analysis(
        redis, user.id, user.daily_analysis_quota, quote, technical, bars, llm_client=llm
    )

    assert first.cached is False
    assert first.quota_used == 1
    assert len(first.analysts) == 6
    assert first.decision is not None
    assert first.decision.rating == "买入"
    assert first.analysis.rating == "看多"
    assert second.cached is True
    assert second.quota_used == 1
    # 六位分析师 + 一次团队讨论 + 一次首席决策；第二次命中缓存不再调用
    assert llm.calls == 8
    assert {item.engine for item in first.analysts} == {"rule"}


async def test_generate_injects_position_and_isolates_cache():
    redis = FakeRedis()
    user, quote, technical, bars = make_analysis("600012")
    position = UserPosition(cost_price=10.0, quantity=1000, note="核心持仓")
    reply = {
        **decision_reply(),
        "position_action": "加仓",
        "position_advice": "成本 10.00，现价高于成本，可分批加仓。",
    }
    llm = FakeLLM([reply])

    first = await generate_ai_analysis(
        redis,
        user.id,
        user.daily_analysis_quota,
        quote,
        technical,
        bars,
        llm_client=llm,
        position=position,
    )

    assert first.cached is False
    assert first.decision is not None
    assert first.decision.position_action == "加仓"
    assert first.decision.position_advice.startswith("成本 10.00")
    decision_prompt = next(prompt for prompt in llm.prompts if '"user_position"' in prompt)
    assert '"pnl_pct"' in decision_prompt

    # 持仓变化后缓存必须失效
    changed = await generate_ai_analysis(
        redis,
        user.id,
        user.daily_analysis_quota,
        quote,
        technical,
        bars,
        llm_client=FakeLLM([decision_reply()]),
        position=UserPosition(cost_price=12.0, quantity=1000),
    )
    assert changed.cached is False

    # 其他用户不能读到该用户的报告缓存
    other_user = make_user()
    other = await generate_ai_analysis(
        redis,
        other_user.id,
        other_user.daily_analysis_quota,
        quote,
        technical,
        bars,
        llm_client=FakeLLM([decision_reply()]),
        position=position,
    )
    assert other.cached is False


async def test_quota_exhausted_blocks_llm():
    redis = FakeRedis()
    user, quote, technical, bars = make_analysis("600011")
    user.daily_analysis_quota = 1
    redis.store[quota_key(user.id)] = 1
    llm = FakeLLM([decision_reply()])

    with pytest.raises(QuotaExceededError):
        await generate_ai_analysis(
            redis,
            user.id,
            user.daily_analysis_quota,
            quote,
            technical,
            bars,
            llm_client=llm,
        )

    assert llm.calls == 0


async def test_invalid_decision_falls_back_to_rule():
    redis = FakeRedis()
    user, quote, technical, bars = make_analysis("600012")
    invalid = {**decision_reply(), "rating": "强烈推荐"}
    llm = FakeLLM([invalid])

    report = await generate_ai_analysis(
        redis,
        user.id,
        user.daily_analysis_quota,
        quote,
        technical,
        bars,
        llm_client=llm,
    )

    assert llm.calls == 8
    assert report.decision is not None
    assert report.decision.decision_source == "rule_fallback"
    assert report.quota_used == 1


async def test_llm_error_falls_back_to_rule():
    redis = FakeRedis()
    user, quote, technical, bars = make_analysis("600013")
    llm = FakeLLM([LLMResponseError("mock llm error")])

    report = await generate_ai_analysis(
        redis,
        user.id,
        user.daily_analysis_quota,
        quote,
        technical,
        bars,
        llm_client=llm,
    )

    assert report.decision is not None
    assert report.decision.decision_source == "rule_fallback"
    assert report.quota_used == 1


async def test_web_info_goes_into_prompt_and_response():
    redis = FakeRedis()
    user, quote, technical, bars = make_analysis("600014")
    web = WebSearchResult(
        query="测试 600014 公告",
        success=True,
        pages=[
            WebSource(
                title="测试公告",
                url="https://example.com/notice",
                date="2026-10-21",
                site="测试站点",
                summary="公司发布公告。",
            )
        ],
        fetched_at=now_shanghai(),
    )
    llm = FakeLLM([decision_reply()])

    report = await generate_ai_analysis(
        redis,
        user.id,
        user.daily_analysis_quota,
        quote,
        technical,
        bars,
        web=web,
        llm_client=llm,
    )

    assert report.web_search_used is True
    assert report.web_sources[0].title == "测试公告"
    assert any("public_web_info" in prompt for prompt in llm.prompts)
    assert any("元宝搜索" in prompt for prompt in llm.prompts)
    news = next(item for item in report.analysts if item.key == "news")
    assert news.data_sources == ["元宝搜索"]


async def test_web_results_feed_multiple_analysts():
    redis = FakeRedis()
    user, quote, technical, bars = make_analysis("600015")
    web = WebSearchResult(
        query="测试 600015 公告",
        success=True,
        pages=[
            WebSource(
                title="公司披露回购股份进展公告",
                url="https://example.com/buyback",
                date="2026-10-20",
                site="上海证券交易所",
                summary="公司回购股份进展顺利。",
            ),
            WebSource(
                title="股东计划减持不超过 2% 股份",
                url="https://example.com/reduce",
                date="2026-10-21",
                site="证券时报",
                summary="股东披露减持计划。",
            ),
        ],
        fetched_at=now_shanghai(),
    )
    llm = FakeLLM([decision_reply()])

    report = await generate_ai_analysis(
        redis,
        user.id,
        user.daily_analysis_quota,
        quote,
        technical,
        bars,
        web=web,
        llm_client=llm,
    )

    by_key = {item.key: item for item in report.analysts}

    fundamental = by_key["fundamental"]
    assert "元宝搜索" in fundamental.data_sources
    assert any("回购" in point for point in fundamental.points)

    risk = by_key["risk"]
    assert "元宝搜索" in risk.data_sources
    assert any("减持" in point for point in risk.points)
    assert any("正式公告核实" in item for item in risk.risks)
    assert risk.missing == []

    sentiment = by_key["sentiment"]
    assert "元宝搜索" in sentiment.data_sources
    assert any("公开信息情绪" in point for point in sentiment.points)

    news = by_key["news"]
    assert news.data_sources == ["元宝搜索"]


def analyst_reply(score: int = 78) -> dict:
    return {
        "score": score,
        "rating": "乐观",
        "summary": "LLM 版维度结论。",
        "points": ["LLM 依据一", "LLM 依据二"],
        "risks": ["LLM 风险一"],
    }


async def test_llm_analysts_replace_rule_drafts():
    redis = FakeRedis()
    user, quote, technical, bars = make_analysis("600016")
    llm = FakeLLM([decision_reply()], analyst_reply=analyst_reply())

    report = await generate_ai_analysis(
        redis,
        user.id,
        user.daily_analysis_quota,
        quote,
        technical,
        bars,
        llm_client=llm,
    )

    assert llm.analyst_calls == 6
    assert llm.decision_calls == 1
    assert all(item.engine == "llm" for item in report.analysts)
    assert all(item.score == 78 for item in report.analysts)
    assert all(item.summary == "LLM 版维度结论。" for item in report.analysts)
    # 风险维度的「乐观」不适用，按分数推导为低风险
    risk = next(item for item in report.analysts if item.key == "risk")
    assert risk.rating == "低风险"
    # 决策 prompt 能看到每位分析师的 engine 标记
    assert any('"engine":"llm"' in prompt for prompt in llm.prompts)


async def test_single_analyst_failure_keeps_rule_draft():
    redis = FakeRedis()
    user, quote, technical, bars = make_analysis("600017")
    llm = FakeLLM(
        [decision_reply()],
        analyst_reply=analyst_reply(),
        fail_keys=("technical",),
    )

    report = await generate_ai_analysis(
        redis,
        user.id,
        user.daily_analysis_quota,
        quote,
        technical,
        bars,
        llm_client=llm,
    )

    by_key = {item.key: item for item in report.analysts}
    assert llm.analyst_calls == 6
    assert by_key["technical"].engine == "rule"
    assert all(item.engine == "llm" for key, item in by_key.items() if key != "technical")
    assert report.decision is not None


def test_missing_score_keeps_rule_score():
    from app.schemas.analyst import AnalystDraft, AnalystReport
    from app.services.llm_analyst_service import _merge_draft

    rule = AnalystReport(key="technical", name="技术面", score=72, rating="乐观", summary="规则稿")
    merged = _merge_draft(
        rule, AnalystDraft.model_validate({"rating": "中性", "summary": "LLM 稿"})
    )

    assert merged.score == 72
    assert merged.engine == "llm"
    assert merged.summary == "LLM 稿"


def test_analyst_prompt_serializes_dates():
    from datetime import date

    from app.llm.analyst_prompts import build_user_prompt

    prompt = build_user_prompt({"period": {"report_date": date(2026, 9, 30)}})
    assert "2026-09-30" in prompt


async def test_force_regenerates_ignoring_cache():
    redis = FakeRedis()
    user, quote, technical, bars = make_analysis("600021")
    llm = FakeLLM([decision_reply()], analyst_reply=analyst_reply())

    first = await generate_ai_analysis(
        redis,
        user.id,
        user.daily_analysis_quota,
        quote,
        technical,
        bars,
        llm_client=llm,
    )
    calls_after_first = llm.calls

    second = await generate_ai_analysis(
        redis,
        user.id,
        user.daily_analysis_quota,
        quote,
        technical,
        bars,
        llm_client=llm,
        force=True,
    )

    assert first.cached is False
    assert second.cached is False
    assert llm.calls == calls_after_first + 8
    assert second.quota_used == first.quota_used + 1


async def test_progress_reports_analyst_completion():
    redis = FakeRedis()
    user, quote, technical, bars = make_analysis("600018")
    llm = FakeLLM([decision_reply()], analyst_reply=analyst_reply())
    phases: list[str] = []

    async def progress(text: str) -> None:
        phases.append(text)

    await generate_ai_analysis(
        redis,
        user.id,
        user.daily_analysis_quota,
        quote,
        technical,
        bars,
        llm_client=llm,
        progress=progress,
    )

    assert phases[0] == "六位分析师分析中 0/6"
    assert phases[1:7] == [f"六位分析师分析中 {done}/6" for done in range(1, 7)]
    assert phases[-2] == "团队讨论中"
    assert phases[-1] == "首席策略官汇总六份报告"


def discussion_reply() -> dict:
    return {
        "turns": [
            {
                "speaker": "技术面",
                "target": "资金面",
                "stance": "质疑",
                "content": "技术面评分 68，但资金面数据缺失，结论应更谨慎。",
            },
            {
                "speaker": "资金面",
                "target": "技术面",
                "stance": "补充",
                "content": "资金流数据缺失，无法确认主力方向，本维度按中性处理。",
            },
            {
                "speaker": "风险",
                "target": "技术面",
                "stance": "同意",
                "content": "波动率可控，但需保留资金面缺口提示。",
            },
        ],
        "summary": "分歧集中在资金面数据缺失，整体维持中性偏多。",
    }


async def test_llm_discussion_enters_report_and_decision():
    redis = FakeRedis()
    user, quote, technical, bars = make_analysis("600019")
    llm = FakeLLM(
        [decision_reply()],
        analyst_reply=analyst_reply(),
        discussion_reply=discussion_reply(),
    )

    report = await generate_ai_analysis(
        redis,
        user.id,
        user.daily_analysis_quota,
        quote,
        technical,
        bars,
        llm_client=llm,
    )

    assert report.discussion is not None
    assert report.discussion.source == "llm"
    assert len(report.discussion.turns) == 3
    assert report.discussion.turns[0].speaker == "技术面"
    assert report.discussion.turns[0].target == "资金面"
    assert report.discussion.summary.startswith("分歧集中在")
    assert llm.discussion_calls == 1
    assert llm.decision_calls == 1
    # 讨论纪要进入首席决策输入
    assert any('"discussion"' in prompt for prompt in llm.prompts)


async def test_discussion_failure_falls_back_to_rule():
    redis = FakeRedis()
    user, quote, technical, bars = make_analysis("600020")
    llm = FakeLLM([decision_reply()], analyst_reply=analyst_reply())

    report = await generate_ai_analysis(
        redis,
        user.id,
        user.daily_analysis_quota,
        quote,
        technical,
        bars,
        llm_client=llm,
    )

    assert report.discussion is not None
    assert report.discussion.source == "rule"
    assert len(report.discussion.turns) >= 2
    assert report.discussion.turns[0].stance == "质疑"
    assert report.decision is not None
