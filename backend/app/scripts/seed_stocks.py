"""全量 A 股种子：拉取东财列表 → 生成拼音 → 写入 stocks 表。

用法：
    uv run python -m app.scripts.seed_stocks            # 全量同步
    uv run python -m app.scripts.seed_stocks --dry-run  # 只拉取并抽样打印
"""

import argparse
import asyncio

from app.db.redis import close_redis, get_redis
from app.db.session import engine
from app.providers.resilience import TokenBucket
from app.providers.stock_directory import EastmoneyStockDirectory
from app.services.stock_directory_service import build_pinyin, sync_stocks


async def run(dry_run: bool) -> None:
    limiter = TokenBucket(get_redis(), rate=5.0, burst=10, name="eastmoney")
    directory = EastmoneyStockDirectory(limiter=limiter.acquire)

    items = await directory.list_all()
    print(f"拉取 A 股列表：{len(items)} 只")

    if dry_run:
        for item in items[:5]:
            print(item.code, item.name, item.exchange, build_pinyin(item.name))
    else:
        result = await sync_stocks(items)
        print(f"同步完成：{result['synced']} 条，停用 {result['deactivated']} 条")

    await close_redis()
    await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="同步全量 A 股基础信息")
    parser.add_argument("--dry-run", action="store_true", help="只拉取，不写库")
    args = parser.parse_args()
    asyncio.run(run(args.dry_run))


if __name__ == "__main__":
    main()
