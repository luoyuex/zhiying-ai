from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.errors import AppError, ErrorCode
from app.core.logging import get_logger, setup_logging
from app.db.redis import close_redis, get_redis
from app.db.session import SessionLocal, engine
from app.providers.http import close_http_client

setup_logging(settings.debug)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("%s 后端启动 | debug=%s | email_mode=%s", settings.app_name, settings.debug, settings.email_mode)
    yield
    await close_http_client()
    await close_redis()
    await engine.dispose()
    logger.info("%s 后端已关闭", settings.app_name)


app = FastAPI(
    title=f"{settings.app_name} API",
    version="0.1.0",
    description="智赢 AI —— A 股 AI 分析工作台后端",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppError)
async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "message": exc.message, "detail": exc.detail},
    )


@app.exception_handler(RequestValidationError)
async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    raw_errors = exc.errors()
    first = raw_errors[0] if raw_errors else {}
    location = ".".join(str(part) for part in first.get("loc", []) if part not in ("body", "query"))
    message = str(first.get("msg", "请求参数不合法")).replace("Value error, ", "")
    if location:
        message = f"{location}: {message}"

    # 只保留可序列化字段，pydantic 的 ctx 里可能带 ValueError 实例
    safe_errors = [
        {
            "loc": [str(part) for part in item.get("loc", [])],
            "msg": str(item.get("msg", "")),
            "type": str(item.get("type", "")),
        }
        for item in raw_errors
    ]
    return JSONResponse(
        status_code=422,
        content={
            "code": ErrorCode.VALIDATION_ERROR,
            "message": message,
            "detail": safe_errors,
        },
    )


@app.exception_handler(Exception)
async def handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("未捕获异常: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"code": ErrorCode.INTERNAL_ERROR, "message": "服务内部错误，请稍后重试"},
    )


@app.get("/", tags=["系统"], summary="服务信息")
async def root() -> dict:
    return {"name": settings.app_name, "version": "0.1.0", "docs": "/docs"}


@app.get("/health", tags=["系统"], summary="健康检查")
async def health() -> JSONResponse:
    db_ok = False
    redis_ok = False

    try:
        async with SessionLocal() as session:
            await session.execute(text("SELECT 1"))
        db_ok = True
    except Exception as exc:  # noqa: BLE001
        logger.error("数据库健康检查失败: %s", exc)

    try:
        redis_ok = bool(await get_redis().ping())
    except Exception as exc:  # noqa: BLE001
        logger.error("Redis 健康检查失败: %s", exc)

    healthy = db_ok and redis_ok
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={
            "status": "ok" if healthy else "degraded",
            "db": "ok" if db_ok else "down",
            "redis": "ok" if redis_ok else "down",
        },
    )


app.include_router(api_router)
