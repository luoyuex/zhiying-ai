from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # 应用
    app_name: str = "智赢 AI"
    debug: bool = False
    cors_origins: str = "http://localhost:5173"
    cookie_secure: bool = False

    # 基础设施
    database_url: str = "postgresql+asyncpg://zhiying:zhiying@localhost:5432/zhiying"
    redis_url: str = "redis://localhost:6379/0"

    # 安全
    jwt_secret: str
    otp_secret: str
    access_token_ttl_min: int = 15
    refresh_token_ttl_days: int = 7

    # 验证码
    otp_ttl_seconds: int = 300
    otp_cooldown_seconds: int = 60
    otp_max_attempts: int = 5
    otp_email_daily_limit: int = 10
    otp_ip_hourly_limit: int = 20

    # 邮件
    email_mode: Literal["smtp", "console"] = "console"
    smtp_host: str = "smtp.qq.com"
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from_name: str = "智赢 AI"

    # 行情数据源
    egress_proxy_url: str = ""
    market_http_timeout: float = 8.0
    market_provider_timeout: float = 6.0
    market_global_concurrency: int = 8
    market_quote_fresh_seconds: int = 3
    market_quote_stale_seconds: int = 60
    market_kline_fresh_seconds: int = 300
    market_kline_stale_seconds: int = 1800
    market_circuit_failures: int = 5
    market_circuit_window_seconds: int = 60
    market_circuit_open_seconds: int = 60

    # LLM（OpenAI 兼容协议）
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = "deepseek-chat"
    llm_timeout_seconds: int = 180
    llm_job_timeout_seconds: int = 420
    llm_job_ttl_seconds: int = 3600
    llm_active_job_ttl_seconds: int = 900
    # 注意：推理型模型（如 sensenova-6.8）的思考过程也消耗 completion token，
    # 900 会被思考吃光导致正文截断，JSON 解析必失败，因此放宽到 2048
    llm_max_tokens: int = 2048
    llm_temperature: float = 0.3
    llm_cache_seconds: int = 21600

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_base_url and self.llm_api_key and self.llm_model)

    # 元宝搜索（腾讯云 WSA SearchPro）
    # 官方 API 3.0：SecretId + SecretKey + TC3 签名，Host wsa.tencentcloudapi.com
    wsa_secret_id: str = ""
    wsa_secret_key: str = ""
    wsa_secret_token: str = ""
    wsa_search_host: str = "wsa.tencentcloudapi.com"
    wsa_search_version: str = "2025-05-08"
    # 兼容服务 API KEY（Bearer）模式（参考项目的 api.wsa.cloud.tencent.com）
    wsa_api_key: str = ""
    wsa_search_url: str = "https://api.wsa.cloud.tencent.com/SearchPro"
    wsa_search_timeout_seconds: int = 20
    wsa_search_count: int = 20
    wsa_search_top_n: int = 8
    wsa_search_freshness: str = "m3"
    wsa_search_cache_seconds: int = 1800

    @property
    def wsa_search_configured(self) -> bool:
        return bool(
            (self.wsa_secret_id and self.wsa_secret_key)
            or self.wsa_api_key
        )

    @property
    def wsa_use_official_api(self) -> bool:
        return bool(self.wsa_secret_id and self.wsa_secret_key)

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def refresh_cookie_name(self) -> str:
        return "zy_refresh"

    @property
    def refresh_cookie_path(self) -> str:
        return "/api/v1/auth"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
