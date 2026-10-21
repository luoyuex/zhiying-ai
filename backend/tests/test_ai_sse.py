"""AI 任务 SSE 事件流测试。"""

import asyncio
import uuid

from httpx import ASGITransport, AsyncClient

from app.core.deps import get_current_user
from app.db.models.user import User
from app.db.redis import get_redis
from app.main import app
from app.providers.base import now_shanghai
from app.schemas.ai import AIJobState, AIJobStatus
from app.services.ai_job_service import _save_state


async def test_job_events_stream_snapshot_phase_done():
    redis = get_redis()
    user = User(id=uuid.uuid4(), email="sse@example.com", nickname="SSE")
    job_id = uuid.uuid4().hex
    created = now_shanghai()
    state = AIJobState(
        job_id=job_id,
        status=AIJobStatus.RUNNING,
        symbol="600519",
        phase="六位分析师分析中 0/6",
        created_at=created,
        updated_at=created,
    )
    await _save_state(redis, job_id, user.id, state)

    async def publish_progress() -> None:
        await asyncio.sleep(0.4)
        await _save_state(
            redis,
            job_id,
            user.id,
            state.model_copy(
                update={"phase": "六位分析师分析中 3/6", "updated_at": now_shanghai()}
            ),
        )
        await asyncio.sleep(0.2)
        await _save_state(
            redis,
            job_id,
            user.id,
            state.model_copy(
                update={
                    "status": AIJobStatus.FAILED,
                    "phase": "失败",
                    "error_code": "MOCK",
                    "error_message": "mock failure",
                    "updated_at": now_shanghai(),
                }
            ),
        )

    app.dependency_overrides[get_current_user] = lambda: user
    task = asyncio.create_task(publish_progress())
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://testserver", timeout=10
        ) as client:
            events: list[str] = []
            async with client.stream(
                "GET", f"/api/v1/ai/jobs/{job_id}/events"
            ) as response:
                assert response.status_code == 200
                assert response.headers["content-type"].startswith("text/event-stream")
                async for line in response.aiter_lines():
                    if line.startswith("event:"):
                        events.append(line.split(":", 1)[1].strip())
                    if events and events[-1] == "done":
                        break

            assert events[0] == "snapshot"
            assert "phase" in events
            assert events[-1] == "done"
        await task
    finally:
        app.dependency_overrides.clear()
        await redis.delete(f"ai:job:{job_id}")
