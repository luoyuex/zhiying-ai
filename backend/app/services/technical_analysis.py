"""技术面诊断：纯代码计算，不依赖 LLM。

口径：日 K 前复权，至少 30 根；价格单位元。
输出评分、评级、信号、支撑压力和三档价位，价位统一由代码计算。
"""

from statistics import pstdev

from app.providers.models import KlineBar, Quote
from app.schemas.analysis import (
    AnalysisSignal,
    IndicatorSnapshot,
    PriceLevels,
    SignalDirection,
    TechnicalAnalysis,
)


class InsufficientDataError(ValueError):
    """K 线数量不足，无法计算有效指标。"""


def _sma(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def _ema_series(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    factor = 2 / (period + 1)
    result = [values[0]]
    for value in values[1:]:
        result.append(value * factor + result[-1] * (1 - factor))
    return result


def _macd(closes: list[float]) -> tuple[float | None, float | None, float | None, float | None]:
    if len(closes) < 35:
        return None, None, None, None
    ema12 = _ema_series(closes, 12)
    ema26 = _ema_series(closes, 26)
    dif = [a - b for a, b in zip(ema12, ema26, strict=True)]
    dea = _ema_series(dif, 9)
    hist = [(d - e) * 2 for d, e in zip(dif, dea, strict=True)]
    previous_hist = hist[-2] if len(hist) >= 2 else None
    return dif[-1], dea[-1], hist[-1], previous_hist


def _rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) <= period:
        return None
    gains: list[float] = []
    losses: list[float] = []
    for index in range(1, len(closes)):
        change = closes[index] - closes[index - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for index in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[index]) / period
        avg_loss = (avg_loss * (period - 1) + losses[index]) / period

    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)


def _boll(closes: list[float], period: int = 20, width: float = 2.0):
    if len(closes) < period:
        return None, None, None
    window = closes[-period:]
    mid = sum(window) / period
    deviation = pstdev(window)
    return mid + width * deviation, mid, mid - width * deviation


def _atr(bars: list[KlineBar], period: int = 14) -> float | None:
    if len(bars) <= period:
        return None
    true_ranges: list[float] = []
    for index in range(1, len(bars)):
        high = bars[index].high
        low = bars[index].low
        previous_close = bars[index - 1].close
        true_ranges.append(
            max(high - low, abs(high - previous_close), abs(low - previous_close))
        )
    if len(true_ranges) < period:
        return None
    atr = sum(true_ranges[:period]) / period
    for true_range in true_ranges[period:]:
        atr = (atr * (period - 1) + true_range) / period
    return atr


def _volume_ratio(volumes: list[float], short: int = 5, long: int = 20) -> float | None:
    if len(volumes) < long:
        return None
    short_average = sum(volumes[-short:]) / short
    long_average = sum(volumes[-long:]) / long
    if long_average <= 0:
        return None
    return short_average / long_average


def _nearest_support(candidates: list[float | None], price: float) -> float | None:
    valid = [value for value in candidates if value is not None and value < price * 0.999]
    return max(valid) if valid else None


def _nearest_resistance(candidates: list[float | None], price: float) -> float | None:
    valid = [value for value in candidates if value is not None and value > price * 1.001]
    return min(valid) if valid else None


def _rating(score: int) -> str:
    if score >= 75:
        return "强势"
    if score >= 60:
        return "偏强"
    if score >= 45:
        return "中性"
    if score >= 30:
        return "偏弱"
    return "弱势"


