"""每日定时任务调度：per-user 时间判断、防重、跳过与入队逻辑。"""

import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import delete, select

from app.db.models.automation_run import AutomationRun
from app.db.models.automation_settings import AutomationSettings
from app.db.models.user import User
from app.db.session import SessionLocal
from app.services import daily_automation_service
from app.services.ai_analysis_service import QuotaExceededError

TZ = ZoneInfo("Asia/Shanghai")


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key: str):
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None, nx: bool = False):
        if nx and key in self.store:
            return False
        self.store[key] = value
        return True


async def make_user_with_settings(
    *,
    screener_enabled: bool = False,
    analysis_enabled: bool = False,
    strategies: dict | None = None,
    status: str = "active",
    screener_run_time: tuple[int, int] = (0, 0),
    analysis_run_time: tuple[int, int] = (0, 0),
) -> User:
    # 清理历史失败运行可能泄漏的测试用户，避免污染"全量启用用户"查询
    async with SessionLocal() as session:
        old = await session.scalars(
            select(User).where(User.email.like("auto-run-%"))
        )
        for row in old:
            await session.delete(row)
        await session.commit()

    user = User(email=f"auto-run-{uuid.uuid4().hex[:10]}@example.com", nickname="AutoRun")
    user.status = status
    async with SessionLocal() as session:
        session.add(user)
        await session.commit()
        await session.refresh(user)
        session.add(
            AutomationSettings(
                user_id=user.id,
                screener_enabled=screener_enabled,
                analysis_enabled=analysis_enabled,
                screener_run_hour=screener_run_time[0],
                screener_run_minute=screener_run_time[1],
                analysis_run_hour=analysis_run_time[0],
                analysis_run_minute=analysis_run_time[1],
                strategy_settings=strategies or {},
            )
        )
        await session.commit()
    return user


async def cleanup_user(user: User) -> None:
    async with SessionLocal() as session:
        await session.execute(delete(User).where(User.id == user.id))
        await session.commit()


@pytest.fixture()
def patch_llm(monkeypatch):
    monkeypatch.setattr(daily_automation_service, "is_llm_configured", lambda: True)


@pytest.fixture(autouse=True)
def isolate_real_automation_users(monkeypatch):
    """数据库里可能有真实账号开着定时任务（如开发账号），过滤到测试用户避免误报。"""
    original = daily_automation_service._load_enabled_users

    async def filtered():
        rows = await original()
        return [row for row in rows if str(row[0].email).startswith("auto-run-")]

    monkeypatch.setattr(daily_automation_service, "_load_enabled_users", filtered)


async def test_run_skipped_before_user_scheduled_time(patch_llm):
    # 用户时间设在 23:59，当前时间必然早于它 → 不应入队也不落防重键
    user = await make_user_with_settings(
        screener_enabled=True,
        strategies={"main_force": {"enabled": True, "filters": {}}},
        screener_run_time=(23, 59),
    )

    async def fail_enqueue(*_args, **_kwargs):
        raise AssertionError("未到用户设定时间不应入队")

    try:
        from app.services import screener_job_service

        original = screener_job_service.start_screener_job
        daily_automation_service.start_screener_job = fail_enqueue  # type: ignore[method-assign]
        try:
            redis = FakeRedis()
            await daily_automation_service.run_daily_automation_task(redis)
            assert not any(key.startswith("automation:ran:") for key in redis.store)
        finally:
            daily_automation_service.start_screener_job = original  # type: ignore[method-assign]
    finally:
        await cleanup_user(user)


async def test_run_deduplicated_per_day(patch_llm):
    user = await make_user_with_settings(
        screener_enabled=True,
        strategies={"main_force": {"enabled": True, "filters": {}}},
        screener_run_time=(0, 0),
    )
    redis = FakeRedis()
    now = datetime.now(TZ)
    redis.store[daily_automation_service._ran_key(now, user.id, "screener")] = "1"

    async def fail_enqueue(*_args, **_kwargs):
        raise AssertionError("防重生效时不应入队")

    try:
        daily_automation_service.start_screener_job = fail_enqueue  # type: ignore[method-assign]
        await daily_automation_service.run_daily_automation_task(redis)
    finally:
        daily_automation_service.start_screener_job = (  # type: ignore[method-assign]
            daily_automation_service.start_screener_job
        )
        await cleanup_user(user)


async def test_run_skipped_without_llm(monkeypatch):
    monkeypatch.setattr(daily_automation_service, "is_llm_configured", lambda: False)
    redis = FakeRedis()
    await daily_automation_service.run_daily_automation_task(redis)
    assert not any(key.startswith("automation:ran:") for key in redis.store)


