"""组合 AI 诊断：持仓汇总、结果合并与接口。"""

import uuid
from datetime import datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.core.deps import get_current_user
from app.db.models.user import User
from app.db.redis import get_redis
from app.db.session import SessionLocal
from app.main import app
from app.schemas.portfolio import PortfolioDiagnosisResponse
from app.services.ai_analysis_service import quota_key
from app.services.portfolio_service import PortfolioEmptyError, diagnose_portfolio
from app.services.report_history_service import (
    get_latest_portfolio_diagnosis,
    get_portfolio_diagnosis,
    list_portfolio_diagnoses,
)
from app.services.watchlist_service import add_watchlist
from tests.test_watchlist import FakeMarket, make_user


class FakeLLM:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.prompts: list[str] = []

    async def generate_json(self, _system: str, user_prompt: str) -> dict:
        self.prompts.append(user_prompt)
        return self.payload


def portfolio_payload() -> dict:
    return {
        "health_score": 72,
        "summary": "组合持仓偏集中，注意单一标的风险。",
        "risk_notes": ["单票占比过高", "缺少低相关资产"],
        "allocation_advice": "将单一持仓控制在总市值 30% 以内。",
        "positions": [
            {"symbol": "600519", "action": "减仓", "reason": "成本高于现价，评级偏空"},
            {"symbol": "999999", "action": "清仓", "reason": "模型编造，应被忽略"},
        ],
    }


async def cleanup_user(user_id: object) -> None:
    redis = get_redis()
    await redis.delete(quota_key(user_id))
    async with SessionLocal() as session:
        await session.execute(delete(User).where(User.id == user_id))
        await session.commit()


async def test_portfolio_diagnosis_merges_positions():
    user = await make_user()
    try:
        await add_watchlist(user.id, "600519", note="核心", cost_price=100, quantity=100)
        await add_watchlist(user.id, "000001")
        llm = FakeLLM(portfolio_payload())

        result = await diagnose_portfolio(
            get_redis(),
            user.id,
            5,
            FakeMarket(),
            llm_client=llm,
        )

        assert result.health_score == 72
        by_symbol = {item.symbol: item for item in result.positions}
        assert set(by_symbol) == {"600519", "000001"}
        assert by_symbol["600519"].action == "减仓"
        assert by_symbol["600519"].name == "贵州茅台"
        assert by_symbol["000001"].action == "观望"
        assert by_symbol["000001"].reason == "AI 未给出明确建议"
        # 600519 的持仓与浮亏应进入提示词
        assert '"pnl_pct"' in llm.prompts[0]
        assert '"cost_price":100.0' in llm.prompts[0]
        assert result.quota_used == 1
    finally:
        await cleanup_user(user.id)


async def test_portfolio_diagnosis_saved_to_history():
    user = await make_user()
    try:
        await add_watchlist(user.id, "600519")
        result = await diagnose_portfolio(
            get_redis(),
            user.id,
            5,
            FakeMarket(),
            llm_client=FakeLLM(portfolio_payload()),
        )
        assert result.id is not None

        summaries = await list_portfolio_diagnoses(user.id, limit=10)
        assert [item.id for item in summaries] == [result.id]
        assert summaries[0].health_score == 72
        assert summaries[0].position_count == 1
        assert summaries[0].summary == result.summary

        detail = await get_portfolio_diagnosis(user.id, result.id)
        assert detail is not None
        assert detail.report.summary == result.summary

        latest = await get_latest_portfolio_diagnosis(user.id)
        assert latest is not None
        assert latest.id == result.id

        assert await get_portfolio_diagnosis(uuid.uuid4(), result.id) is None
    finally:
        await cleanup_user(user.id)


async def test_portfolio_diagnosis_requires_watchlist():
    user = await make_user()
    try:
        with pytest.raises(PortfolioEmptyError):
            await diagnose_portfolio(
                get_redis(),
                user.id,
                5,
                FakeMarket(),
                llm_client=FakeLLM(portfolio_payload()),
            )
    finally:
        await cleanup_user(user.id)


async def test_portfolio_api(monkeypatch):
    user = await make_user()

    async def fake_diagnose(*_args, **_kwargs) -> PortfolioDiagnosisResponse:
        return PortfolioDiagnosisResponse(
            health_score=60,
            summary="组合整体中性。",
            risk_notes=["注意集中度"],
            allocation_advice="均衡配置。",
            positions=[],
            generated_at=datetime.now(),
            model="test-model",
        )

    monkeypatch.setattr("app.api.v1.watchlist.diagnose_portfolio", fake_diagnose)
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post("/api/v1/watchlist/portfolio-analysis")
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["health_score"] == 60
            assert body["summary"] == "组合整体中性。"
    finally:
        app.dependency_overrides.clear()
        await cleanup_user(user.id)


async def test_portfolio_history_api():
    user = await make_user()
    try:
        await add_watchlist(user.id, "600519")
        result = await diagnose_portfolio(
            get_redis(),
            user.id,
            5,
            FakeMarket(),
            llm_client=FakeLLM(portfolio_payload()),
        )
        assert result.id is not None

        app.dependency_overrides[get_current_user] = lambda: user
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get(
                "/api/v1/watchlist/portfolio-analysis/history", params={"limit": 10}
            )
            assert response.status_code == 200, response.text
            body = response.json()
            assert [item["id"] for item in body] == [str(result.id)]
            assert body[0]["health_score"] == 72

            response = await client.get("/api/v1/watchlist/portfolio-analysis/latest")
            assert response.status_code == 200, response.text
            assert response.json()["id"] == str(result.id)

            response = await client.get(
                f"/api/v1/watchlist/portfolio-analysis/history/{result.id}"
            )
            assert response.status_code == 200, response.text
            assert response.json()["report"]["summary"] == result.summary

            response = await client.get(
                f"/api/v1/watchlist/portfolio-analysis/history/{uuid.uuid4()}"
            )
            assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()
        await cleanup_user(user.id)