def analyze_technicals(quote: Quote, bars: list[KlineBar], kline_source: str) -> TechnicalAnalysis:
    if len(bars) < 30:
        raise InsufficientDataError("有效 K 线不足 30 根，暂时无法进行技术诊断")

    bars = sorted(bars, key=lambda bar: bar.time)
    closes = [bar.close for bar in bars]
    highs = [bar.high for bar in bars]
    lows = [bar.low for bar in bars]
    volumes = [bar.volume for bar in bars]
    price = quote.price

    ma5 = _sma(closes, 5)
    ma10 = _sma(closes, 10)
    ma20 = _sma(closes, 20)
    ma60 = _sma(closes, 60)
    ma20_previous = _sma(closes[:-5], 20) if len(closes) >= 25 else None
    macd_dif, macd_dea, macd_hist, previous_hist = _macd(closes)
    rsi14 = _rsi(closes)
    boll_upper, boll_mid, boll_lower = _boll(closes)
    atr14 = _atr(bars)
    volume_ratio = _volume_ratio(volumes)

    score = 50
    signals: list[AnalysisSignal] = []

    def add_signal(
        name: str,
        direction: SignalDirection,
        detail: str,
        delta: int = 0,
    ) -> None:
        nonlocal score
        score += delta
        signals.append(AnalysisSignal(name=name, direction=direction, detail=detail))

    if ma20 is not None:
        if price >= ma20:
            add_signal(
                "MA20",
                SignalDirection.BULLISH,
                f"价格 {price:.2f} 位于 MA20 {ma20:.2f} 上方",
                8,
            )
        else:
            add_signal(
                "MA20",
                SignalDirection.BEARISH,
                f"价格 {price:.2f} 位于 MA20 {ma20:.2f} 下方",
                -8,
            )

    if ma60 is not None:
        if price >= ma60:
            add_signal(
                "MA60",
                SignalDirection.BULLISH,
                f"价格 {price:.2f} 位于 MA60 {ma60:.2f} 上方",
                8,
            )
        else:
            add_signal(
                "MA60",
                SignalDirection.BEARISH,
                f"价格 {price:.2f} 位于 MA60 {ma60:.2f} 下方",
                -8,
            )

    alignment = "交织"
    if ma5 is not None and ma10 is not None and ma20 is not None:
        if ma5 > ma10 > ma20:
            alignment = "多头排列"
            add_signal(
                "均线排列",
                SignalDirection.BULLISH,
                f"MA5 {ma5:.2f} > MA10 {ma10:.2f} > MA20 {ma20:.2f}",
                8,
            )
        elif ma5 < ma10 < ma20:
            alignment = "空头排列"
            add_signal(
                "均线排列",
                SignalDirection.BEARISH,
                f"MA5 {ma5:.2f} < MA10 {ma10:.2f} < MA20 {ma20:.2f}",
                -8,
            )
        else:
            add_signal(
                "均线排列",
                SignalDirection.NEUTRAL,
                f"MA5 {ma5:.2f} / MA10 {ma10:.2f} / MA20 {ma20:.2f} 交织",
            )

    macd_state = "零轴附近"
    if macd_hist is not None and macd_dif is not None and macd_dea is not None:
        if macd_hist > 0:
            macd_state = "红柱"
            cross = previous_hist is not None and previous_hist <= 0
            detail = (
                f"{'MACD 金叉，' if cross else ''}红柱 {macd_hist:.3f}，"
                f"DIF {macd_dif:.3f} / DEA {macd_dea:.3f}"
            )
            add_signal("MACD", SignalDirection.BULLISH, detail, 8)
        elif macd_hist < 0:
            macd_state = "绿柱"
            cross = previous_hist is not None and previous_hist >= 0
            detail = (
                f"{'MACD 死叉，' if cross else ''}绿柱 {macd_hist:.3f}，"
                f"DIF {macd_dif:.3f} / DEA {macd_dea:.3f}"
            )
            add_signal("MACD", SignalDirection.BEARISH, detail, -8)
        else:
            add_signal("MACD", SignalDirection.NEUTRAL, "MACD 柱体接近零轴")

    if rsi14 is not None:
        if rsi14 >= 70:
            add_signal(
                "RSI",
                SignalDirection.BEARISH,
                f"RSI14 {rsi14:.1f}，进入超买区",
                -4,
            )
        elif rsi14 >= 50:
            add_signal(
                "RSI",
                SignalDirection.BULLISH,
                f"RSI14 {rsi14:.1f}，处于偏强区间",
                5,
            )
        elif rsi14 >= 30:
            add_signal(
                "RSI",
                SignalDirection.BEARISH,
                f"RSI14 {rsi14:.1f}，处于偏弱区间",
                -3,
            )
        else:
            add_signal(
                "RSI",
                SignalDirection.NEUTRAL,
                f"RSI14 {rsi14:.1f}，进入超卖区，关注反弹",
                2,
            )

    if volume_ratio is not None:
        rising = closes[-1] >= closes[-2]
        if volume_ratio >= 1.2:
            if rising:
                add_signal(
                    "量能",
                    SignalDirection.BULLISH,
                    f"5 日/20 日均量比 {volume_ratio:.2f}，放量上涨",
                    5,
                )
            else:
                add_signal(
                    "量能",
                    SignalDirection.BEARISH,
                    f"5 日/20 日均量比 {volume_ratio:.2f}，放量下跌",
                    -5,
                )
        elif volume_ratio <= 0.8:
            add_signal(
                "量能",
                SignalDirection.NEUTRAL,
                f"5 日/20 日均量比 {volume_ratio:.2f}，缩量",
                -1,
            )
        else:
            add_signal(
                "量能",
                SignalDirection.NEUTRAL,
                f"5 日/20 日均量比 {volume_ratio:.2f}，量能平稳",
            )

    if boll_upper is not None and boll_lower is not None:
        if price > boll_upper:
            add_signal(
                "布林",
                SignalDirection.BEARISH,
                f"价格高于布林上轨 {boll_upper:.2f}，短线偏热",
                -3,
            )
        elif price < boll_lower:
            add_signal(
                "布林",
                SignalDirection.NEUTRAL,
                f"价格低于布林下轨 {boll_lower:.2f}，关注超跌反弹",
                2,
            )

    score = max(0, min(100, score))
    rating = _rating(score)

    trend = "震荡整理"
    if ma20 is not None and ma20_previous is not None:
        if price > ma20 and ma20 > ma20_previous:
            trend = "上升趋势"
        elif price < ma20 and ma20 < ma20_previous:
            trend = "下降趋势"
    elif ma20 is not None:
        trend = "偏强整理" if price > ma20 else "偏弱整理"

    recent20_low = min(lows[-20:])
    recent20_high = max(highs[-20:])
    recent60_low = min(lows[-60:]) if len(lows) >= 60 else min(lows)
    recent60_high = max(highs[-60:]) if len(highs) >= 60 else max(highs)
    support = _nearest_support(
        [recent20_low, recent60_low, ma20, ma60, boll_lower],
        price,
    )
    resistance = _nearest_resistance(
        [recent20_high, recent60_high, ma20, ma60, boll_upper],
        price,
    )
    support = round(support if support is not None else price * 0.97, 2)
    resistance = round(resistance if resistance is not None else price * 1.03, 2)

    atr_value = atr14 if atr14 is not None else price * 0.02
    entry = round(price * 0.98, 2)
    take_profit = round(price * 1.08, 2)
    raw_stop = price - 2.5 * atr_value
    stop_loss = round(max(price * 0.92, min(price * 0.95, raw_stop)), 2)
    if stop_loss >= entry:
        stop_loss = round(entry * 0.98, 2)
    risk = entry - stop_loss
    risk_reward = round((take_profit - entry) / risk, 2) if risk > 0 else 0.0

    rsi_text = f"{rsi14:.1f}" if rsi14 is not None else "—"
    volume_text = f"{volume_ratio:.2f}" if volume_ratio is not None else "—"
    ma_position = "上方" if ma20 is not None and price >= ma20 else "下方"
    summary = (
        f"{quote.name} 最新价 {price:.2f} 元，处于{trend}；"
        f"价格位于 MA20 {ma_position}，短中期均线{alignment}；"
        f"MACD {macd_state}，RSI14 {rsi_text}，量比 {volume_text}。"
        f"技术评分 {score}，评级「{rating}」。"
    )

    indicators = IndicatorSnapshot(
        ma5=_round(ma5),
        ma10=_round(ma10),
        ma20=_round(ma20),
        ma60=_round(ma60),
        rsi14=_round(rsi14, 2),
        macd_dif=_round(macd_dif),
        macd_dea=_round(macd_dea),
        macd_hist=_round(macd_hist),
        boll_upper=_round(boll_upper, 2),
        boll_mid=_round(boll_mid, 2),
        boll_lower=_round(boll_lower, 2),
        atr14=_round(atr14),
        volume_ratio=_round(volume_ratio, 2),
    )

    return TechnicalAnalysis(
        symbol=quote.symbol,
        name=quote.name,
        price=price,
        as_of=quote.fetched_at,
        score=score,
        rating=rating,
        trend=trend,
        summary=summary,
        signals=signals,
        indicators=indicators,
        levels=PriceLevels(
            entry=entry,
            take_profit=take_profit,
            stop_loss=stop_loss,
            risk_reward=risk_reward,
            support=support,
            resistance=resistance,
        ),
        # 报价与 K 线常为同一来源，去重避免界面出现「腾讯行情 / 腾讯行情」
        source=" / ".join(dict.fromkeys([quote.source, kline_source])),
    )


def _round(value: float | None, digits: int = 4) -> float | None:
    return round(value, digits) if value is not None else None
