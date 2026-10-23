"""资金流排行 Provider：东财区间排行（今日/3/5/10 日），新浪今日兜底。"""

import asyncio
from dataclasses import dataclass

from app.core.logging import get_logger
from app.providers.base import (
    DataNotFound,
    ProviderError,
    ProviderSchemaDrift,
    safe_float,
)
from app.providers.http import fetch, provider_slot
from app.providers.symbols import InvalidSymbolError, parse_symbol
from app.schemas.screener import FlowWindow, FundFlowRankItem

logger = get_logger(__name__)


@dataclass(frozen=True)
class FlowWindowSpec:
    label: str
    fid: str
    change_field: str
    main_net_field: str
    main_pct_field: str
    source: str


FLOW_WINDOWS: dict[str, FlowWindowSpec] = {
    "today": FlowWindowSpec("今日", "f62", "f3", "f62", "f184", "eastmoney_fundflow_today"),
    "3d": FlowWindowSpec("近3日", "f267", "f127", "f267", "f268", "eastmoney_fundflow_3d"),
    "5d": FlowWindowSpec("近5日", "f164", "f109", "f164", "f165", "eastmoney_fundflow_5d"),
    "10d": FlowWindowSpec("近10日", "f174", "f160", "f174", "f175", "eastmoney_fundflow_10d"),
}


def flow_window_label(window: FlowWindow) -> str:
    return FLOW_WINDOWS[window].label


def flow_window_source(window: FlowWindow) -> str:
    return FLOW_WINDOWS[window].source


class EastmoneyFundFlowRankProvider:
    """东财 push2 个股资金流排行，按所选区间主力净流入降序。"""

    name = "eastmoney_fundflow"
    # 编号镜像是东财前端实际使用的入口，比主站更稳；失败时切换备用编号
    HOSTS = ("29.push2.eastmoney.com", "1.push2.eastmoney.com")
    UT = "7eea3edcaed734bea9cbfc24409ed989"
    PAGE_SIZE = 100
    MAX_PAGES = 4
    # 沪深 A 股主板/创业板/科创板；北交所由筛选层排除
    FS = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23"

    async def _fetch_page(
        self,
        page: int,
        spec: FlowWindowSpec,
        fields: str,
    ) -> list:
        params = {
            "pn": page,
            "pz": self.PAGE_SIZE,
            "po": 1,
            "np": 1,
            "fltt": 2,
            "invt": 2,
            "fid": spec.fid,
            "fs": self.FS,
            "fields": fields,
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
                last_exc = ProviderSchemaDrift("东财资金流排行返回非 JSON")
                continue
            except Exception as exc:  # noqa: BLE001 - 换镜像重试一次
                last_exc = exc
                continue

            data = payload.get("data") if isinstance(payload, dict) else None
            rows = (data or {}).get("diff")
            if not isinstance(rows, list):
                last_exc = ProviderSchemaDrift("东财资金流排行格式异常")
                continue
            return rows
        raise last_exc or DataNotFound("东财资金流排行暂无数据")

    async def fetch(
        self,
        window: FlowWindow = "10d",
        limit: int = 400,
    ) -> list[FundFlowRankItem]:
        spec = FLOW_WINDOWS[window]
        fields = ",".join(
            dict.fromkeys(
                [
                    "f12",
                    "f14",
                    "f2",
                    "f6",
                    "f20",
                    "f124",
                    spec.change_field,
                    spec.main_net_field,
                    spec.main_pct_field,
                ]
            )
        )
        items: list[FundFlowRankItem] = []
        for page in range(1, self.MAX_PAGES + 1):
            try:
                rows = await self._fetch_page(page, spec, fields)
            except ProviderError as exc:
                if not items:
                    raise
                # 东财按突发请求限流：后续页断连时保留已拿到的候选
                logger.warning(
                    "东财资金流排行第 %d 页失败，使用已获取的 %d 条: %s",
                    page,
                    len(items),
                    exc,
                )
                break
            for row in rows:
                item = self.parse_row(row, window)
                if item is not None:
                    items.append(item)
            if len(rows) < self.PAGE_SIZE or len(items) >= limit:
                break
            await asyncio.sleep(0.3)

        if not items:
            raise DataNotFound("东财资金流排行暂无数据")
        return items[:limit]

    @staticmethod
    def parse_row(
        row: object,
        window: FlowWindow = "10d",
    ) -> FundFlowRankItem | None:
        if not isinstance(row, dict):
            return None
        spec = FLOW_WINDOWS[window]
        raw_symbol = str(row.get("f12") or "").strip()
        try:
            symbol = parse_symbol(raw_symbol)
        except InvalidSymbolError:
            return None

        change = safe_float(row.get(spec.change_field))
        main_net_pct = safe_float(row.get(spec.main_pct_field))
        main_net = safe_float(row.get(spec.main_net_field))
        return FundFlowRankItem(
            symbol=symbol.code,
            name=str(row.get("f14") or symbol.code).strip(),
            price=safe_float(row.get("f2")),
            change_pct=round(change, 2) if change is not None else None,
            main_net=main_net or 0.0,
            main_net_pct=round(main_net_pct, 2) if main_net_pct is not None else None,
            amount=safe_float(row.get("f6")),
            market_cap=safe_float(row.get("f20")),
        )


class SinaFundFlowRankProvider:
    """新浪今日超大单净流入排行，仅作东财今日榜失败时的兜底。"""

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
