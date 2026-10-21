"""AI 配置状态与任务接口。"""

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from redis.asyncio import Redis

from app.core import errors
from app.core.config import settings
from app.core.deps import get_current_user
from app.db.models.user import User
from app.db.redis import get_redis
from app.llm.client import is_llm_configured
from app.llm.prompts import PROMPT_VERSION
from app.schemas.ai import AIConfigResponse, AIJobState
from app.services.ai_analysis_service import read_quota_used
from app.services.ai_job_service import (
    AIJobForbiddenError,
    AIJobNotFoundError,
    get_ai_job,
)
from app.services.ai_job_stream import stream_job_events

router = APIRouter(prefix="/ai", tags=["AI"])


@router.get("/config", response_model=AIConfigResponse, summary="AI 配置状态")
async def get_ai_config(
    user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> AIConfigResponse:
    quota_used = await read_quota_used(redis, user.id)
    return AIConfigResponse(
        configured=is_llm_configured(),
        model=settings.llm_model,
        prompt_version=PROMPT_VERSION,
        daily_quota=settings.effective_daily_quota(user.daily_analysis_quota),
        quota_used=quota_used,
    )


@router.get("/jobs/{job_id}", response_model=AIJobState, summary="查询 AI 分析任务")
async def get_job(
    job_id: str,
    user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> AIJobState:
    try:
        return await get_ai_job(redis, user.id, job_id)
    except AIJobNotFoundError as exc:
        raise errors.not_found("分析任务不存在或已过期") from exc
    except AIJobForbiddenError as exc:
        raise errors.forbidden() from exc


@router.get("/jobs/{job_id}/events", summary="AI 分析任务事件流（SSE）")
async def stream_job(
    job_id: str,
    user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> StreamingResponse:
    try:
        state = await get_ai_job(redis, user.id, job_id)
    except AIJobNotFoundError as exc:
        raise errors.not_found("分析任务不存在或已过期") from exc
    except AIJobForbiddenError as exc:
        raise errors.forbidden() from exc

    return StreamingResponse(
        stream_job_events(redis, user.id, job_id, state),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )
