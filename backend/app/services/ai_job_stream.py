"""AI 分析任务事件流：Redis Pub/Sub → SSE。"""

import time
from collections.abc import AsyncIterator

from redis.asyncio import Redis

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.ai import AIJobState, AIJobStatus
from app.services.ai_job_service import get_ai_job, job_events_channel

logger = get_logger(__name__)

TERMINAL_STATUSES = {AIJobStatus.SUCCEEDED, AIJobStatus.FAILED}
HEARTBEAT_SECONDS = 15


def format_sse(event: str, data: str) -> str:
    return f"event: {event}\ndata: {data}\n\n"


async def stream_job_events(
    redis: Redis,
    user_id: object,
    job_id: str,
    initial: AIJobState,
) -> AsyncIterator[str]:
    """先发快照，再持续推送；任务终态后发送 done 并关闭。

    订阅发生在读取快照之前，避免任务恰好在两次请求之间完成而丢事件。
    """
    pubsub = redis.pubsub()
    await pubsub.subscribe(job_events_channel(job_id))
    deadline = time.monotonic() + settings.llm_job_timeout_seconds + 120

    try:
        try:
            state = await get_ai_job(redis, user_id, job_id)
        except Exception:  # noqa: BLE001 - 快照竞态时沿用创建时的状态
            state = initial

        yield format_sse("snapshot", state.model_dump_json())
        if state.status in TERMINAL_STATUSES:
            yield format_sse("done", state.model_dump_json())
            return

        while time.monotonic() < deadline:
            message = await pubsub.get_message(
                ignore_subscribe_messages=True,
                timeout=HEARTBEAT_SECONDS,
            )
            if message is None:
                yield ": ping\n\n"
                continue

            raw = message.get("data")
            try:
                state = AIJobState.model_validate_json(raw)
            except (TypeError, ValueError):
                logger.warning("忽略无法解析的 AI job 事件 job_id=%s", job_id)
                continue

            event = "done" if state.status in TERMINAL_STATUSES else "phase"
            yield format_sse(event, state.model_dump_json())
            if event == "done":
                return

        yield format_sse("error", '{"message":"事件流超时，请刷新页面查看任务状态"}')
    finally:
        try:
            await pubsub.unsubscribe(job_events_channel(job_id))
            await pubsub.aclose()
        except Exception as exc:  # noqa: BLE001
            logger.warning("关闭 AI job 订阅失败 job_id=%s: %s", job_id, exc)
