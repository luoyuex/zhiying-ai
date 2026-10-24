"""关键价位提醒：创建 / 取消 / 交易时段定时检查行情并邮件通知。

触发规则：
- above：最新价 >= 目标价；below：最新价 <= 目标价。
- 只在 A 股交易时段（周一至周五 09:30–15:00，Asia/Shanghai）检查，行情走现有批量报价缓存。
- 触发即把状态改为 triggered（天然防重，不会重复通知），随后给用户邮箱发一封汇总提醒。
"""

import html
import uuid
from datetime import datetime, time
from zoneinfo import ZoneInfo

from sqlalchemy import select, update

from app.core.config import settings
from app.core.logging import get_logger
from app.db.models.automation_settings import AutomationSettings
from app.db.models.price_alert import PriceAlert
from app.db.models.stock import Stock
from app.db.models.user import User
from app.db.session import SessionLocal
from app.providers.symbols import InvalidSymbolError, parse_symbol
from app.schemas.watchlist import PriceAlertView
from app.services.mail_service import send_email
from app.services.quote_batch import fetch_quotes

logger = get_logger(__name__)
TZ_SHANGHAI = ZoneInfo("Asia/Shanghai")

MAX_ACTIVE_ALERTS_PER_USER = 20
# 交易时段守卫：早盘集合竞价后到收盘；周末与午休外的时间行情本来也不动
SESSION_START = time(9, 30)
SESSION_END = time(15, 0)

DIRECTION_LABELS = {"above": "涨到", "below": "跌破"}


class PriceAlertLimitError(Exception):
    pass


class PriceAlertNotWatchlistedError(Exception):
    pass


def _to_view(row: PriceAlert) -> PriceAlertView:
    return PriceAlertView(
        id=str(row.id),
        symbol=row.symbol,
        name=row.name,
        direction=row.direction,
        target_price=float(row.target_price),
        status=row.status,
        triggered_price=float(row.triggered_price) if row.triggered_price is not None else None,
        triggered_at=row.triggered_at,
        created_at=row.created_at,
    )


