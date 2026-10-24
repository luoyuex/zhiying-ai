"""LLM 输出解析与客户端协议测试（不访问外网）。"""

from types import SimpleNamespace

import openai
import pytest
from pydantic import ValidationError

from app.core.config import settings
from app.llm.client import LLMClient, LLMRequestError, extract_json
from app.schemas.ai import AIAnalysisPayload


class FakeCompletions:
    def __init__(self, content: str | None = None, error: Exception | None = None) -> None:
        self.content = content
        self.error = error
        self.calls = 0
        self.last_kwargs: dict = {}

    async def create(self, **kwargs: object):
        self.calls += 1
        self.last_kwargs = kwargs
        if self.error:
            raise self.error
        return SimpleNamespace(
            model="mock-model",
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(role="assistant", content=self.content)
                )
            ],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=20),
        )


class FakeSDK:
    def __init__(self, completions: FakeCompletions) -> None:
        self.chat = SimpleNamespace(completions=completions)


def valid_payload() -> dict:
    return {
        "rating": "看多",
        "confidence": 78,
        "trend": "上升",
        "summary": "均线多头排列，量能配合。",
        "key_points": ["价格站上 MA20", "MACD 红柱"],
        "risks": ["RSI 偏高"],
        "watch": "关注 MA20 支撑",
    }


def test_extract_json_variants():
    assert extract_json('{"a": 1}') == {"a": 1}
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('分析如下：\n{"a": 1}\n以上。') == {"a": 1}
    assert extract_json('{"a": 1,}') == {"a": 1}


def test_payload_normalizes_llm_aliases():
    payload = AIAnalysisPayload.model_validate(
        {
            "rating": "看涨",
            "confidence": "82%",
            "trend": "上涨",
            "summary": "  技术面偏强。 ",
            "key_points": "- 站上 MA20\n- MACD 红柱",
            "risks": ["RSI 偏高"],
            "watch": "关注量能",
        }
    )
    assert payload.rating == "看多"
    assert payload.confidence == 82
    assert payload.trend == "上升"
    assert payload.key_points == ["站上 MA20", "MACD 红柱"]


def test_payload_rejects_unknown_rating():
    with pytest.raises(ValidationError):
        AIAnalysisPayload.model_validate(
            {
                "rating": "强烈推荐",
                "confidence": 80,
                "trend": "上升",
                "summary": "test",
            }
        )


async def test_client_parses_openai_chat_completion():
    completions = FakeCompletions(content='```json\n{"a": 1}\n```')
    client = LLMClient(client=FakeSDK(completions))

    data = await client.generate_json("system", "user", reasoning_effort="none")

    assert data == {"a": 1}
    assert completions.calls == 1
    assert completions.last_kwargs["extra_body"] == {"reasoning_effort": "none"}


async def test_client_allows_reasoning_effort_override():
    completions = FakeCompletions(content='{"a": 1}')
    client = LLMClient(client=FakeSDK(completions))

    await client.generate_json("system", "user", reasoning_effort="low")

    assert completions.last_kwargs["extra_body"] == {"reasoning_effort": "low"}


async def test_client_auto_disables_sensenova_reasoning(monkeypatch):
    monkeypatch.setattr(settings, "llm_model", "sensenova-6.8-flash-lite")
    monkeypatch.setattr(settings, "llm_reasoning_effort", "default")
    completions = FakeCompletions(content='{"a": 1}')
    client = LLMClient(client=FakeSDK(completions))

    await client.generate_json("system", "user")

    assert completions.last_kwargs["extra_body"] == {"reasoning_effort": "none"}


async def test_client_omits_reasoning_effort_for_other_models(monkeypatch):
    monkeypatch.setattr(settings, "llm_model", "deepseek-chat")
    monkeypatch.setattr(settings, "llm_reasoning_effort", "default")
    completions = FakeCompletions(content='{"a": 1}')
    client = LLMClient(client=FakeSDK(completions))

    await client.generate_json("system", "user")

    assert completions.last_kwargs["extra_body"] is None


async def test_client_wraps_sdk_error():
    completions = FakeCompletions(error=openai.OpenAIError("boom"))
    client = LLMClient(client=FakeSDK(completions))

    with pytest.raises(LLMRequestError):
        await client.generate_json("system", "user")
