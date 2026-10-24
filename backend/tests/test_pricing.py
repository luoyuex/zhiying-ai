"""LLM 成本估算：内置单价与环境变量覆盖。"""

from decimal import Decimal

from app.core.config import settings
from app.llm.pricing import estimate_cost


def test_static_price_for_known_model(monkeypatch):
    monkeypatch.setattr(settings, "llm_price_input_per_m", "")
    monkeypatch.setattr(settings, "llm_price_output_per_m", "")
    assert estimate_cost("deepseek-chat", 1_000_000, 0) == Decimal("2.000000")


def test_unknown_model_without_price_returns_none(monkeypatch):
    monkeypatch.setattr(settings, "llm_price_input_per_m", "")
    monkeypatch.setattr(settings, "llm_price_output_per_m", "")
    assert estimate_cost("sensenova-6.8-flash-lite", 1000, 1000) is None


def test_env_price_overrides_static_table(monkeypatch):
    monkeypatch.setattr(settings, "llm_price_input_per_m", "0.5")
    monkeypatch.setattr(settings, "llm_price_output_per_m", "1.5")
    assert estimate_cost(
        "sensenova-6.8-flash-lite",
        1_000_000,
        1_000_000,
    ) == Decimal("2.000000")


def test_incomplete_env_price_is_ignored(monkeypatch):
    monkeypatch.setattr(settings, "llm_price_input_per_m", "0.5")
    monkeypatch.setattr(settings, "llm_price_output_per_m", "")
    assert estimate_cost("sensenova-6.8-flash-lite", 1000, 1000) is None
