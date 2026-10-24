"""定时任务汇总邮件：等待任务完成、合并发送与按天去重。"""

import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import delete, select

from app.core.config import settings
from app.db.models.ai_job import AIJob
from app.db.models.analysis_report import AnalysisReport
from app.db.models.automation_settings import AutomationSettings
from app.db.models.screener_record import ScreenerRecord
from app.db.models.user import User
from app.db.session import SessionLocal
from app.services import automation_mail_service

TZ = ZoneInfo("Asia/Shanghai")


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key: str):
        return self.store.get(key)

    async def exists(self, key: str):
        return 1 if key in self.store else 0

    async def set(self, key: str, value: str, ex: int | None = None, nx: bool = False):
        if nx and key in self.store:
            return False
        self.store[key] = value
        return True

    async def delete(self, key: str) -> None:
        self.store.pop(key, None)


async def cleanup_mail_users() -> None:
    async with SessionLocal() as session:
        rows = await session.scalars(select(User).where(User.email.like("mail-%")))
        for row in rows:
            await session.delete(row)
        await session.commit()


async def make_user_with_settings(**overrides) -> User:
    await cleanup_mail_users()
    user = User(email=f"mail-{uuid.uuid4().hex[:10]}@example.com", nickname="Mail")
    async with SessionLocal() as session:
        session.add(user)
        await session.commit()
        await session.refresh(user)
        values = {
            "user_id": user.id,
            "screener_enabled": False,
            "analysis_enabled": False,
            "screener_run_hour": 0,
            "screener_run_minute": 0,
            "analysis_run_hour": 0,
            "analysis_run_minute": 0,
            "strategy_settings": {},
            "email_notify_enabled": True,
            "notify_email": "notify@example.com",
        }
        values.update(overrides)
        session.add(AutomationSettings(**values))
        await session.commit()
    return user


async def add_analysis_job(user: User, *, status: str = "succeeded") -> AIJob:
    async with SessionLocal() as session:
        report = AnalysisReport(
            user_id=user.id,
            symbol="000001",
            name="平安银行",
            rating="看多",
            confidence=82,
            model="test-model",
            prompt_version="test",
            report={
                "symbol": "000001",
                "name": "平安银行",
                "rating": "看多",
                "confidence": 82,
                "analysis": {"rating": "看多", "summary": "量价配合良好，主力资金持续流入。"},
                "decision": {"rating": "买入", "position_action": "加仓"},
            },
        )
        session.add(report)
        await session.commit()
        await session.refresh(report)
        job = AIJob(
            id=uuid.uuid4().hex,
            kind="analysis",
            user_id=user.id,
            symbol="000001",
            status=status,
            trigger="scheduled",
            report_id=report.id,
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)
        return job


async def add_screener_job(user: User) -> AIJob:
    async with SessionLocal() as session:
        record = ScreenerRecord(
            user_id=user.id,
            strategy="main_force",
            filters={"final_n": 5},
            result={
                "recommendations": [
                    {
                        "rank": 1,
                        "symbol": "600000",
                        "name": "浦发银行",
                        "highlights": "主力净流入居前",
                    }
                ],
                "analyzed_count": 36,
            },
            analyzed_count=36,
            recommendation_count=1,
            model="test-model",
        )
        session.add(record)
        await session.commit()
        await session.refresh(record)
        job = AIJob(
            id=uuid.uuid4().hex,
            kind="screener",
            user_id=user.id,
            strategy="main_force",
            status="succeeded",
            trigger="scheduled",
            record_id=record.id,
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)
        return job


async def set_job_status(job: AIJob, status: str) -> None:
    async with SessionLocal() as session:
        row = await session.get(AIJob, job.id)
        assert row is not None
        row.status = status
        await session.commit()


async def cleanup_user(user: User) -> None:
    async with SessionLocal() as session:
        await session.execute(delete(User).where(User.id == user.id))
        await session.commit()


