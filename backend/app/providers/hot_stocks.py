"""热门股票 Provider：按当日成交额排序的活跃榜。

腾讯排行接口作为主源（与行情同源、直连可用），东财 clist 作为兜底；
只保留沪深 A 股，剔除 ST 与退市整理标的。
"""

from app.core.logging import get_logger
from app.providers.base import DataNotFound, ProviderSchemaDrift, safe_float
from app.providers.http import fetch, provider_slot
from app.providers.symbols import InvalidSymbolError, parse_symbol
from app.schemas.stock import HotStockItem

logger = get_logger(__name__)


def _should_skip(name: str) -> bool:
    upper = name.upper()
    return not name or "ST" in upper or "退" in name


class TencentHotStocksProvider:
    """腾讯自选股排行：board_code=aStock，按成交额降序。"""

    name = "tencent_hot"
    URL = "https://proxy.finance.qq.com/cgi/cgi-bin/rank/hs/getBoardRankList"

    async def fetch(self, limit: int = 8) -> list[HotStockItem]:
        # 多取一些用于剔除 ST / 非 A 股标的
        count = max(20, limit * 3)
        async with provider_slot():
            response = await fetch(
                self.URL,
                params={
                    "board_code": "aStock",
                    "sort_type": "turnover",
                    "direct": "down",
                    "offset": 0,
                    "count": count,
                },
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderSchemaDrift("腾讯活跃榜返回非 JSON") from exc
        if not isinstance(payload, dict) or payload.get("code") != 0:
            raise ProviderSchemaDrift("腾讯活跃榜返回异常")
        rows = (payload.get("data") or {}).get("rank_list")
        if not isinstance(rows, list):
            raise ProviderSchemaDrift("腾讯活跃榜格式异常")

        items = [item for item in (self.parse_row(row) for row in rows) if item is not None]
        if not items:
            raise DataNotFound("腾讯活跃榜暂无数据")
        return items[:limit]

    @staticmethod
    def parse_row(row: object) -> HotStockItem | None:
        if not isinstance(row, dict):
            return None
        name = str(row.get("name") or "").strip()
        if _should_skip(name):
            return None
        stock_type = str(row.get("stock_type") or "")
        if stock_type and not stock_type.startswith("GP-A"):
            return None
        raw = str(row.get("code") or "").strip().lower()
        if not raw.startswith(("sh", "sz")):
            return None
        try:
            symbol = parse_symbol(raw)
        except InvalidSymbolError:
            return None

        change = safe_float(row.get("zdf"))
        return HotStockItem(
            code=symbol.code,
            name=name,
            price=safe_float(row.get("zxj")),
            change_pct=round(change, 2) if change is not None else None,
        )


class EastmoneyHotStocksProvider:
    """东财 push2 成交额榜：腾讯不可用时兜底，镜像与资金流排行一致。"""

    name = "eastmoney_hot"
    HOSTS = ("29.push2.eastmoney.com", "1.push2.eastmoney.com")
    UT = "7eea3edcaed734bea9cbfc24409ed989"
    # 沪深主板 / 创业板 / 科创板；北交所不入榜
    FS = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23"
    FIELDS = "f12,f14,f2,f3"
    PAGE_SIZE = 40

    async def fetch(self, limit: int = 8) -> list[HotStockItem]:
        params = {
            "pn": 1,
            "pz": self.PAGE_SIZE,
            "po": 1,
            "np": 1,
            "fltt": 2,
            "invt": 2,
            "fid": "f6",
            "fs": self.FS,
            "fields": self.FIELDS,
            "ut": self.UT,
        }
        last_exc: Exception | None = None
        for host in self.HOSTS:
            try:
                async with provider_slot():
                    response = await fetch(
                        f"https://{host}/api/qt/clist/get",
                        params=params,
                    )
                payload = response.json()
            except ValueError:
                last_exc = ProviderSchemaDrift("东财活跃榜返回非 JSON")
                continue
            except Exception as exc:  # noqa: BLE001 - 换镜像重试一次
                last_exc = exc
                continue

            data = payload.get("data") if isinstance(payload, dict) else None
            rows = (data or {}).get("diff")
            if not isinstance(rows, list):
                last_exc = ProviderSchemaDrift("东财活跃榜格式异常")
                continue

            items = [item for item in (self.parse_row(row) for row in rows) if item is not None]
            if not items:
                last_exc = DataNotFound("东财活跃榜暂无数据")
                continue
            return items[:limit]

        raise last_exc or DataNotFound("东财活跃榜暂无数据")

    @staticmethod
    def parse_row(row: object) -> HotStockItem | None:
        if not isinstance(row, dict):
            return None
        name = str(row.get("f14") or "").strip()
        if _should_skip(name):
            return None
        try:
            symbol = parse_symbol(str(row.get("f12") or "").strip())
        except InvalidSymbolError:
            return None

        change = safe_float(row.get("f3"))
        return HotStockItem(
            code=symbol.code,
            name=name,
            price=safe_float(row.get("f2")),
            change_pct=round(change, 2) if change is not None else None,
        )
