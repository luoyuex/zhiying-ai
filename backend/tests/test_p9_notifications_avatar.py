"""A 包：Webhook 通知、报告价位提醒与头像。"""

import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.core.deps import get_current_user
from app.db.models.analysis_report import AnalysisReport
from app.db.models.automation_settings import AutomationSettings
from app.db.models.price_alert import PriceAlert
from app.db.models.user import User
from app.db.session import SessionLocal
from app.main import app
from app.providers.base import now_shanghai
from app.providers.models import Quote
from app.schemas.watchlist import PriceAlertView
from app.services import automation_mail_service, price_alert_service, webhook_service
from app.services.price_alert_service import (
    PriceAlertReportError,
    create_alert,
    list_alerts,
    run_price_alert_check,
)
from app.services.webhook_service import WebhookSendError, send_webhook
from tests.test_automation_mail import (
    FakeRedis,
    add_analysis_job,
    make_user_with_settings,
)
from tests.test_automation_mail import (
    cleanup_user as cleanup_mail_user,
)
from tests.test_report_history import make_user

TZ = ZoneInfo("Asia/Shanghai")
TINY_PNG = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8"
    "/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)
DINGTALK_URL = "https://oapi.dingtalk.com/robot/send?access_token=test"
FEISHU_URL = "https://open.feishu.cn/open-apis/bot/v2/hook/test"


async def cleanup_user(user_id: object) -> None:
    async with SessionLocal() as session:
        await session.execute(delete(User).where(User.id == user_id))
        await session.commit()


async def add_report_with_levels(user_id: object) -> uuid.UUID:
    async with SessionLocal() as session:
        report = AnalysisReport(
            user_id=user_id,
            symbol="600519",
            name="贵州茅台",
            rating="看多",
            confidence=80,
            model="test-model",
            prompt_version="test",
            report={
                "symbol": "600519",
                "decision": {
                    "rating": "买入",
                    "levels": {
                        "entry": 10.0,
                        "take_profit": 20.0,
                        "stop_loss": 8.0,
                        "support": 9.0,
                        "resistance": 18.0,
                    },
                },
            },
        )
        session.add(report)
        await session.commit()
        await session.refresh(report)
        return report.id


async def test_automation_settings_webhook_validation_and_roundtrip():
    user = await make_user()
    app.dependency_overrides[get_current_user] = lambda: user
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            base = {
                "screener_enabled": False,
                "analysis_enabled": False,
                "strategy_settings": {},
                "email_notify_enabled": False,
                "notify_email": None,
            }
            # 开启 Webhook 但未填地址
            response = await client.put(
                "/api/v1/automation/settings",
                json={**base, "webhook_notify_enabled": True},
            )
            assert response.status_code == 422, response.text

            # 非官方域名
            response = await client.put(
                "/api/v1/automation/settings",
                json={
                    **base,
                    "webhook_notify_enabled": True,
                    "webhook_url": "https://example.com/hook",
                },
            )
            assert response.status_code == 422, response.text

            # 正常保存钉钉地址
            response = await client.put(
                "/api/v1/automation/settings",
                json={
                    **base,
                    "webhook_notify_enabled": True,
                    "price_alert_webhook_enabled": True,
                    "webhook_type": "dingtalk",
                    "webhook_url": DINGTALK_URL,
                    "webhook_keyword": "智盈",
                },
            )
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["webhook_notify_enabled"] is True
            assert body["webhook_type"] == "dingtalk"
            assert body["webhook_url"] == DINGTALK_URL
            assert body["webhook_keyword"] == "智盈"

            response = await client.get("/api/v1/automation/settings")
            assert response.status_code == 200, response.text
            assert response.json()["price_alert_webhook_enabled"] is True
    finally:
        app.dependency_overrides.clear()
        await cleanup_user(user.id)


async def test_webhook_payloads_and_host_guard(monkeypatch):
    captured: list[dict] = []

    class FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {"errcode": 0, "code": 0}

    class FakeClient:
        async def post(self, url, **kwargs):
            captured.append({"url": url, **kwargs})
            return FakeResponse()

    monkeypatch.setattr(webhook_service, "get_http_client", lambda: FakeClient())

    await send_webhook(
        url=DINGTALK_URL,
        kind="dingtalk",
        keyword="智盈",
        title="定时任务结果",
        text="600519 看多",
    )
    payload = captured[0]["json"]
    assert payload["msgtype"] == "markdown"
    assert "智盈" in payload["markdown"]["text"]
    assert "600519" in payload["markdown"]["text"]

    await send_webhook(
        url=FEISHU_URL,
        kind="feishu",
        keyword=None,
        title="价位提醒",
        text="现价已到目标价",
    )
    payload = captured[1]["json"]
    assert payload["msg_type"] == "text"
    assert "价位提醒" in payload["content"]["text"]

    with pytest.raises(WebhookSendError):
        await send_webhook(
            url="http://oapi.dingtalk.com/robot/send?access_token=x",
            kind="dingtalk",
            keyword=None,
            title="t",
            text="x",
        )
    with pytest.raises(WebhookSendError):
        await send_webhook(
            url="https://example.com/hook",
            kind="feishu",
            keyword=None,
            title="t",
            text="x",
        )


