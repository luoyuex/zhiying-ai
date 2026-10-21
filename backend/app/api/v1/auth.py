from fastapi import APIRouter, Cookie, Depends, Request, Response
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_current_user, get_db
from app.db.models.user import User
from app.db.redis import get_redis
from app.schemas.auth import (
    AuthResponse,
    CodeLoginRequest,
    LoginRequest,
    OkResponse,
    RefreshResponse,
    RegisterRequest,
    ResetPasswordRequest,
    SendCodeRequest,
    SendCodeResponse,
    UserOut,
)
from app.services import auth_service
from app.services.mail_service import send_otp_email
from app.services.otp_service import OtpService

router = APIRouter(prefix="/auth", tags=["认证"])


def get_otp_service(redis: Redis = Depends(get_redis)) -> OtpService:
    return OtpService(redis)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "0.0.0.0"


def _client_ua(request: Request) -> str:
    return request.headers.get("user-agent", "")


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=token,
        max_age=settings.refresh_token_ttl_days * 86400,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path=settings.refresh_cookie_path,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        path=settings.refresh_cookie_path,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )


@router.post("/email/send-code", response_model=SendCodeResponse, summary="发送邮箱验证码")
async def send_code(
    payload: SendCodeRequest,
    request: Request,
    otp: OtpService = Depends(get_otp_service),
) -> SendCodeResponse:
    email = payload.email
    code, ttl = await otp.issue(email, payload.purpose, _client_ip(request))
    await send_otp_email(email, code, payload.purpose, ttl)
    return SendCodeResponse(expires_in=ttl, cooldown=settings.otp_cooldown_seconds)


@router.post("/register", response_model=AuthResponse, summary="邮箱验证码注册")
async def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    otp: OtpService = Depends(get_otp_service),
) -> AuthResponse:
    user, access_token, refresh_token = await auth_service.register(
        db, otp, payload, ip=_client_ip(request), user_agent=_client_ua(request)
    )
    _set_refresh_cookie(response, refresh_token)
    return AuthResponse(
        access_token=access_token,
        expires_in=settings.access_token_ttl_min * 60,
        user=UserOut.model_validate(user),
    )


@router.post("/login", response_model=AuthResponse, summary="密码登录")
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    user, access_token, refresh_token = await auth_service.login_with_password(
        db, payload.email, payload.password, ip=_client_ip(request), user_agent=_client_ua(request)
    )
    _set_refresh_cookie(response, refresh_token)
    return AuthResponse(
        access_token=access_token,
        expires_in=settings.access_token_ttl_min * 60,
        user=UserOut.model_validate(user),
    )


@router.post("/login/code", response_model=AuthResponse, summary="验证码登录")
async def login_by_code(
    payload: CodeLoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    otp: OtpService = Depends(get_otp_service),
) -> AuthResponse:
    user, access_token, refresh_token = await auth_service.login_with_code(
        db, otp, payload.email, payload.code, ip=_client_ip(request), user_agent=_client_ua(request)
    )
    _set_refresh_cookie(response, refresh_token)
    return AuthResponse(
        access_token=access_token,
        expires_in=settings.access_token_ttl_min * 60,
        user=UserOut.model_validate(user),
    )


@router.post("/password/reset", response_model=OkResponse, summary="通过邮箱验证码重置密码")
async def reset_password(
    payload: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
    otp: OtpService = Depends(get_otp_service),
) -> OkResponse:
    await auth_service.reset_password(db, otp, payload.email, payload.code, payload.new_password)
    return OkResponse(message="密码已重置，请使用新密码登录")


@router.post("/refresh", response_model=RefreshResponse, summary="刷新访问令牌")
async def refresh(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    refresh_token: str | None = Cookie(default=None, alias=settings.refresh_cookie_name),
) -> RefreshResponse:
    user, access_token, new_refresh = await auth_service.rotate_session(
        db, refresh_token, ip=_client_ip(request), user_agent=_client_ua(request)
    )
    _set_refresh_cookie(response, new_refresh)
    return RefreshResponse(
        access_token=access_token,
        expires_in=settings.access_token_ttl_min * 60,
        user=UserOut.model_validate(user),
    )


@router.post("/logout", response_model=OkResponse, summary="退出登录")
async def logout(
    response: Response,
    db: AsyncSession = Depends(get_db),
    refresh_token: str | None = Cookie(default=None, alias=settings.refresh_cookie_name),
) -> OkResponse:
    await auth_service.logout(db, refresh_token)
    _clear_refresh_cookie(response)
    return OkResponse(message="已退出登录")


@router.get("/me", response_model=UserOut, summary="当前登录用户")
async def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user)
