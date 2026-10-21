"""东方财富财务指标（F10）Provider。"""

from app.providers.base import DataNotFound, ProviderSchemaDrift, now_shanghai, safe_float
from app.providers.http import fetch
from app.providers.models import Quote
from app.providers.symbols import StockSymbol
from app.schemas.company import FinancialData, FinancialMetric


class EastmoneyFinancialProvider:
    name = "eastmoney_finance"
    URL = "https://datacenter.eastmoney.com/securities/api/data/v1/get"
    _HEADERS = {"Referer": "https://emweb.securities.eastmoney.com/"}

    async def fetch(self, symbol: StockSymbol) -> FinancialData:
        params = {
            "reportName": "RPT_F10_FINANCE_MAINFINADATA",
            "columns": "ALL",
            "filter": f'(SECUCODE="{symbol.ts_code}")',
            "pageNumber": 1,
            "pageSize": 8,
            "sortTypes": -1,
            "sortColumns": "REPORT_DATE",
        }
        response = await fetch(self.URL, params=params, headers=self._HEADERS)
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderSchemaDrift("东财财务返回非 JSON") from exc
        result = payload.get("result") or {}
        rows = result.get("data") or []
        if not rows:
            raise DataNotFound(f"东财无 {symbol.code} 财务数据")

        periods: list[FinancialMetric] = []
        for row in rows[:6]:
            if not isinstance(row, dict):
                continue
            report_date = str(row.get("REPORT_DATE") or "")[:10]
            if not report_date:
                continue
            periods.append(
                FinancialMetric(
                    report_date=report_date,
                    report_name=str(row.get("REPORT_DATE_NAME") or ""),
                    revenue=safe_float(row.get("TOTALOPERATEREVE")),
                    revenue_growth_pct=safe_float(row.get("TOTALOPERATEREVETZ")),
                    net_profit=safe_float(row.get("PARENTNETPROFIT")),
                    profit_growth_pct=safe_float(row.get("PARENTNETPROFITTZ")),
                    roe=safe_float(row.get("ROEJQ")),
                    gross_margin_pct=safe_float(row.get("XSMLL")),
                    net_margin_pct=safe_float(row.get("XSJLL")),
                    debt_ratio_pct=safe_float(row.get("ZCFZL")),
                    current_ratio=safe_float(row.get("LD")),
                    eps=safe_float(row.get("EPSJB")),
                    bps=safe_float(row.get("BPS")),
                )
            )
        if not periods:
            raise ProviderSchemaDrift(f"东财 {symbol.code} 财务字段解析为空")

        return FinancialData(
            symbol=symbol.code,
            name=str(rows[0].get("SECURITY_NAME_ABBR") or ""),
            periods=periods,
            fetched_at=now_shanghai(),
        )


async def get_financial_data(redis, quote: Quote) -> FinancialData | None:
    from app.core.logging import get_logger
    from app.providers.symbols import parse_symbol

    logger = get_logger(__name__)
    try:
        symbol = parse_symbol(quote.symbol)
    except ValueError:
        return None

    key = f"mkt:fin:{symbol.code}"
    try:
        cached = await redis.get(key)
        if cached:
            try:
                return FinancialData.model_validate_json(cached)
            except ValueError:
                logger.warning("财务缓存内容损坏 %s", symbol.code)
    except Exception as exc:  # noqa: BLE001
        logger.warning("读取财务缓存失败: %s", exc)

    try:
        data = await EastmoneyFinancialProvider().fetch(symbol)
    except Exception as exc:  # noqa: BLE001
        logger.warning("获取财务数据失败 %s: %s", symbol.code, exc)
        return None

    try:
        await redis.set(key, data.model_dump_json(), ex=43200)
    except Exception as exc:  # noqa: BLE001
        logger.warning("写入财务缓存失败: %s", exc)
    return data
