"""独立代理连通性测试：只依赖 httpx，不读 .env / 不连数据库。

用法（在 backend 目录）：
    python scripts/test_proxy.py "http://user:pass@host:port"
    python scripts/test_proxy.py "http://host:port" --skip-direct
    python scripts/test_proxy.py "socks5://host:port"

退出码：0 = 目标站点可达；1 = 代理或目标不可达。
"""

import argparse
import asyncio
import re
import sys
import time
from urllib.parse import urlsplit

import httpx

IP_URL = "https://myip.ipip.net"
DEFAULT_TARGET = (
    "https://push2.eastmoney.com/api/qt/stock/get"
    "?secid=1.600519&fields=f43,f57,f58"
)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
)
_IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


def normalize_proxy(raw: str) -> str:
    return raw if "://" in raw else f"http://{raw}"


def mask_proxy(raw: str) -> str:
    try:
        parts = urlsplit(raw)
        if not parts.hostname:
            return "<invalid>"
        port = f":{parts.port}" if parts.port else ""
        return f"{parts.scheme}://{parts.hostname}{port}"
    except ValueError:
        return "<invalid>"


def make_client(proxy: str | None, timeout: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        proxy=proxy,
        timeout=httpx.Timeout(timeout, connect=min(5.0, timeout)),
        headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
        follow_redirects=True,
        trust_env=False,
    )


def describe_error(exc: Exception) -> str:
    if isinstance(exc, httpx.ProxyError):
        return (
            f"代理认证/隧道失败（{exc}）\n"
            "    检查：代理用户名密码；密码里的 @ : / # 是否 URL 编码；"
            "或服务商要求 IP 白名单"
        )
    if isinstance(exc, httpx.ConnectError):
        return (
            f"连不上代理（{exc}）\n"
            "    检查：host/port、本机网络/防火墙、服务商白名单是否含本机公网 IP"
        )
    if isinstance(exc, httpx.TimeoutException):
        return f"超时（{exc}）\n    代理或目标站响应太慢，换端口/节点再试"
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code}（目标站返回错误）"
    return f"{type(exc).__name__}: {exc}"


async def check_ip(client: httpx.AsyncClient) -> str | None:
    started = time.perf_counter()
    try:
        response = await client.get(IP_URL)
        response.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        print(f"  查出口 IP 失败：{describe_error(exc)}")
        return None

    text = " ".join(response.text.split())
    match = _IPV4_RE.search(text)
    ip = match.group(0) if match else text[:60]
    elapsed = (time.perf_counter() - started) * 1000
    print(f"  出口 IP：{ip}（{elapsed:.0f}ms）")
    if text:
        print(f"  原始返回：{text[:100]}")
    return ip


async def check_target(client: httpx.AsyncClient, target: str) -> bool:
    started = time.perf_counter()
    try:
        response = await client.get(target)
        response.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        print(f"  目标站失败：{describe_error(exc)}")
        return False

    detail = ""
    if "eastmoney.com" in target:
        try:
            data = response.json().get("data") or {}
            detail = f" {data.get('f58')} f43={data.get('f43')}"
        except Exception:  # noqa: BLE001
            pass
    elapsed = (time.perf_counter() - started) * 1000
    print(
        f"  目标站：HTTP {response.status_code}{detail} "
        f"{len(response.content)}B（{elapsed:.0f}ms）"
    )
    return True


async def run(args: argparse.Namespace) -> int:
    proxy = normalize_proxy(args.proxy)
    print(f"代理入口：{mask_proxy(proxy)}")

    direct_ip: str | None = None
    if not args.skip_direct:
        print("直连：")
        direct_client = make_client(None, args.timeout)
        try:
            direct_ip = await check_ip(direct_client)
        finally:
            await direct_client.aclose()

    print("代理：")
    try:
        proxy_client = make_client(proxy, args.timeout)
    except Exception as exc:  # noqa: BLE001
        print(f"  创建代理客户端失败：{type(exc).__name__}: {exc}")
        print('  socks5 入口需要先安装：uv add "httpx[socks]"')
        return 1

    try:
        proxy_ip = await check_ip(proxy_client)
        target_ok = await check_target(proxy_client, args.target)
    finally:
        await proxy_client.aclose()

    print()
    if direct_ip and proxy_ip:
        if direct_ip == proxy_ip:
            print("注意：代理出口 IP 与直连相同，代理可能未生效或服务商未轮换 IP。")
        else:
            print(f"出口 IP 已变化：{direct_ip} -> {proxy_ip}，代理生效。")
    if target_ok:
        print("结论：代理可用，目标站点可访问。")
        return 0
    print("结论：代理不可用或目标站点不可达，看上面的失败原因。")
    return 1


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:  # noqa: BLE001
                pass

    parser = argparse.ArgumentParser(description="测试代理是否能连通")
    parser.add_argument(
        "proxy",
        help="代理地址，例如 http://user:pass@host:port 或 socks5://host:port",
    )
    parser.add_argument(
        "--target",
        default=DEFAULT_TARGET,
        help="要测试的目标 URL（默认东财贵州茅台行情）",
    )
    parser.add_argument("--timeout", type=float, default=10.0, help="超时秒数")
    parser.add_argument(
        "--skip-direct", action="store_true", help="跳过直连对照，只测代理"
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
