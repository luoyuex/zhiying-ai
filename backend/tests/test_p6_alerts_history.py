"""P6 增强：评级变化标记、调仓记录与关键价位提醒。"""

import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.core.deps import get_current_user
from app.db.models.automation_settings import AutomationSettings
from app.db.models.user import User
from app.db.session import SessionLocal
from app.main import app
from app.providers.base import now_shanghai
from app.providers.models import Quote
from app.schemas.ai import AIAnalysisPayload, AIAnalysisResponse
from app.services import price_alert_service
from app.services.price_alert_service import (
    PriceAlertLimitError,
    cancel_alert,
    create_alert,
    list_alerts,
    run_price_alert_check,
)
from app.services.report_history_service import (
    compute_rating_change,
    list_analysis_reports,
    save_analysis_report,
)
from app.services.watchlist_service import (
    add_watchlist,
    list_position_history,
    update_watchlist,
)
from tests.test_report_history import make_report, make_user

TZ_SHANGHAI = ZoneInfo("Asia/Shanghai")


def make_rating_report(symbol: str, rating: str) -> AIAnalysisResponse:
    report = make_report(symbol)
    return report.model_copy(
        update={
            "analysis": AIAnalysisPayload(
                rating=rating,
                confidence=60,
                trend="震荡",
                summary="测试结论。",
                key_points=["要点"],
                risks=["风险"],
                watch="观察",
            )
        }
    )


def make_quote(price: float, symbol: str = "600519") -> Quote:
    return Quote(
        symbol=symbol,
        name="贵州茅台",
        price=price,
        change_pct=1.0,
        source="test",
        fetched_at=now_shanghai(),
    )


async def cleanup_user(user_id: object) -> None:
    async with SessionLocal() as session:
        await session.execute(delete(User).where(User.id == user_id))
        await session.commit()


async def test_compute_rating_change_directions():
    assert compute_rating_change("买入", None) is None
    assert compute_rating_change("买入", "持有") == "up"
    assert compute_rating_change("持有", "买入") == "down"
    assert compute_rating_change("持有", "持有") == "flat"
    # 未知评级口径不产生误判
    assert compute_rating_change("强烈推荐", "买入") is None
    assert compute_rating_change("买入", "不知名") is None


async def test_rating_change_recorded_on_save():
    user = await make_user()
    try:
        first_id = await save_analysis_report(user.id, make_rating_report("600519", "看多"))
        assert compute_rating_change("看多", "看多") == "flat"  # 帮助函数自检

        second_id = await save_analysis_report(user.id, make_rating_report("600519", "看空"))
        third_id = await save_analysis_report(user.id, make_rating_report("600519", "看多"))

        summaries = await list_analysis_reports(user.id, symbol="600519", limit=10)
        by_id = {item.id: item for item in summaries}
        # 第一份：无上一份
        assert by_id[first_id].rating_change is None
        assert by_id[first_id].prev_rating is None
        # 第二份：看空 vs 看多 → 下调
        assert by_id[second_id].rating_change == "down"
        assert by_id[second_id].prev_rating == "看多"
        # 第三份：看多 vs 看空 → 上调
        assert by_id[third_id].rating_change == "up"
        assert by_id[third_id].prev_rating == "看空"

        # 结果对象本身也带回标记（供 job 状态与缓存复用）
        detail = await list_analysis_reports(user.id, symbol="600519", limit=1)
        assert detail[0].rating_change == "up"
    finally:
        await cleanup_user(user.id)


async def test_position_change_log_written():
    user = await make_user()
    try:
        await add_watchlist(user.id, "600519", cost_price=10.0, quantity=100)

        # 成本变化 → 记一条（数量未动则原值透传）
        assert await update_watchlist(user.id, "600519", {"cost_price": 12.5}) is True
        # 只改备注 → 不记
        assert await update_watchlist(user.id, "600519", {"note": "长期"}) is True
        # 数量清零 → 记一条
        assert await update_watchlist(user.id, "600519", {"quantity": 0}) is True
        # 相同值 → 不记
        assert await update_watchlist(user.id, "600519", {"quantity": 0}) is True

        history = await list_position_history(user.id, "600519")
        assert len(history) == 2
        newest, oldest = history
        assert oldest.old_cost_price == 10.0
        assert oldest.new_cost_price == 12.5
        assert oldest.old_quantity == 100
        assert oldest.new_quantity == 100
        assert newest.old_quantity == 100
        assert newest.new_quantity == 0
        assert newest.old_cost_price == 12.5

        # 用户隔离与空历史
        other = await make_user()
        try:
            assert await list_position_history(other.id, "600519") == []
        finally:
            await cleanup_user(other.id)
    finally:
        await cleanup_user(user.id)


async def test_price_alert_create_list_cancel(monkeypatch):
    user = await make_user()
    try:
        alert = await create_alert(user.id, "600519", direction="above", target_price=99.0)
        assert alert.symbol == "600519"
        assert alert.status == "active"
        assert alert.name == "贵州茅台"

        alerts = await list_alerts(user.id)
        assert [item.id for item in alerts] == [alert.id]

        assert await cancel_alert(user.id, uuid.uuid4()) is False
        assert await cancel_alert(user.id, uuid.UUID(alert.id)) is True
        # 已结束的提醒不能再次取消
        assert await cancel_alert(user.id, uuid.UUID(alert.id)) is False
        again = await list_alerts(user.id)
        assert again[0].status == "cancelled"

        # 生效中数量上限（快速插入 20 条）
        made = []
        for _ in range(20):
            made.append(
                await create_alert(user.id, "600519", direction="below", target_price=1.0)
            )
        try:
            await create_alert(user.id, "600519", direction="below", target_price=2.0)
            raised = False
        except PriceAlertLimitError:
            raised = True
        assert raised
    finally:
        await cleanup_user(user.id)


