"""行情出站自检：验证服务器能否取到选股依赖的行情数据。

排查「行情/资金流数据暂不可用」时先跑这个脚本。它会分别测试：

1. 直连能否访问东财资金流排行（主力追踪的第一步，也是最容易失败的一步）
2. 直连能否访问东财行情、腾讯行情、新浪行情
3. 按 .env 的代理配置取出口（source=api 走提取链接，source=static 走入口列表），
   再用同样的请求测一遍

最后给出结论：该开代理、该加白名单，还是该查出站网络。

用法（在 /opt/zhiying-ai/backend）：
    .venv/bin/python -m app.scripts.check_proxy
    .venv/bin/python -m app.scripts.check_proxy --skip-direct

退出码：0 = 至少一条路径能取到东财资金流排行；1 = 都失败。
不会打印 vkey、账号密码等密钥。
"""

import argparse
import asyncio
import logging
import re
import sys
import time
from urllib.parse import urlsplit

import httpx

from app.core.config import settings
from app.providers.egress import DEFAULT_HEADERS, ProxyClientCache
from app.providers.fund_flow_rank import EastmoneyFundFlowRankProvider
from app.providers.proxy_pool import (
    ApiProxySource,
    ProxyEndpoint,
    parse_proxy_endpoints,
)

IP_URL = "https://myip.ipip.net"
# 与主力追踪实际请求保持一致：29 是首选镜像，失败才会切 1
RANK_URL = f"https://{EastmoneyFundFlowRankProvider.HOSTS[0]}/api/qt/clist/get"
RANK_PARAMS = {
    "pn": 1,
    "pz": 20,
    "po": 1,
    "np": 1,
    "fltt": 2,
    "invt": 2,
    "fid": "f62",
    "fs": EastmoneyFundFlowRankProvider.FS,
    "fields": "f12,f14,f3,f62",
    "ut": EastmoneyFundFlowRankProvider.UT,
}
QUOTE_URL = "https://push2.eastmoney.com/api/qt/stock/get"
QUOTE_PARAMS = {"secid": "1.600519", "fields": "f43,f57,f58"}
TENCENT_URL = "https://qt.gtimg.cn/q=sh600519"
SINA_URL = "https://hq.sinajs.cn/list=sh600519"
SINA_HEADERS = {"Referer": "https://finance.sina.com.cn/"}

_IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


def mask_url(raw: str) -> str:
    """只保留 scheme://host:port，避免 vkey / 账号密码进终端和工单。"""
    try:
        parts = urlsplit(raw)
        if not parts.hostname:
            return "<invalid>"
        port = f":{parts.port}" if parts.port else ""
        return f"{parts.scheme}://{parts.hostname}{port}"
    except ValueError:
        return "<invalid>"


def describe_error(exc: Exception, *, via_proxy: bool = False) -> str:
    detail = str(exc).strip() or type(exc).__name__
    if isinstance(exc, httpx.ProxyError):
        return f"代理认证/隧道失败（{detail}）；检查代理账号密码，或服务商要求的白名单 IP"
    if isinstance(exc, httpx.RemoteProtocolError):
        return (
            f"对端主动断开连接（{detail}）；东财对机房出口常这样，"
            "说明该出口被限流/封禁，不是代码问题"
        )
    if isinstance(exc, httpx.ConnectTimeout):
        if via_proxy:
            return f"代理出口连不上（{detail}）；这个 IP 已失效，重跑一次会换新 IP"
        return f"连不上目标站（{detail}）；服务器出站被安全组/防火墙拦截，或目标站不可达"
    if isinstance(exc, httpx.ConnectError):
        if via_proxy:
            return f"代理出口连不上（{detail}）；这个 IP 已失效，重跑一次会换新 IP"
        return f"连不上目标站（{detail}）；检查 DNS、出站防火墙、安全组"
    if isinstance(exc, httpx.TimeoutException):
        return f"请求超时（{detail}）；代理出口或目标站太慢"
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status in (403, 429):
            return f"HTTP {status}；出口 IP 被目标站拦截或限流"
        if status == 407:
            return "HTTP 407；代理要求认证"
        return f"HTTP {status}；目标站返回错误"
    text = str(exc).replace("\n", " ")[:120]
    return f"{type(exc).__name__}: {text}"


def _new_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(settings.market_http_timeout, connect=5.0),
        headers=DEFAULT_HEADERS,
        trust_env=False,
    )


