"""后台 P2：跨用户内容库（报告/选股/组合诊断/自选）只读查询。"""

import uuid
from datetime import datetime

from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.core.deps import get_current_user
from app.db.models.portfolio_diagnosis import PortfolioDiagnosisRecord
from app.db.models.screener_record import ScreenerRecord
from app.db.models.user import User
from app.db.session import SessionLocal
from app.main import app
from app.services.report_history_service import save_analysis_report
from app.services.watchlist_service import add_watchlist
from tests.test_admin import make_user
from tests.test_report_history import make_report


async def cleanup(*users: User) -> None:
    ids = [user.id for user in users]
    if not ids:
        return
    async with SessionLocal() as session:
        await session.execute(delete(User).where(User.id.in_(ids)))
        await session.commit()


async def seed_content(user: User) -> dict:
    report_id = await save_analysis_report(user.id, make_report("600519"))
    await add_watchlist(user.id, "600519", cost_price=10.0, quantity=100, note="内容库")
    async with SessionLocal() as session:
        screener = ScreenerRecord(
            user_id=user.id,
            strategy="low_price_bull",
            filters={"max_price": 10},
            result={
                "recommendations": [
                    {"rank": 1, "symbol": "600519", "name": "贵州茅台", "reasons": ["低价"]}
                ],
                "fund_flow": "资金面摘要",
                "industry": "行业摘要",
                "fundamental": "基本面摘要",
            },
            analyzed_count=6,
            recommendation_count=1,
            model="mock-model",
        )
        portfolio = PortfolioDiagnosisRecord(
            user_id=user.id,
            health_score=72,
            position_count=1,
            summary="组合健康度良好",
            model="mock-model",
            report={
                "health_score": 72,
                "summary": "组合健康度良好",
                "risk_notes": ["集中度偏高"],
                "allocation_advice": "保持仓位",
                "positions": [
                    {"symbol": "600519", "name": "贵州茅台", "action": "持有", "reason": "基本面稳健"}
                ],
            },
        )
        session.add_all([screener, portfolio])
        await session.commit()
        await session.refresh(screener)
        await session.refresh(portfolio)
    return {
        "report_id": str(report_id),
        "screener_id": str(screener.id),
        "portfolio_id": str(portfolio.id),
    }


async def test_admin_content_lists_and_details():
    admin = await make_user(role="admin", nickname="Boss")
    target = await make_user(nickname="Content Target")
    ids = await seed_content(target)
    app.dependency_overrides[get_current_user] = lambda: admin
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            # 报告
            response = await client.get("/api/v1/admin/reports", params={"q": target.email})
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["total"] == 1
            assert body["items"][0]["user_email"] == target.email
            assert body["items"][0]["symbol"] == "600519"

            response = await client.get(
                "/api/v1/admin/reports", params={"symbol": "600519", "q": target.email}
            )
            assert response.status_code == 200
            assert response.json()["total"] == 1

            response = await client.get(f"/api/v1/admin/reports/{ids['report_id']}")
            assert response.status_code == 200, response.text
            detail = response.json()
            assert detail["report"]["analysis"]["rating"] == "看多"
            assert detail["user_email"] == target.email

            # 选股记录
            response = await client.get(
                "/api/v1/admin/screener-records",
                params={"strategy": "low_price_bull", "q": target.email},
            )
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["total"] == 1
            assert body["items"][0]["picks"][0]["name"] == "贵州茅台"

            response = await client.get(
                f"/api/v1/admin/screener-records/{ids['screener_id']}"
            )
            assert response.status_code == 200
            detail = response.json()
            assert detail["filters"]["max_price"] == 10
            assert detail["result"]["fund_flow"] == "资金面摘要"

            # 组合诊断
            response = await client.get(
                "/api/v1/admin/portfolio-diagnoses", params={"q": target.email}
            )
            assert response.status_code == 200
            body = response.json()
            assert body["total"] == 1
            assert body["items"][0]["health_score"] == 72

            response = await client.get(
                f"/api/v1/admin/portfolio-diagnoses/{ids['portfolio_id']}"
            )
            assert response.status_code == 200
            detail = response.json()
            assert detail["report"]["positions"][0]["action"] == "持有"

            # 自选股
            response = await client.get(
                "/api/v1/admin/watchlist-items", params={"q": target.email}
            )
            assert response.status_code == 200
            body = response.json()
            assert body["total"] == 1
            assert body["items"][0]["name"] == "贵州茅台"
            assert body["items"][0]["cost_price"] == 10.0

            # 不存在的记录
            response = await client.get(f"/api/v1/admin/reports/{uuid.uuid4()}")
            assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()
        await cleanup(admin, target)


async def test_admin_content_requires_admin():
    normal = await make_user()
    app.dependency_overrides[get_current_user] = lambda: normal
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            for path in (
                "/api/v1/admin/reports",
                "/api/v1/admin/screener-records",
                "/api/v1/admin/portfolio-diagnoses",
                "/api/v1/admin/watchlist-items",
            ):
                response = await client.get(path)
                assert response.status_code == 403, path
    finally:
        app.dependency_overrides.clear()
        await cleanup(normal)
