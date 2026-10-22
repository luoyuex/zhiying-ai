"""选股记录：落库、列表、详情与用户隔离。"""

import uuid

from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.core.deps import get_current_user
from app.db.models.user import User
from app.db.session import SessionLocal
from app.main import app
from app.providers.base import now_shanghai
from app.schemas.screener import MainForceAnalysisResponse, MainForceRecommendation
from app.services.screener_history_service import (
    get_screener_record,
    list_screener_records,
    save_screener_record,
)

FILTERS = {
    "final_n": 3,
    "max_change_pct": 7.0,
    "exclude_st": True,
    "exclude_gem": True,
    "exclude_star": True,
    "exclude_bj": True,
}


async def make_user() -> User:
    email = f"screener-history-{uuid.uuid4().hex[:10]}@example.com"
    user = User(email=email, nickname="Screener History")
    async with SessionLocal() as session:
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


def make_analysis(symbol: str = "603236", name: str = "移远通信") -> MainForceAnalysisResponse:
    return MainForceAnalysisResponse(
        fund_flow="资金面报告",
        industry="行业报告",
        fundamental="基本面报告",
        recommendations=[
            MainForceRecommendation(
                rank=1,
                symbol=symbol,
                name=name,
                reasons=["资金面强"],
                position="20-25%",
                investment_period="中期",
            )
        ],
        generated_at=now_shanghai(),
        model="mock-model",
        analyzed_count=40,
        quota_used=1,
        quota_limit=5,
    )


async def test_screener_record_save_list_and_user_isolation():
    user = await make_user()
    other = User(id=uuid.uuid4(), email="screener-other@example.com", nickname="Other")
    try:
        record_id = await save_screener_record(
            user.id, "main_force", FILTERS, make_analysis()
        )

        summaries = await list_screener_records(user.id, "main_force", 5)
        assert len(summaries) == 1
        assert summaries[0].id == record_id
        assert summaries[0].recommendation_count == 1
        assert summaries[0].analyzed_count == 40
        assert summaries[0].final_n == 3
        assert summaries[0].picks[0].symbol == "603236"

        detail = await get_screener_record(user.id, record_id, "main_force")
        assert detail is not None
        assert detail.filters["final_n"] == 3
        assert detail.result.recommendations[0].name == "移远通信"

        assert await get_screener_record(other.id, record_id, "main_force") is None
        assert await list_screener_records(other.id, "main_force") == []
    finally:
        async with SessionLocal() as session:
            await session.execute(delete(User).where(User.id == user.id))
            await session.commit()


async def test_screener_records_api():
    user = await make_user()
    try:
        first_id = await save_screener_record(
            user.id, "main_force", FILTERS, make_analysis()
        )
        second_id = await save_screener_record(
            user.id,
            "main_force",
            {**FILTERS, "final_n": 5},
            make_analysis("002074", "国轩高科"),
        )
        app.dependency_overrides[get_current_user] = lambda: user
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get(
                "/api/v1/screener/main-force/records", params={"limit": 10}
            )
            assert response.status_code == 200, response.text
            body = response.json()
            assert [item["id"] for item in body] == [str(second_id), str(first_id)]
            assert body[0]["picks"][0]["name"] == "国轩高科"

            response = await client.get(
                f"/api/v1/screener/main-force/records/{first_id}"
            )
            assert response.status_code == 200, response.text
            detail = response.json()
            assert detail["filters"]["final_n"] == 3
            assert detail["result"]["recommendations"][0]["symbol"] == "603236"

            response = await client.get(
                f"/api/v1/screener/main-force/records/{uuid.uuid4()}"
            )
            assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()
        async with SessionLocal() as session:
            await session.execute(delete(User).where(User.id == user.id))
            await session.commit()


async def test_analysis_endpoint_saves_record(monkeypatch):
    user = await make_user()

    async def fake_analyze(_redis, _user_id, _quota, _request):
        return make_analysis()

    monkeypatch.setattr("app.api.v1.screener.analyze_main_force", fake_analyze)
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post(
                "/api/v1/screener/main-force/analysis",
                json={"final_n": 3, "max_change_pct": 7},
            )
            assert response.status_code == 200, response.text
            record_id = response.json()["record_id"]
            assert record_id

            response = await client.get(
                "/api/v1/screener/main-force/records", params={"limit": 10}
            )
            assert response.status_code == 200, response.text
            body = response.json()
            assert len(body) == 1
            assert body[0]["id"] == record_id
            assert body[0]["picks"][0]["symbol"] == "603236"

            response = await client.get(
                f"/api/v1/screener/main-force/records/{record_id}"
            )
            assert response.status_code == 200, response.text
            assert response.json()["filters"]["final_n"] == 3
    finally:
        app.dependency_overrides.clear()
        async with SessionLocal() as session:
            await session.execute(delete(User).where(User.id == user.id))
            await session.commit()