async def probe_ip(client: httpx.AsyncClient, *, via_proxy: bool = False) -> str | None:
    try:
        response = await client.get(IP_URL, timeout=8.0)
        response.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        print(f"  出口 IP  : 查询失败（{describe_error(exc, via_proxy=via_proxy)}）")
        return None
    text = " ".join(response.text.split())
    match = _IPV4_RE.search(text)
    ip = match.group(0) if match else text[:60]
    print(f"  出口 IP  : {ip}")
    return ip


async def probe_rank(client: httpx.AsyncClient, *, via_proxy: bool = False) -> bool:
    started = time.perf_counter()
    try:
        response = await client.get(RANK_URL, params=RANK_PARAMS)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:  # noqa: BLE001
        print(f"  东财排行 : 失败 - {describe_error(exc, via_proxy=via_proxy)}")
        return False
    elapsed = (time.perf_counter() - started) * 1000
    rows = (payload.get("data") or {}).get("diff") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        body = response.text[:120].replace("\n", " ")
        print(f"  东财排行 : 失败 - 返回格式异常 {body!r}")
        return False
    print(f"  东财排行 : 成功 {len(rows)} 条（{elapsed:.0f}ms）")
    return True


async def probe_quotes(client: httpx.AsyncClient, *, via_proxy: bool = False) -> None:
    try:
        response = await client.get(QUOTE_URL, params=QUOTE_PARAMS)
        response.raise_for_status()
        data = response.json().get("data") or {}
        print(f"  东财行情 : 成功 {data.get('f58')} f43={data.get('f43')}")
    except Exception as exc:  # noqa: BLE001
        print(f"  东财行情 : 失败 - {describe_error(exc, via_proxy=via_proxy)}")

    try:
        response = await client.get(TENCENT_URL)
        response.raise_for_status()
        print(f"  腾讯行情 : 成功 {len(response.content)}B")
    except Exception as exc:  # noqa: BLE001
        print(f"  腾讯行情 : 失败 - {describe_error(exc, via_proxy=via_proxy)}")

    try:
        response = await client.get(SINA_URL, headers=SINA_HEADERS)
        response.raise_for_status()
        print(f"  新浪行情 : 成功 {len(response.content)}B")
    except Exception as exc:  # noqa: BLE001
        print(f"  新浪行情 : 失败 - {describe_error(exc, via_proxy=via_proxy)}")


async def probe_path(client: httpx.AsyncClient, label: str, *, via_proxy: bool = False) -> dict:
    print(f"== {label} ==")
    ip = await probe_ip(client, via_proxy=via_proxy)
    rank_ok = await probe_rank(client, via_proxy=via_proxy)
    await probe_quotes(client, via_proxy=via_proxy)
    print()
    return {"ip": ip, "rank_ok": rank_ok}


async def resolve_proxy_endpoints(*, verbose: bool = True) -> list[ProxyEndpoint]:
    def say(text: str) -> None:
        if verbose:
            print(text)

    if not settings.egress_proxy_enabled:
        say("  代理开关 : 关闭（EGRESS_PROXY_ENABLED=false，行情请求全部直连）")
        return []

    source = settings.egress_proxy_source
    say(f"  代理开关 : 开启，source={source}")

    if source == "api":
        url = settings.egress_proxy_api_url.strip()
        if not url:
            say("  提取链接 : 未配置（EGRESS_PROXY_SOURCE=api 但 EGRESS_PROXY_API_URL 为空）")
            return []
        say(f"  提取链接 : {mask_url(url)}（含 uid/vkey，已省略参数）")
        extractor = ApiProxySource(url, timeout=8.0)
        try:
            endpoints = await extractor.fetch()
        finally:
            await extractor.aclose()
        if not endpoints:
            say(
                "  提取结果 : 0 个（提取接口失败或返回空）\n"
                "             检查 vkey 是否过期、当日提取量是否用完、"
                "服务商白名单是否包含上面「直连」里打印的服务器出口 IP"
            )
            return []
        say(f"  提取结果 : {len(endpoints)} 个 -> {', '.join(e.display for e in endpoints)}")
        return endpoints

    endpoints = parse_proxy_endpoints(
        settings.egress_proxy_entries,
        rotates=settings.egress_proxy_rotate_per_request,
    )
    if not endpoints:
        say("  静态入口 : 未配置或格式非法（EGRESS_PROXY_STATIC / EGRESS_PROXY_URL 都是空）")
        return []
    say(f"  静态入口 : {len(endpoints)} 个 -> {', '.join(e.display for e in endpoints)}")
    return endpoints


