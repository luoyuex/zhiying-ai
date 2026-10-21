"""Provider 解析测试：用真实接口抓下来的报文做 fixture，测试不联网。"""

import json
from pathlib import Path

import pytest

from app.providers.base import DataNotFound
from app.providers.eastmoney import EastmoneyProvider
from app.providers.models import Adjust, KlinePeriod
from app.providers.sina import SinaProvider
from app.providers.symbols import InvalidSymbolError, parse_symbol
from app.providers.tencent import TencentProvider

FIXTURES = Path(__file__).parent / "fixtures"


def load_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def load_json(name: str) -> dict | list:
    return json.loads(load_text(name))


@pytest.mark.parametrize(
    ("raw", "code", "exchange"),
    [
        ("600519", "600519", "SH"),
        ("sh600519", "600519", "SH"),
        ("SH600519", "600519", "SH"),
        ("600519.SH", "600519", "SH"),
        ("000001", "000001", "SZ"),
        ("300750.sz", "300750", "SZ"),
        ("830799", "830799", "BJ"),
        ("920001", "920001", "BJ"),
    ],
)
def test_parse_symbol_variants(raw: str, code: str, exchange: str):
    symbol = parse_symbol(raw)
    assert symbol.code == code
    assert symbol.exchange == exchange
    assert symbol.prefixed == f"{exchange.lower()}{code}"


@pytest.mark.parametrize("raw", ["", "60051", "6005190", "hk00700", "510300", "600519.SZ"])
def test_parse_symbol_invalid(raw: str):
    with pytest.raises(InvalidSymbolError):
        parse_symbol(raw)


def test_tencent_quote_parse():
    symbol = parse_symbol("600519")
    quote = TencentProvider.parse_quote(symbol, load_text("tencent_quote.txt").encode("gbk"))

    assert quote.symbol == "600519"
    assert quote.name == "贵州茅台"
    assert quote.price > 0
    assert quote.high >= quote.low
    assert quote.volume and quote.volume > 0
    assert quote.amount and quote.amount > 0
    assert quote.total_market_cap and quote.total_market_cap > 0
    assert quote.source == "tencent"
    assert quote.fetched_at.tzinfo is not None


def test_sina_quote_parse():
    symbol = parse_symbol("600519")
    quote = SinaProvider.parse_quote(symbol, load_text("sina_quote.txt").encode("gbk"))

    assert quote.name == "贵州茅台"
    assert quote.price > 0
    assert quote.volume and quote.volume > 0
    assert quote.amount and quote.amount > 0
    assert quote.source == "sina"


def test_eastmoney_quote_parse():
    symbol = parse_symbol("600519")
    quote = EastmoneyProvider.parse_quote(symbol, load_json("eastmoney_quote.json"))

    assert quote.name == "贵州茅台"
    assert quote.price > 0
    assert quote.volume and quote.volume > 0
    assert quote.amount and quote.amount > 0
    assert quote.pe is not None
    assert quote.pb is not None
    assert quote.total_market_cap and quote.total_market_cap > 0
    assert quote.limit_up and quote.limit_down
    assert quote.source == "eastmoney"


def test_tencent_kline_parse():
    symbol = parse_symbol("600519")
    series = TencentProvider.parse_kline(
        symbol, load_json("tencent_kline.json"), KlinePeriod.DAY, Adjust.QFQ, 5
    )

    assert len(series.bars) == 5
    assert series.source == "tencent"
    assert series.bars[0].time < series.bars[-1].time
    assert all(bar.volume > 0 for bar in series.bars)
    assert all(bar.high >= bar.low for bar in series.bars)


def test_sina_kline_parse():
    symbol = parse_symbol("600519")
    series = SinaProvider.parse_kline(
        symbol, load_json("sina_kline.json"), KlinePeriod.DAY, Adjust.NONE, 5
    )

    assert len(series.bars) == 5
    assert series.source == "sina"
    assert series.bars[0].time < series.bars[-1].time
    assert all(bar.volume > 0 for bar in series.bars)


def test_eastmoney_kline_parse():
    symbol = parse_symbol("600519")
    series = EastmoneyProvider.parse_kline(
        symbol, load_json("eastmoney_kline.json"), KlinePeriod.DAY, Adjust.QFQ, 5
    )

    assert len(series.bars) == 5
    assert series.source == "eastmoney"
    assert series.bars[0].time < series.bars[-1].time
    assert all(bar.amount and bar.amount > 0 for bar in series.bars)
    assert all(bar.turnover_pct is not None for bar in series.bars)


def test_bad_payloads_raise_not_found():
    symbol = parse_symbol("600519")
    with pytest.raises(DataNotFound):
        TencentProvider.parse_quote(symbol, b'v_sh600519="";')
    with pytest.raises(DataNotFound):
        SinaProvider.parse_quote(symbol, b'var hq_str_sh600519="";')
    with pytest.raises(DataNotFound):
        EastmoneyProvider.parse_quote(symbol, {"data": None})
    with pytest.raises(DataNotFound):
        EastmoneyProvider.parse_kline(
            symbol,
            {"data": {"klines": []}},
            KlinePeriod.DAY,
            Adjust.QFQ,
            5,
        )
