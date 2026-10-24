"""LLM 估算单价（人民币 / 百万 token）。

只用于后台成本估算，不作为财务结算依据。供应商调价时更新此表。
未知模型返回 None，页面显示“未配置单价”。
"""

from decimal import Decimal

# model -> (input, output)
_PRICES: dict[str, tuple[Decimal, Decimal]] = {
    "deepseek-chat": (Decimal("2"), Decimal("8")),
    "deepseek-reasoner": (Decimal("4"), Decimal("16")),
}

_MILLION = Decimal("1000000")


def estimate_cost(
    model: str | None,
    prompt_tokens: int,
    completion_tokens: int,
) -> Decimal | None:
    name = (model or "").strip().lower()
    if not name:
        return None

    price = _PRICES.get(name)
    if price is None:
        for key, value in _PRICES.items():
            if name.startswith(key):
                price = value
                break
    if price is None:
        return None

    input_price, output_price = price
    cost = (
        Decimal(max(prompt_tokens, 0)) * input_price
        + Decimal(max(completion_tokens, 0)) * output_price
    ) / _MILLION
    return cost.quantize(Decimal("0.000001"))