def print_conclusion(
    *,
    enabled: bool,
    direct: dict | None,
    proxied: list[dict],
) -> bool:
    direct_ok = bool(direct and direct["rank_ok"])
    proxy_ok = any(item["rank_ok"] for item in proxied)
    print("== 结论 ==")

    if direct_ok and (not enabled or proxy_ok):
        print("东财资金流排行可达，选股链路的数据源没有问题。")
        print("如果页面仍报错，看 worker 日志里的具体异常：")
        print("  journalctl -u zhiying-worker -n 200 --no-pager | grep -E '数据不可用|排行'")
        return True

    if not enabled:
        print("行情请求走直连，但当前出口取不到东财资金流排行。")
        print("服务器是机房出口时，东财经常直接断连；这是线上最常见的失败原因。")
        print("处理：在仓库根目录 .env 打开行情代理，然后重启 API 和 worker：")
        print("  EGRESS_PROXY_ENABLED=true")
        print("  EGRESS_PROXY_SOURCE=api")
        print("  EGRESS_PROXY_API_URL=<服务商给的完整提取链接>")
        print("  EGRESS_PROXY_API_TTL_SECONDS=25")
        print("  systemctl restart zhiying-api zhiying-worker")
        return False

    if proxy_ok:
        if direct is None:
            print("代理出口可用（本次未测直连）。")
        else:
            print("代理出口可用，直连不可用；线上的代理配置正确。")
        print("请确认 API 和 worker 用的是同一个 .env，并且改完已重启：")
        print("  systemctl restart zhiying-api zhiying-worker")
        return True

    if not proxied:
        print("代理已开启，但没有拿到任何可用出口。")
        print("先解决提取失败：vkey 是否过期、提取额度、服务商白名单 IP。")
        return False

    print("直连和代理出口都取不到东财资金流排行。")
    print("优先确认服务器出站网络（安全组、DNS），再看代理出口是否被东财限流。")
    return False


async def test_endpoints(
    endpoints: list[ProxyEndpoint],
    results: list[dict],
    seen: set[str],
) -> None:
    cache = ProxyClientCache(timeout=settings.market_http_timeout)
    try:
        for endpoint in endpoints:
            if endpoint.id in seen:
                continue
            seen.add(endpoint.id)
            try:
                client = cache.get(endpoint)
            except Exception as exc:  # noqa: BLE001
                print(f"== 代理 {endpoint.display} ==")
                print(f"  客户端创建失败: {describe_error(exc, via_proxy=True)}")
                print()
                continue
            results.append(await probe_path(client, f"代理 {endpoint.display}", via_proxy=True))
    finally:
        await cache.aclose()


async def run(skip_direct: bool) -> int:
    print("== 配置 ==")
    endpoints = await resolve_proxy_endpoints()
    print()

    direct: dict | None = None
    if skip_direct:
        print("（--skip-direct：跳过直连测试）\n")
    else:
        client = _new_client()
        try:
            direct = await probe_path(client, "直连")
        finally:
            await client.aclose()

    proxied: list[dict] = []
    seen: set[str] = set()
    if endpoints:
        await test_endpoints(endpoints, proxied, seen)
        # 提取源每次给的是随机 IP，单次失败可能只是拿到坏出口。
        # 与应用内「丢弃坏 IP 再提取」的行为一致，最多换一轮。
        if (
            settings.egress_proxy_enabled
            and settings.egress_proxy_source == "api"
            and not any(item["rank_ok"] for item in proxied)
        ):
            print("（本轮出口不可用，重新提取一次）\n")
            await test_endpoints(await resolve_proxy_endpoints(verbose=False), proxied, seen)

    ok = print_conclusion(enabled=settings.egress_proxy_enabled, direct=direct, proxied=proxied)
    print()
    print("应用内验证：触发一次行情请求后，检查日志中的")
    print('  "代理出口已确认可用"（INFO）或 "代理请求成功"（DEBUG）。')
    return 0 if ok else 1


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:  # noqa: BLE001
                pass
    # 让提取失败的 code/msg 也能显示出来（httpx 的完整 URL 已在 ApiProxySource 里压掉）
    logging.basicConfig(level=logging.INFO, format="  %(message)s")

    parser = argparse.ArgumentParser(description="检查行情出站与代理是否可用")
    parser.add_argument("--skip-direct", action="store_true", help="跳过直连对照，只测代理")
    args = parser.parse_args()
    sys.exit(asyncio.run(run(args.skip_direct)))


if __name__ == "__main__":
    main()
