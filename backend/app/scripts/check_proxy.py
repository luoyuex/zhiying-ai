"""代理自检：对比直连与代理出口 IP，并实际请求一次东财行情。

用法（在项目根目录）：
    uv run --directory backend python -m app.scripts.check_proxy
    uv run --directory backend python -m app.scripts.check_proxy --skip-direct
"""

import argparse
import asyncio
import re
import sys
import time

import httpx

from app.core.config import settings
from app.providers.egress import DEFAULT_HEADERS, ProxyClientCache
from app.providers.proxy_pool import parse_proxy_endpoints

IP_URL = "https://myip.ipip.net"
QUOTE_URL = "https://push2.eastmoney.com/api/qt/stock/get"
QUOTE_PARAMS = {"secid": "1.600519", "fields": "f43,f57,f58"}
_IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


def _new_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(settings.market_http_timeout, connect=5.0),
        headers=DEFAULT_HEADERS,
        trust_env=False,
    )


async def probe(client: httpx.AsyncClient, label: str) -> dict:
    started = time.perf_counter()
    try:
        response = await client.get(IP_URL)
        response.raise_for_status()
    except httpx.ProxyError as exc:
        print(f"[{label}] 代理认证/隧道失败: {exc}")
        print("         检查：代理用户名密码是否正确；密码里的 @ : / 等字符是否已 URL 编码；")
        print("         或服务商要求的是 IP 白名单而不是账号密码。")
        return {"ok": False}
    except httpx.ConnectError as exc:
        print(f"[{label}] 连不上代理入口: {exc}")
        print("         检查：host/port、本机网络/防火墙、服务商白名单是否包含本机公网 IP。")
        return {"ok": False}
    except httpx.TimeoutException as exc:
        print(f"[{label}] 代理请求超时: {exc}")
        return {"ok": False}
    except Exception as exc:  # noqa: BLE001
        print(f"[{label}] 查出口 IP 失败: {type(exc).__name__}: {exc}")
        return {"ok": False}

    text = " ".join(response.text.split())
    match = _IPV4_RE.search(text)
    ip = match.group(0) if match else text[:80]
    elapsed = (time.perf_counter() - started) * 1000
    print(f"[{label}] 出口 IP: {ip}（{elapsed:.0f}ms）")
    if text:
        print(f"         原始返回: {text[:100]}")

    started = time.perf_counter()
    try:
        quote = await client.get(QUOTE_URL, params=QUOTE_PARAMS)
        quote.raise_for_status()
        payload = quote.json()
    except Exception as exc:  # noqa: BLE001
        print(f"[{label}] 东财行情失败: {type(exc).__name__}: {exc}")
        return {"ok": False, "ip": ip}

    data = payload.get("data") or {}
    elapsed = (time.perf_counter() - started) * 1000
    print(
        f"[{label}] 东财行情: {data.get('f58')} f43={data.get('f43')} "
        f"{len(quote.content)}B（{elapsed:.0f}ms）"
    )
    return {"ok": True, "ip": ip}


async def run(skip_direct: bool) -> int:
    enabled = settings.egress_proxy_enabled
    raw = settings.egress_proxy_entries
    print(f"代理池开关: {'开启' if enabled else '关闭'}")
    print(f"代理入口配置: {'已配置' if raw else '未配置'}")

    if not enabled and not raw:
        print("代理池未启用且未配置 EGRESS_PROXY_URL，行情请求走直连。")
        return 0

    rotates = settings.egress_proxy_rotate_per_request if enabled else False
    endpoints = parse_proxy_endpoints(raw, rotates=rotates)
    for endpoint in endpoints:
        print(f"  - {endpoint.display}（rotates={endpoint.rotates}）")

    if enabled and not endpoints:
        print("错误：EGRESS_PROXY_ENABLED=true，但没有解析到可用入口。")
        return 1
    if not enabled:
        print("注意：EGRESS_PROXY_ENABLED=false，但配置了 EGRESS_PROXY_URL，")
        print("      行情请求会走旧的全局代理（元宝搜索也会走）。")

    direct_ip = None
    if not skip_direct:
        direct_client = _new_client()
        try:
            direct = await probe(direct_client, "直连")
            direct_ip = direct.get("ip")
        finally:
            await direct_client.aclose()

    cache = ProxyClientCache(timeout=settings.market_http_timeout)
    ok = True
    try:
        for endpoint in endpoints:
            try:
                client = cache.get(endpoint)
            except Exception as exc:  # noqa: BLE001
                print(f"[{endpoint.display}] 客户端创建失败: {type(exc).__name__}: {exc}")
                ok = False
                continue

            result = await probe(client, endpoint.display)
            if not result["ok"]:
                ok = False
                continue
            if direct_ip and result.get("ip") == direct_ip:
                print("         注意：出口 IP 与直连相同，代理可能未生效或服务商未轮换 IP")
    finally:
        await cache.aclose()

    print()
    print("应用内验证：触发一次行情请求后，检查 backend/logs/app.log 中的")
    print('  "代理出口已确认可用"（INFO）或 "代理请求成功"（DEBUG）。')
    return 0 if ok else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="检查出站代理是否生效")
    parser.add_argument(
        "--skip-direct", action="store_true", help="跳过直连对照，只测代理"
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(run(args.skip_direct)))


if __name__ == "__main__":
    main()
