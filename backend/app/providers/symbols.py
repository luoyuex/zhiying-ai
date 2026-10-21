"""A 股代码归一化。

对外只接受六位代码；内部统一转成 ``StockSymbol``，由它派生各家数据源需要的格式。
"""

import re
from dataclasses import dataclass

_CODE_RE = re.compile(r"^\d{6}$")
_PREFIXES = {"sh": "SH", "sz": "SZ", "bj": "BJ"}


class InvalidSymbolError(ValueError):
    """代码格式不合法或不属于当前支持的 A 股市场。"""


@dataclass(frozen=True, slots=True)
class StockSymbol:
    code: str
    exchange: str

    @property
    def prefixed(self) -> str:
        """腾讯/新浪使用的格式：sh600519。"""
        return f"{self.exchange.lower()}{self.code}"

    @property
    def secid(self) -> str:
        """东方财富使用的格式：1.600519（沪市 1，深市/北交所 0）。"""
        return f"{1 if self.exchange == 'SH' else 0}.{self.code}"

    @property
    def ts_code(self) -> str:
        """Tushare 风格：600519.SH。"""
        return f"{self.code}.{self.exchange}"


def _exchange_for(code: str) -> str:
    if code.startswith("6"):
        return "SH"
    if code[0] in {"0", "3"}:
        return "SZ"
    # 北交所：43/83/87/88 开头，以及 920 新号段
    if code[0] in {"4", "8"} or code.startswith("92"):
        return "BJ"
    raise InvalidSymbolError(f"不支持的证券代码：{code}")


def parse_symbol(raw: str) -> StockSymbol:
    text = (raw or "").strip().lower()
    if not text:
        raise InvalidSymbolError("股票代码不能为空")

    suffix = ""
    if "." in text:
        code, suffix = text.split(".", 1)
    elif text[:2] in _PREFIXES:
        code, suffix = text[2:], text[:2]
    else:
        code = text

    if not _CODE_RE.fullmatch(code):
        raise InvalidSymbolError(f"股票代码必须是 6 位数字：{raw}")

    exchange = _exchange_for(code)
    if suffix:
        expected = _PREFIXES.get(suffix, suffix.upper())
        if expected != exchange:
            raise InvalidSymbolError(f"代码 {code} 与市场后缀 {suffix} 不匹配")

    return StockSymbol(code=code, exchange=exchange)