async def create_alert(
    user_id: object,
    raw_symbol: str,
    *,
    direction: str,
    target_price: float,
) -> PriceAlertView:
    symbol = parse_symbol(raw_symbol).code
    async with SessionLocal() as session:
        active_rows = (
            await session.scalars(
                select(PriceAlert.id).where(
                    PriceAlert.user_id == user_id, PriceAlert.status == "active"
                )
            )
        ).all()
        if len(active_rows) >= MAX_ACTIVE_ALERTS_PER_USER:
            raise PriceAlertLimitError(
                f"最多同时保留 {MAX_ACTIVE_ALERTS_PER_USER} 条生效中的提醒"
            )
        name_row = await session.scalar(
            select(Stock.name).where(Stock.code == symbol).limit(1)
        )
        row = PriceAlert(
            user_id=user_id,
            symbol=symbol,
            name=name_row or "",
            direction=direction,
            target_price=target_price,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return _to_view(row)


async def list_alerts(user_id: object, *, limit: int = 100) -> list[PriceAlertView]:
    async with SessionLocal() as session:
        rows = (
            await session.scalars(
                select(PriceAlert)
                .where(PriceAlert.user_id == user_id)
                .order_by(PriceAlert.created_at.desc())
                .limit(limit)
            )
        ).all()
    return [_to_view(row) for row in rows]


async def cancel_alert(user_id: object, alert_id: uuid.UUID) -> bool:
    async with SessionLocal() as session:
        result = await session.execute(
            update(PriceAlert)
            .where(
                PriceAlert.id == alert_id,
                PriceAlert.user_id == user_id,
                PriceAlert.status == "active",
            )
            .values(status="cancelled")
        )
        await session.commit()
        return bool(result.rowcount)


def in_trading_session(now: datetime) -> bool:
    if now.weekday() >= 5:
        return False
    return SESSION_START <= now.time() <= SESSION_END


async def run_price_alert_check(*, now: datetime | None = None) -> int:
    """检查所有启用中的提醒；返回本轮触发的提醒条数。"""
    current = (now or datetime.now(TZ_SHANGHAI)).astimezone(TZ_SHANGHAI)
    if not in_trading_session(current):
        return 0

    async with SessionLocal() as session:
        rows = (
            await session.scalars(
                select(PriceAlert).where(PriceAlert.status == "active")
            )
        ).all()
    if not rows:
        return 0

    parsed = []
    for row in rows:
        try:
            parsed.append(parse_symbol(row.symbol))
        except InvalidSymbolError:
            logger.info("价位提醒代码无效，跳过 %s", row.symbol)
    quotes = await fetch_quotes(parsed)

    triggered_by_user: dict[object, list[PriceAlert]] = {}
    async with SessionLocal() as session:
        for row in rows:
            quote = quotes.get(row.symbol)
            if quote is None or quote.price is None:
                continue
            target = float(row.target_price)
            hit = (
                quote.price >= target
                if row.direction == "above"
                else quote.price <= target
            )
            if not hit:
                continue
            row.status = "triggered"
            row.triggered_price = quote.price
            row.triggered_at = current
            await session.execute(
                update(PriceAlert)
                .where(PriceAlert.id == row.id)
                .values(
                    status="triggered",
                    triggered_price=quote.price,
                    triggered_at=current,
                )
            )
            triggered_by_user.setdefault(row.user_id, []).append(row)
        await session.commit()

    hit_count = sum(len(alerts) for alerts in triggered_by_user.values())
    if not hit_count:
        return 0

    sent = 0
    for user_id, alerts in triggered_by_user.items():
        try:
            if await _send_alert_mail(user_id, alerts, current):
                sent += 1
        except Exception as exc:  # noqa: BLE001 - 单用户发信失败不影响其他
            logger.warning("价位提醒邮件发送失败 user=%s: %s", user_id, exc)
    logger.info("价位提醒触发 %s 条，发送邮件 %s 封", hit_count, sent)
    return hit_count


def _app_url(path: str) -> str:
    return f"{settings.public_app_url.rstrip('/')}/app{path}"


async def _send_alert_mail(user_id: object, alerts: list[PriceAlert], now: datetime) -> bool:
    """按统一通知设置发送：价位提醒开关 + 接收地址（留空回落账号邮箱）。"""
    async with SessionLocal() as session:
        row = (
            await session.execute(
                select(
                    User.email,
                    AutomationSettings.price_alert_email_enabled,
                    AutomationSettings.notify_email,
                )
                .outerjoin(
                    AutomationSettings, AutomationSettings.user_id == User.id
                )
                .where(User.id == user_id)
            )
        ).first()
    if row is None:
        return False
    account_email, alert_email_enabled, notify_email = row
    # 没有设置行时按默认开启处理
    if alert_email_enabled is False:
        logger.info("价位提醒邮件已关闭，跳过发送 user=%s", user_id)
        return False
    recipient = (notify_email or "").strip() or (account_email or "").strip()
    if not recipient:
        return False

    subject = f"{settings.app_name} · 价位提醒触发（{now.month}月{now.day}日）"
    lines = [f"【{settings.app_name}】你设置的 {len(alerts)} 条价位提醒已触发：", ""]
    html_rows: list[str] = []
    for row in alerts:
        label = DIRECTION_LABELS.get(row.direction, row.direction)
        title = f"{row.symbol} {row.name}".strip()
        detail = (
            f"现价 {row.triggered_price:.2f} 元，已{label}你设置的目标价 {float(row.target_price):.2f} 元"
        )
        link = _app_url(f"/stock/{row.symbol}")
        lines.append(f"- {title}：{detail}")
        if link:
            lines.append(f"  {link}")
        html_rows.append(
            '<tr><td style="padding-top:14px;border-top:1px solid #EEF0F3;">'
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
            f'<tr><td style="font-size:14px;font-weight:600;">'
            f'<a href="{html.escape(link)}" style="color:#16181D;text-decoration:none;">'
            f"{html.escape(title)}</a></td>"
            f'<td align="right" style="font-size:12px;color:#8A9099;">'
            f"{html.escape(label)} {float(row.target_price):.2f}</td></tr>"
            '<tr><td colspan="2" style="padding-top:4px;font-size:12px;color:#5A6069;">'
            f"触发时现价 {row.triggered_price:.2f} 元 · {now.strftime('%H:%M')}</td></tr>"
            "</table></td></tr>"
        )
    lines.append("")
    lines.append("以上提醒由你自行设置，仅供研究参考，不构成投资建议。")
    text_body = "\n".join(lines)

    html_body = (
        '<!DOCTYPE html><html lang="zh-CN"><body style="margin:0;padding:0;'
        "background:#F7F8FA;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',"
        "'PingFang SC','Microsoft YaHei',sans-serif;\">"
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="background:#F7F8FA;padding:32px 16px;"><tr><td align="center">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="max-width:600px;background:#FFFFFF;border:1px solid #E6E8EB;'
        'border-radius:14px;"><tr><td style="padding:30px;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
        f'<tr><td style="font-size:15px;font-weight:600;color:#16181D;">'
        f"{html.escape(settings.app_name)}</td></tr>"
        f'<tr><td style="padding-top:18px;font-size:20px;font-weight:600;color:#16181D;">'
        f"价位提醒触发（{now.month}月{now.day}日）</td></tr>"
        f'<tr><td style="padding-top:6px;font-size:13px;color:#5A6069;line-height:1.6;">'
        f"共 {len(alerts)} 条提醒达到目标价</td></tr>"
        + "".join(html_rows)
        + '<tr><td style="padding-top:24px;border-top:1px solid #E6E8EB;'
        'font-size:12px;color:#8A9099;line-height:1.7;">'
        "以上提醒由你自行设置，仅供研究参考，不构成投资建议。<br />"
        "提醒在自选股卡片上管理，触发后不会重复通知。</td></tr>"
        "</table></td></tr></table></td></tr></table></body></html>"
    )

    await send_email(
        to=recipient,
        subject=subject,
        text=text_body,
        html=html_body,
        console_detail=f"price_alerts user={user_id}",
    )
    return True
