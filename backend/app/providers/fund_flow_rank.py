"""新浪个股资金流排行：按超大单净流入排序，用于主力选股。

东方财富 push2 在部分网络环境会被限流，这里改用新浪公开接口；
字段口径：r0_net 为超大单净额，r0_ratio 为超大单净占比，changeratio 为涨跌幅小数。
"""

from app.core.logging import get_logger
from app.providers.base import (
    DataNotFound,
    ProviderSchemaDrift,
    safe_float,
)
from app.providers.http import fetch, provider_slot
from app.providers.symbols import InvalidSymbolError, parse_symbol
from app.schemas.screener import FundFlowRankItem

logger = get_logger(__name__)


class SinaFundFlowRankProvider:
    name = "sina_fundflow"
    URL = (
        "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
        "MoneyFlow.ssl_bkzj_ssggzj"
    )
    PAGE_SIZE = 100
    MAX_PAGES = 5

    async def fetch(self, limit: int = 300) -> list[FundFlowRankItem]:
        items: list[FundFlowRankItem] = []
        for page in range(1, self.MAX_PAGES + 1):
            async with provider_slot():
                response = await fetch(
                    self.URL,
                    params={
                        "page": page,
                        "num": self.PAGE_SIZE,
                        "sort": "r0_net",
                        "asc": 0,
                        "bankuai": "",
                        "shangzhang": "",
                    },
                )
            try:
                payload = response.json()
            except ValueError as exc:
                raise ProviderSchemaDrift("新浪资金流排行返回非 JSON") from exc
            if not isinstance(payload, list):
                raise ProviderSchemaDrift("新浪资金流排行格式异常")

            for row in payload:
                item = self.parse_row(row)
                if item is not None:
                    items.append(item)
            if len(payload) < self.PAGE_SIZE or len(items) >= limit:
                break

        if not items:
            raise DataNotFound("新浪资金流排行暂无数据")
        return items[:limit]

    @staticmethod
    def parse_row(row: object) -> FundFlowRankItem | None:
        if not isinstance(row, dict):
            return None
        raw_symbol = str(row.get("symbol") or "").strip()
        try:
            symbol = parse_symbol(raw_symbol)
        except InvalidSymbolError:
            return None  # ETF / 基金 / 债券等非 A 股标的
        if raw_symbol[:2].lower() not in {"sh", "sz", "bj"}:
            return None

        change = safe_float(row.get("changeratio"))
        main_net_pct = safe_float(row.get("r0_ratio"))
        main_net = safe_float(row.get("r0_net"))
        return FundFlowRankItem(
            symbol=symbol.code,
            name=str(row.get("name") or symbol.code).strip(),
            price=safe_float(row.get("trade")),
            change_pct=round(change * 100, 2) if change is not None else None,
            main_net=main_net or 0.0,
            main_net_pct=round(main_net_pct * 100, 2) if main_net_pct is not None else None,
            amount=safe_float(row.get("amount")),
        )
