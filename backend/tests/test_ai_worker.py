"""ARQ 入队、worker 心跳与 inline 回退测试。"""

import asyncio
import uuid

import pytest

from app.core.config import settings
from app.db.redis import get_redis
from app.services import ai_job_service
from app.services.ai_job_service import (
    WORKER_HEARTBEAT_KEY,
    AIWorkerUnavailableError,
    get_active_job,
    start_ai_job,
    worker_alive,
)
from app.worker import run_ai_job


class FakePool:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple, dict]] = []

    async def enqueue_job(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return object()


async def test_worker_heartbeat_visibility():
    redis = get_redis()
    await redis.set(WORKER_HEARTBEAT_KEY, "1", ex=30)
    try:
        assert await worker_alive(redis) is True
    finally:
        await redis.delete(WORKER_HEARTBEAT_KEY)

    assert await worker_alive(redis) is False


async def test_start_blocks_when_worker_missing(monkeypatch):
    redis = get_redis()
    await redis.delete(WORKER_HEARTBEAT_KEY)
    monkeypatch.setattr(settings, "ai_job_execution", "arq")
    monkeypatch.setattr(ai_job_service, "is_llm_configured", lambda: True)

    with pytest.raises(AIWorkerUnavailableError):
        await start_ai_job(redis, uuid.uuid4(), 5, "600519")


async def test_start_enqueues_arq_job(monkeypatch):
    redis = get_redis()
    user_id = uuid.uuid4()
    monkeypatch.setattr(settings, "ai_job_execution", "arq")
    monkeypatch.setattr(ai_job_service, "is_llm_configured", lambda: True)

    async def alive(_: object) -> bool:
        return True

    pool = FakePool()

    async def fake_pool() -> FakePool:
        return pool

    monkeypatch.setattr(ai_job_service, "worker_alive", alive)
    monkeypatch.setattr(ai_job_service, "get_arq_pool", fake_pool)

    try:
        state = await start_ai_job(redis, user_id, 5, "600519")
        assert state.status.value == "queued"
        assert len(pool.calls) == 1

        args, kwargs = pool.calls[0]
        assert args == ("run_ai_job", state.job_id, str(user_id), 5, "600519", False)
        assert kwargs["_job_id"] == state.job_id
    finally:
        for job_id in (state.job_id if "state" in locals() else "",):
            if job_id:
                await redis.delete(f"ai:job:{job_id}")
        await redis.delete(f"ai:active:{user_id}:600519")


async def test_active_job_lookup(monkeypatch):
    redis = get_redis()
    user_id = uuid.uuid4()
    monkeypatch.setattr(settings, "ai_job_execution", "arq")
    monkeypatch.setattr(ai_job_service, "is_llm_configured", lambda: True)

    async def alive(_: object) -> bool:
        return True

    async def fake_pool() -> FakePool:
        return FakePool()

    monkeypatch.setattr(ai_job_service, "worker_alive", alive)
    monkeypatch.setattr(ai_job_service, "get_arq_pool", fake_pool)

    state = None
    try:
        state = await start_ai_job(redis, user_id, 5, "sh600519")
        active = await get_active_job(redis, user_id, "600519")
        assert active is not None
        assert active.job_id == state.job_id
        assert await get_active_job(redis, user_id, "000001") is None

        await redis.delete(f"ai:active:{user_id}:600519")
        assert await get_active_job(redis, user_id, "600519") is None
    finally:
        if state is not None:
            await redis.delete(f"ai:job:{state.job_id}")
        await redis.delete(f"ai:active:{user_id}:600519")


async def test_force_request_creates_new_job_over_plain_job(monkeypatch):
    redis = get_redis()
    user_id = uuid.uuid4()
    monkeypatch.setattr(settings, "ai_job_execution", "arq")
    monkeypatch.setattr(ai_job_service, "is_llm_configured", lambda: True)

    async def alive(_: object) -> bool:
        return True

    pool = FakePool()

    async def fake_pool() -> FakePool:
        return pool

    monkeypatch.setattr(ai_job_service, "worker_alive", alive)
    monkeypatch.setattr(ai_job_service, "get_arq_pool", fake_pool)

    state = None
    forced = None
    try:
        state = await start_ai_job(redis, user_id, 5, "600519")
        forced = await start_ai_job(redis, user_id, 5, "600519", force=True)

        assert forced.job_id != state.job_id
        assert forced.force is True
        assert len(pool.calls) == 2
        assert pool.calls[1][0][-1] is True
    finally:
        for job_id in (state.job_id if state else None, forced.job_id if forced else None):
            if job_id:
                await redis.delete(f"ai:job:{job_id}")
        await redis.delete(f"ai:active:{user_id}:600519")


async def test_force_request_reuses_running_force_job(monkeypatch):
    redis = get_redis()
    user_id = uuid.uuid4()
    monkeypatch.setattr(settings, "ai_job_execution", "arq")
    monkeypatch.setattr(ai_job_service, "is_llm_configured", lambda: True)

    async def alive(_: object) -> bool:
        return True

    pool = FakePool()

    async def fake_pool() -> FakePool:
        return pool

    monkeypatch.setattr(ai_job_service, "worker_alive", alive)
    monkeypatch.setattr(ai_job_service, "get_arq_pool", fake_pool)

    state = None
    try:
        state = await start_ai_job(redis, user_id, 5, "600519", force=True)
        again = await start_ai_job(redis, user_id, 5, "600519", force=True)

        assert again.job_id == state.job_id
        assert len(pool.calls) == 1
    finally:
        if state is not None:
            await redis.delete(f"ai:job:{state.job_id}")
        await redis.delete(f"ai:active:{user_id}:600519")


async def test_active_job_ignores_finished_job(monkeypatch):
    redis = get_redis()
    user_id = uuid.uuid4()
    monkeypatch.setattr(settings, "ai_job_execution", "arq")
    monkeypatch.setattr(ai_job_service, "is_llm_configured", lambda: True)

    async def alive(_: object) -> bool:
        return True

    async def fake_pool() -> FakePool:
        return FakePool()

    monkeypatch.setattr(ai_job_service, "worker_alive", alive)
    monkeypatch.setattr(ai_job_service, "get_arq_pool", fake_pool)

    state = None
    try:
        state = await start_ai_job(redis, user_id, 5, "600519")
        await ai_job_service._update_state(
            redis, state.job_id, user_id, status=ai_job_service.AIJobStatus.FAILED
        )
        assert await get_active_job(redis, user_id, "600519") is None
    finally:
        if state is not None:
            await redis.delete(f"ai:job:{state.job_id}")
        await redis.delete(f"ai:active:{user_id}:600519")


async def test_inline_execution_runs_task(monkeypatch):
    redis = get_redis()
    user_id = uuid.uuid4()
    called = asyncio.Event()

    async def fake_run(*_: object) -> None:
        called.set()

    monkeypatch.setattr(settings, "ai_job_execution", "inline")
    monkeypatch.setattr(ai_job_service, "is_llm_configured", lambda: True)
    monkeypatch.setattr(ai_job_service, "_run_job", fake_run)

    try:
        state = await start_ai_job(redis, user_id, 5, "300750")
        await asyncio.wait_for(called.wait(), timeout=2)
    finally:
        await redis.delete(f"ai:job:{state.job_id}")
        await redis.delete(f"ai:active:{user_id}:300750")


async def test_worker_entry_delegates(monkeypatch):
    captured: dict = {}

    async def fake_run(redis, job_id, user_id, daily_quota, symbol, force=False):
        captured.update(
            redis=redis,
            job_id=job_id,
            user_id=user_id,
            daily_quota=daily_quota,
            symbol=symbol,
            force=force,
        )

    monkeypatch.setattr("app.worker.run_ai_job_task", fake_run)

    await run_ai_job({"redis": "fake-redis"}, "job-1", "user-1", 5, "600519", True)

    assert captured == {
        "redis": "fake-redis",
        "job_id": "job-1",
        "user_id": "user-1",
        "daily_quota": 5,
        "symbol": "600519",
        "force": True,
    }
