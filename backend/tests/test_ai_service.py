"""AI 多分析师服务测试：缓存、额度、决策兜底与公开信息。"""

import uuid

import pytest

from app.db.models.user import User
from app.llm.client import LLMResponseError
from app.providers.base import now_shanghai
from app.schemas.analysis import TechnicalAnalysis
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


class FakeLLM:
    def __init__(self, replies: list[dict | Exception]) -> None:
        self.replies = replies
        self.calls = 0
        self.prompts: list[str] = []

    async def generate_json(self, system_prompt: str, user_prompt: str) -> dict:
        self.calls += 1
        self.prompts.append(user_prompt)
        reply = self.replies[min(self.calls - 1, len(self.replies) - 1)]
        if isinstance(reply, Exception):
            raise reply
        return reply


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
    assert llm.calls == 1


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

    assert llm.calls == 1
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
    assert "public_web_info" in llm.prompts[0]
    assert "元宝搜索" in llm.prompts[0]
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
