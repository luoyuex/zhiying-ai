"""主力选股后台任务：状态机、worker 执行与接口。"""

import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from httpx import ASGITransport, AsyncClient

from app.core.deps import get_current_user
from app.db.models.user import User
from app.llm.client import LLMRequestError
from app.main import app
from app.schemas.ai import AIJobStatus
from app.schemas.screener import (
    MainForceAnalysisResponse,
    MainForceRecommendation,
    ScreenerJobState,
)
from app.services import screener_job_service

TZ = ZoneInfo("Asia/Shanghai")


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key: str):
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.store[key] = value

    async def delete(self, *keys: str) -> None:
        for key in keys:
            self.store.pop(key, None)


class FakePool:
    def __init__(self) -> None:
        self.jobs: list[tuple[str, tuple, dict]] = []

    async def enqueue_job(self, function: str, *args, **kwargs) -> None:
        self.jobs.append((function, args, kwargs))


def make_state(job_id: str = "job-1") -> ScreenerJobState:
    now = datetime.now(TZ)
    return ScreenerJobState(
        job_id=job_id,
        status=AIJobStatus.QUEUED,
        phase="排队中",
        created_at=now,
        updated_at=now,
    )


def make_response() -> MainForceAnalysisResponse:
    return MainForceAnalysisResponse(
        fund_flow="资金面",
        industry="行业",
        fundamental="基本面",
        recommendations=[
            MainForceRecommendation(rank=1, symbol="603236", name="移远通信")
        ],
        generated_at=datetime.now(TZ),
        model="mock-model",
        analyzed_count=40,
    )


async def test_run_screener_job_saves_record(monkeypatch):
    redis = FakeRedis()
    user_id = uuid.uuid4()
    await screener_job_service._save_state(redis, user_id, make_state())
    phases: list[str] = []

    async def fake_analyze(_redis, _user_id, _quota, _request, *, on_phase=None):
        await on_phase("三位分析师整体分析中")
        phases.append("三位分析师整体分析中")
        return make_response()

    record_id = uuid.uuid4()

    async def fake_save(*_args, **_kwargs):
        return record_id

    monkeypatch.setattr(screener_job_service, "analyze_main_force", fake_analyze)
    monkeypatch.setattr(screener_job_service, "save_screener_record", fake_save)

    await screener_job_service.run_screener_job_task(
        redis, "job-1", str(user_id), 5, "main_force", {"final_n": 3}
    )

    state = await screener_job_service.get_screener_job(redis, user_id, "job-1")
    assert state.status == AIJobStatus.SUCCEEDED
    assert state.phase == "已完成"
    assert state.record_id == record_id
    assert phases == ["三位分析师整体分析中"]


async def test_run_screener_job_records_failure(monkeypatch):
    redis = FakeRedis()
    user_id = uuid.uuid4()
    await screener_job_service._save_state(redis, user_id, make_state())

    async def broken(*_args, **_kwargs):
        raise LLMRequestError("mock timeout")

    monkeypatch.setattr(screener_job_service, "analyze_main_force", broken)

    await screener_job_service.run_screener_job_task(
        redis, "job-1", str(user_id), 5, "main_force", {"final_n": 3}
    )

    state = await screener_job_service.get_screener_job(redis, user_id, "job-1")
    assert state.status == AIJobStatus.FAILED
    assert state.error_code == "LLM_ERROR"


async def test_start_screener_job_reuses_active_job(monkeypatch):
    redis = FakeRedis()
    user_id = uuid.uuid4()
    pool = FakePool()

    async def fake_worker_alive(_redis):
        return True

    async def fake_pool():
        return pool

    monkeypatch.setattr(screener_job_service, "is_llm_configured", lambda: True)
    monkeypatch.setattr(screener_job_service, "worker_alive", fake_worker_alive)
    monkeypatch.setattr(screener_job_service, "get_arq_pool", fake_pool)
    monkeypatch.setattr(screener_job_service.settings, "ai_job_execution", "arq")

    payload = screener_job_service.MainForceAnalysisRequest(final_n=3)
    first = await screener_job_service.start_screener_job(
        redis, user_id, 5, "main_force", payload
    )
    second = await screener_job_service.start_screener_job(
        redis, user_id, 5, "main_force", payload
    )

    assert first.job_id == second.job_id
    assert first.strategy == "main_force"
    assert len(pool.jobs) == 1
    assert pool.jobs[0][0] == "run_screener_job"
    assert first.status == AIJobStatus.QUEUED


async def test_screener_jobs_api(monkeypatch):
    user = User(id=uuid.uuid4(), email="screener-job@example.com", nickname="Job")
    state = make_state()

    async def fake_start(*_args, **_kwargs):
        return state

    async def fake_active(*_args, **_kwargs):
        return state

    async def fake_get(*_args, **_kwargs):
        return state

    monkeypatch.setattr("app.api.v1.screener.start_screener_job", fake_start)
    monkeypatch.setattr("app.api.v1.screener.get_active_screener_job", fake_active)
    monkeypatch.setattr("app.api.v1.screener.get_screener_job", fake_get)
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post(
                "/api/v1/screener/main-force/jobs", json={"final_n": 3}
            )
            assert response.status_code == 200, response.text
            assert response.json()["job_id"] == "job-1"

            response = await client.get("/api/v1/screener/main-force/jobs/active")
            assert response.status_code == 200, response.text
            assert response.json()["status"] == "queued"

            response = await client.get("/api/v1/screener/main-force/jobs/job-1")
            assert response.status_code == 200, response.text
            assert response.json()["phase"] == "排队中"
    finally:
        app.dependency_overrides.clear()


async def test_strategy_job_endpoints(monkeypatch):
    user = User(id=uuid.uuid4(), email="strategy-job@example.com", nickname="Job")
    strategies: list[str] = []

    async def fake_start(_redis, _user_id, _quota, strategy, _payload):
        strategies.append(strategy)
        return make_state()

    monkeypatch.setattr("app.api.v1.screener.start_screener_job", fake_start)
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post(
                "/api/v1/screener/low-price-bull/jobs",
                json={"final_n": 3, "max_price": 10, "min_profit_growth": 100},
            )
            assert response.status_code == 200, response.text

            response = await client.post(
                "/api/v1/screener/small-cap/jobs",
                json={
                    "final_n": 3,
                    "max_market_cap": 50,
                    "min_profit_growth": 100,
                    "min_revenue_growth": 10,
                },
            )
            assert response.status_code == 200, response.text

            response = await client.post(
                "/api/v1/screener/profit-growth/jobs",
                json={"final_n": 3, "min_profit_growth": 10},
            )
            assert response.status_code == 200, response.text

            response = await client.post(
                "/api/v1/screener/value-stock/jobs",
                json={
                    "final_n": 3,
                    "max_pe": 20,
                    "max_pb": 1.5,
                    "min_dividend_yield": 1,
                    "max_debt_ratio": 30,
                },
            )
            assert response.status_code == 200, response.text
    finally:
        app.dependency_overrides.clear()

    assert strategies == [
        "low_price_bull",
        "small_cap",
        "profit_growth",
        "value_stock",
    ]
