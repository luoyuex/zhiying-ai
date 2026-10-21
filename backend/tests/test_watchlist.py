"""自选股：增删查、行情降级与用户隔离。"""

import uuid

from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.core.deps import get_current_user
from app.db.models.user import User
from app.db.models.watchlist import WatchlistItem
from app.db.session import SessionLocal
from app.main import app
from app.providers.base import now_shanghai
from app.providers.models import Quote
from app.providers.symbols import parse_symbol
from app.schemas.ai import AIJobState, AIJobStatus
from app.services import watchlist_service
from app.services.market_service import MarketDataService
from app.services.report_history_service import save_analysis_report
from app.services.watchlist_service import (
    add_watchlist,
    list_watchlist,
    remove_watchlist,
    update_watchlist,
)
from tests.test_report_history import make_report


class FakeMarket:
    async def get_quote(self, symbol: str) -> Quote:
        if symbol == "000001":
            raise RuntimeError("mock quote failure")
        return Quote(
            symbol=symbol,
            name=f"测试{symbol}",
            price=10.0,
            change_pct=1.2,
            source="test",
            fetched_at=now_shanghai(),
        )


async def make_user() -> User:
    user = User(email=f"watch-{uuid.uuid4().hex[:10]}@example.com", nickname="Watch")
    async with SessionLocal() as session:
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


async def test_watchlist_service_flow():
    user = await make_user()
    other = await make_user()
    try:
        symbol, added = await add_watchlist(
            user.id, "600519", note="核心持仓", cost_price=95.5, quantity=100
        )
        assert (symbol, added) == ("600519", True)

        same_symbol, added_again = await add_watchlist(user.id, "sh600519")
        assert (same_symbol, added_again) == ("600519", False)

        await add_watchlist(user.id, "000001")
        assert await update_watchlist(user.id, "600519", {"note": "长期持有"}) is True

        report_id = await save_analysis_report(user.id, make_report("600519"))
        entries = await list_watchlist(user.id, FakeMarket())
        by_symbol = {entry.symbol: entry for entry in entries}

        assert by_symbol["600519"].name == "贵州茅台"
        assert by_symbol["600519"].price == 10.0
        assert by_symbol["600519"].note == "长期持有"
        assert by_symbol["600519"].cost_price == 95.5
        assert by_symbol["600519"].quantity == 100
        assert by_symbol["600519"].latest is not None
        assert by_symbol["600519"].latest.report_id == str(report_id)
        assert by_symbol["600519"].latest.rating == "看多"
        assert by_symbol["600519"].latest.confidence == 70

        assert by_symbol["000001"].price is None
        assert by_symbol["000001"].name == "平安银行"
        assert by_symbol["000001"].latest is None

        assert await list_watchlist(other.id, FakeMarket()) == []

        assert await remove_watchlist(user.id, "600519") is True
        assert await remove_watchlist(user.id, "600519") is False
        assert [entry.symbol for entry in await list_watchlist(user.id, FakeMarket())] == [
            "000001"
        ]
    finally:
        async with SessionLocal() as session:
            await session.execute(delete(User).where(User.id.in_([user.id, other.id])))
            await session.commit()


async def test_watchlist_api(monkeypatch):
    user = await make_user()

    async def fake_quote(_: MarketDataService, symbol: str) -> Quote:
        return Quote(
            symbol=symbol,
            name="贵州茅台",
            price=100.0,
            change_pct=2.5,
            source="test",
            fetched_at=now_shanghai(),
        )

    monkeypatch.setattr(MarketDataService, "get_quote", fake_quote)
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post("/api/v1/watchlist", json={"symbol": "600519"})
            assert response.status_code == 200, response.text
            assert response.json() == {"symbol": "600519", "added": True}

            response = await client.post("/api/v1/watchlist", json={"symbol": "600519"})
            assert response.status_code == 200
            assert response.json()["added"] is False

            response = await client.get("/api/v1/watchlist")
            assert response.status_code == 200
            body = response.json()
            assert body[0]["symbol"] == "600519"
            assert body[0]["price"] == 100.0
            assert body[0]["name"] == "贵州茅台"

            response = await client.get("/api/v1/watchlist/600519")
            assert response.status_code == 200
            assert response.json() == {"symbol": "600519", "in_watchlist": True}

            response = await client.delete("/api/v1/watchlist/600519")
            assert response.status_code == 204

            response = await client.get("/api/v1/watchlist")
            assert response.json() == []

            response = await client.post("/api/v1/watchlist", json={"symbol": "ABC"})
            assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()
        async with SessionLocal() as session:
            await session.execute(delete(User).where(User.id == user.id))
            await session.commit()


async def test_watchlist_api_update_and_batch(monkeypatch):
    user = await make_user()

    async def fake_start(_redis, _user_id, _quota, raw_symbol, force=False):
        state = AIJobState(
            job_id=f"job-{parse_symbol(raw_symbol).code}",
            status=AIJobStatus.QUEUED,
            symbol=parse_symbol(raw_symbol).code,
            phase="排队中",
            created_at=now_shanghai(),
            updated_at=now_shanghai(),
        )
        assert force is True
        return state

    monkeypatch.setattr(watchlist_service, "start_ai_job", fake_start)
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post(
                "/api/v1/watchlist",
                json={"symbol": "600519", "note": "核心", "cost_price": 90, "quantity": 200},
            )
            assert response.status_code == 200, response.text

            response = await client.patch(
                "/api/v1/watchlist/600519",
                json={"note": "长期持有", "cost_price": None, "quantity": 300},
            )
            assert response.status_code == 200, response.text
            assert response.json() == {"symbol": "600519", "in_watchlist": True}

            async with SessionLocal() as session:
                row = await session.scalar(
                    select(WatchlistItem).where(WatchlistItem.user_id == user.id)
                )
                assert row.note == "长期持有"
                assert row.cost_price is None
                assert row.quantity == 300

            response = await client.patch(
                "/api/v1/watchlist/000001", json={"note": "不在自选"}
            )
            assert response.status_code == 404

            response = await client.post(
                "/api/v1/watchlist/batch-analysis",
                json={"symbols": ["600519", "000001", "ABC"], "force": True},
            )
            assert response.status_code == 200, response.text
            body = response.json()
            assert body[0] == {
                "symbol": "600519",
                "job_id": "job-600519",
                "status": "queued",
                "error_code": None,
                "error_message": None,
            }
            assert body[1]["job_id"] == "job-000001"
            assert body[2]["status"] == "failed"
            assert body[2]["error_code"] == "INVALID_SYMBOL"
    finally:
        app.dependency_overrides.clear()
        async with SessionLocal() as session:
            await session.execute(delete(User).where(User.id == user.id))
            await session.commit()
