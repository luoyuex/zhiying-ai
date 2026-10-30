"""后台管理 P0：权限、用户查询/写操作、审计与任务台账。"""

import uuid
from datetime import UTC, datetime, timedelta

from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.core.config import settings
from app.core.deps import get_current_user
from app.db.models.admin_audit_log import AdminAuditLog
from app.db.models.ai_job import AIJob
from app.db.models.refresh_token import RefreshToken
from app.db.models.user import User
from app.db.redis import get_redis
from app.db.session import SessionLocal
from app.main import app
from app.services.ai_analysis_service import quota_key
from app.services.job_ledger import (
    record_job_created,
    record_job_failed,
    record_job_running,
    record_job_succeeded,
)
from app.services.platform_settings_service import (
    get_default_daily_quota,
    set_default_daily_quota,
)


class FakeRedis:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    async def mget(self, keys):
        return [self.data.get(key) for key in keys]

    async def get(self, key):
        return self.data.get(key)

    async def delete(self, key):
        self.data.pop(key, None)
        return 1


async def make_user(*, role: str = "user", nickname: str = "Admin Test") -> User:
    email = f"admin-{uuid.uuid4().hex[:10]}@example.com"
    user = User(
        email=email,
        nickname=nickname,
        role=role,
        daily_analysis_quota=5,
    )
    async with SessionLocal() as session:
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


async def cleanup(*users: User) -> None:
    user_ids = [user.id for user in users]
    if not user_ids:
        return
    async with SessionLocal() as session:
        await session.execute(
            delete(AdminAuditLog).where(
                AdminAuditLog.target_id.in_([str(uid) for uid in user_ids])
                | AdminAuditLog.admin_user_id.in_(user_ids)
            )
        )
        await session.execute(delete(User).where(User.id.in_(user_ids)))
        await session.commit()


async def test_admin_requires_admin_role():
    normal = await make_user()
    redis = FakeRedis()
    app.dependency_overrides[get_current_user] = lambda: normal
    app.dependency_overrides[get_redis] = lambda: redis
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get("/api/v1/admin/users")
            assert response.status_code == 403, response.text
            assert response.json()["code"] == "FORBIDDEN"
    finally:
        app.dependency_overrides.clear()
        await cleanup(normal)


async def test_admin_user_list_update_reset_and_revoke():
    admin = await make_user(role="admin", nickname="Boss")
    target = await make_user(nickname="Target")
    redis = FakeRedis()
    redis.data[quota_key(target.id)] = "3"

    async with SessionLocal() as session:
        session.add(
            RefreshToken(
                user_id=target.id,
                token_hash=uuid.uuid4().hex * 2,
                expires_at=datetime.now(UTC) + timedelta(days=7),
                ip="203.0.113.9",
                user_agent="pytest",
            )
        )
        await session.commit()

    app.dependency_overrides[get_current_user] = lambda: admin
    app.dependency_overrides[get_redis] = lambda: redis
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get(
                "/api/v1/admin/users", params={"q": target.email, "page_size": 10}
            )
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["total"] == 1
            item = body["items"][0]
            assert item["email"] == target.email
            assert item["today_used"] == 3
            assert item["effective_quota"] == settings.effective_daily_quota(5)
            assert item["quota_override_active"] == (
                settings.ai_daily_quota_override > 0
            )

            response = await client.get(f"/api/v1/admin/users/{target.id}")
            assert response.status_code == 200, response.text
            detail = response.json()
            assert detail["today_used"] == 3
            assert detail["counts"]["reports"] == 0
            assert detail["automation"]["screener_enabled"] is False

            response = await client.patch(
                f"/api/v1/admin/users/{target.id}",
                json={"daily_analysis_quota": 9},
            )
            assert response.status_code == 200, response.text
            assert response.json()["daily_analysis_quota"] == 9

            response = await client.post(f"/api/v1/admin/users/{target.id}/reset-quota")
            assert response.status_code == 200, response.text
            assert response.json()["used_before"] == 3
            assert quota_key(target.id) not in redis.data

            response = await client.post(
                f"/api/v1/admin/users/{target.id}/revoke-sessions"
            )
            assert response.status_code == 200, response.text
            assert response.json()["revoked"] == 1

            response = await client.get(
                f"/api/v1/admin/users/{target.id}/sessions"
            )
            assert response.status_code == 200, response.text
            sessions = response.json()["items"]
            assert len(sessions) == 1
            assert sessions[0]["active"] is False
    finally:
        app.dependency_overrides.clear()

    async with SessionLocal() as session:
        updated = await session.get(User, target.id)
        assert updated is not None
        assert updated.daily_analysis_quota == 9

        token = await session.scalar(
            select(RefreshToken).where(RefreshToken.user_id == target.id)
        )
        assert token is not None
        assert token.revoked_at is not None

        actions = (
            await session.scalars(
                select(AdminAuditLog.action).where(
                    AdminAuditLog.target_id == str(target.id)
                )
            )
        ).all()
        assert set(actions) == {"user.update", "user.reset_quota", "user.revoke_sessions"}

    await cleanup(admin, target)


