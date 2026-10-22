"""元宝搜索（腾讯云 WSA SearchPro）。

支持两种接入：
1. 官方腾讯云 API 3.0：wsa.tencentcloudapi.com + TC3-HMAC-SHA256 签名（优先）
2. 兼容参考项目的服务 API KEY（Bearer）模式

定位：公开网页检索，只作为新闻/事件/题材背景，不替代行情与财务数据。
一次个股分析最多调用一次；结果缓存 30 分钟。
"""

import hashlib
import hmac
import json
import time
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import httpx
from redis.asyncio import Redis

from app.core.config import settings
from app.core.logging import get_logger
from app.providers.http import get_http_client, provider_slot
from app.providers.models import Quote
from app.schemas.search import WebSearchResult, WebSource

logger = get_logger(__name__)
TZ_SHANGHAI = ZoneInfo("Asia/Shanghai")
_VALID_COUNTS = (10, 20, 30, 40, 50)
_SERVICE = "wsa"
_ACTION = "SearchPro"
_CONTENT_TYPE = "application/json; charset=utf-8"


def _now() -> datetime:
    return datetime.now(TZ_SHANGHAI)


def build_query(quote: Quote) -> str:
    return f"{quote.name} {quote.symbol} 最新公告 业绩 题材 风险 减持 解禁"


def _cache_key(quote: Quote, query: str) -> str:
    digest = hashlib.sha1(query.encode("utf-8")).hexdigest()[:10]
    return f"web:search:{quote.symbol}:{digest}"


def _failure(query: str, message: str) -> WebSearchResult:
    return WebSearchResult(
        query=query,
        success=False,
        error=message,
        fetched_at=_now(),
    )


def _credential_hint() -> str | None:
    """识别把 SecretId 填进服务 API KEY 的常见错误，避免发出注定 401 的请求。"""
    if settings.wsa_use_official_api:
        return None
    key = settings.wsa_api_key.strip()
    if key.upper().startswith("AKID"):
        return (
            "WSA_API_KEY 看起来是腾讯云 SecretId（AKID…）；"
            "服务 API KEY 应形如 sk-…。请改用 WSA_SECRET_ID + WSA_SECRET_KEY，"
            "或到控制台创建服务 API KEY"
        )
    return None


