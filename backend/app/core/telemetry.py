"""轻量埋点：把 LLM 调用异步写入 llm_calls。

原则：写库失败只记日志，绝不影响业务返回；队列有界，满了丢弃并告警。
"""

import asyncio
import contextlib
import contextvars
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

from app.core.logging import get_logger
from app.db.models.llm_call import LLMCall
from app.db.session import SessionLocal
from app.llm.pricing import estimate_cost

logger = get_logger(__name__)

_user_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "telemetry_user_id", default=None
)
_job_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "telemetry_job_id", default=None
)
_task: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "telemetry_task", default=None
)
_prompt_version: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "telemetry_prompt_version", default=None
)

_queue: asyncio.Queue[dict | None] | None = None
_writer_task: asyncio.Task | None = None


@contextlib.contextmanager
def bind_context(
    *,
    user_id: object | None = None,
    job_id: str | None = None,
    task: str | None = None,
    prompt_version: str | None = None,
) -> Iterator[None]:
    """给当前协程树绑定归属信息；未传的字段沿用外层上下文。"""
    tokens: list[tuple[contextvars.ContextVar, contextvars.Token]] = []
    if user_id is not None:
        tokens.append((_user_id, _user_id.set(str(user_id))))
    if job_id is not None:
        tokens.append((_job_id, _job_id.set(job_id)))
    if task is not None:
        tokens.append((_task, _task.set(task)))
    if prompt_version is not None:
        tokens.append((_prompt_version, _prompt_version.set(prompt_version)))
    try:
        yield
    finally:
        for var, token in reversed(tokens):
            var.reset(token)


def _as_uuid(value: str | None) -> uuid.UUID | None:
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError):
        return None


async def start_telemetry() -> None:
    global _queue, _writer_task
    if _writer_task is not None:
        return
    _queue = asyncio.Queue(maxsize=2000)
    _writer_task = asyncio.create_task(_writer_loop(), name="telemetry-writer")


async def stop_telemetry() -> None:
    global _queue, _writer_task
    if _writer_task is None:
        return
    try:
        if _queue is not None:
            _queue.put_nowait(None)
        await asyncio.wait_for(_writer_task, timeout=5)
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM 埋点 writer 关闭失败: %s", exc)
        _writer_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await _writer_task
    finally:
        _writer_task = None
        _queue = None


def emit_llm_call(
    *,
    model: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    duration_ms: int = 0,
    status: str = "success",
    error_code: str | None = None,
    finish_reason: str | None = None,
    prompt_version: str | None = None,
) -> None:
    """非阻塞写入一条调用记录；writer 未启动（测试/脚本）时直接跳过。"""
    if _writer_task is None or _queue is None:
        return

    cost = estimate_cost(model, prompt_tokens, completion_tokens)
    event = {
        "created_at": datetime.now(UTC),
        "user_id": _as_uuid(_user_id.get()),
        "job_id": _job_id.get(),
        "task": _task.get() or "unknown",
        "model": model,
        "prompt_version": prompt_version or _prompt_version.get(),
        "prompt_tokens": max(prompt_tokens, 0),
        "completion_tokens": max(completion_tokens, 0),
        "duration_ms": max(duration_ms, 0),
        "status": status,
        "error_code": error_code,
        "finish_reason": finish_reason,
        "cost": cost,
    }
    try:
        _queue.put_nowait(event)
    except asyncio.QueueFull:
        logger.warning("LLM 埋点队列已满，丢弃一条调用记录")


async def _writer_loop() -> None:
    assert _queue is not None
    queue = _queue
    batch: list[dict] = []
    while True:
        try:
            item = await asyncio.wait_for(queue.get(), timeout=2.0)
        except TimeoutError:
            if batch:
                await _flush(batch)
                batch = []
            continue

        if item is None:
            break
        batch.append(item)

        while len(batch) < 20:
            try:
                nxt = queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            if nxt is None:
                await _flush(batch)
                return
            batch.append(nxt)

        if len(batch) >= 20:
            await _flush(batch)
            batch = []

    if batch:
        await _flush(batch)


async def _flush(batch: list[dict]) -> None:
    if not batch:
        return
    try:
        async with SessionLocal() as session:
            session.add_all([LLMCall(**event) for event in batch])
            await session.commit()
    except Exception as exc:  # noqa: BLE001 - 埋点不能影响业务
        logger.warning("写入 LLM 调用记录失败 count=%s: %s", len(batch), exc)
