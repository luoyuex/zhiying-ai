"""分析报告历史：落库、列表、详情与用户隔离。"""

import uuid

from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.core.deps import get_current_user
from app.db.models.user import User
from app.db.session import SessionLocal
from app.main import app
from app.providers.base import now_shanghai
from app.schemas.ai import AIAnalysisPayload, AIAnalysisResponse
from app.services.report_history_service import (
    get_analysis_report,
    list_analysis_reports,
    save_analysis_report,
)


async def make_user() -> User:
    email = f"report-{uuid.uuid4().hex[:10]}@example.com"
    user = User(
        email=email,
        nickname="Report Test",
        daily_analysis_quota=5,
    )
    async with SessionLocal() as session:
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


def make_report(symbol: str = "600519", name: str = "贵州茅台") -> AIAnalysisResponse:
    now = now_shanghai()
    return AIAnalysisResponse(
        symbol=symbol,
        name=name,
        model="mock-model",
        prompt_version="multi_agent_decision.v1:test",
        generated_at=now,
        data_as_of=now,
        data_source="tencent / eastmoney",
        cached=False,
        quota_used=1,
        quota_limit=5,
        analysis=AIAnalysisPayload(
            rating="看多",
            confidence=70,
            trend="上升",
            summary="技术面与情绪面偏强，给出看多结论。",
            key_points=["站上 MA20"],
            risks=["资金流数据缺失"],
            watch="关注 MA20 支撑",
        ),
        analysts=[],
        decision=None,
        web_search_used=False,
        web_sources=[],
        disclaimer="仅供研究参考",
    )


async def test_report_save_list_and_user_isolation():
    user = await make_user()
    other = User(id=uuid.uuid4(), email="other@example.com", nickname="Other")
    try:
        report_id = await save_analysis_report(user.id, make_report())

        summaries = await list_analysis_reports(user.id, symbol="600519", limit=5)
        assert len(summaries) == 1
        assert summaries[0].id == report_id
        assert summaries[0].rating == "看多"

        detail = await get_analysis_report(user.id, report_id)
        assert detail is not None
        assert detail.report.symbol == "600519"
        assert detail.report.analysis.confidence == 70

        assert await get_analysis_report(other.id, report_id) is None
        assert await list_analysis_reports(other.id) == []
    finally:
        async with SessionLocal() as session:
            await session.execute(delete(User).where(User.id == user.id))
            await session.commit()


async def test_reports_api():
    user = await make_user()
    try:
        report_id = await save_analysis_report(user.id, make_report())
        other_report_id = await save_analysis_report(user.id, make_report("300750"))
        app.dependency_overrides[get_current_user] = lambda: user
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get("/api/v1/analysis/reports", params={"limit": 50})
            assert response.status_code == 200, response.text
            body = response.json()
            assert len(body) == 2
            assert {item["symbol"] for item in body} == {"600519", "300750"}
            assert {item["id"] for item in body} == {str(report_id), str(other_report_id)}

            response = await client.get("/api/v1/analysis/reports", params={"symbol": "600519"})
            assert response.status_code == 200, response.text
            body = response.json()
            assert len(body) == 1
            assert body[0]["id"] == str(report_id)
            assert body[0]["rating"] == "看多"

            response = await client.get(f"/api/v1/analysis/reports/{report_id}")
            assert response.status_code == 200, response.text
            assert response.json()["report"]["symbol"] == "600519"

            response = await client.get(f"/api/v1/analysis/reports/{uuid.uuid4()}")
            assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()
        async with SessionLocal() as session:
            await session.execute(delete(User).where(User.id == user.id))
            await session.commit()


async def test_reports_pagination_search_and_stats():
    user = await make_user()
    try:
        fixtures = [
            ("600519", "贵州茅台"),
            ("300750", "宁德时代"),
            ("600036", "招商银行"),
            ("000001", "平安银行"),
            ("600519", "贵州茅台"),
        ]
        report_ids = [
            await save_analysis_report(user.id, make_report(symbol, name))
            for symbol, name in fixtures
        ]

        app.dependency_overrides[get_current_user] = lambda: user
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            seen: list[str] = []
            for offset in (0, 2, 4):
                response = await client.get(
                    "/api/v1/analysis/reports",
                    params={"limit": 2, "offset": offset},
                )
                assert response.status_code == 200, response.text
                seen.extend(item["id"] for item in response.json())

            assert len(seen) == 5
            assert len(set(seen)) == 5
            assert set(seen) == {str(report_id) for report_id in report_ids}

            response = await client.get(
                "/api/v1/analysis/reports",
                params={"keyword": "600519"},
            )
            assert response.status_code == 200, response.text
            body = response.json()
            assert len(body) == 2
            assert {item["symbol"] for item in body} == {"600519"}

            response = await client.get(
                "/api/v1/analysis/reports",
                params={"keyword": "茅台"},
            )
            assert response.status_code == 200, response.text
            assert len(response.json()) == 2

            response = await client.get("/api/v1/analysis/reports/stats")
            assert response.status_code == 200, response.text
            assert response.json() == {"total": 5, "stock_count": 4}

            response = await client.get(
                "/api/v1/analysis/reports/stats",
                params={"keyword": "600519"},
            )
            assert response.status_code == 200, response.text
            assert response.json() == {"total": 2, "stock_count": 1}

            response = await client.get(
                "/api/v1/analysis/reports/stats",
                params={"keyword": "不存在"},
            )
            assert response.status_code == 200, response.text
            assert response.json() == {"total": 0, "stock_count": 0}
    finally:
        app.dependency_overrides.clear()
        async with SessionLocal() as session:
            await session.execute(delete(User).where(User.id == user.id))
            await session.commit()
