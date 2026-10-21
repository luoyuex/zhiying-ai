"""检查元宝搜索配置；加 --live 时发起一次真实 SearchPro 请求（会计费）。"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.config import settings  # noqa: E402
from app.services.web_search_service import YuanbaoSearchClient  # noqa: E402

DEFAULT_QUERY = "贵州茅台 600519 最新公告"


def print_config() -> str:
    key = settings.wsa_api_key.strip()
    if settings.wsa_use_official_api:
        mode = "official"
        mode_text = "官方 TC3（WSA_SECRET_ID + WSA_SECRET_KEY）"
    elif key:
        mode = "bearer"
        mode_text = "服务 API KEY（Bearer）"
    else:
        mode = "none"
        mode_text = "未配置"

    print(f"配置状态：{mode_text}")
    print(f"Host：{settings.wsa_search_host}")
    print(f"Version：{settings.wsa_search_version}")
    print(f"Freshness：{settings.wsa_search_freshness or '不限'}")
    print(f"每次搜索条数：{settings.wsa_search_count}，返回上限：{settings.wsa_search_top_n}")

    if mode == "none":
        print("提示：需要 SecretId/SecretKey，或 sk- 开头的服务 API KEY。")
    elif mode == "bearer" and key.upper().startswith("AKID"):
        print("提示：WSA_API_KEY 看起来是 SecretId；应填 WSA_SECRET_ID + WSA_SECRET_KEY。")
    return mode


async def run_live(query: str) -> int:
    result = await YuanbaoSearchClient().search(query)
    print("\n=== 真实搜索结果 ===")
    print(f"success={result.success} version={result.version or '-'} pages={len(result.pages)}")
    if result.error:
        print(f"error={result.error}")
    for index, page in enumerate(result.pages[:5], 1):
        meta = " | ".join(part for part in (page.site, page.date) if part)
        print(f"{index}. {page.title}")
        if meta:
            print(f"   {meta}")
        print(f"   {page.url}")
    return 0 if result.success else 1


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="检查腾讯元宝 SearchPro 接入")
    parser.add_argument("--live", action="store_true", help="发起一次真实搜索（会计费）")
    parser.add_argument("--query", default=DEFAULT_QUERY, help="真实搜索使用的 Query")
    args = parser.parse_args()

    mode = print_config()
    if mode == "none":
        return 2
    if not args.live:
        print("\n仅检查了配置。加 --live 可验证真实连通性（会消耗一次调用）。")
        return 0
    return asyncio.run(run_live(args.query))


if __name__ == "__main__":
    raise SystemExit(main())
