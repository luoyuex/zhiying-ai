"""统一错误体系：所有业务异常都带 code，前端按 code 做提示映射。"""

from typing import Any


class ErrorCode:
    EMAIL_EXISTS = "EMAIL_EXISTS"
    CODE_INVALID = "CODE_INVALID"
    CODE_EXPIRED = "CODE_EXPIRED"
    RATE_LIMITED = "RATE_LIMITED"
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    ACCOUNT_BANNED = "ACCOUNT_BANNED"
    MAIL_SEND_FAILED = "MAIL_SEND_FAILED"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    INVALID_SYMBOL = "INVALID_SYMBOL"
    STOCK_NOT_FOUND = "STOCK_NOT_FOUND"
    MARKET_UNAVAILABLE = "MARKET_UNAVAILABLE"
    ANALYSIS_UNAVAILABLE = "ANALYSIS_UNAVAILABLE"
    LLM_NOT_CONFIGURED = "LLM_NOT_CONFIGURED"
    LLM_ERROR = "LLM_ERROR"
    LLM_BUSY = "LLM_BUSY"
    LLM_INVALID_RESPONSE = "LLM_INVALID_RESPONSE"
    ANALYSIS_QUOTA_EXCEEDED = "ANALYSIS_QUOTA_EXCEEDED"
    AI_SERVICE_UNAVAILABLE = "AI_SERVICE_UNAVAILABLE"


class AppError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        detail: Any | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.detail = detail


def email_exists() -> AppError:
    return AppError(ErrorCode.EMAIL_EXISTS, "该邮箱已注册，请直接登录", 409)


def code_invalid(attempts_left: int | None = None) -> AppError:
    message = "验证码不正确"
    if attempts_left is not None:
        message = f"验证码不正确，还可尝试 {attempts_left} 次"
    return AppError(ErrorCode.CODE_INVALID, message, 400, {"attempts_left": attempts_left})


def code_expired() -> AppError:
    return AppError(ErrorCode.CODE_EXPIRED, "验证码已失效，请重新获取", 400)


def rate_limited(message: str, retry_after: int) -> AppError:
    return AppError(ErrorCode.RATE_LIMITED, message, 429, {"retry_after": retry_after})


def invalid_credentials() -> AppError:
    return AppError(ErrorCode.INVALID_CREDENTIALS, "邮箱或密码不正确", 401)


def account_banned() -> AppError:
    return AppError(ErrorCode.ACCOUNT_BANNED, "账号已被停用，请联系管理员", 403)


def mail_send_failed() -> AppError:
    return AppError(ErrorCode.MAIL_SEND_FAILED, "验证码邮件发送失败，请稍后重试", 502)


def unauthorized(message: str = "登录状态已失效，请重新登录") -> AppError:
    return AppError(ErrorCode.UNAUTHORIZED, message, 401)


def forbidden(message: str = "没有权限执行该操作") -> AppError:
    return AppError(ErrorCode.FORBIDDEN, message, 403)


def not_found(message: str = "资源不存在") -> AppError:
    return AppError(ErrorCode.NOT_FOUND, message, 404)


def invalid_symbol(reason: str) -> AppError:
    return AppError(ErrorCode.INVALID_SYMBOL, reason, 422)


def stock_not_found(symbol: str) -> AppError:
    return AppError(
        ErrorCode.STOCK_NOT_FOUND,
        f"未找到股票 {symbol} 的行情数据",
        404,
        {"symbol": symbol},
    )


def market_unavailable() -> AppError:
    return AppError(
        ErrorCode.MARKET_UNAVAILABLE,
        "行情数据源暂时不可用，请稍后重试",
        503,
    )


def analysis_unavailable(message: str) -> AppError:
    return AppError(ErrorCode.ANALYSIS_UNAVAILABLE, message, 422)


def llm_not_configured() -> AppError:
    return AppError(
        ErrorCode.LLM_NOT_CONFIGURED,
        "尚未配置 LLM，请在 .env 填写 LLM_BASE_URL、LLM_API_KEY、LLM_MODEL 后重启后端",
        503,
    )


def llm_error(message: str = "AI 分析服务暂不可用，请稍后重试") -> AppError:
    return AppError(ErrorCode.LLM_ERROR, message, 502)


def llm_busy() -> AppError:
    return AppError(ErrorCode.LLM_BUSY, "LLM 服务繁忙，请稍后重试", 503)


def llm_invalid_response() -> AppError:
    return AppError(
        ErrorCode.LLM_INVALID_RESPONSE,
        "LLM 返回格式不符合要求，请稍后重试",
        502,
    )


def analysis_quota_exceeded(limit: int, reset_seconds: int) -> AppError:
    return AppError(
        ErrorCode.ANALYSIS_QUOTA_EXCEEDED,
        "今日 AI 分析额度已用完，明天 00:00 重置",
        429,
        {"limit": limit, "reset_seconds": reset_seconds},
    )


def ai_service_unavailable(message: str) -> AppError:
    return AppError(ErrorCode.AI_SERVICE_UNAVAILABLE, message, 503)
