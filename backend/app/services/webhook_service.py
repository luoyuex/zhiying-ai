"""钉钉 / 飞书机器人 Webhook 通知。

只允许官方域名，消息体保持纯文本/简单 Markdown；发送失败抛异常，由调用方决定是否降级，
不影响任务执行与提醒落库。
"""

from typing import Literal

import httpx

from app.core.logging import get_logger
from app.core.webhook import WebhookUrlError, normalize_webhook_url
from app.providers.http import get_http_client

logger = get_logger(__name__)

WebhookKind = Literal["dingtalk", "feishu"]
_MAX_TEXT = 3500


class WebhookSendError(Exception):
    pass


def _shorten(text: str, limit: int = _MAX_TEXT) -> str:
    value = str(text or "").strip()
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _build_payload(
    kind: WebhookKind,
    keyword: str | None,
    title: str,
    text: str,
) -> dict:
    safe_title = _shorten(title, 120)
    safe_text = _shorten(text)
    keyword_text = (keyword or "").strip()
    if kind == "dingtalk":
        body = f"### {safe_title}\n\n{safe_text}"
        if keyword_text and keyword_text not in body:
            body = f"{keyword_text}\n\n{body}"
        return {
            "msgtype": "markdown",
            "markdown": {"title": safe_title, "text": body},
        }
    body = f"{safe_title}\n\n{safe_text}"
    if keyword_text and keyword_text not in body:
        body = f"{keyword_text}\n\n{body}"
    return {"msg_type": "text", "content": {"text": _shorten(body)}}


async def send_webhook(
    *,
    url: str | None,
    kind: str,
    keyword: str | None,
    title: str,
    text: str,
) -> None:
    """发送一条 Webhook；未配置地址时直接返回。"""
    try:
        safe_url = normalize_webhook_url(url)
    except WebhookUrlError as exc:
        raise WebhookSendError(str(exc)) from exc
    if not safe_url:
        return
    if kind not in ("dingtalk", "feishu"):
        raise WebhookSendError("不支持的 Webhook 类型")

    payload = _build_payload(kind, keyword, title, text)  # type: ignore[arg-type]
    client = get_http_client()
    try:
        response = await client.post(
            safe_url,
            json=payload,
            timeout=httpx.Timeout(10.0, connect=4.0),
            follow_redirects=False,
        )
    except httpx.HTTPError as exc:
        logger.warning("Webhook 请求失败 kind=%s: %s", kind, exc)
        raise WebhookSendError("Webhook 请求失败") from exc

    if response.status_code >= 400:
        logger.warning(
            "Webhook 返回异常 kind=%s status=%s body=%s",
            kind,
            response.status_code,
            response.text[:200],
        )
        raise WebhookSendError(f"Webhook 返回 HTTP {response.status_code}")

    # 钉钉/飞书都可能用 HTTP 200 返回业务错误，尽量识别并记录
    try:
        data = response.json()
    except ValueError:
        data = None
    if isinstance(data, dict):
        errcode = data.get("errcode", data.get("code", 0))
        if errcode not in (0, "0", None):
            message = str(data.get("errmsg") or data.get("msg") or "Webhook 返回错误")
            logger.warning("Webhook 业务错误 kind=%s code=%s msg=%s", kind, errcode, message)
            raise WebhookSendError(message)

    logger.info("Webhook 已发送 kind=%s title=%s", kind, title[:60])
