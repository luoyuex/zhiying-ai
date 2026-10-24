"""后台 P1：成本日报、任务中心与重跑、定时执行记录。"""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.core.deps import get_current_user
from app.db.models.admin_audit_log import AdminAuditLog
from app.db.models.ai_job import AIJob
from app.db.models.automation_run import AutomationRun
from app.db.models.llm_call import LLMCall
from app.db.models.user import User
from app.db.redis import get_redis
from app.db.session import SessionLocal
from app.main import app
from app.services.admin import jobs as jobs_service
from app.services.job_ledger import record_job_created, record_job_failed
from tests.test_admin import FakeRedis, make_user


async def cleanup(*users: User) -> None:
    ids = [user.id for user in users]
    if not ids:
        return
    async with SessionLocal() as session:
        await session.execute(
            delete(AdminAuditLog).where(AdminAuditLog.admin_user_id.in_(ids))
        )
        await session.execute(delete(LLMCall).where(LLMCall.user_id.in_(ids)))
        await session.execute(delete(User).where(User.id.in_(ids)))
        await session.commit()


def make_llm_call(
    user_id: uuid.UUID,
    *,
    task: str = "analysis",
    status: str = "success",
    cost: float | None = 0.01,
    tokens: tuple[int, int] = (100, 50),
) -> LLMCall:
    return LLMCall(
        created_at=datetime.now(UTC),
        user_id=user_id,
        task=task,
        model="mock-model",
        prompt_tokens=tokens[0],
        completion_tokens=tokens[1],
        duration_ms=1200,
        status=status,
        cost=cost,
    )


async def test_admin_costs_summary_and_calls():
    admin = await make_user(role="admin", nickname="Boss")
    target = await make_user(nickname="Cost Target")
    try:
        async with SessionLocal() as session:
            session.add_all(
                [
                    make_llm_call(target.id, task="analysis", cost=0.01),
                    make_llm_call(target.id, task="screener", cost=0.02),
                    make_llm_call(
                        target.id, task="analysis", status="error", cost=None
                    ),
                ]
            )
            await session.commit()

        app.dependency_overrides[get_current_user] = lambda: admin
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get("/api/v1/admin/costs/summary", params={"days": 7})
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["calls"] == 3
            assert body["failures"] == 1
            assert body["unpriced_calls"] == 1
            assert body["cost"] == 0.03
            assert len(body["daily"]) == 7
            assert body["top_tasks"][0]["task"] == "screener"  # 成本最高
            assert body["top_users"][0]["email"] == target.email
            assert body["data_since"] is not None

            response = await client.get(
                "/api/v1/admin/costs/calls",
                params={"task": "analysis", "q": target.email},
            )
            assert response.status_code == 200, response.text
            page = response.json()
            assert page["total"] == 2
            assert all(item["task"] == "analysis" for item in page["items"])

            response = await client.get(
                "/api/v1/admin/costs/calls", params={"status": "error"}
            )
            assert response.status_code == 200
            assert response.json()["total"] == 1
            assert response.json()["items"][0]["cost"] is None
    finally:
        app.dependency_overrides.clear()
        await cleanup(admin, target)