def _hmac_sha256(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()


def _tc3_authorization(
    secret_id: str,
    secret_key: str,
    host: str,
    timestamp: int,
    body: bytes,
) -> str:
    """按腾讯云 API 3.0 规范生成 Authorization。只签名 content-type 与 host。"""
    date = datetime.fromtimestamp(timestamp, tz=UTC).strftime("%Y-%m-%d")
    canonical_headers = f"content-type:{_CONTENT_TYPE}\nhost:{host}\n"
    signed_headers = "content-type;host"
    payload_hash = hashlib.sha256(body).hexdigest()
    canonical_request = f"POST\n/\n\n{canonical_headers}\n{signed_headers}\n{payload_hash}"
    credential_scope = f"{date}/{_SERVICE}/tc3_request"
    string_to_sign = (
        f"TC3-HMAC-SHA256\n{timestamp}\n{credential_scope}\n"
        f"{hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()}"
    )

    key_date = _hmac_sha256(("TC3" + secret_key).encode("utf-8"), date)
    key_service = hmac.new(key_date, _SERVICE.encode(), hashlib.sha256).digest()
    key_signing = hmac.new(key_service, b"tc3_request", hashlib.sha256).digest()
    signature = hmac.new(
        key_signing,
        string_to_sign.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    return (
        f"TC3-HMAC-SHA256 Credential={secret_id}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )


class YuanbaoSearchClient:
    def __init__(self, http_client: httpx.AsyncClient | None = None) -> None:
        self._client = http_client or get_http_client()

    async def search(self, query: str) -> WebSearchResult:
        if not settings.wsa_search_configured:
            return _failure(
                query,
                "元宝搜索未配置（WSA_SECRET_ID/WSA_SECRET_KEY 或 WSA_API_KEY）",
            )
        hint = _credential_hint()
        if hint:
            return _failure(query, hint)

        count = settings.wsa_search_count if settings.wsa_search_count in _VALID_COUNTS else 20
        payload: dict[str, object] = {
            "Query": query,
            "Cnt": count,
            "Mode": 0,
            "Industry": "finance",
        }
        freshness = settings.wsa_search_freshness.strip()
        if freshness and settings.wsa_use_official_api:
            payload["Freshness"] = freshness

        if settings.wsa_use_official_api:
            return await self._search_official(query, payload)
        return await self._search_bearer(query, payload)

    async def _search_official(
        self,
        query: str,
        payload: dict[str, object],
    ) -> WebSearchResult:
        host = settings.wsa_search_host
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        timestamp = int(time.time())
        headers = {
            "Content-Type": _CONTENT_TYPE,
            "Host": host,
            "X-TC-Action": _ACTION,
            "X-TC-Timestamp": str(timestamp),
            "X-TC-Version": settings.wsa_search_version,
            "Authorization": _tc3_authorization(
                settings.wsa_secret_id,
                settings.wsa_secret_key,
                host,
                timestamp,
                body,
            ),
        }
        if settings.wsa_secret_token:
            headers["X-TC-Token"] = settings.wsa_secret_token

        response = await self._post(
            query,
            f"https://{host}/",
            content=body,
            headers=headers,
        )
        if isinstance(response, WebSearchResult):
            return response
        return self._parse_response(query, response)

    async def _search_bearer(
        self,
        query: str,
        payload: dict[str, object],
    ) -> WebSearchResult:
        response = await self._post(
            query,
            settings.wsa_search_url,
            json_body=payload,
            headers={
                "Authorization": f"Bearer {settings.wsa_api_key}",
                "Content-Type": _CONTENT_TYPE,
            },
        )
        if isinstance(response, WebSearchResult):
            return response
        return self._parse_response(query, response)

    async def _post(
        self,
        query: str,
        url: str,
        *,
        content: bytes | None = None,
        json_body: dict | None = None,
        headers: dict[str, str],
    ) -> httpx.Response | WebSearchResult:
        try:
            async with provider_slot():
                return await self._client.post(
                    url,
                    content=content,
                    json=json_body,
                    headers=headers,
                    timeout=settings.wsa_search_timeout_seconds,
                )
        except httpx.TimeoutException:
            return _failure(query, f"元宝搜索超时（{settings.wsa_search_timeout_seconds}s）")
        except httpx.HTTPError as exc:
            logger.warning("元宝搜索请求失败: %s", exc)
            return _failure(query, "元宝搜索网络请求失败")

    def _parse_response(
        self,
        query: str,
        response: httpx.Response,
    ) -> WebSearchResult:
        if response.status_code in (401, 403):
            return _failure(
                query,
                f"元宝搜索鉴权失败({response.status_code})，请检查 SecretId/SecretKey 或 API KEY",
            )
        if not response.is_success:
            logger.warning("元宝搜索返回 %s: %s", response.status_code, response.text[:200])
            return _failure(query, f"元宝搜索接口错误({response.status_code})")

        try:
            payload = response.json()
        except ValueError:
            return _failure(query, "元宝搜索返回非 JSON")
        if not isinstance(payload, dict):
            return _failure(query, "元宝搜索返回格式异常")

        data = payload.get("Response") if isinstance(payload.get("Response"), dict) else payload
        error = data.get("Error")
        if isinstance(error, dict):
            code = str(error.get("Code") or "")
            message = str(error.get("Message") or "未知错误")
            logger.warning("元宝搜索错误 code=%s message=%s", code, message)
            if "Unauthorized" in code or "AuthFailure" in code:
                return _failure(query, f"元宝搜索鉴权失败：{message}")
            if code in {"ResourceNotFound", "ResourceUnavailable"}:
                return _failure(query, f"元宝搜索服务未开通或不可用：{message}")
            if code == "RequestLimitExceeded":
                return _failure(query, "元宝搜索请求频率超限，请稍后重试")
            return _failure(query, f"元宝搜索错误 {code}: {message}")

        pages = self.parse_pages(data.get("Pages"))
        if not pages:
            message = str(data.get("Msg") or "未检索到相关公开信息")
            return _failure(query, message)

        return WebSearchResult(
            query=query,
            success=True,
            pages=pages[: settings.wsa_search_top_n],
            version=str(data.get("Version") or ""),
            fetched_at=_now(),
        )

    @staticmethod
    def parse_pages(raw: object) -> list[WebSource]:
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except ValueError:
                return []
        if not isinstance(raw, list):
            return []

        pages: list[WebSource] = []
        seen: set[str] = set()
        for item in raw:
            if isinstance(item, str):
                try:
                    item = json.loads(item)
                except ValueError:
                    continue
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            url = str(item.get("url") or "").strip()
            if not title or not url:
                continue
            key = url or title
            if key in seen:
                continue
            seen.add(key)
            summary = str(item.get("passage") or item.get("content") or "").strip()
            pages.append(
                WebSource(
                    title=title,
                    url=url,
                    date=str(item.get("date") or "").strip(),
                    site=str(item.get("site") or "").strip(),
                    summary=summary[:500],
                )
            )
        return pages


async def search_symbol_web(
    redis: Redis,
    quote: Quote,
    *,
    client: YuanbaoSearchClient | None = None,
    cache_seconds: int | None = None,
) -> WebSearchResult:
    query = build_query(quote)
    if not settings.wsa_search_configured:
        return _failure(
            query,
            "元宝搜索未配置（WSA_SECRET_ID/WSA_SECRET_KEY 或 WSA_API_KEY）",
        )
    hint = _credential_hint()
    if hint:
        return _failure(query, hint)

    cache_key = _cache_key(quote, query)
    try:
        cached = await redis.get(cache_key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("读取元宝搜索缓存失败: %s", exc)
        cached = None
    if cached:
        try:
            result = WebSearchResult.model_validate_json(cached)
            return result.model_copy(update={"cached": True})
        except ValueError:
            logger.warning("元宝搜索缓存内容损坏")

    result = await (client or YuanbaoSearchClient()).search(query)
    if result.success and result.pages:
        try:
            await redis.set(
                cache_key,
                result.model_dump_json(),
                ex=(
                    cache_seconds
                    if cache_seconds is not None
                    else settings.wsa_search_cache_seconds
                ),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("写入元宝搜索缓存失败: %s", exc)
    return result


def format_for_prompt(result: WebSearchResult | None, max_items: int | None = None) -> str:
    if result is None or not result.success or not result.pages:
        return "（本次没有可用的公开网页信息）"
    limit = max_items or settings.wsa_search_top_n
    lines = [
        "【元宝搜索·公开网页信息】",
        "以下内容仅供新闻/事件/题材背景，必须核对发布日期，不要当作财务事实；与结构化数据冲突时以结构化数据为准。",
    ]
    for index, page in enumerate(result.pages[:limit], 1):
        meta = " | ".join(part for part in (page.site, page.date) if part)
        lines.append(f"{index}. {page.title}" + (f"（{meta}）" if meta else ""))
        if page.summary:
            lines.append(f"   摘要：{page.summary[:300]}")
        lines.append(f"   链接：{page.url}")
    return "\n".join(lines)


def sources_for_response(result: WebSearchResult | None) -> list[WebSource]:
    if result is None or not result.success:
        return []
    return result.pages[: settings.wsa_search_top_n]
