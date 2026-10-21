"""东方财富全量 A 股列表：代码、名称。交易所由代码号段推导。"""

import asyncio
from collections.abc import Awaitable, Callable
from math import ceil

from app.core.logging import get_logger
from app.providers.base import (
    DataNotFound,
    ProviderSchemaDrift,
    ProviderUnavailable,
)
from app.providers.http import fetch
from app.providers.models import StockBasic
from app.providers.symbols import InvalidSymbolError, parse_symbol

logger = get_logger(__name__)

# 免费源会临时断开连接，逐次退避重试
_RETRY_DELAYS = (1.0, 3.0, 7.0)


class EastmoneyStockDirectory:
    name = "eastmoney"

    LIST_URL = "https://push2.eastmoney.com/api/qt/clist/get"
    # 沪市 A 股 / 深市 A 股 / 北交所
    MARKETS = "m:1+t:2,m:1+t:23,m:0+t:6,m:0+t:80,m:0+t:81+s:2048"
    FIELDS = "f12,f13,f14"
    PAGE_SIZE = 100

    def __init__(self, limiter: Callable[[], Awaitable[None]] | None = None) -> None:
        self._limiter = limiter

    async def list_all(self) -> list[StockBasic]:
        total, first_page = await self._fetch_page(1)
        if total <= 0:
            raise DataNotFound("东财股票列表为空")

        items = list(first_page)
        pages = ceil(total / self.PAGE_SIZE)
        for page in range(2, pages + 1):
            _, page_items = await self._fetch_page(page)
            items.extend(page_items)
        return self.normalize(items)

    async def _fetch_page(self, page: int) -> tuple[int, list[dict]]:
        last_error: Exception | None = None
        for delay in (0.0, *_RETRY_DELAYS):
            if delay:
                await asyncio.sleep(delay)
            if self._limiter is not None:
                await self._limiter()
            try:
                return await self._request_page(page)
            except ProviderUnavailable as exc:
                last_error = exc
                logger.warning("东财股票列表第 %s 页失败，准备重试: %s", page, exc)
        raise ProviderUnavailable(f"东财股票列表第 {page} 页多次失败") from last_error

    async def _request_page(self, page: int) -> tuple[int, list[dict]]:
        response = await fetch(
            self.LIST_URL,
            params={
                "pn": page,
                "pz": self.PAGE_SIZE,
                "po": 1,
                "np": 1,
                "fltt": 2,
                "invt": 2,
                "fid": "f12",
                "fs": self.MARKETS,
                "fields": self.FIELDS,
            },
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderSchemaDrift("东财股票列表返回非 JSON") from exc

        data = payload.get("data")
        if not isinstance(data, dict):
            raise ProviderSchemaDrift("东财股票列表缺少 data")
        total = data.get("total")
        if not isinstance(total, int):
            raise ProviderSchemaDrift("东财股票列表缺少 total")

        diff = data.get("diff") or []
        if isinstance(diff, dict):  # 东财偶尔以对象返回
            diff = list(diff.values())
        return total, diff

    @staticmethod
    def normalize(rows: list[dict]) -> list[StockBasic]:
        """按代码去重；非 A 股代码或空名称直接跳过。"""
        result: dict[str, StockBasic] = {}
        for row in rows:
            code = str(row.get("f12") or "").strip()
            name = str(row.get("f14") or "").strip()
            try:
                symbol = parse_symbol(code)
            except InvalidSymbolError:
                continue
            if not name:
                continue
            result[symbol.code] = StockBasic(
                code=symbol.code,
                name=name,
                exchange=symbol.exchange,
            )
        return list(result.values())
