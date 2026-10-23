"""出站代理池：入口解析、健康度、选择。

P1 只支持静态入口（隧道代理填一个固定 host:port 即可）。健康度落在 Redis，
Redis 不可用时一律放行 / 按默认分处理，避免代理层拖垮行情。
"""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import logging
import random
import re
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from urllib.parse import urlsplit

import httpx
from redis.asyncio import Redis

from app.core.logging import get_logger

logger = get_logger(__name__)

_SUPPORTED_SCHEMES = {"http", "https", "socks5", "socks5h"}


class FailureKind(StrEnum):
    DEAD = "dead"  # 代理不可用（连不上、407）
    BANNED = "banned"  # 目标站封了这个出口
    UPSTREAM = "upstream"  # 目标站 5xx，与代理无关


@dataclass(frozen=True, slots=True)
class ProxyEndpoint:
    url: str
    # 隧道入口背后会换 IP：被站点封时换一个请求可能就好了，不应冷却整个入口
    rotates: bool = True
    # 服务商按需提取的 IP：失败后由池子丢弃换新，不按静态入口冷却
    dynamic: bool = False

    @property
    def id(self) -> str:
        """稳定标识：只取 scheme://host:port，账号密码轮换不影响健康度。"""
        parts = urlsplit(self.url)
        port = f":{parts.port}" if parts.port else ""
        identity = f"{parts.scheme.lower()}://{(parts.hostname or '').lower()}{port}"
        return hashlib.sha1(identity.encode("utf-8")).hexdigest()[:12]

    @property
    def display(self) -> str:
        """日志用，绝不输出账号密码。"""
        return _redact_url(self.url)


class ProxyPoolProtocol(Protocol):
    @property
    def endpoints(self) -> list[ProxyEndpoint]: ...

    async def acquire(
        self, provider: str, exclude: set[str] | None = None
    ) -> ProxyEndpoint | None: ...

    async def report_success(self, endpoint: ProxyEndpoint, latency_ms: float) -> None: ...

    async def report_failure(
        self, endpoint: ProxyEndpoint, provider: str, kind: FailureKind
    ) -> None: ...

    async def aclose(self) -> None: ...


def _redact_url(url: str) -> str:
    try:
        parts = urlsplit(url)
        if not parts.hostname:
            return "<invalid>"
        port = f":{parts.port}" if parts.port else ""
        return f"{parts.scheme}://{parts.hostname}{port}"
    except ValueError:
        return "<invalid>"


def parse_proxy_endpoints(raw: str, *, rotates: bool) -> list[ProxyEndpoint]:
    """按逗号/空白切分；允许只写 host:port，默认 http://。"""
    endpoints: list[ProxyEndpoint] = []
    seen: set[str] = set()
    for item in re.split(r"[,\s]+", raw.strip()):
        if not item:
            continue
        url = item if "://" in item else f"http://{item}"
        try:
            parts = urlsplit(url)
            port = parts.port  # 非法端口在这里抛 ValueError
        except ValueError:
            logger.warning("忽略无效代理入口: %s", _redact_url(url))
            continue
        if parts.scheme.lower() not in _SUPPORTED_SCHEMES or not parts.hostname or not port:
            logger.warning("忽略无效代理入口: %s", _redact_url(url))
            continue
        endpoint = ProxyEndpoint(url=url, rotates=rotates)
        if endpoint.id in seen:
            continue
        seen.add(endpoint.id)
        endpoints.append(endpoint)
    return endpoints