async def test_admin_jobs_list_detail_and_retry(monkeypatch):
    admin = await make_user(role="admin", nickname="Boss")
    target = await make_user(nickname="Job Target")
    job_id = uuid.uuid4().hex
    ok_job_id = uuid.uuid4().hex
    await record_job_created(
        job_id=job_id,
        kind="analysis",
        user_id=target.id,
        symbol="600519",
        trigger="scheduled",
    )
    await record_job_failed(
        job_id, error_code="LLM_ERROR", error_message="mock failure", phase="失败"
    )
    await record_job_created(
        job_id=ok_job_id, kind="analysis", user_id=target.id, symbol="000001"
    )

    retried: dict = {}

    async def fake_start_ai_job(redis, user_id, quota, symbol, force=False, *, trigger="manual"):
        retried.update(
            {"user_id": user_id, "symbol": symbol, "force": force, "trigger": trigger}
        )
        return SimpleNamespace(job_id="new-job-1", status=SimpleNamespace(value="queued"))

    monkeypatch.setattr(jobs_service, "start_ai_job", fake_start_ai_job)
    app.dependency_overrides[get_current_user] = lambda: admin
    app.dependency_overrides[get_redis] = lambda: FakeRedis()
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get(
                "/api/v1/admin/jobs", params={"status": "failed", "q": "600519"}
            )
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["total"] == 1
            assert body["items"][0]["id"] == job_id
            assert body["items"][0]["trigger"] == "scheduled"
            assert body["items"][0]["user_email"] == target.email

            response = await client.get(f"/api/v1/admin/jobs/{job_id}")
            assert response.status_code == 200
            assert response.json()["error_code"] == "LLM_ERROR"

            # 成功任务不能重跑
            response = await client.post(f"/api/v1/admin/jobs/{ok_job_id}/retry")
            assert response.status_code == 409
            assert response.json()["code"] == "JOB_NOT_RETRYABLE"

            response = await client.post(f"/api/v1/admin/jobs/{job_id}/retry")
            assert response.status_code == 200, response.text
            assert response.json()["job_id"] == "new-job-1"
            assert retried["symbol"] == "600519"
            assert retried["trigger"] == "manual"

        # 写审计
        async with SessionLocal() as session:
            audit = await session.scalar(
                select(AdminAuditLog).where(
                    AdminAuditLog.action == "job.retry",
                    AdminAuditLog.target_id == job_id,
                )
            )
        assert audit is not None
        assert audit.admin_user_id == admin.id
    finally:
        app.dependency_overrides.clear()
        await cleanup(admin, target)


async def test_admin_retry_screener_job(monkeypatch):
    admin = await make_user(role="admin", nickname="Boss")
    target = await make_user(nickname="Screener Target")
    job_id = uuid.uuid4().hex
    await record_job_created(
        job_id=job_id,
        kind="screener",
        user_id=target.id,
        strategy="low_price_bull",
        meta={"filters": {}},
    )
    await record_job_failed(job_id, error_code="LLM_ERROR", error_message="mock")

    called: dict = {}

    async def fake_start_screener_job(redis, user_id, quota, strategy, payload, *, trigger="manual"):
        called.update({"strategy": strategy, "trigger": trigger})
        return SimpleNamespace(job_id="new-screener-1", status=SimpleNamespace(value="queued"))

    monkeypatch.setattr(jobs_service, "start_screener_job", fake_start_screener_job)
    app.dependency_overrides[get_current_user] = lambda: admin
    app.dependency_overrides[get_redis] = lambda: FakeRedis()
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post(f"/api/v1/admin/jobs/{job_id}/retry")
            assert response.status_code == 200, response.text
            assert response.json()["job_id"] == "new-screener-1"
        assert called == {"strategy": "low_price_bull", "trigger": "manual"}
    finally:
        app.dependency_overrides.clear()
        await cleanup(admin, target)


async def test_admin_automation_runs_api():
    admin = await make_user(role="admin", nickname="Boss")
    target = await make_user(nickname="Auto Target")
    today = datetime.now().date()
    try:
        async with SessionLocal() as session:
            session.add_all(
                [
                    AutomationRun(
                        run_date=today,
                        user_id=target.id,
                        line="screener",
                        status="enqueued",
                        enqueued=2,
                    ),
                    AutomationRun(
                        run_date=today,
                        user_id=target.id,
                        line="analysis",
                        status="skipped_quota",
                        reason="额度不足",
                    ),
                ]
            )
            await session.commit()

        app.dependency_overrides[get_current_user] = lambda: admin
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get(
                "/api/v1/admin/automation-runs",
                params={"run_date": today.isoformat()},
            )
            assert response.status_code == 200, response.text
            assert response.json()["total"] == 2

            response = await client.get(
                "/api/v1/admin/automation-runs", params={"status": "skipped_quota"}
            )
            body = response.json()
            assert body["total"] == 1
            assert body["items"][0]["reason"] == "额度不足"
            assert body["items"][0]["line"] == "analysis"
    finally:
        app.dependency_overrides.clear()
        await cleanup(admin, target)


async def test_admin_p1_endpoints_require_admin():
    normal = await make_user()
    app.dependency_overrides[get_current_user] = lambda: normal
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            for path in (
                "/api/v1/admin/costs/summary",
                "/api/v1/admin/costs/calls",
                "/api/v1/admin/jobs",
                "/api/v1/admin/automation-runs",
            ):
                response = await client.get(path)
                assert response.status_code == 403, path
    finally:
        app.dependency_overrides.clear()
        await cleanup(normal)
