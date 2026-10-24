"""LLM 估算单价（人民币 / 百万 token）。

优先使用 .env 的 LLM_PRICE_INPUT_PER_M / LLM_PRICE_OUTPUT_PER_M；
未配置时回退到内置静态表。只用于后台成本估算，不作为财务结算依据。
未知模型返回 None，页面显示“未配置单价”。
"""

from decimal import Decimal, InvalidOperation

from app.core.config import settings

# model -> (input, output)
_PRICES: dict[str, tuple[Decimal, Decimal]] = {
    "deepseek-chat": (Decimal("2"), Decimal("8")),
    "deepseek-reasoner": (Decimal("4"), Decimal("16")),
}

_MILLION = Decimal("1000000")


def _parse_price(raw: str) -> Decimal | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        value = Decimal(text)
    except InvalidOperation:
        return None
    return value if value >= 0 else None


def configured_prices() -> tuple[Decimal, Decimal] | None:
    """两项都配置才启用；只配一项视为未配置，避免成本被低估。"""
    input_price = _parse_price(settings.llm_price_input_per_m)
    output_price = _parse_price(settings.llm_price_output_per_m)
    if input_price is None or output_price is None:
        return None
    return input_price, output_price


def _static_prices(name: str) -> tuple[Decimal, Decimal] | None:
    price = _PRICES.get(name)
    if price is None:
        for key, value in _PRICES.items():
            if name.startswith(key):
                return value
    return price


def estimate_cost(
    model: str | None,
    prompt_tokens: int,
    completion_tokens: int,
) -> Decimal | None:
    name = (model or "").strip().lower()
    price = configured_prices() or _static_prices(name)
    if price is None:
        return None

    input_price, output_price = price
    cost = (
        Decimal(max(prompt_tokens, 0)) * input_price
        + Decimal(max(completion_tokens, 0)) * output_price
    ) / _MILLION
    return cost.quantize(Decimal("0.000001"))
