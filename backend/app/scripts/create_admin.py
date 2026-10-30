"""创建或提升管理员账号。

用法（在 backend 目录）：
    uv run python -m app.scripts.create_admin --email you@example.com --promote
    uv run python -m app.scripts.create_admin --email you@example.com --demote
"""

import argparse
import asyncio
import getpass
from datetime import UTC, datetime

from sqlalchemy import func, select

from app.core.security import hash_password
from app.db.models.admin_audit_log import AdminAuditLog
from app.db.models.user import User
from app.db.session import SessionLocal, engine


def _validate_password(password: str) -> None:
    if len(password) < 8 or not any(ch.isalpha() for ch in password) or not any(
        ch.isdigit() for ch in password
    ):
        raise SystemExit("密码至少 8 位，且必须同时包含字母和数字")


async def _run(args: argparse.Namespace) -> None:
    email = args.email.strip().lower()
    if "@" not in email:
        raise SystemExit("邮箱格式不正确")

    async with SessionLocal() as session:
        user = await session.scalar(select(User).where(User.email == email))

        if args.demote:
            if user is None or user.role != "admin":
                raise SystemExit("该账号不是管理员")
            active_admins = await session.scalar(
                select(func.count())
                .select_from(User)
                .where(User.role == "admin", User.status == "active")
            )
            if int(active_admins or 0) <= 1:
                raise SystemExit("至少保留一个 active 管理员，拒绝降级")
            user.role = "user"
            session.add(
                AdminAuditLog(
                    action="admin.demote",
                    target_type="user",
                    target_id=str(user.id),
                    before={"role": "admin"},
                    after={"role": "user"},
                    result="success",
                    ip="cli",
                    ua="create_admin.py",
                )
            )
            await session.commit()
            print(f"已取消管理员：{user.email}")
            return

        if user is not None and user.role == "admin":
            print(f"该账号已经是管理员：{user.email}")
            return

        if user is not None and not args.promote:
            raise SystemExit("账号已存在；如需提升为管理员请加 --promote")

        if user is not None:
            before = {"role": user.role, "status": user.status}
            user.role = "admin"
            user.status = "active"
            session.add(
                AdminAuditLog(
                    action="admin.promote",
                    target_type="user",
                    target_id=str(user.id),
                    before=before,
                    after={"role": "admin", "status": "active"},
                    result="success",
                    ip="cli",
                    ua="create_admin.py",
                )
            )
            await session.commit()
            print(f"已提升为管理员：{user.email}")
            return

        password = getpass.getpass("设置管理员密码: ")
        _validate_password(password)
        if password.lower() == email.split("@")[0].lower():
            raise SystemExit("密码不能与邮箱前缀相同")

        nickname = (args.nickname or "管理员").strip() or "管理员"
        user = User(
            email=email,
            nickname=nickname[:20],
            password_hash=hash_password(password),
            email_verified_at=datetime.now(UTC),
            role="admin",
            status="active",
            daily_analysis_quota=100,
        )
        session.add(user)
        await session.flush()
        session.add(
            AdminAuditLog(
                action="admin.create",
                target_type="user",
                target_id=str(user.id),
                after={"role": "admin", "status": "active"},
                result="success",
                ip="cli",
                ua="create_admin.py",
            )
        )
        await session.commit()
        print(f"已创建管理员：{user.email}")


async def _main() -> None:
    parser = argparse.ArgumentParser(description="创建或管理智盈 AI 管理员账号")
    parser.add_argument("--email", required=True, help="管理员邮箱")
    parser.add_argument("--nickname", default="管理员", help="新建账号的昵称")
    parser.add_argument(
        "--promote",
        action="store_true",
        help="账号已存在时提升为管理员",
    )
    parser.add_argument(
        "--demote",
        action="store_true",
        help="取消管理员（不能移除最后一个 active 管理员）",
    )
    args = parser.parse_args()
    if args.promote and args.demote:
        raise SystemExit("--promote 与 --demote 不能同时使用")
    try:
        await _run(args)
    finally:
        await engine.dispose()


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
