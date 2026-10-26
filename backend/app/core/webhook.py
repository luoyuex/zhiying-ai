"""Webhook 地址校验：只允许钉钉/飞书官方机器人域名，避免 SSRF。"""

from urllib.parse import urlparse

ALLOWED_WEBHOOK_HOSTS = {
    "oapi.dingtalk.com",
    "open.feishu.cn",
    "open.larksuite.com",
}


class WebhookUrlError(ValueError):
    pass


def normalize_webhook_url(raw: str | None) -> str | None:
    text = (raw or "").strip()
    if not text:
        return None
    parsed = urlparse(text)
    if parsed.scheme != "https":
        raise WebhookUrlError("Webhook 地址必须使用 https")
    host = (parsed.hostname or "").lower()
    if host not in ALLOWED_WEBHOOK_HOSTS:
        raise WebhookUrlError("只支持钉钉或飞书官方机器人地址")
    if not parsed.path or parsed.path == "/":
        raise WebhookUrlError("Webhook 地址不完整")
    if len(text) > 512:
        raise WebhookUrlError("Webhook 地址过长")
    return text


def is_safe_webhook_url(url: str | None) -> bool:
    try:
        normalize_webhook_url(url)
    except WebhookUrlError:
        return False
    return True