async def test_price_alert_check_triggers_and_dedupes(monkeypatch):
    user = await make_user()
    sent: list[dict] = []

    async def fake_send_email(**kwargs):
        sent.append(kwargs)

    async def fake_fetch_quotes(symbols):
        return {item.code: make_quote(9.0) for item in symbols}

    monkeypatch.setattr(price_alert_service, "send_email", fake_send_email)
    monkeypatch.setattr(price_alert_service, "fetch_quotes", fake_fetch_quotes)
    monkeypatch.setattr(price_alert_service, "in_trading_session", lambda now: True)

    try:
        above = await create_alert(user.id, "600519", direction="above", target_price=8.0)
        below = await create_alert(user.id, "600519", direction="below", target_price=10.0)
        miss = await create_alert(user.id, "600519", direction="below", target_price=5.0)

        # 现价 9：above 8 触发（9>=8），below 10 触发（9<=10），below 5 未触发
        assert await run_price_alert_check(
            now=datetime(2026, 10, 26, 10, 30, tzinfo=TZ_SHANGHAI)
        ) == 2

        alerts = {item.id: item for item in await list_alerts(user.id)}
        assert alerts[above.id].status == "triggered"
        assert alerts[above.id].triggered_price == 9.0
        assert alerts[below.id].status == "triggered"
        assert alerts[miss.id].status == "active"

        # 邮件发给用户邮箱，一封汇总两条
        assert len(sent) == 1
        assert sent[0]["to"] == user.email
        assert "600519" in sent[0]["text"]

        # 触发即防重：第二轮不再触发、不再发信
        assert await run_price_alert_check(
            now=datetime(2026, 10, 26, 10, 35, tzinfo=TZ_SHANGHAI)
        ) == 0
        assert len(sent) == 1
    finally:
        await cleanup_user(user.id)


async def test_price_alert_check_skips_outside_session():
    # 周六不触发（2026-10-24 是周六）
    assert await run_price_alert_check(
        now=datetime(2026, 10, 24, 10, 30, tzinfo=TZ_SHANGHAI)
    ) == 0
    # 交易时段外（开盘前）不触发
    assert await run_price_alert_check(
        now=datetime(2026, 10, 26, 8, 30, tzinfo=TZ_SHANGHAI)
    ) == 0


async def test_price_alert_mail_uses_notification_settings(monkeypatch):
    """统一通知设置：优先发接收地址；关闭价位提醒邮件后只记录不发送。"""
    user = await make_user()
    sent: list[dict] = []

    async def fake_send_email(**kwargs):
        sent.append(kwargs)

    async def fake_fetch_quotes(symbols):
        return {item.code: make_quote(9.0) for item in symbols}

    monkeypatch.setattr(price_alert_service, "send_email", fake_send_email)
    monkeypatch.setattr(price_alert_service, "fetch_quotes", fake_fetch_quotes)
    monkeypatch.setattr(price_alert_service, "in_trading_session", lambda now: True)

    try:
        async with SessionLocal() as session:
            session.add(
                AutomationSettings(
                    user_id=user.id,
                    notify_email="alert-box@example.com",
                    price_alert_email_enabled=True,
                )
            )
            await session.commit()

        await create_alert(user.id, "600519", direction="above", target_price=8.0)
        assert await run_price_alert_check(
            now=datetime(2026, 10, 26, 10, 0, tzinfo=TZ_SHANGHAI)
        ) == 1
        assert len(sent) == 1
        assert sent[0]["to"] == "alert-box@example.com"

        # 关闭价位提醒邮件
        async with SessionLocal() as session:
            row = await session.scalar(
                select(AutomationSettings).where(AutomationSettings.user_id == user.id)
            )
            row.price_alert_email_enabled = False
            await session.commit()

        await create_alert(user.id, "600519", direction="above", target_price=8.0)
        assert await run_price_alert_check(
            now=datetime(2026, 10, 26, 10, 5, tzinfo=TZ_SHANGHAI)
        ) == 1  # 仍触发并记录
        assert len(sent) == 1  # 但不再发信
    finally:
        await cleanup_user(user.id)


async def test_position_history_and_alerts_api(monkeypatch):
    user = await make_user()
    try:
        await add_watchlist(user.id, "600519", cost_price=10.0, quantity=100)
        await update_watchlist(user.id, "600519", {"cost_price": 11.0})
        alert = await create_alert(user.id, "600519", direction="below", target_price=90.0)

        app.dependency_overrides[get_current_user] = lambda: user
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get("/api/v1/watchlist/600519/position-history")
            assert response.status_code == 200, response.text
            body = response.json()
            assert len(body) == 1
            assert body[0]["old_cost_price"] == 10.0
            assert body[0]["new_cost_price"] == 11.0

            response = await client.get("/api/v1/watchlist/alerts")
            assert response.status_code == 200, response.text
            body = response.json()
            assert len(body) == 1
            assert body[0]["id"] == alert.id
            assert body[0]["target_price"] == 90.0

            response = await client.post(
                "/api/v1/watchlist/600519/alerts",
                json={"direction": "above", "target_price": 120.0},
            )
            assert response.status_code == 200, response.text
            created = response.json()
            assert created["status"] == "active"

            response = await client.post(
                "/api/v1/watchlist/600519/alerts",
                json={"direction": "above", "target_price": 0},
            )
            assert response.status_code == 422

            response = await client.delete(f"/api/v1/watchlist/alerts/{created['id']}")
            assert response.status_code == 204
            response = await client.delete(f"/api/v1/watchlist/alerts/{created['id']}")
            assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()
        await cleanup_user(user.id)
