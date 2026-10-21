"""用户持仓上下文：分析时带入成本、数量与浮盈亏。"""

from pydantic import BaseModel


class UserPosition(BaseModel):
    """来自自选股的持仓信息；成本与数量都可能为空。"""

    cost_price: float | None = None
    quantity: int | None = None
    note: str = ""

    @property
    def has_cost(self) -> bool:
        return self.cost_price is not None and self.cost_price > 0

    def snapshot(self, price: float | None) -> dict:
        """生成给 LLM 的持仓快照，只包含可计算的字段。"""
        data: dict = {"note": self.note}
        if self.quantity is not None:
            data["quantity"] = self.quantity
        if self.has_cost:
            data["cost_price"] = self.cost_price
        if price is not None and self.has_cost:
            pnl_pct = (price - self.cost_price) / self.cost_price * 100
            data["pnl_pct"] = round(pnl_pct, 2)
            if self.quantity is not None:
                data["pnl_amount"] = round(
                    (price - self.cost_price) * self.quantity, 2
                )
                data["market_value"] = round(price * self.quantity, 2)
                data["cost_value"] = round(self.cost_price * self.quantity, 2)
        return data
