"""低估值选股数据：东财估值快照、股息率与资产负债率。"""

from datetime import timedelta

from app.core.logging import get_logger
from app.providers.base import (
    DataNotFound,
    ProviderSchemaDrift,
    ProviderUnavailable,
    now_shanghai,
    safe_float,
)
from app.providers.http import fetch
from app.providers.symbols import InvalidSymbolError, parse_symbol

logger = get_logger(__name__)

URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
PAGE_SIZE = 500
CHUNK_SIZE = 80


async def _query(params: dict) -> dict:
    try:
        response = await fetch(
            URL,
            params={"source": "WEB", "client": "WEB", **params},
        )
    except Exception as exc:  # noqa: BLE001
        raise ProviderUnavailable(f"东财低估值数据请求失败: {exc}") from exc
    try:
        payload = response.json()
    except ValueError as exc:
        raise ProviderSchemaDrift("东财低估值数据返回非 JSON") from exc
    if not isinstance(payload, dict):
        raise ProviderSchemaDrift("东财低估值数据格式异常")
    if not payload.get("success"):
        logger.warning("东财低估值数据返回失败: %s", payload.get("message"))
    return payload


def _rows(payload: dict) -> tuple[list[dict], int]:
    result = payload.get("result") or {}
    rows = result.get("data") or []
    pages = int(result.get("pages") or 1)
    return [row for row in rows if isinstance(row, dict)], pages


def _secucode(code: str) -> str:
    try:
        return parse_symbol(code).ts_code
    except InvalidSymbolError:
        return ""


def _chunks(codes: list[str]) -> list[list[str]]:
    return [codes[index : index + CHUNK_SIZE] for index in range(0, len(codes), CHUNK_SIZE)]


async def latest_trade_date() -> str:
    payload = await _query(
        {
            "reportName": "RPT_VALUEANALYSIS_DET",
            "columns": "TRADE_DATE",
            "pageNumber": 1,
            "pageSize": 1,
            "sortColumns": "TRADE_DATE",
            "sortTypes": -1,
        }
    )
    rows, _ = _rows(payload)
    if not rows:
        raise DataNotFound("东财估值数据暂无交易日")
    return str(rows[0].get("TRADE_DATE") or "")[:10]


async def fetch_valuation_snapshot(
    max_pe: float,
    max_pb: float,
    *,
    trade_date: str | None = None,
) -> list[dict]:
    date = trade_date or await latest_trade_date()
    filter_text = (
        f"(TRADE_DATE='{date}')"
        f"(PE_TTM>0)(PE_TTM<={max_pe:g})"
        f"(PB_MRQ>0)(PB_MRQ<={max_pb:g})"
    )
    columns = (
        "SECURITY_CODE,SECUCODE,SECURITY_NAME_ABBR,BOARD_NAME,CLOSE_PRICE,"
        "CHANGE_RATE,PE_TTM,PB_MRQ,TOTAL_MARKET_CAP,NOTLIMITED_MARKETCAP_A,TRADE_DATE"
    )
    rows: list[dict] = []
    page = 1
    while page <= 20:
        payload = await _query(
            {
                "reportName": "RPT_VALUEANALYSIS_DET",
                "columns": columns,
                "filter": filter_text,
                "pageNumber": page,
                "pageSize": PAGE_SIZE,
                "sortColumns": "NOTLIMITED_MARKETCAP_A",
                "sortTypes": 1,
            }
        )
        page_rows, pages = _rows(payload)
        rows.extend(page_rows)
        if page >= pages or not page_rows:
            break
        page += 1
    if not rows:
        raise DataNotFound("当前 PE/PB 条件下没有估值数据")
    return rows


async def fetch_debt_ratios(
    codes: list[str],
    *,
    report_date: str | None = None,
) -> dict[str, float]:
    if not codes:
        return {}
    ratios: dict[str, float] = {}
    for chunk in _chunks(codes):
        secucodes = ",".join(f'"{item}"' for item in (_secucode(code) for code in chunk) if item)
        if not secucodes:
            continue
        filter_text = f"(SECUCODE in ({secucodes}))"
        if report_date:
            filter_text += f"(REPORT_DATE='{report_date}')"
        wanted = set(chunk)
        page = 1
        while page <= 5 and len(ratios) < len(wanted):
            payload = await _query(
                {
                    "reportName": "RPT_F10_FINANCE_MAINFINADATA",
                    "columns": "SECUCODE,SECURITY_CODE,REPORT_DATE,ZCFZL",
                    "filter": filter_text,
                    "pageNumber": page,
                    "pageSize": PAGE_SIZE,
                    "sortColumns": "REPORT_DATE",
                    "sortTypes": -1,
                }
            )
            rows, pages = _rows(payload)
            for row in rows:
                code = str(row.get("SECUCODE") or "").split(".")[0]
                value = safe_float(row.get("ZCFZL"))
                if code and code not in ratios and value is not None:
                    ratios[code] = value
            if page >= pages or not rows:
                break
            page += 1
    return ratios


async def fetch_dividend_yields(
    codes: list[str],
    prices: dict[str, float],
    *,
    cutoff: str | None = None,
) -> dict[str, float]:
    if not codes:
        return {}
    cutoff_date = cutoff or (now_shanghai() - timedelta(days=365)).strftime("%Y-%m-%d")
    totals: dict[str, float] = {}
    for chunk in _chunks(codes):
        secucodes = ",".join(f'"{item}"' for item in (_secucode(code) for code in chunk) if item)
        if not secucodes:
            continue
        filter_text = f"(SECUCODE in ({secucodes}))(EX_DIVIDEND_DATE>='{cutoff_date}')"
        payload = await _query(
            {
                "reportName": "RPT_SHAREBONUS_DET",
                "columns": "SECUCODE,SECURITY_CODE,PRETAX_BONUS_RMB,EX_DIVIDEND_DATE",
                "filter": filter_text,
                "pageNumber": 1,
                "pageSize": PAGE_SIZE,
                "sortColumns": "EX_DIVIDEND_DATE",
                "sortTypes": -1,
            }
        )
        rows, _ = _rows(payload)
        for row in rows:
            code = str(row.get("SECUCODE") or "").split(".")[0]
            amount = safe_float(row.get("PRETAX_BONUS_RMB"))
            if code and amount is not None:
                totals[code] = totals.get(code, 0.0) + amount

    yields: dict[str, float] = {}
    for code, total_per_ten in totals.items():
        price = prices.get(code)
        if price is not None and price > 0:
            yields[code] = round(total_per_ten / 10 / price * 100, 2)
    return yields
