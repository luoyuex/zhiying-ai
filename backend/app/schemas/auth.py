from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

OtpPurpose = Literal["register", "login", "reset"]

PASSWORD_RULE = "密码至少 8 位，且必须同时包含字母和数字"


class SendCodeRequest(BaseModel):
    email: EmailStr
    purpose: OtpPurpose = "register"

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class SendCodeResponse(BaseModel):
    sent: bool = True
    expires_in: int
    cooldown: int
    message: str = "验证码已发送，请查收邮件"


class _PasswordMixin(BaseModel):
    @staticmethod
    def _ensure_strength(value: str) -> str:
        if not any(ch.isalpha() for ch in value) or not any(ch.isdigit() for ch in value):
            raise ValueError(PASSWORD_RULE)
        return value


class RegisterRequest(_PasswordMixin):
    email: EmailStr
    code: str = Field(pattern=r"^\d{6}$")
    password: str = Field(min_length=8, max_length=64)
    nickname: str = Field(min_length=2, max_length=20)

    @field_validator("password")
    @classmethod
    def check_password_strength(cls, value: str) -> str:
        return cls._ensure_strength(value)


    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("nickname")
    @classmethod
    def strip_nickname(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("昵称不能为空")
        return value

    @model_validator(mode="after")
    def password_not_same_as_email(self) -> "RegisterRequest":
        local_part = self.email.split("@")[0].lower()
        if self.password.lower() == local_part:
            raise ValueError("密码不能与邮箱前缀相同")
        return self


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=64)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class CodeLoginRequest(BaseModel):
    email: EmailStr
    code: str = Field(pattern=r"^\d{6}$")

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class ResetPasswordRequest(_PasswordMixin):
    email: EmailStr
    code: str = Field(pattern=r"^\d{6}$")
    new_password: str = Field(min_length=8, max_length=64)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("new_password")
    @classmethod
    def check_new_password(cls, value: str) -> str:
        if not any(ch.isalpha() for ch in value) or not any(ch.isdigit() for ch in value):
            raise ValueError(PASSWORD_RULE)
        return value


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    nickname: str
    role: str
    status: str
    email_verified_at: datetime | None = None
    daily_analysis_quota: int = 5
    created_at: datetime


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


class RefreshResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


class OkResponse(BaseModel):
    ok: bool = True
    message: str = "操作成功"
