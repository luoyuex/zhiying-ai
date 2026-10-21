"""东方财富行情：push2 报价 + push2his K 线。"""

from datetime import datetime, timedelta
from math import ceil

from app.providers.base import (
    TZ_SHANGHAI,
    DataNotFound,
    ProviderSchemaDrift,
    UnsupportedCapability,
    now_shanghai,
    parse_datetime,
    safe_float,
)
from app.providers.http import fetch
from app.providers.models import Adjust, KlineBar, KlinePeriod, KlineSeries, Quote
from app.providers.symbols import StockSymbol


class EastmoneyProvider:
    name = "eastmoney"

    QUOTE_URL = "https://push2.eastmoney.com/api/qt/stock/get"
    KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"

    QUOTE_FIELDS = (
        "f43,f44,f45,f46,f47,f48,f50,f51,f52,f57,f58,f59,f60,"
        "f86,f116,f117,f162,f167,f168,f169,f170"
    )
    KLINE_FIELDS1 = "f1,f2,f3,f4,f5,f6"
    KLINE_FIELDS2 = "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"

    _KLT = {
        KlinePeriod.MIN1: 1,
        KlinePeriod.MIN5: 5,
        KlinePeriod.MIN15: 15,
        KlinePeriod.MIN30: 30,
        KlinePeriod.MIN60: 60,
        KlinePeriod.DAY: 101,
        KlinePeriod.WEEK: 102,
        KlinePeriod.MONTH: 103,
    }
    _FQT = {Adjust.NONE: 0, Adjust.QFQ: 1, Adjust.HFQ: 2}
    _BARS_PER_DAY = {
        KlinePeriod.MIN1: 240,
        KlinePeriod.MIN5: 48,
        KlinePeriod.MIN15: 16,
        KlinePeriod.MIN30: 8,
        KlinePeriod.MIN60: 4,
    }

    async def quote(self, symbol: StockSymbol) -> Quote:
        response = await fetch(
            self.QUOTE_URL,
            params={"secid": symbol.secid, "fields": self.QUOTE_FIELDS},
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderSchemaDrift("东财报价返回非 JSON") from exc
        return self.parse_quote(symbol, payload)

    @classmethod
    def parse_quote(cls, symbol: StockSymbol, payload: dict) -> Quote:
        data = payload.get("data")
        if not isinstance(data, dict) or not data.get("f58"):
            raise DataNotFound(f"东财无 {symbol.code} 报价")

        decimals = cls._decimals(data)
        price = cls._scaled(data.get("f43"), decimals)
        pre_close = cls._scaled(data.get("f60"), decimals)
        if price is None or price <= 0:
            price = pre_close
        if price is None or price <= 0:
            raise DataNotFound(f"东财 {symbol.code} 停牌或无成交")

        timestamp = safe_float(data.get("f86"))
        fetched_at = now_shanghai()
        if timestamp and timestamp > 0:
            try:
                fetched_at = datetime.fromtimestamp(timestamp, tz=TZ_SHANGHAI)
            except (OverflowError, OSError, ValueError):
                pass

        volume_lots = safe_float(data.get("f47"))

        return Quote(
            symbol=symbol.code,
            name=str(data.get("f58")),
            price=price,
            open=cls._scaled(data.get("f46"), decimals),
            pre_close=pre_close,
            high=cls._scaled(data.get("f44"), decimals),
            low=cls._scaled(data.get("f45"), decimals),
            change=cls._scaled_ratio(data.get("f169")),
            change_pct=cls._scaled_ratio(data.get("f170")),
            volume=volume_lots * 100 if volume_lots is not None else None,
            amount=safe_float(data.get("f48")),
            turnover_pct=cls._scaled_ratio(data.get("f168")),
            pe=cls._scaled_ratio(data.get("f162")),
            pb=cls._scaled_ratio(data.get("f167")),
            total_market_cap=safe_float(data.get("f116")),
            float_market_cap=safe_float(data.get("f117")),
            limit_up=cls._scaled(data.get("f51"), decimals),
            limit_down=cls._scaled(data.get("f52"), decimals),
            source=cls.name,
            fetched_at=fetched_at,
        )

    async def kline(
        self,
        symbol: StockSymbol,
        period: KlinePeriod,
        adjust: Adjust,
        limit: int,
    ) -> KlineSeries:
        klt = self._KLT.get(period)
        if klt is None:
            raise UnsupportedCapability(f"东财不支持 {period.value} K 线")

        response = await fetch(
            self.KLINE_URL,
            params={
                "secid": symbol.secid,
                "klt": klt,
                "fqt": self._FQT[adjust],
                "beg": self._begin_date(period, limit),
                "end": "20500101",
                "fields1": self.KLINE_FIELDS1,
                "fields2": self.KLINE_FIELDS2,
            },
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderSchemaDrift("东财 K 线返回非 JSON") from exc
        return self.parse_kline(symbol, payload, period, adjust, limit)

    @classmethod
    def parse_kline(
        cls,
        symbol: StockSymbol,
        payload: dict,
        period: KlinePeriod,
        adjust: Adjust,
        limit: int,
    ) -> KlineSeries:
        data = payload.get("data")
        if not isinstance(data, dict):
            raise DataNotFound(f"东财无 {symbol.code} K 线")
        rows = data.get("klines")
        if not isinstance(rows, list) or not rows:
            raise DataNotFound(f"东财无 {symbol.code} {period.value} K 线")

        bars: list[KlineBar] = []
        for raw in rows[-limit:]:
            parts = str(raw).split(",")
            if len(parts) < 6:
                continue
            moment = parse_datetime(parts[0])
            open_ = safe_float(parts[1])
            close = safe_float(parts[2])
            high = safe_float(parts[3])
            low = safe_float(parts[4])
            volume_lots = safe_float(parts[5])
            if moment is None or None in (open_, close, high, low, volume_lots):
                continue
            bars.append(
                KlineBar(
                    time=moment,
                    open=open_,
                    high=high,
                    low=low,
                    close=close,
                    volume=volume_lots * 100,
                    amount=safe_float(parts[6]) if len(parts) > 6 else None,
                    turnover_pct=safe_float(parts[10]) if len(parts) > 10 else None,
                )
            )

        if not bars:
            raise ProviderSchemaDrift(f"东财 {symbol.code} K 线解析为空")

        return KlineSeries(
            symbol=symbol.code,
            period=period,
            adjust=adjust,
            bars=bars,
            source=cls.name,
            fetched_at=now_shanghai(),
        )

    @classmethod
    def _begin_date(cls, period: KlinePeriod, limit: int) -> str:
        bars_per_day = cls._BARS_PER_DAY.get(period)
        if bars_per_day:
            days = ceil(limit / bars_per_day) * 2 + 10
        elif period is KlinePeriod.DAY:
            days = limit * 2 + 15
        elif period is KlinePeriod.WEEK:
            days = limit * 9 + 45
        else:
            days = limit * 35 + 90
        days = min(days, 20000)
        return (now_shanghai() - timedelta(days=days)).strftime("%Y%m%d")

    @staticmethod
    def _decimals(data: dict) -> int:
        try:
            return int(data.get("f59") or 2)
        except (TypeError, ValueError):
            return 2

    @staticmethod
    def _scaled(value: object, decimals: int) -> float | None:
        number = safe_float(value)
        if number is None:
            return None
        return round(number / (10**decimals), decimals)

    @staticmethod
    def _scaled_ratio(value: object) -> float | None:
        number = safe_float(value)
        if number is None:
            return None
        return round(number / 100, 4)