async def test_admin_quota_policy_read_write():
    admin = await make_user(role="admin", nickname="Boss")
    async with SessionLocal() as session:
        before = await get_default_daily_quota(session)

    app.dependency_overrides[get_current_user] = lambda: admin
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get("/api/v1/admin/quota-policy")
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["default_daily_quota"] == before
            assert body["override_active"] == (settings.ai_daily_quota_override > 0)

            response = await client.put(
                "/api/v1/admin/quota-policy", json={"default_daily_quota": 7}
            )
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["default_daily_quota"] == 7
            # 未勾选同步时不动现有用户
            assert body["updated_users"] == 0

            response = await client.put(
                "/api/v1/admin/quota-policy", json={"default_daily_quota": 101}
            )
            assert response.status_code == 422

        async with SessionLocal() as session:
            assert await get_default_daily_quota(session) == 7
    finally:
        async with SessionLocal() as session:
            await set_default_daily_quota(session, before, admin_id=None)
        app.dependency_overrides.clear()
        await cleanup(admin)


async def test_admin_cannot_ban_admin_account():
    admin = await make_user(role="admin", nickname="Boss")
    redis = FakeRedis()
    app.dependency_overrides[get_current_user] = lambda: admin
    app.dependency_overrides[get_redis] = lambda: redis
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.patch(
                f"/api/v1/admin/users/{admin.id}",
                json={"status": "banned"},
            )
            assert response.status_code == 422, response.text
    finally:
        app.dependency_overrides.clear()
        await cleanup(admin)


async def test_job_ledger_lifecycle():
    user = await make_user()
    job_id = uuid.uuid4().hex
    failed_job_id = uuid.uuid4().hex
    report_id = uuid.uuid4()
    try:
        await record_job_created(
            job_id=job_id,
            kind="analysis",
            user_id=user.id,
            symbol="600519",
            trigger="manual",
        )
        await record_job_running(job_id, "准备行情数据")
        await record_job_succeeded(job_id, report_id=report_id)

        await record_job_created(
            job_id=failed_job_id,
            kind="screener",
            user_id=user.id,
            strategy="main_force",
        )
        await record_job_failed(
            failed_job_id,
            error_code="LLM_ERROR",
            error_message="mock failure",
        )

        async with SessionLocal() as session:
            done = await session.get(AIJob, job_id)
            assert done is not None
            assert done.status == "succeeded"
            assert done.symbol == "600519"
            assert done.started_at is not None
            assert done.finished_at is not None
            assert done.report_id == report_id

            failed = await session.get(AIJob, failed_job_id)
            assert failed is not None
            assert failed.status == "failed"
            assert failed.error_code == "LLM_ERROR"
            assert failed.strategy == "main_force"
    finally:
        async with SessionLocal() as session:
            await session.execute(
                delete(AIJob).where(AIJob.id.in_([job_id, failed_job_id]))
            )
            await session.commit()
        await cleanup(user)
