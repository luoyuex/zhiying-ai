"""腾讯行情：qt.gtimg.cn 实时报价 + web.ifzq.gtimg.cn K 线。"""

from datetime import datetime

from app.providers.base import (
    TZ_SHANGHAI,
    DataNotFound,
    ProviderSchemaDrift,
    UnsupportedCapability,
    now_shanghai,
    safe_float,
)
from app.providers.http import fetch
from app.providers.models import Adjust, KlineBar, KlinePeriod, KlineSeries, Quote
from app.providers.symbols import StockSymbol


class TencentProvider:
    name = "tencent"

    QUOTE_URL = "https://qt.gtimg.cn/q={}"
    KLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"

    _KLINE_PERIODS = {KlinePeriod.DAY: "day", KlinePeriod.WEEK: "week", KlinePeriod.MONTH: "month"}

    async def quote(self, symbol: StockSymbol) -> Quote:
        response = await fetch(self.QUOTE_URL.format(symbol.prefixed))
        return self.parse_quote(symbol, response.content)

    @classmethod
    def parse_quote(cls, symbol: StockSymbol, content: bytes) -> Quote:
        text = content.decode("gbk", errors="replace")
        marker = f'v_{symbol.prefixed}="'
        start = text.find(marker)
        if start < 0:
            raise DataNotFound(f"腾讯无 {symbol.code} 报价")
        start += len(marker)
        end = text.find('"', start)
        if end <= start:
            raise DataNotFound(f"腾讯无 {symbol.code} 报价")

        fields = text[start:end].split("~")
        if len(fields) < 50 or not fields[1].strip():
            raise DataNotFound(f"腾讯无 {symbol.code} 报价")

        price = safe_float(fields[3])
        pre_close = safe_float(fields[4])
        if price is None or price <= 0:
            price = pre_close
        if price is None or price <= 0:
            raise DataNotFound(f"腾讯 {symbol.code} 停牌或无成交")

        fetched_at = cls._parse_timestamp(fields[30]) if len(fields) > 30 else None
        volume_lots = safe_float(fields[6])
        amount = cls._parse_amount(fields)

        return Quote(
            symbol=symbol.code,
            name=fields[1].strip(),
            price=price,
            open=safe_float(fields[5]),
            pre_close=pre_close,
            high=safe_float(fields[33]),
            low=safe_float(fields[34]),
            change=safe_float(fields[31]),
            change_pct=safe_float(fields[32]),
            volume=volume_lots * 100 if volume_lots is not None else None,
            amount=amount,
            turnover_pct=safe_float(fields[38]) if len(fields) > 38 else None,
            pe=safe_float(fields[39]) if len(fields) > 39 else None,
            pb=safe_float(fields[46]) if len(fields) > 46 else None,
            total_market_cap=cls._scale_yi(fields[45]) if len(fields) > 45 else None,
            float_market_cap=cls._scale_yi(fields[44]) if len(fields) > 44 else None,
            limit_up=safe_float(fields[47]) if len(fields) > 47 else None,
            limit_down=safe_float(fields[48]) if len(fields) > 48 else None,
            source=cls.name,
            fetched_at=fetched_at or now_shanghai(),
        )

    async def kline(
        self,
        symbol: StockSymbol,
        period: KlinePeriod,
        adjust: Adjust,
        limit: int,
    ) -> KlineSeries:
        tencent_period = self._KLINE_PERIODS.get(period)
        if tencent_period is None:
            raise UnsupportedCapability(f"腾讯不支持 {period.value} K 线")

        adjust_param = "" if adjust is Adjust.NONE else adjust.value
        param = f"{symbol.prefixed},{tencent_period},,,{limit},{adjust_param}"
        response = await fetch(self.KLINE_URL, params={"param": param})
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderSchemaDrift("腾讯 K 线返回非 JSON") from exc
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
        if payload.get("code") not in (0, "0"):
            raise ProviderSchemaDrift(f"腾讯 K 线返回 code={payload.get('code')}")

        node = (payload.get("data") or {}).get(symbol.prefixed)
        if not isinstance(node, dict):
            raise DataNotFound(f"腾讯无 {symbol.code} K 线")

        prefix = "" if adjust is Adjust.NONE else adjust.value
        rows = node.get(f"{prefix}{period.value}")
        if not rows:
            rows = node.get(period.value)
        if not isinstance(rows, list) or not rows:
            raise DataNotFound(f"腾讯无 {symbol.code} {period.value} K 线")

        bars: list[KlineBar] = []
        for row in rows[-limit:]:
            if not isinstance(row, list) or len(row) < 6:
                continue
            moment = cls._parse_day(row[0])
            values = [safe_float(item) for item in row[1:6]]
            if moment is None or any(value is None for value in values):
                continue
            open_, close, high, low, volume_lots = values
            bars.append(
                KlineBar(
                    time=moment,
                    open=open_,
                    high=high,
                    low=low,
                    close=close,
                    volume=volume_lots * 100,
                )
            )

        if not bars:
            raise ProviderSchemaDrift(f"腾讯 {symbol.code} K 线解析为空")

        return KlineSeries(
            symbol=symbol.code,
            period=period,
            adjust=adjust,
            bars=bars,
            source=cls.name,
            fetched_at=now_shanghai(),
        )

    @staticmethod
    def _parse_timestamp(raw: str) -> datetime | None:
        try:
            return datetime.strptime(raw, "%Y%m%d%H%M%S").replace(tzinfo=TZ_SHANGHAI)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_day(raw: str) -> datetime | None:
        try:
            return datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=TZ_SHANGHAI)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_amount(fields: list[str]) -> float | None:
        if len(fields) > 35:
            parts = fields[35].split("/")
            if len(parts) >= 3:
                amount = safe_float(parts[2])
                if amount is not None:
                    return amount
        # 字段 37 单位是万元
        amount_wan = safe_float(fields[37]) if len(fields) > 37 else None
        return amount_wan * 10000 if amount_wan is not None else None

    @staticmethod
    def _scale_yi(raw: str) -> float | None:
        value = safe_float(raw)
        return value * 1e8 if value is not None else None
