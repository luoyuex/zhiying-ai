"""技术面诊断引擎测试：纯函数，不依赖网络与数据库。"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.providers.models import KlineBar, Quote
from app.services.technical_analysis import InsufficientDataError, analyze_technicals

TZ = ZoneInfo("Asia/Shanghai")
START = datetime(2026, 6, 1, tzinfo=TZ)


def make_bars(up: bool, count: int = 90) -> list[KlineBar]:
    bars: list[KlineBar] = []
    for index in range(count):
        close = 10 + index * 0.1 if up else 20 - index * 0.1
        bars.append(
            KlineBar(
                time=START + timedelta(days=index),
                open=close - 0.02,
                high=close + 0.08,
                low=close - 0.08,
                close=close,
                volume=1_000_000 + index * 4_000,
            )
        )
    return bars


def make_quote(bars: list[KlineBar]) -> Quote:
    return Quote(
        symbol="600519",
        name="测试股份",
        price=bars[-1].close,
        pre_close=bars[-2].close,
        source="fake-quote",
        fetched_at=START + timedelta(days=len(bars)),
    )


def test_uptrend_is_bullish_and_levels_ordered():
    bars = make_bars(up=True)
    analysis = analyze_technicals(make_quote(bars), bars, "fake-kline")

    assert analysis.score >= 60
    assert analysis.rating in {"偏强", "强势"}
    assert analysis.trend == "上升趋势"
    assert {signal.name for signal in analysis.signals} >= {"MA20", "MA60", "MACD", "RSI"}
    assert analysis.levels.stop_loss < analysis.levels.entry < analysis.price
    assert analysis.price < analysis.levels.take_profit
    assert analysis.levels.support < analysis.price < analysis.levels.resistance
    assert analysis.levels.computed_by == "code"
    assert analysis.levels.risk_reward > 0
    assert "技术评分" in analysis.summary
    assert analysis.source == "fake-quote / fake-kline"


def test_downtrend_is_bearish():
    bars = make_bars(up=False)
    analysis = analyze_technicals(make_quote(bars), bars, "fake-kline")

    assert analysis.score <= 40
    assert analysis.rating in {"偏弱", "弱势"}
    assert analysis.trend == "下降趋势"
    assert analysis.levels.stop_loss < analysis.levels.entry < analysis.price
    assert analysis.levels.support < analysis.price < analysis.levels.resistance


def test_indicators_are_computed():
    bars = make_bars(up=True)
    indicators = analyze_technicals(make_quote(bars), bars, "fake-kline").indicators

    assert indicators.ma5 is not None
    assert indicators.ma20 is not None
    assert indicators.ma60 is not None
    assert indicators.rsi14 is not None and 0 <= indicators.rsi14 <= 100
    assert indicators.macd_hist is not None
    assert indicators.atr14 is not None and indicators.atr14 > 0
    assert indicators.volume_ratio is not None and indicators.volume_ratio > 0
    assert indicators.boll_upper is not None
    assert indicators.boll_upper > indicators.boll_mid > indicators.boll_lower


def test_insufficient_bars_raise():
    with pytest.raises(InsufficientDataError):
        analyze_technicals(make_quote(make_bars(True, 20)), make_bars(True, 20), "fake")