class ProxyHealthStore:
    """Redis 健康度。

    mkt:proxy:{id}                → hash{ok, fail, banned, consecutive_fail,
                                          latency_ms, last_used, cooldown_until}
    mkt:proxy:{id}:ban:{provider} → 被该站封禁的到期时间戳
    """

    PREFIX = "mkt:proxy:"
    _TTL_SECONDS = 86_400

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    def _key(self, endpoint_id: str) -> str:
        return f"{self.PREFIX}{endpoint_id}"

    def _ban_key(self, endpoint_id: str, provider: str) -> str:
        return f"{self.PREFIX}{endpoint_id}:ban:{provider}"

    async def cooldown_remaining(self, endpoint_id: str, provider: str) -> float:
        try:
            cooldown_until, banned_until = await asyncio.gather(
                self._redis.hget(self._key(endpoint_id), "cooldown_until"),
                self._redis.get(self._ban_key(endpoint_id, provider)),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("读取代理健康度失败，放行: %s", exc)
            return 0.0
        now = time.time()
        return max(float(cooldown_until or 0) - now, float(banned_until or 0) - now, 0.0)

    async def score(self, endpoint_id: str) -> float:
        try:
            data = await self._redis.hgetall(self._key(endpoint_id))
        except Exception as exc:  # noqa: BLE001
            logger.warning("读取代理评分失败，按默认分: %s", exc)
            return 1.0
        ok = int(data.get("ok") or 0)
        fail = int(data.get("fail") or 0)
        success_rate = (ok + 1.0) / (ok + fail + 2.0)
        latency_ms = float(data.get("latency_ms") or 0.0)
        latency_factor = 1.0 / (1.0 + latency_ms / 500.0)
        last_used = float(data.get("last_used") or 0.0)
        recency_factor = 0.35 if time.time() - last_used < 1.0 else 1.0
        return max(success_rate * latency_factor * recency_factor, 0.01)

    async def mark_used(self, endpoint_id: str) -> None:
        try:
            await self._redis.hset(
                self._key(endpoint_id), "last_used", round(time.time(), 3)
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("记录代理使用时间失败: %s", exc)

    async def record_success(self, endpoint_id: str, latency_ms: float) -> None:
        key = self._key(endpoint_id)
        try:
            async with self._redis.pipeline(transaction=False) as pipe:
                pipe.hincrby(key, "ok", 1)
                pipe.hset(
                    key,
                    mapping={
                        "consecutive_fail": 0,
                        "latency_ms": round(latency_ms, 1),
                        "last_fail_reason": "",
                    },
                )
                pipe.expire(key, self._TTL_SECONDS)
                await pipe.execute()
        except Exception as exc:  # noqa: BLE001
            logger.warning("记录代理成功失败: %s", exc)

    async def record_failure(
        self,
        endpoint_id: str,
        kind: FailureKind,
        *,
        provider: str,
        cooldown_seconds: int,
        ban_seconds: int,
    ) -> None:
        if kind is FailureKind.UPSTREAM:
            return
        key = self._key(endpoint_id)
        now = time.time()
        try:
            async with self._redis.pipeline(transaction=False) as pipe:
                pipe.hincrby(key, "fail", 1)
                pipe.hincrby(key, "consecutive_fail", 1)
                pipe.hset(key, mapping={"last_fail_reason": kind.value})
                if kind is FailureKind.DEAD:
                    pipe.hset(key, mapping={"cooldown_until": now + cooldown_seconds})
                pipe.expire(key, self._TTL_SECONDS)
                if kind is FailureKind.BANNED:
                    pipe.set(
                        self._ban_key(endpoint_id, provider),
                        now + ban_seconds,
                        ex=ban_seconds,
                    )
                await pipe.execute()
        except Exception as exc:  # noqa: BLE001
            logger.warning("记录代理失败失败: %s", exc)

    async def record_soft_failure(self, endpoint_id: str) -> None:
        """隧道入口的站点级封禁：只计数，不冷却入口。"""
        key = self._key(endpoint_id)
        try:
            async with self._redis.pipeline(transaction=False) as pipe:
                pipe.hincrby(key, "banned", 1)
                pipe.hset(key, mapping={"last_fail_reason": FailureKind.BANNED.value})
                pipe.expire(key, self._TTL_SECONDS)
                await pipe.execute()
        except Exception as exc:  # noqa: BLE001
            logger.warning("记录代理软失败失败: %s", exc)


class ProxySelector:
    """过滤冷却中的入口，按成功率 × 延迟 × 最近使用衰减加权随机。"""

    def __init__(self, store: ProxyHealthStore) -> None:
        self._store = store
        self._rng = random.Random()

    async def pick(
        self,
        endpoints: list[ProxyEndpoint],
        provider: str,
        exclude: set[str],
    ) -> ProxyEndpoint | None:
        candidates = [item for item in endpoints if item.id not in exclude]
        if not candidates:
            return None
        probes = await asyncio.gather(
            *(self._probe(item, provider) for item in candidates)
        )
        available = [(item, score) for item, score in probes if score is not None]
        if not available:
            return None
        endpoint = self._rng.choices(
            [item for item, _ in available],
            weights=[score for _, score in available],
            k=1,
        )[0]
        await self._store.mark_used(endpoint.id)
        return endpoint

    async def _probe(
        self, endpoint: ProxyEndpoint, provider: str
    ) -> tuple[ProxyEndpoint, float | None]:
        remaining = await self._store.cooldown_remaining(endpoint.id, provider)
        if remaining > 0:
            return endpoint, None
        return endpoint, await self._store.score(endpoint.id)


class ProxyPool:
    def __init__(
        self,
        endpoints: list[ProxyEndpoint],
        store: ProxyHealthStore,
        selector: ProxySelector,
        *,
        cooldown_seconds: int,
        ban_seconds: int,
    ) -> None:
        self._endpoints = endpoints
        self._store = store
        self._selector = selector
        self._cooldown_seconds = cooldown_seconds
        self._ban_seconds = ban_seconds

    @property
    def endpoints(self) -> list[ProxyEndpoint]:
        return list(self._endpoints)

    async def acquire(
        self, provider: str, exclude: set[str] | None = None
    ) -> ProxyEndpoint | None:
        return await self._selector.pick(self._endpoints, provider, exclude or set())

    async def report_success(self, endpoint: ProxyEndpoint, latency_ms: float) -> None:
        await self._store.record_success(endpoint.id, latency_ms)

    async def report_failure(
        self, endpoint: ProxyEndpoint, provider: str, kind: FailureKind
    ) -> None:
        if kind is FailureKind.BANNED and endpoint.rotates:
            await self._store.record_soft_failure(endpoint.id)
            return
        await self._store.record_failure(
            endpoint.id,
            kind,
            provider=provider,
            cooldown_seconds=self._cooldown_seconds,
            ban_seconds=self._ban_seconds,
        )

    async def aclose(self) -> None:
        return None


def parse_api_payload(payload: object) -> list[ProxyEndpoint]:
    """解析提取接口返回：{"code":0,"data":[{"IP":"...","Port":3828}]}。"""
    if not isinstance(payload, dict) or str(payload.get("code")) != "0":
        return []
    rows = payload.get("data")
    if not isinstance(rows, list):
        return []

    endpoints: list[ProxyEndpoint] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        ip = str(row.get("IP") or "").strip()
        try:
            port = int(row.get("Port"))
            address = ipaddress.ip_address(ip)
        except (TypeError, ValueError):
            continue
        if not isinstance(address, ipaddress.IPv4Address) or not 0 < port < 65536:
            continue
        endpoint = ProxyEndpoint(url=f"http://{ip}:{port}", rotates=False, dynamic=True)
        if endpoint.id in seen:
            continue
        seen.add(endpoint.id)
        endpoints.append(endpoint)
    return endpoints


class ApiProxySource:
    """从服务商提取接口取代理，返回 http://IP:Port。"""

    def __init__(self, url: str, *, timeout: float = 10.0) -> None:
        self._url = url
        self._client = httpx.AsyncClient(timeout=timeout, trust_env=False)
        # 提取链接里带 uid/vkey；httpx 默认会在 INFO 级别打印完整 URL，必须压掉
        logging.getLogger("httpx").setLevel(logging.WARNING)

    async def fetch(self) -> list[ProxyEndpoint]:
        try:
            response = await self._client.get(self._url)
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            # 不打印 URL / 异常原文，避免 vkey 进日志
            logger.warning("提取代理失败: %s", type(exc).__name__)
            return []
        except ValueError:
            logger.warning("提取代理失败: 返回非 JSON")
            return []

        endpoints = parse_api_payload(payload)
        if not endpoints:
            code = payload.get("code") if isinstance(payload, dict) else "?"
            message = payload.get("msg") if isinstance(payload, dict) else ""
            logger.warning(
                "提取代理失败: code=%s msg=%s", code, str(message or "")[:80]
            )
        return endpoints

    async def aclose(self) -> None:
        await self._client.aclose()


class ApiProxyPool:
    """进程内提取代理池：API/worker 各用各的 IP，按请求懒提取。

    当前 IP 过期后不主动刷新，等下一个行情请求进来才提取；同一进程内的
    并发请求共用一把锁，只会提取一次。
    """

    def __init__(
        self,
        source: ApiProxySource,
        *,
        ttl_seconds: int,
        error_cooldown_seconds: float,
    ) -> None:
        self._source = source
        self._ttl = max(ttl_seconds, 0)
        self._error_cooldown = max(error_cooldown_seconds, 0.0)
        self._endpoints: list[ProxyEndpoint] = []
        self._expires_at = 0.0
        self._retry_after = 0.0
        self._lock = asyncio.Lock()

    @property
    def endpoints(self) -> list[ProxyEndpoint]:
        return list(self._endpoints)

    async def acquire(
        self, provider: str, exclude: set[str] | None = None
    ) -> ProxyEndpoint | None:
        excluded = exclude or set()
        async with self._lock:
            if not self._usable():
                await self._refresh_locked()
            endpoint = self._pick(excluded)
            if endpoint is not None:
                return endpoint
            if not self._endpoints:
                # 当前 IP 已被判死/封禁并移除：提取新 IP 再试
                await self._refresh_locked()
                return self._pick(excluded)
            # 当前 IP 仍有效，只是本轮被排除（目标站 5xx/断开）：
            # 本次不再提取，避免为站点故障白白消耗提取次数
            return None

    def _usable(self) -> bool:
        return bool(self._endpoints) and time.time() < self._expires_at

    def _pick(self, excluded: set[str]) -> ProxyEndpoint | None:
        for endpoint in self._endpoints:
            if endpoint.id not in excluded:
                return endpoint
        return None

    async def _refresh_locked(self) -> None:
        now = time.time()
        if now < self._retry_after:
            return
        endpoints = await self._source.fetch()
        if not endpoints:
            self._endpoints = []
            self._expires_at = 0.0
            self._retry_after = time.time() + self._error_cooldown
            return
        self._endpoints = endpoints
        self._expires_at = time.time() + self._ttl
        self._retry_after = 0.0
        logger.info(
            "已提取代理入口 %s（共 %d 个，ttl=%ss）",
            endpoints[0].display,
            len(endpoints),
            self._ttl,
        )

    async def report_success(self, endpoint: ProxyEndpoint, latency_ms: float) -> None:
        return None

    async def report_failure(
        self, endpoint: ProxyEndpoint, provider: str, kind: FailureKind
    ) -> None:
        async with self._lock:
            if kind is FailureKind.UPSTREAM:
                # 目标站 5xx/断开不是这个 IP 的问题，保留到 TTL
                return
            self._endpoints = [
                item for item in self._endpoints if item.id != endpoint.id
            ]
            if not self._endpoints:
                self._expires_at = 0.0

    async def aclose(self) -> None:
        await self._source.aclose()
