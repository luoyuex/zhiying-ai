"""认证链路端到端测试：直接跑在真实 Postgres + Redis 上。

运行前确保 docker compose 已启动、alembic 已迁移。
"""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

import app.api.v1.auth as auth_module
from app.db.models.user import User
from app.db.redis import get_redis
from app.db.session import SessionLocal
from app.main import app

PASSWORD = "zhiying2026"


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest.fixture
def outbox(monkeypatch):
    box: dict[str, str] = {}

    async def fake_send(to: str, code: str, purpose: str, ttl: int) -> None:
        box["code"] = code
        box["to"] = to
        box["purpose"] = purpose

    monkeypatch.setattr(auth_module, "send_otp_email", fake_send)
    return box


@pytest.fixture
async def email():
    address = f"test-{uuid.uuid4().hex[:10]}@example.com"
    yield address
    async with SessionLocal() as session:
        await session.execute(delete(User).where(User.email == address))
        await session.commit()
    redis = get_redis()
    for purpose in ("register", "login", "reset"):
        await redis.delete(f"otp:{purpose}:{address}", f"otp:cd:{purpose}:{address}")
    for pattern in (f"otp:cnt:email:{address}:*", "otp:cnt:ip:*"):
        keys = [key async for key in redis.scan_iter(pattern)]
        if keys:
            await redis.delete(*keys)


async def _send_code(client: AsyncClient, email: str, purpose: str = "register"):
    return await client.post("/api/v1/auth/email/send-code", json={"email": email, "purpose": purpose})


async def _register(client: AsyncClient, outbox: dict, email: str, nickname: str = "测试用户"):
    resp = await _send_code(client, email)
    assert resp.status_code == 200, resp.text
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "code": outbox["code"], "password": PASSWORD, "nickname": nickname},
    )
    return resp


async def test_register_and_me(client: AsyncClient, outbox: dict, email: str):
    resp = await _register(client, outbox, email)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["user"]["email"] == email
    assert body["user"]["email_verified_at"] is not None
    assert body["access_token"]
    assert resp.cookies.get("zy_refresh")

    me = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"}
    )
    assert me.status_code == 200
    assert me.json()["nickname"] == "测试用户"


async def test_duplicate_email(client: AsyncClient, outbox: dict, email: str):
    assert (await _register(client, outbox, email)).status_code == 200
    # 已存在判断在验证码校验之前，因此直接复用旧码即可
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "code": outbox["code"], "password": PASSWORD, "nickname": "重复"},
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "EMAIL_EXISTS"


async def test_wrong_code_five_times_invalidates(client: AsyncClient, outbox: dict, email: str):
    resp = await _send_code(client, email)
    assert resp.status_code == 200
    real_code = outbox["code"]
    wrong_code = "000000" if real_code != "000000" else "111111"

    last = None
    for _ in range(5):
        last = await client.post(
            "/api/v1/auth/register",
            json={"email": email, "code": wrong_code, "password": PASSWORD, "nickname": "测试"},
        )
    assert last is not None and last.status_code == 400
    assert last.json()["code"] == "CODE_INVALID"

    # 码已被作废，即使输入正确也失效
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "code": real_code, "password": PASSWORD, "nickname": "测试"},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "CODE_EXPIRED"


async def test_send_cooldown(client: AsyncClient, outbox: dict, email: str):
    assert (await _send_code(client, email)).status_code == 200
    resp = await _send_code(client, email)
    assert resp.status_code == 429
    assert resp.json()["code"] == "RATE_LIMITED"
    assert resp.json()["detail"]["retry_after"] > 0


async def test_code_expired(client: AsyncClient, outbox: dict, email: str):
    assert (await _send_code(client, email)).status_code == 200
    await get_redis().delete(f"otp:register:{email}")
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "code": outbox["code"], "password": PASSWORD, "nickname": "测试"},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "CODE_EXPIRED"


async def test_password_login_wrong_password(client: AsyncClient, outbox: dict, email: str):
    assert (await _register(client, outbox, email)).status_code == 200
    client.cookies.clear()

    resp = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "wrongpass123"}
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "INVALID_CREDENTIALS"

    # 不存在的账号返回同样的错误码，避免枚举
    resp = await client.post(
        "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "wrongpass123"}
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "INVALID_CREDENTIALS"


async def test_login_with_code(client: AsyncClient, outbox: dict, email: str):
    assert (await _register(client, outbox, email)).status_code == 200
    client.cookies.clear()

    resp = await _send_code(client, email, "login")
    assert resp.status_code == 200
    resp = await client.post(
        "/api/v1/auth/login/code", json={"email": email, "code": outbox["code"]}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["access_token"]


async def test_refresh_rotation_and_replay_detection(client: AsyncClient, outbox: dict, email: str):
    resp = await _register(client, outbox, email)
    old_refresh = resp.cookies.get("zy_refresh")
    assert old_refresh

    resp = await client.post("/api/v1/auth/refresh")
    assert resp.status_code == 200, resp.text
    new_refresh = resp.cookies.get("zy_refresh")
    assert new_refresh and new_refresh != old_refresh

    # 用已轮换掉的旧 token 重放 → 拒绝，并吊销全部会话
    replay = await client.post("/api/v1/auth/refresh", cookies={"zy_refresh": old_refresh})
    assert replay.status_code == 401
    assert replay.json()["code"] == "UNAUTHORIZED"

    # 新 token 也已被一并吊销
    after = await client.post("/api/v1/auth/refresh", cookies={"zy_refresh": new_refresh})
    assert after.status_code == 401


async def test_logout_revokes_refresh(client: AsyncClient, outbox: dict, email: str):
    resp = await _register(client, outbox, email)
    refresh = resp.cookies.get("zy_refresh")
    assert refresh

    assert (await client.post("/api/v1/auth/logout")).status_code == 200
    resp = await client.post("/api/v1/auth/refresh", cookies={"zy_refresh": refresh})
    assert resp.status_code == 401


async def test_reset_password(client: AsyncClient, outbox: dict, email: str):
    assert (await _register(client, outbox, email)).status_code == 200
    client.cookies.clear()

    resp = await _send_code(client, email, "reset")
    assert resp.status_code == 200
    resp = await client.post(
        "/api/v1/auth/password/reset",
        json={"email": email, "code": outbox["code"], "new_password": "newpass2026"},
    )
    assert resp.status_code == 200, resp.text

    resp = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "newpass2026"}
    )
    assert resp.status_code == 200


async def test_password_policy(client: AsyncClient, outbox: dict, email: str):
    assert (await _send_code(client, email)).status_code == 200
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "code": outbox["code"], "password": "12345678", "nickname": "测试"},
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "VALIDATION_ERROR"
