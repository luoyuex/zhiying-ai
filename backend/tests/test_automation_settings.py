"""定时任务设置：API 读写、参数校验与用户隔离。"""

import uuid

from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.core.deps import get_current_user
from app.db.models.user import User
from app.db.session import SessionLocal
from app.main import app
from app.services.automation_settings_service import get_settings

VALID_FILTERS = {"final_n": 3, "max_change_pct": 7.0}


async def make_user() -> User:
    email = f"automation-{uuid.uuid4().hex[:10]}@example.com"
    user = User(email=email, nickname="Automation")
    async with SessionLocal() as session:
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


async def test_settings_default_and_roundtrip():
    user = await make_user()
    try:
        # 默认全关
        default = await get_settings(user.id)
        assert default.screener_enabled is False
        assert default.analysis_enabled is False
        assert default.strategy_settings == {}
        assert default.email_notify_enabled is False
        assert default.notify_email is None

        app.dependency_overrides[get_current_user] = lambda: user
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.put(
                "/api/v1/automation/settings",
                json={
                    "screener_enabled": True,
                    "analysis_enabled": True,
                    "screener_run_hour": 8,
                    "screener_run_minute": 30,
                    "analysis_run_hour": 21,
                    "analysis_run_minute": 5,
                    "strategy_settings": {
                        "main_force": {"enabled": True, "filters": VALID_FILTERS}
                    },
                    "email_notify_enabled": True,
                    "notify_email": " Notify@Example.com ",
                },
            )
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["screener_enabled"] is True
            assert body["analysis_enabled"] is True
            assert body["screener_run_hour"] == 8
            assert body["screener_run_minute"] == 30
            assert body["analysis_run_hour"] == 21
            assert body["analysis_run_minute"] == 5
            assert body["email_notify_enabled"] is True
            assert body["notify_email"] == "notify@example.com"
            # filters 补全默认值
            filters = body["strategy_settings"]["main_force"]["filters"]
            assert filters["final_n"] == 3
            assert filters["exclude_st"] is True

            response = await client.get("/api/v1/automation/settings")
            assert response.status_code == 200, response.text
            assert response.json()["strategy_settings"]["main_force"]["enabled"] is True
    finally:
        app.dependency_overrides.clear()
        async with SessionLocal() as session:
            await session.execute(delete(User).where(User.id == user.id))
            await session.commit()


async def test_settings_invalid_filters_rejected():
    user = await make_user()
    try:
        app.dependency_overrides[get_current_user] = lambda: user
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.put(
                "/api/v1/automation/settings",
                json={
                    "screener_enabled": True,
                    "analysis_enabled": False,
                    "strategy_settings": {
                        "main_force": {"enabled": True, "filters": {"final_n": 99}}
                    },
                },
            )
            assert response.status_code == 422, response.text

            response = await client.put(
                "/api/v1/automation/settings",
                json={
                    "screener_enabled": True,
                    "analysis_enabled": False,
                    "strategy_settings": {"unknown": {"enabled": True, "filters": {}}},
                },
            )
            assert response.status_code == 422, response.text

            # 非法执行时间
            response = await client.put(
                "/api/v1/automation/settings",
                json={
                    "screener_enabled": True,
                    "analysis_enabled": False,
                    "screener_run_hour": 25,
                    "strategy_settings": {},
                },
            )
            assert response.status_code == 422, response.text

            # 开启邮件通知但未填地址
            response = await client.put(
                "/api/v1/automation/settings",
                json={
                    "screener_enabled": True,
                    "email_notify_enabled": True,
                    "notify_email": "",
                    "strategy_settings": {},
                },
            )
            assert response.status_code == 422, response.text

            # 邮箱格式非法
            response = await client.put(
                "/api/v1/automation/settings",
                json={
                    "screener_enabled": True,
                    "email_notify_enabled": True,
                    "notify_email": "not-an-email",
                    "strategy_settings": {},
                },
            )
            assert response.status_code == 422, response.text

        # 两次失败请求都不应留下任何设置记录
        assert (await get_settings(user.id)).strategy_settings == {}
    finally:
        app.dependency_overrides.clear()
        async with SessionLocal() as session:
            await session.execute(delete(User).where(User.id == user.id))
            await session.commit()


async def test_settings_user_isolation():
    user = await make_user()
    other = await make_user()
    try:
        await get_settings(user.id)
        from app.schemas.automation import AutomationSettingsUpdate
        from app.services.automation_settings_service import update_settings

        await update_settings(
            user.id,
            AutomationSettingsUpdate.model_validate(
                {
                    "screener_enabled": True,
                    "analysis_enabled": False,
                    "strategy_settings": {
                        "value_stock": {"enabled": True, "filters": {"max_pe": 15}}
                    },
                }
            ),
        )
        other_settings = await get_settings(other.id)
        assert other_settings.strategy_settings == {}
        assert other_settings.screener_enabled is False
    finally:
        app.dependency_overrides.clear()
        async with SessionLocal() as session:
            await session.execute(delete(User).where(User.id.in_([user.id, other.id])))
            await session.commit()
