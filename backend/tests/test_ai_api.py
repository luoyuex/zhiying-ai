"""AI 接口装配测试：未配置提示、配置状态与鉴权。"""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

import app.api.v1.ai as ai_module
import app.api.v1.stocks as stocks_module
import app.services.ai_job_service as ai_job_service
from app.core.config import settings
from app.core.deps import get_current_user
from app.db.models.user import User
from app.db.redis import get_redis
from app.main import app
from app.services.ai_analysis_service import quota_key


@pytest.fixture
async def client():
    user = User(
        id=uuid.uuid4(),
        email="ai-api@example.com",
        nickname="AI API",
        daily_analysis_quota=5,
    )
    app.dependency_overrides[get_current_user] = lambda: user
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
    app.dependency_overrides.clear()


async def test_ai_config_reports_unconfigured(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(ai_module, "is_llm_configured", lambda: False)
    monkeypatch.setattr(settings, "ai_daily_quota_override", 0)

    response = await client.get("/api/v1/ai/config")

    assert response.status_code == 200
    body = response.json()
    assert body["configured"] is False
    assert body["daily_quota"] == 5
    assert body["quota_used"] == 0
    assert body["prompt_version"].startswith("multi_agent_decision.v4:")


async def test_ai_config_quota_override(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(ai_module, "is_llm_configured", lambda: False)
    monkeypatch.setattr(settings, "ai_daily_quota_override", 9999)

    response = await client.get("/api/v1/ai/config")

    assert response.status_code == 200
    assert response.json()["daily_quota"] == 9999


async def test_ai_analysis_fails_clearly_when_unconfigured(
    client: AsyncClient, monkeypatch
):
    monkeypatch.setattr(stocks_module, "is_llm_configured", lambda: False)

    response = await client.post("/api/v1/stocks/600519/ai-analysis")

    assert response.status_code == 503
    body = response.json()
    assert body["code"] == "LLM_NOT_CONFIGURED"
    assert "LLM_BASE_URL" in body["message"]


async def test_ai_analysis_quota_checked_before_job(client: AsyncClient, monkeypatch):
    """额度用尽时在创建任务前就拒绝，不能先拉行情再失败。"""
    monkeypatch.setattr(stocks_module, "is_llm_configured", lambda: True)
    monkeypatch.setattr(ai_job_service, "is_llm_configured", lambda: True)
    monkeypatch.setattr(settings, "ai_daily_quota_override", 0)

    user = User(
        id=uuid.uuid4(),
        email="quota@example.com",
        nickname="Quota",
        daily_analysis_quota=1,
    )
    app.dependency_overrides[get_current_user] = lambda: user

    redis = get_redis()
    key = quota_key(user.id)
    try:
        await redis.set(key, 1, ex=60)
        response = await client.post("/api/v1/stocks/600519/ai-analysis")
    finally:
        await redis.delete(key)

    assert response.status_code == 429
    body = response.json()
    assert body["code"] == "ANALYSIS_QUOTA_EXCEEDED"
    assert body["detail"]["reset_seconds"] > 0


async def test_job_not_found(client: AsyncClient):
    response = await client.get("/api/v1/ai/jobs/does-not-exist")

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


async def test_active_job_none(client: AsyncClient):
    response = await client.get("/api/v1/ai/jobs/active", params={"symbol": "600519"})

    assert response.status_code == 200
    assert response.json() is None


async def test_active_job_rejects_invalid_symbol(client: AsyncClient):
    response = await client.get("/api/v1/ai/jobs/active", params={"symbol": "ABC"})

    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_SYMBOL"


async def test_ai_config_requires_login():
    app.dependency_overrides.clear()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        response = await ac.get("/api/v1/ai/config")

    assert response.status_code == 401
