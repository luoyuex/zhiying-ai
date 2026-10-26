"""定时任务设置模型：每日自动选股与自动分析自选股。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.core.config import settings
from app.core.webhook import WebhookUrlError, normalize_webhook_url
from app.schemas.screener import (
    LowPriceBullAnalysisRequest,
    MainForceAnalysisRequest,
    ProfitGrowthAnalysisRequest,
    ScreenerStrategyId,
    SmallCapAnalysisRequest,
    ValueStockAnalysisRequest,
)

# 各策略的筛选参数模型：设置校验与调度器反序列化共用，保证口径一致
STRATEGY_FILTER_MODELS = {
    "main_force": MainForceAnalysisRequest,
    "low_price_bull": LowPriceBullAnalysisRequest,
    "small_cap": SmallCapAnalysisRequest,
    "profit_growth": ProfitGrowthAnalysisRequest,
    "value_stock": ValueStockAnalysisRequest,
}


class AutomationStrategySetting(BaseModel):
    enabled: bool = False
    # 空字段按模型默认值补全；空 dict 表示全默认
    filters: dict = Field(default_factory=dict)


class AutomationSettingsUpdate(BaseModel):
    screener_enabled: bool = False
    analysis_enabled: bool = False
    # 每条任务线各自的执行时间（24 小时制），实际执行可能延迟至多 5 分钟
    screener_run_hour: int = Field(
        default_factory=lambda: settings.automation_cron_hour, ge=0, le=23
    )
    screener_run_minute: int = Field(
        default_factory=lambda: settings.automation_cron_minute, ge=0, le=59
    )
    analysis_run_hour: int = Field(
        default_factory=lambda: settings.automation_cron_hour, ge=0, le=23
    )
    analysis_run_minute: int = Field(
        default_factory=lambda: settings.automation_cron_minute, ge=0, le=59
    )
    strategy_settings: dict[ScreenerStrategyId, AutomationStrategySetting] = Field(
        default_factory=dict
    )
    email_notify_enabled: bool = False
    price_alert_email_enabled: bool = True
    notify_email: EmailStr | None = None
    # Webhook：与邮件并列的消息渠道；两个事件开关独立，地址/类型共用
    webhook_notify_enabled: bool = False
    price_alert_webhook_enabled: bool = True
    webhook_type: Literal["dingtalk", "feishu"] = "dingtalk"
    webhook_url: str | None = None
    webhook_keyword: str | None = Field(default=None, max_length=64)

    @field_validator("notify_email", mode="before")
    @classmethod
    def normalize_notify_email(cls, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip().lower()
        return text or None

    @field_validator("webhook_url", mode="before")
    @classmethod
    def normalize_url(cls, value: object) -> str | None:
        if value is None:
            return None
        try:
            return normalize_webhook_url(str(value))
        except WebhookUrlError as exc:
            raise ValueError(str(exc)) from exc

    @field_validator("webhook_keyword", mode="before")
    @classmethod
    def normalize_keyword(cls, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @model_validator(mode="after")
    def require_notify_email(self) -> "AutomationSettingsUpdate":
        if self.email_notify_enabled and not self.notify_email:
            raise ValueError("开启邮件通知时必须填写接收地址")
        if self.webhook_notify_enabled and not self.webhook_url:
            raise ValueError("开启 Webhook 通知时必须填写机器人地址")
        return self

    def normalized_strategy_settings(self) -> dict:
        """逐策略校验 filters 并补全默认值；失败抛 pydantic.ValidationError（API 层转 422）。"""
        result: dict = {}
        for strategy, setting in self.strategy_settings.items():
            model = STRATEGY_FILTER_MODELS[strategy]
            validated = model.model_validate(setting.filters)
            result[strategy] = {
                "enabled": setting.enabled,
                "filters": validated.model_dump(mode="json"),
            }
        return result


class AutomationSettingsResponse(BaseModel):
    screener_enabled: bool = False
    analysis_enabled: bool = False
    screener_run_hour: int = Field(
        default_factory=lambda: settings.automation_cron_hour
    )
    screener_run_minute: int = Field(
        default_factory=lambda: settings.automation_cron_minute
    )
    analysis_run_hour: int = Field(
        default_factory=lambda: settings.automation_cron_hour
    )
    analysis_run_minute: int = Field(
        default_factory=lambda: settings.automation_cron_minute
    )
    strategy_settings: dict = Field(default_factory=dict)
    email_notify_enabled: bool = False
    price_alert_email_enabled: bool = True
    notify_email: str | None = None
    webhook_notify_enabled: bool = False
    price_alert_webhook_enabled: bool = True
    webhook_type: str = "dingtalk"
    webhook_url: str | None = None
    webhook_keyword: str | None = None
    updated_at: datetime | None = None
