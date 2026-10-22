"""东方财富业绩报表：全市场净利润同比增速（用于低价擒牛等基本面选股）。"""

from app.core.logging import get_logger
from app.providers.base import (
    DataNotFound,
    ProviderSchemaDrift,
    safe_float,
)
from app.providers.http import fetch
from app.providers.symbols import InvalidSymbolError, parse_symbol
from app.schemas.screener import PerformanceRow

logger = get_logger(__name__)


class EastmoneyPerformanceProvider:
    name = "eastmoney_performance"
    URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
    REPORT_NAME = "RPT_LICO_FN_CPD"
    PAGE_SIZE = 500

    async def fetch(
        self,
        min_profit_growth: float,
        min_revenue_growth: float = 0.0,
    ) -> tuple[str, list[PerformanceRow]]:
        """返回（最新报告期, 满足净利/营收增速阈值且为 A 股的记录）。"""
        report_date = await self.latest_report_date()
        filter_text = (
            f"(REPORTDATE='{report_date}')"
            f"(SJLTZ>={min_profit_growth})"
        )
        if min_revenue_growth > 0:
            filter_text += f"(YSTZ>={min_revenue_growth})"
        params = {
            "reportName": self.REPORT_NAME,
            "columns": (
                "SECURITY_CODE,SECURITY_NAME_ABBR,REPORTDATE,YSTZ,SJLTZ"
            ),
            "pageNumber": 1,
            "pageSize": self.PAGE_SIZE,
            "sortColumns": "SJLTZ",
            "sortTypes": -1,
            "filter": filter_text,
            "source": "WEB",
            "client": "WEB",
        }
        response = await fetch(self.URL, params=params)
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderSchemaDrift("东财业绩报表返回非 JSON") from exc
        rows = self.parse_rows(payload)
        if not rows:
            raise DataNotFound(f"东财业绩报表暂无 {report_date} 数据")
        return report_date, rows

    async def latest_report_date(self) -> str:
        params = {
            "reportName": self.REPORT_NAME,
            "columns": "REPORTDATE",
            "pageNumber": 1,
            "pageSize": 1,
            "sortColumns": "REPORTDATE",
            "sortTypes": -1,
            "source": "WEB",
            "client": "WEB",
        }
        response = await fetch(self.URL, params=params)
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderSchemaDrift("东财业绩报表返回非 JSON") from exc
        rows = self._result_rows(payload)
        if not rows:
            raise DataNotFound("东财业绩报表无报告期")
        return str(rows[0].get("REPORTDATE") or "")[:10]

    @classmethod
    def parse_rows(cls, payload: dict) -> list[PerformanceRow]:
        items: list[PerformanceRow] = []
        for raw in cls._result_rows(payload):
            code = str(raw.get("SECURITY_CODE") or "").strip()
            try:
                parse_symbol(code)
            except InvalidSymbolError:
                continue
            name = str(raw.get("SECURITY_NAME_ABBR") or code).strip()
            items.append(
                PerformanceRow(
                    symbol=code,
                    name=name,
                    report_date=str(raw.get("REPORTDATE") or "")[:10],
                    profit_growth=safe_float(raw.get("SJLTZ")),
                    revenue_growth=safe_float(raw.get("YSTZ")),
                )
            )
        return items

    @staticmethod
    def _result_rows(payload: dict) -> list[dict]:
        result = payload.get("result")
        if not isinstance(result, dict):
            raise ProviderSchemaDrift("东财业绩报表缺少 result")
        rows = result.get("data") or []
        if not isinstance(rows, list):
            raise ProviderSchemaDrift("东财业绩报表 data 格式异常")
        return [row for row in rows if isinstance(row, dict)]