async def test_digest_waits_for_jobs_then_sends_once(monkeypatch):
    user = await make_user_with_settings(analysis_enabled=True)
    sent: list[dict] = []

    async def fake_send_email(**kwargs) -> None:
        sent.append(kwargs)

    monkeypatch.setattr(automation_mail_service, "send_email", fake_send_email)
    monkeypatch.setattr(settings, "automation_mail_wait_minutes", 24 * 60)
    redis = FakeRedis()

    try:
        job = await add_analysis_job(user, status="running")
        now = datetime.now(TZ)

        # 仍有任务在跑：等待，不发信
        assert await automation_mail_service.send_due_digests(redis, now=now) == 0
        assert sent == []

        await set_job_status(job, "succeeded")
        assert await automation_mail_service.send_due_digests(redis, now=now) == 1
        assert len(sent) == 1
        mail = sent[0]
        assert mail["to"] == "notify@example.com"
        assert "000001" in mail["text"]
        assert "平安银行" in mail["text"]
        assert "看多" in mail["text"]
        assert "加仓" in mail["text"]
        assert "定时分析" in mail["subject"]
        assert "<html" in mail["html"].lower()

        # 当天去重：再跑一轮不再发送
        assert await automation_mail_service.send_due_digests(redis, now=now) == 0
        assert len(sent) == 1
    finally:
        await cleanup_user(user)


async def test_digest_combines_screener_and_analysis(monkeypatch):
    user = await make_user_with_settings(screener_enabled=True, analysis_enabled=True)
    sent: list[dict] = []

    async def fake_send_email(**kwargs) -> None:
        sent.append(kwargs)

    monkeypatch.setattr(automation_mail_service, "send_email", fake_send_email)
    redis = FakeRedis()

    try:
        await add_analysis_job(user)
        await add_screener_job(user)
        now = datetime.now(TZ)

        assert await automation_mail_service.send_due_digests(redis, now=now) == 1
        assert len(sent) == 1
        text = sent[0]["text"]
        assert "定时分析" in text
        assert "定时选股" in text
        assert "主力追踪" in text
        assert "600000" in text
        assert "浦发银行" in text
        assert "定时选股与定时分析" in sent[0]["subject"]
    finally:
        await cleanup_user(user)


async def test_digest_skips_users_without_email_notification(monkeypatch):
    """未开启邮件通知时定时任务照常执行，只是不发邮件。"""
    user = await make_user_with_settings(
        analysis_enabled=True,
        email_notify_enabled=False,
        notify_email=None,
    )
    sent: list[dict] = []

    async def fake_send_email(**kwargs) -> None:
        sent.append(kwargs)

    monkeypatch.setattr(automation_mail_service, "send_email", fake_send_email)
    redis = FakeRedis()

    try:
        await add_analysis_job(user)
        assert await automation_mail_service.send_due_digests(
            redis, now=datetime.now(TZ)
        ) == 0
        assert sent == []
        assert not any(key.startswith("automation:mail:") for key in redis.store)
    finally:
        await cleanup_user(user)


async def test_digest_waits_for_scheduled_time(monkeypatch):
    now = datetime.now(TZ)
    if now.hour >= 23:
        pytest.skip("临近零点无法构造今日更晚的执行时间")
    # 把执行时间放到一小时后，此时不应发信
    due_hour = (now.hour + 1) % 24
    user = await make_user_with_settings(
        analysis_enabled=True,
        analysis_run_hour=due_hour,
        analysis_run_minute=now.minute,
    )
    sent: list[dict] = []

    async def fake_send_email(**kwargs) -> None:
        sent.append(kwargs)

    monkeypatch.setattr(automation_mail_service, "send_email", fake_send_email)
    redis = FakeRedis()

    try:
        await add_analysis_job(user)
        assert await automation_mail_service.send_due_digests(redis, now=now) == 0
        assert sent == []
    finally:
        await cleanup_user(user)


async def test_digest_sends_partial_after_wait_limit(monkeypatch):
    user = await make_user_with_settings(analysis_enabled=True)
    sent: list[dict] = []

    async def fake_send_email(**kwargs) -> None:
        sent.append(kwargs)

    monkeypatch.setattr(automation_mail_service, "send_email", fake_send_email)
    monkeypatch.setattr(settings, "automation_mail_wait_minutes", 0)
    redis = FakeRedis()

    try:
        await add_analysis_job(user, status="succeeded")
        await add_analysis_job(user, status="running")
        now = datetime.now(TZ)

        assert await automation_mail_service.send_due_digests(redis, now=now) == 1
        assert len(sent) == 1
        assert "部分任务仍在执行" in sent[0]["text"]
    finally:
        await cleanup_user(user)