async def test_run_enqueues_screener_and_analysis(patch_llm, monkeypatch):
    user = await make_user_with_settings(
        screener_enabled=True,
        analysis_enabled=True,
        strategies={
            "main_force": {"enabled": True, "filters": {"final_n": 3}},
            "low_price_bull": {"enabled": False, "filters": {}},
            "value_stock": {"enabled": True, "filters": {"max_pe": 15}},
        },
    )
    watchlist_symbols = ["600519", "300750"]
    screener_calls: list[tuple] = []
    analysis_calls: list[str] = []

    async def fake_start_screener(
        _redis, _user_id, _quota, strategy, payload, **_kwargs
    ):
        screener_calls.append((strategy, payload.model_dump(mode="json")))

    async def fake_start_ai(
        _redis, _user_id, _quota, symbol, force=False, **_kwargs
    ):
        assert force is False
        analysis_calls.append(symbol)

    async def fake_read_quota_used(_redis, _user_id, *, strict=False):
        return 0

    async def fake_watchlist_symbols(_user_id):
        return list(watchlist_symbols)

    monkeypatch.setattr(daily_automation_service, "start_screener_job", fake_start_screener)
    monkeypatch.setattr(daily_automation_service, "start_ai_job", fake_start_ai)
    monkeypatch.setattr(
        daily_automation_service, "read_quota_used", fake_read_quota_used
    )
    monkeypatch.setattr(
        daily_automation_service, "_watchlist_symbols", fake_watchlist_symbols
    )

    redis = FakeRedis()
    try:
        await daily_automation_service.run_daily_automation_task(redis)

        # 两策略开启（一个未启用）→ 只入队 2 个选股任务
        assert [strategy for strategy, _ in screener_calls] == ["main_force", "value_stock"]
        assert screener_calls[0][1]["final_n"] == 3
        assert screener_calls[1][1]["max_pe"] == 15
        assert analysis_calls == watchlist_symbols
        assert any(":screener" in key for key in redis.store if key.startswith("automation:ran:"))
        assert any(":analysis" in key for key in redis.store if key.startswith("automation:ran:"))
    finally:
        await cleanup_user(user)


async def test_run_records_execution_log(patch_llm, monkeypatch):
    """每条任务线每天落一条执行记录：入队数、无任务、额度不足可查。"""
    user = await make_user_with_settings(
        screener_enabled=True,
        analysis_enabled=True,
        strategies={"main_force": {"enabled": True, "filters": {}}},
    )

    async def fake_start_screener(*_args, **_kwargs):
        return None

    async def fake_start_ai(*_args, **_kwargs):
        return None

    async def fake_read_quota_used(_redis, _user_id, *, strict=False):
        return 0

    async def fake_watchlist_symbols(_user_id):
        return ["600519"]

    monkeypatch.setattr(daily_automation_service, "start_screener_job", fake_start_screener)
    monkeypatch.setattr(daily_automation_service, "start_ai_job", fake_start_ai)
    monkeypatch.setattr(
        daily_automation_service, "read_quota_used", fake_read_quota_used
    )
    monkeypatch.setattr(
        daily_automation_service, "_watchlist_symbols", fake_watchlist_symbols
    )

    redis = FakeRedis()
    try:
        await daily_automation_service.run_daily_automation_task(redis)

        async with SessionLocal() as session:
            rows = (
                await session.scalars(
                    select(AutomationRun).where(AutomationRun.user_id == user.id)
                )
            ).all()
        by_line = {row.line: row for row in rows}
        assert set(by_line) == {"screener", "analysis"}
        assert by_line["screener"].status == "enqueued"
        assert by_line["screener"].enqueued == 1
        assert by_line["analysis"].status == "enqueued"
        assert by_line["analysis"].enqueued == 1
    finally:
        await cleanup_user(user)


async def test_run_quota_exhausted_skips_analysis(patch_llm, monkeypatch):
    user = await make_user_with_settings(analysis_enabled=True)

    async def fail_start_ai(*_args, **_kwargs):
        raise AssertionError("额度用尽时不应入队")

    async def fake_read_quota_used(_redis, _user_id, *, strict=False):
        return 5

    monkeypatch.setattr(daily_automation_service, "start_ai_job", fail_start_ai)
    monkeypatch.setattr(
        daily_automation_service, "read_quota_used", fake_read_quota_used
    )

    redis = FakeRedis()
    try:
        await daily_automation_service.run_daily_automation_task(redis)
    finally:
        await cleanup_user(user)


async def test_run_single_user_failure_does_not_block_others(patch_llm, monkeypatch):
    first = await make_user_with_settings(
        screener_enabled=True,
        strategies={"main_force": {"enabled": True, "filters": {}}},
    )
    second = await make_user_with_settings(
        screener_enabled=True,
        strategies={"main_force": {"enabled": True, "filters": {}}},
    )
    calls: list[str] = []

    async def fake_start_screener(
        _redis, user_id, _quota, _strategy, _payload, **_kwargs
    ):
        if user_id == first.id:
            raise RuntimeError("boom")
        calls.append(str(user_id))

    monkeypatch.setattr(daily_automation_service, "start_screener_job", fake_start_screener)

    redis = FakeRedis()
    try:
        await daily_automation_service.run_daily_automation_task(redis)
        assert calls == [str(second.id)]
    finally:
        await cleanup_user(first)
        await cleanup_user(second)
