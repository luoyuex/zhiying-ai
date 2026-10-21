"""新浪行情：hq.sinajs.cn 实时报价 + quotes.sina.cn K 线。"""

from app.providers.base import (
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

_SINA_REFERER = {"Referer": "https://finance.sina.com.cn/"}


class SinaProvider:
    name = "sina"

    QUOTE_URL = "https://hq.sinajs.cn/list={}"
    KLINE_URL = "https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData"

    # 新浪日线只支持不复权，分钟线为原生数据
    _KLINE_SCALES = {
        KlinePeriod.MIN5: 5,
        KlinePeriod.MIN15: 15,
        KlinePeriod.MIN30: 30,
        KlinePeriod.MIN60: 60,
        KlinePeriod.DAY: 240,
    }

    async def quote(self, symbol: StockSymbol) -> Quote:
        response = await fetch(self.QUOTE_URL.format(symbol.prefixed), headers=_SINA_REFERER)
        return self.parse_quote(symbol, response.content)

    @classmethod
    def parse_quote(cls, symbol: StockSymbol, content: bytes) -> Quote:
        text = content.decode("gbk", errors="replace")
        marker = f'var hq_str_{symbol.prefixed}="'
        start = text.find(marker)
        if start < 0:
            raise DataNotFound(f"新浪无 {symbol.code} 报价")
        start += len(marker)
        end = text.find('"', start)
        if end <= start:
            raise DataNotFound(f"新浪无 {symbol.code} 报价")

        fields = text[start:end].split(",")
        if len(fields) < 32 or not fields[0].strip():
            raise DataNotFound(f"新浪无 {symbol.code} 报价")

        price = safe_float(fields[3])
        pre_close = safe_float(fields[2])
        if price is None or price <= 0:
            price = pre_close
        if price is None or price <= 0:
            raise DataNotFound(f"新浪 {symbol.code} 停牌或无成交")

        fetched_at = parse_datetime(f"{fields[30]} {fields[31]}")
        change = price - pre_close if pre_close else None
        change_pct = change / pre_close * 100 if change is not None and pre_close else None

        return Quote(
            symbol=symbol.code,
            name=fields[0].strip(),
            price=price,
            open=safe_float(fields[1]),
            pre_close=pre_close,
            high=safe_float(fields[4]),
            low=safe_float(fields[5]),
            change=round(change, 4) if change is not None else None,
            change_pct=round(change_pct, 4) if change_pct is not None else None,
            volume=safe_float(fields[8]),
            amount=safe_float(fields[9]),
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
        scale = self._KLINE_SCALES.get(period)
        if scale is None or adjust is not Adjust.NONE:
            raise UnsupportedCapability(f"新浪不支持 {period.value}/{adjust.value} K 线")

        response = await fetch(
            self.KLINE_URL,
            params={
                "symbol": symbol.prefixed,
                "scale": scale,
                "ma": "no",
                "datalen": limit,
            },
            headers=_SINA_REFERER,
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderSchemaDrift("新浪 K 线返回非 JSON") from exc
        return self.parse_kline(symbol, payload, period, adjust, limit)

    @classmethod
    def parse_kline(
        cls,
        symbol: StockSymbol,
        payload: object,
        period: KlinePeriod,
        adjust: Adjust,
        limit: int,
    ) -> KlineSeries:
        if not isinstance(payload, list) or not payload:
            raise DataNotFound(f"新浪无 {symbol.code} K 线")

        bars: list[KlineBar] = []
        for row in payload[-limit:]:
            if not isinstance(row, dict):
                continue
            moment = parse_datetime(str(row.get("day", "")))
            open_ = safe_float(row.get("open"))
            high = safe_float(row.get("high"))
            low = safe_float(row.get("low"))
            close = safe_float(row.get("close"))
            volume = safe_float(row.get("volume"))
            if moment is None or None in (open_, high, low, close, volume):
                continue
            bars.append(
                KlineBar(
                    time=moment,
                    open=open_,
                    high=high,
                    low=low,
                    close=close,
                    volume=volume,
                )
            )

        if not bars:
            raise ProviderSchemaDrift(f"新浪 {symbol.code} K 线解析为空")

        return KlineSeries(
            symbol=symbol.code,
            period=period,
            adjust=adjust,
            bars=bars,
            source=cls.name,
            fetched_at=now_shanghai(),
        )
