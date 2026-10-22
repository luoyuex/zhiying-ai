"""个股资金流 Provider：东财为主，新浪为降级备用。

东财会按 IP 临时断开连接（Server disconnected），此时改用新浪资金流；
新浪只提供净流入、超大单与净占比，其余分档留空。
"""

from app.providers.base import DataNotFound, ProviderSchemaDrift, now_shanghai, safe_float
from app.providers.http import fetch
from app.providers.symbols import StockSymbol
from app.schemas.company import FundFlowData, FundFlowDay


class EastmoneyFundFlowProvider:
    name = "eastmoney_fundflow"
    URL = "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get"

    async def fetch(self, symbol: StockSymbol) -> FundFlowData:
        params = {
            "secid": symbol.secid,
            "fields1": "f1,f2,f3,f7",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63",
        }
        response = await fetch(self.URL, params=params)
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderSchemaDrift("东财资金流返回非 JSON") from exc
        data = payload.get("data") or {}
        rows = data.get("klines") or []
        if not rows:
            raise DataNotFound(f"东财无 {symbol.code} 资金流数据")

        days: list[FundFlowDay] = []
        for raw in rows[-30:]:
            parts = str(raw).split(",")
            if len(parts) < 13:
                continue
            days.append(
                FundFlowDay(
                    date=parts[0],
                    main_net=safe_float(parts[1]),
                    small_net=safe_float(parts[2]),
                    medium_net=safe_float(parts[3]),
                    large_net=safe_float(parts[4]),
                    super_large_net=safe_float(parts[5]),
                    main_pct=safe_float(parts[6]),
                    close=safe_float(parts[11]),
                    change_pct=safe_float(parts[12]),
                )
            )
        if not days:
            raise ProviderSchemaDrift(f"东财 {symbol.code} 资金流解析为空")

        return FundFlowData(
            symbol=symbol.code,
            days=days,
            fetched_at=now_shanghai(),
        )


class SinaFundFlowProvider:
    name = "sina_fundflow"
    URL = (
        "https://vip.stock.finance.sina.com.cn/quotes_service/"
        "api/json_v2.php/MoneyFlow.ssl_qsfx_zjlrqs"
    )
    _HEADERS = {"Referer": "https://finance.sina.com.cn/"}

    async def fetch(self, symbol: StockSymbol) -> FundFlowData:
        params = {
            "page": 1,
            "num": 30,
            "sort": "opendate",
            "asc": 0,
            "daima": symbol.prefixed,
        }
        response = await fetch(self.URL, params=params, headers=self._HEADERS)
        try:
            rows = response.json()
        except ValueError as exc:
            raise ProviderSchemaDrift("新浪资金流返回非 JSON") from exc
        if not isinstance(rows, list) or not rows:
            raise DataNotFound(f"新浪无 {symbol.code} 资金流数据")

        days = self.parse(rows)
        if not days:
            raise ProviderSchemaDrift(f"新浪 {symbol.code} 资金流解析为空")

        return FundFlowData(
            symbol=symbol.code,
            days=days,
            source=self.name,
            fetched_at=now_shanghai(),
        )

    @staticmethod
    def parse(rows: list) -> list[FundFlowDay]:
        days: list[FundFlowDay] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            date = str(row.get("opendate") or "").strip()
            if not date:
                continue
            net = safe_float(row.get("netamount"))
            ratio = safe_float(row.get("ratioamount"))
            change = safe_float(row.get("changeratio"))
            days.append(
                FundFlowDay(
                    date=date,
                    main_net=net,
                    super_large_net=safe_float(row.get("r0_net")),
                    main_pct=ratio * 100 if ratio is not None else None,
                    close=safe_float(row.get("trade")),
                    change_pct=change * 100 if change is not None else None,
                )
            )
        # 新浪按日期倒序返回，统一为升序，和东财保持一致
        days.sort(key=lambda item: item.date)
        return days[-30:]


async def get_fund_flow(redis, symbol_text: str) -> FundFlowData | None:
    from app.core.logging import get_logger
    from app.providers.symbols import parse_symbol

    logger = get_logger(__name__)
    try:
        symbol = parse_symbol(symbol_text)
    except ValueError:
        return None

    key = f"mkt:fundflow:{symbol.code}"
    try:
        cached = await redis.get(key)
        if cached:
            try:
                return FundFlowData.model_validate_json(cached)
            except ValueError:
                logger.warning("资金流缓存内容损坏 %s", symbol.code)
    except Exception as exc:  # noqa: BLE001
        logger.warning("读取资金流缓存失败: %s", exc)

    data: FundFlowData | None = None
    for provider in (EastmoneyFundFlowProvider(), SinaFundFlowProvider()):
        try:
            data = await provider.fetch(symbol)
            break
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "获取资金流失败 %s（%s）: %s", symbol.code, provider.name, exc
            )
    if data is None:
        return None

    try:
        await redis.set(key, data.model_dump_json(), ex=300)
    except Exception as exc:  # noqa: BLE001
        logger.warning("写入资金流缓存失败: %s", exc)
    return data
