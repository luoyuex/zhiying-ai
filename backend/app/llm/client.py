"""OpenAI 兼容 LLM 客户端。

只依赖 /chat/completions 协议，base_url / api_key / model 全部来自环境变量。
不要求供应商支持 response_format，JSON 由提示词约束 + 本地修复兜底。
"""

import json
import re
from typing import Any

import openai
from json_repair import loads as repair_loads
from openai import AsyncOpenAI

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class LLMError(Exception):
    """LLM 层可预期异常基类。"""


class LLMNotConfiguredError(LLMError):
    pass


class LLMRateLimitedError(LLMError):
    pass


class LLMRequestError(LLMError):
    pass


class LLMResponseError(LLMError):
    pass


def is_llm_configured() -> bool:
    return settings.llm_configured


def extract_json(content: str) -> dict[str, Any]:
    """从模型输出中提取 JSON：兼容代码块、前后说明文字和轻微格式错误。"""
    text = (content or "").strip()
    if not text:
        raise LLMResponseError("LLM 返回为空")

    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()

    candidates = [text]
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        candidates.append(text[start : end + 1])

    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(data, dict):
            return data

    try:
        repaired = repair_loads(text)
    except Exception as exc:  # noqa: BLE001
        raise LLMResponseError("LLM 返回的 JSON 无法解析") from exc
    if not isinstance(repaired, dict):
        raise LLMResponseError("LLM 返回的不是 JSON 对象")
    return repaired


class LLMClient:
    def __init__(self, client: AsyncOpenAI | None = None) -> None:
        if client is None:
            if not settings.llm_configured:
                raise LLMNotConfiguredError("尚未配置 LLM")
            client = AsyncOpenAI(
                api_key=settings.llm_api_key,
                base_url=settings.llm_base_url,
                timeout=settings.llm_timeout_seconds,
                max_retries=0,
            )
        self._client = client

    async def generate_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        try:
            response = await self._client.chat.completions.create(
                model=settings.llm_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=settings.llm_temperature,
                max_tokens=settings.llm_max_tokens,
            )
        except openai.RateLimitError as exc:
            logger.warning("LLM 限流: %s", exc)
            raise LLMRateLimitedError("LLM 服务限流，请稍后重试") from exc
        except openai.APITimeoutError as exc:
            logger.warning("LLM 超时: %s", exc)
            raise LLMRequestError("LLM 请求超时") from exc
        except openai.OpenAIError as exc:
            logger.warning("LLM 调用失败: %s", exc)
            raise LLMRequestError("LLM 服务调用失败") from exc

        if not response.choices:
            raise LLMResponseError("LLM 未返回候选结果")
        content = response.choices[0].message.content or ""
        usage = response.usage
        logger.info(
            "LLM 调用完成 model=%s prompt_tokens=%s completion_tokens=%s",
            response.model,
            getattr(usage, "prompt_tokens", None),
            getattr(usage, "completion_tokens", None),
        )
        return extract_json(content)