async def test_digest_can_use_webhook_only(monkeypatch):
    user = await make_user_with_settings(
        analysis_enabled=True,
        email_notify_enabled=False,
        notify_email=None,
        webhook_notify_enabled=True,
        webhook_url=DINGTALK_URL,
        webhook_type="dingtalk",
        webhook_keyword="智盈",
    )
    emails: list[dict] = []
    hooks: list[dict] = []

    async def fake_email(**kwargs):
        emails.append(kwargs)

    async def fake_webhook(**kwargs):
        hooks.append(kwargs)

    monkeypatch.setattr(automation_mail_service, "send_email", fake_email)
    monkeypatch.setattr(automation_mail_service, "send_webhook", fake_webhook)
    redis = FakeRedis()
    try:
        await add_analysis_job(user)
        assert await automation_mail_service.send_due_digests(
            redis, now=datetime.now(TZ)
        ) == 1
        assert emails == []
        assert len(hooks) == 1
        assert "000001" in hooks[0]["text"]
        assert hooks[0]["url"] == DINGTALK_URL
    finally:
        await cleanup_mail_user(user)


async def test_report_price_alerts_and_dedupe():
    user = await make_user()
    other = await make_user()
    try:
        report_id = await add_report_with_levels(user.id)
        entry = await create_alert(
            user.id, "600519", kind="entry", report_id=report_id
        )
        assert entry.kind == "entry"
        assert entry.direction == "below"
        assert entry.target_price == 10.0
        assert entry.report_id == str(report_id)

        # 同类型重复创建：更新原记录，不新增
        again = await create_alert(
            user.id, "600519", kind="entry", report_id=report_id
        )
        assert again.id == entry.id
        active = [
            item
            for item in await list_alerts(user.id)
            if item.status == "active" and item.kind == "entry"
        ]
        assert len(active) == 1

        take_profit = await create_alert(
            user.id, "600519", kind="take_profit", report_id=report_id
        )
        assert take_profit.direction == "above"
        assert take_profit.target_price == 20.0

        stop_loss = await create_alert(
            user.id, "600519", kind="stop_loss", report_id=report_id
        )
        assert stop_loss.direction == "below"
        assert stop_loss.target_price == 8.0

        with pytest.raises(PriceAlertReportError):
            await create_alert(
                other.id, "600519", kind="entry", report_id=report_id
            )
    finally:
        await cleanup_user(user.id)
        await cleanup_user(other.id)


async def test_price_alert_webhook_channel(monkeypatch):
    user = await make_user()
    emails: list[dict] = []
    hooks: list[dict] = []

    async def fake_email(**kwargs):
        emails.append(kwargs)

    async def fake_webhook(**kwargs):
        hooks.append(kwargs)

    async def fake_fetch_quotes(symbols):
        return {
            item.code: Quote(
                symbol=item.code,
                name="贵州茅台",
                price=9.0,
                change_pct=1.0,
                source="test",
                fetched_at=now_shanghai(),
            )
            for item in symbols
        }

    monkeypatch.setattr(price_alert_service, "send_email", fake_email)
    monkeypatch.setattr(price_alert_service, "send_webhook", fake_webhook)
    monkeypatch.setattr(price_alert_service, "fetch_quotes", fake_fetch_quotes)
    monkeypatch.setattr(price_alert_service, "in_trading_session", lambda now: True)

    try:
        async with SessionLocal() as session:
            session.add(
                AutomationSettings(
                    user_id=user.id,
                    price_alert_email_enabled=False,
                    price_alert_webhook_enabled=True,
                    webhook_type="dingtalk",
                    webhook_url=DINGTALK_URL,
                    webhook_keyword="智盈",
                )
            )
            await session.commit()

        await create_alert(user.id, "600519", direction="above", target_price=8.0)
        assert await run_price_alert_check(
            now=datetime(2026, 10, 26, 10, 0, tzinfo=TZ)
        ) == 1
        assert emails == []
        assert len(hooks) == 1
        assert hooks[0]["url"] == DINGTALK_URL
        assert "贵州茅台" in hooks[0]["text"]
    finally:
        await cleanup_user(user.id)


async def test_avatar_upload_get_and_delete_api():
    user = await make_user()
    app.dependency_overrides[get_current_user] = lambda: user
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post(
                "/api/v1/auth/me/avatar", json={"data": TINY_PNG}
            )
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["avatar_url"]
            avatar_url = body["avatar_url"]

            response = await client.get(avatar_url)
            assert response.status_code == 200, response.text
            assert response.headers["content-type"].startswith("image/png")

            response = await client.post(
                "/api/v1/auth/me/avatar",
                json={"data": "data:image/gif;base64,R0lGODlhAQABAAAAACw="},
            )
            assert response.status_code == 422, response.text

            response = await client.delete("/api/v1/auth/me/avatar")
            assert response.status_code == 200, response.text
            assert response.json()["avatar_url"] is None

            response = await client.get(avatar_url)
            assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()
        await cleanup_user(user.id)


async def test_report_alert_api_from_report_levels():
    user = await make_user()
    report_id = await add_report_with_levels(user.id)
    app.dependency_overrides[get_current_user] = lambda: user
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post(
                "/api/v1/watchlist/600519/alerts",
                json={"kind": "take_profit", "report_id": str(report_id)},
            )
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["kind"] == "take_profit"
            assert body["direction"] == "above"
            assert body["target_price"] == 20.0

            response = await client.post(
                "/api/v1/watchlist/600519/alerts",
                json={"kind": "custom"},
            )
            assert response.status_code == 422, response.text
    finally:
        app.dependency_overrides.clear()
        await cleanup_user(user.id)


async def test_price_alert_report_view_fields():
    """列表视图字段完整，避免前端拿不到 kind / report_id。"""
    user = await make_user()
    try:
        report_id = await add_report_with_levels(user.id)
        view: PriceAlertView = await create_alert(
            user.id, "600519", kind="stop_loss", report_id=report_id
        )
        assert view.kind == "stop_loss"
        assert view.report_id == str(report_id)
        async with SessionLocal() as session:
            row = await session.scalar(
                select(PriceAlert).where(PriceAlert.id == uuid.UUID(view.id))
            )
            assert row is not None
            assert row.report_id == report_id
    finally:
        await cleanup_user(user.id)
