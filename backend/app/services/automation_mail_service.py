"""定时任务结果邮件：定时选股/分析跑完后，把当天结果汇总成一封邮件。

与调度器解耦：只读取 AI 任务台账（trigger=scheduled）和已落库的报告/选股记录，
等该任务线当天任务全部结束（或超过等待上限）后发送，避免每只股票发一封。
每个用户、每条任务线每天最多一封，Redis 键去重。
"""

import html
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import and_, or_, select

from app.core.config import settings
from app.core.logging import get_logger
from app.db.models.ai_job import AIJob
from app.db.models.analysis_report import AnalysisReport
from app.db.models.automation_settings import AutomationSettings
from app.db.models.screener_record import ScreenerRecord
from app.db.models.user import User
from app.db.session import SessionLocal
from app.services.mail_service import send_email
from app.services.webhook_service import send_webhook

logger = get_logger(__name__)
TZ_SHANGHAI = ZoneInfo("Asia/Shanghai")

# 去重键保留 2 天，覆盖跨日边界
_SENT_TTL_SECONDS = 172_800
# 调度器每 5 分钟扫描一次，留 1 分钟余量再判断是否需要发信
_SCHEDULER_GRACE = timedelta(minutes=6)
# 当天没有任何任务时，超过这个时间就把该任务线标记为已处理，避免整日轮询
_EMPTY_MARK_AFTER = timedelta(minutes=60)

LINE_LABELS = {"analysis": "定时分析", "screener": "定时选股"}
STRATEGY_LABELS = {
    "main_force": "主力追踪",
    "low_price_bull": "低价寻宝",
    "small_cap": "小盘精选",
    "profit_growth": "业绩高增",
    "value_stock": "价值洼地",
}
_RATING_COLORS = {
    "看多": "#D14343",
    "偏多": "#D14343",
    "中性": "#8A9099",
    "偏空": "#2E9E6B",
    "看空": "#2E9E6B",
    "买入": "#D14343",
    "持有": "#8A9099",
    "卖出": "#2E9E6B",
}


def _sent_key(now: datetime, user_id: object, line: str) -> str:
    return f"automation:mail:{now.strftime('%Y%m%d')}:{user_id}:{line}"


@dataclass
class _AnalysisEntry:
    symbol: str
    name: str = ""
    rating: str = ""
    confidence: int = 0
    action: str = ""
    summary: str = ""
    link: str = ""
    error: str = ""


@dataclass
class _ScreenerEntry:
    strategy: str
    analyzed_count: int = 0
    picks: list[tuple[str, str, str]] = field(default_factory=list)
    link: str = ""
    error: str = ""


@dataclass
class _ReadyLine:
    line: str
    jobs: list[AIJob]
    pending: int
    sent_key: str


@dataclass
class _Digest:
    analysis: list[_AnalysisEntry] = field(default_factory=list)
    screener: list[_ScreenerEntry] = field(default_factory=list)
    analysis_failed: int = 0
    screener_failed: int = 0
    partial: bool = False

    @property
    def total(self) -> int:
        return len(self.analysis) + len(self.screener)

    @property
    def success_total(self) -> int:
        return len([entry for entry in self.analysis if not entry.error]) + len(
            [entry for entry in self.screener if not entry.error]
        )


def _app_url(path: str) -> str:
    return f"{settings.public_app_url.rstrip('/')}/app{path}"


def _truncate(text: object, limit: int) -> str:
    value = str(text or "").strip().replace("\r", "")
    value = " ".join(value.split())
    return value if len(value) <= limit else value[: limit - 1] + "…"


async def send_due_digests(redis, *, now: datetime | None = None) -> int:  # noqa: ANN001
    """检查所有到点的用户，发送汇总邮件；返回实际发送的邮件数。"""
    current = (now or datetime.now(TZ_SHANGHAI)).astimezone(TZ_SHANGHAI)
    rows = await _load_candidates()

    sent = 0
    for user, automation in rows:
        try:
            sent += await _process_user(redis, user, automation, current)
        except Exception as exc:  # noqa: BLE001 - 单个用户失败不影响其他
            logger.exception("定时任务邮件处理失败 user=%s: %s", user.id, exc)
    if sent:
        logger.info("定时任务汇总邮件已发送 %s 封", sent)
    return sent


async def _load_candidates() -> list[tuple[User, AutomationSettings]]:
    async with SessionLocal() as session:
        email_ready = and_(
            AutomationSettings.email_notify_enabled.is_(True),
            AutomationSettings.notify_email.is_not(None),
            AutomationSettings.notify_email != "",
        )
        webhook_ready = and_(
            AutomationSettings.webhook_notify_enabled.is_(True),
            AutomationSettings.webhook_url.is_not(None),
            AutomationSettings.webhook_url != "",
        )
        stmt = (
            select(User, AutomationSettings)
            .join(AutomationSettings, AutomationSettings.user_id == User.id)
            .where(
                User.status == "active",
                or_(email_ready, webhook_ready),
                (AutomationSettings.screener_enabled.is_(True))
                | (AutomationSettings.analysis_enabled.is_(True)),
            )
        )
        return list((await session.execute(stmt)).all())


async def _process_user(
    redis,  # noqa: ANN001
    user: User,
    automation: AutomationSettings,
    now: datetime,
) -> int:
    notify_to = (automation.notify_email or "").strip()
    email_ready = bool(automation.email_notify_enabled and notify_to)
    webhook_ready = bool(
        automation.webhook_notify_enabled and (automation.webhook_url or "").strip()
    )
    if not email_ready and not webhook_ready:
        return 0

    line_times = []
    if automation.screener_enabled:
        line_times.append(
            (
                "screener",
                now.replace(
                    hour=automation.screener_run_hour,
                    minute=automation.screener_run_minute,
                    second=0,
                    microsecond=0,
                ),
            )
        )
    if automation.analysis_enabled:
        line_times.append(
            (
                "analysis",
                now.replace(
                    hour=automation.analysis_run_hour,
                    minute=automation.analysis_run_minute,
                    second=0,
                    microsecond=0,
                ),
            )
        )

    candidates: list[tuple[str, datetime, str]] = []
    for line, due in line_times:
        if now < due + _SCHEDULER_GRACE:
            continue
        key = _sent_key(now, user.id, line)
        if await redis.exists(key):
            continue
        candidates.append((line, due, key))
    if not candidates:
        return 0

    by_line = await _load_today_jobs(user.id, now)
    wait_limit = timedelta(minutes=settings.automation_mail_wait_minutes)

    ready: list[_ReadyLine] = []
    for line, due, key in candidates:
        jobs = by_line.get(line, [])
        if not jobs:
            # 用户可能没启用策略/自选为空：等足够久后标记，避免整天反复查询
            if now >= due + _EMPTY_MARK_AFTER:
                await redis.set(key, "1", ex=_SENT_TTL_SECONDS)
            continue
        pending = sum(1 for job in jobs if job.status in ("queued", "running"))
        if pending and now < due + wait_limit:
            continue
        ready.append(_ReadyLine(line=line, jobs=jobs, pending=pending, sent_key=key))

    if not ready:
        return 0

    digest = await _build_digest(ready)
    if digest.total == 0 and not (digest.analysis_failed or digest.screener_failed):
        # 只有排队中的任务、没有可展示结果：本次不发，等下一轮
        return 0

    lines = [item.line for item in ready]
    labels = "与".join(LINE_LABELS[line] for line in lines)
    claim_key = (
        f"automation:mail:claim:{now.strftime('%Y%m%d')}:{user.id}:"
        f"{'-'.join(sorted(line for line in lines))}"
    )
    # 多实例并发时只允许一个进程发信；发送失败释放占用，下一轮重试
    if not await redis.set(claim_key, "1", nx=True, ex=600):
        return 0

    subject = f"{settings.app_name} · {now.month}月{now.day}日{labels}结果"
    text, html_body = _render(subject, digest, now)

    email_ok = False
    webhook_ok = False
    if email_ready:
        try:
            await send_email(to=notify_to, subject=subject, text=text, html=html_body)
            email_ok = True
        except Exception as exc:  # noqa: BLE001 - 单渠道失败不影响另一渠道
            logger.warning("定时任务汇总邮件发送失败 user=%s: %s", user.id, exc)
    if webhook_ready:
        try:
            await send_webhook(
                url=automation.webhook_url,
                kind=automation.webhook_type,
                keyword=automation.webhook_keyword,
                title=subject,
                text=text,
            )
            webhook_ok = True
        except Exception as exc:  # noqa: BLE001
            logger.warning("定时任务汇总 Webhook 发送失败 user=%s: %s", user.id, exc)

    if (email_ready or webhook_ready) and not email_ok and not webhook_ok:
        await redis.delete(claim_key)
        return 0

    for item in ready:
        await redis.set(item.sent_key, "1", ex=_SENT_TTL_SECONDS)
    return 1


async def _load_today_jobs(user_id: object, now: datetime) -> dict[str, list[AIJob]]:
    day_start = datetime.combine(now.date(), time.min, tzinfo=TZ_SHANGHAI)
    async with SessionLocal() as session:
        stmt = (
            select(AIJob)
            .where(
                AIJob.user_id == user_id,
                AIJob.trigger == "scheduled",
                AIJob.kind.in_(("analysis", "screener")),
                AIJob.created_at >= day_start,
            )
            .order_by(AIJob.created_at.asc())
        )
        jobs = (await session.scalars(stmt)).all()

    grouped: dict[str, list[AIJob]] = defaultdict(list)
    for job in jobs:
        grouped[job.kind].append(job)
    return grouped


async def _build_digest(ready: list[_ReadyLine]) -> _Digest:
    digest = _Digest(partial=any(item.pending for item in ready))
    report_ids = [
        job.report_id
        for item in ready
        if item.line == "analysis"
        for job in item.jobs
        if job.status == "succeeded" and job.report_id
    ]
    record_ids = [
        job.record_id
        for item in ready
        if item.line == "screener"
        for job in item.jobs
        if job.status == "succeeded" and job.record_id
    ]

    reports: dict[object, AnalysisReport] = {}
    records: dict[object, ScreenerRecord] = {}
    async with SessionLocal() as session:
        if report_ids:
            rows = (
                await session.scalars(
                    select(AnalysisReport).where(AnalysisReport.id.in_(report_ids))
                )
            ).all()
            reports = {row.id: row for row in rows}
        if record_ids:
            rows = (
                await session.scalars(
                    select(ScreenerRecord).where(ScreenerRecord.id.in_(record_ids))
                )
            ).all()
            records = {row.id: row for row in rows}

    for item in ready:
        if item.line == "analysis":
            _collect_analysis(item.jobs, reports, digest)
        else:
            _collect_screener(item.jobs, records, digest)
    return digest


def _collect_analysis(
    jobs: list[AIJob],
    reports: dict[object, AnalysisReport],
    digest: _Digest,
) -> None:
    reports_url = _app_url("/reports")
    for job in jobs:
        symbol = job.symbol or "—"
        if job.status != "succeeded":
            digest.analysis_failed += 1
            digest.analysis.append(
                _AnalysisEntry(
                    symbol=symbol,
                    error=_truncate(job.error_message or "分析未完成", 120),
                    link=reports_url,
                )
            )
            continue

        row = reports.get(job.report_id) if job.report_id else None
        if row is None:
            # 命中 6h 缓存时不会重复落库，仍告知用户已有可用结果
            digest.analysis.append(
                _AnalysisEntry(
                    symbol=symbol,
                    summary="命中近期分析结果，可在历史报告中查看完整内容。",
                    link=reports_url,
                )
            )
            continue

        payload = row.report or {}
        decision = payload.get("decision") or {}
        analysis = payload.get("analysis") or {}
        digest.analysis.append(
            _AnalysisEntry(
                symbol=row.symbol,
                name=row.name or "",
                rating=row.rating or str(analysis.get("rating") or ""),
                confidence=int(row.confidence or 0),
                action=str(
                    decision.get("position_action") or decision.get("rating") or ""
                ),
                summary=_truncate(
                    analysis.get("summary") or decision.get("summary") or "", 180
                ),
                link=_app_url(f"/reports/{row.id}"),
            )
        )


def _collect_screener(
    jobs: list[AIJob],
    records: dict[object, ScreenerRecord],
    digest: _Digest,
) -> None:
    screener_url = _app_url("/screener")
    for job in jobs:
        strategy = STRATEGY_LABELS.get(job.strategy or "", job.strategy or "选股")
        if job.status != "succeeded":
            digest.screener_failed += 1
            digest.screener.append(
                _ScreenerEntry(
                    strategy=strategy,
                    error=_truncate(job.error_message or "选股未完成", 120),
                    link=screener_url,
                )
            )
            continue

        row = records.get(job.record_id) if job.record_id else None
        if row is None:
            digest.screener.append(
                _ScreenerEntry(
                    strategy=strategy,
                    error="结果已生成，可在选股记录中查看。",
                    link=screener_url,
                )
            )
            continue

        raw = row.result or {}
        picks: list[tuple[str, str, str]] = []
        for rec in raw.get("recommendations") or []:
            if not isinstance(rec, dict):
                continue
            symbol = str(rec.get("symbol") or "").strip()
            if not symbol:
                continue
            note = rec.get("highlights") or ""
            if not note:
                reasons = rec.get("reasons") or []
                note = reasons[0] if reasons else ""
            picks.append(
                (
                    symbol,
                    str(rec.get("name") or "").strip(),
                    _truncate(note, 90),
                )
            )
        digest.screener.append(
            _ScreenerEntry(
                strategy=strategy,
                analyzed_count=int(row.analyzed_count or 0),
                picks=picks[:10],
                link=screener_url,
            )
        )


def _render(subject: str, digest: _Digest, now: datetime) -> tuple[str, str]:
    date_label = f"{now.year}年{now.month}月{now.day}日"
    lines: list[str] = [f"【{settings.app_name}】{date_label}定时任务结果", ""]
    if digest.partial:
        lines.append("部分任务仍在执行，本次先发送已完成的结果。")
        lines.append("")

    if digest.analysis:
        ok = len(digest.analysis) - digest.analysis_failed
        lines.append(f"定时分析：成功 {ok} 只，失败 {digest.analysis_failed} 只")
        for entry in digest.analysis:
            title = f"{entry.symbol} {entry.name}".strip()
            if entry.error:
                lines.append(f"- {title}：{entry.error}")
                continue
            meta = " · ".join(
                part
                for part in (
                    entry.rating,
                    f"置信度 {entry.confidence}%" if entry.confidence else "",
                    f"建议 {entry.action}" if entry.action else "",
                )
                if part
            )
            lines.append(f"- {title}：{meta}")
            if entry.summary:
                lines.append(f"  {entry.summary}")
            if entry.link:
                lines.append(f"  {entry.link}")
        lines.append("")

    if digest.screener:
        lines.append("定时选股")
        for entry in digest.screener:
            if entry.error:
                lines.append(f"- {entry.strategy}：{entry.error}")
                continue
            head = f"- {entry.strategy}：扫描 {entry.analyzed_count} 只，推荐 {len(entry.picks)} 只"
            lines.append(head)
            for index, (symbol, name, note) in enumerate(entry.picks, start=1):
                suffix = f" —— {note}" if note else ""
                lines.append(f"  {index}. {symbol} {name}{suffix}")
            if entry.link:
                lines.append(f"  {entry.link}")
        lines.append("")

    lines.append("以上结果由系统自动生成，仅供研究参考，不构成投资建议。")
    text = "\n".join(lines)

    html_parts: list[str] = [
        '<!DOCTYPE html><html lang="zh-CN"><body style="margin:0;padding:0;'
        "background:#F7F8FA;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',"
        "'PingFang SC','Microsoft YaHei',sans-serif;\">",
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="background:#F7F8FA;padding:32px 16px;"><tr><td align="center">',
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="max-width:600px;background:#FFFFFF;border:1px solid #E6E8EB;'
        'border-radius:14px;">',
        '<tr><td style="padding:30px;">',
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0">',
        '<tr><td style="font-size:15px;font-weight:600;color:#16181D;">'
        f"{html.escape(settings.app_name)}</td></tr>",
        '<tr><td style="padding-top:18px;font-size:20px;font-weight:600;color:#16181D;">'
        f"{date_label}定时任务结果</td></tr>",
        '<tr><td style="padding-top:6px;font-size:13px;color:#5A6069;line-height:1.6;">'
        f"共 {digest.success_total} 项结果"
        + ("（部分任务仍在执行，先发送已完成部分）" if digest.partial else "")
        + "</td></tr>",
    ]

    if digest.analysis:
        html_parts.extend(_render_analysis_html(digest))
    if digest.screener:
        html_parts.extend(_render_screener_html(digest))

    html_parts.extend(
        [
            '<tr><td style="padding-top:24px;border-top:1px solid #E6E8EB;'
            'font-size:12px;color:#8A9099;line-height:1.7;">'
            "以上结果由系统自动生成，仅供研究参考，不构成投资建议。<br />"
            "如需调整接收地址、Webhook 或关闭通知，请在个人中心 → 定时与通知中修改。</td></tr>",
            "</table></td></tr></table></td></tr></table></body></html>",
        ]
    )
    return text, "".join(html_parts)


def _render_analysis_html(digest: _Digest) -> list[str]:
    ok = len(digest.analysis) - digest.analysis_failed
    parts = [
        '<tr><td style="padding-top:24px;font-size:16px;font-weight:600;color:#16181D;">'
        "定时分析</td></tr>",
        '<tr><td style="padding-top:4px;font-size:12px;color:#8A9099;">'
        f"成功 {ok} 只 · 失败 {digest.analysis_failed} 只</td></tr>",
    ]
    for entry in digest.analysis:
        title = html.escape(f"{entry.symbol} {entry.name}".strip())
        if entry.error:
            parts.append(
                '<tr><td style="padding-top:14px;border-top:1px solid #EEF0F3;">'
                f'<div style="font-size:13px;font-weight:600;color:#5A6069;">{title}</div>'
                '<div style="padding-top:4px;font-size:12px;color:#8A9099;">'
                f"{html.escape(entry.error)}</div></td></tr>"
            )
            continue

        color = _RATING_COLORS.get(entry.rating, "#5A6069")
        meta = " · ".join(
            part
            for part in (
                entry.rating,
                f"置信度 {entry.confidence}%" if entry.confidence else "",
                f"建议 {entry.action}" if entry.action else "",
            )
            if part
        )
        summary = (
            '<tr><td colspan="2" style="padding-top:5px;font-size:12px;'
            f'color:#5A6069;line-height:1.65;">{html.escape(entry.summary)}</td></tr>'
            if entry.summary
            else ""
        )
        parts.append(
            '<tr><td style="padding-top:14px;border-top:1px solid #EEF0F3;">'
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
            '<tr><td style="font-size:14px;font-weight:600;">'
            f'<a href="{html.escape(entry.link)}" style="color:#16181D;text-decoration:none;">'
            f"{title}</a></td>"
            f'<td align="right" style="font-size:12px;font-weight:600;color:{color};">'
            f"{html.escape(meta)}</td></tr>{summary}</table></td></tr>"
        )
    return parts


def _render_screener_html(digest: _Digest) -> list[str]:
    parts = [
        '<tr><td style="padding-top:24px;font-size:16px;font-weight:600;color:#16181D;">'
        "定时选股</td></tr>",
    ]
    for entry in digest.screener:
        if entry.error:
            parts.append(
                '<tr><td style="padding-top:14px;border-top:1px solid #EEF0F3;">'
                f'<div style="font-size:13px;font-weight:600;color:#5A6069;">'
                f"{html.escape(entry.strategy)}</div>"
                '<div style="padding-top:4px;font-size:12px;color:#8A9099;">'
                f"{html.escape(entry.error)}</div></td></tr>"
            )
            continue

        rows = "".join(
            '<tr><td style="padding-top:6px;font-size:12px;color:#5A6069;">'
            f'<span style="font-weight:600;">{index}. {html.escape(symbol)} '
            f"{html.escape(name)}</span>"
            + (
                f'<span style="color:#8A9099;"> —— {html.escape(note)}</span>'
                if note
                else ""
            )
            + "</td></tr>"
            for index, (symbol, name, note) in enumerate(entry.picks, start=1)
        )
        parts.append(
            '<tr><td style="padding-top:14px;border-top:1px solid #EEF0F3;">'
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
            '<tr><td style="font-size:13px;font-weight:600;">'
            f'<a href="{html.escape(entry.link)}" style="color:#16181D;text-decoration:none;">'
            f"{html.escape(entry.strategy)}</a></td>"
            '<td align="right" style="font-size:12px;color:#8A9099;">'
            f"扫描 {entry.analyzed_count} 只 · 推荐 {len(entry.picks)} 只</td></tr>"
            f"{rows}</table></td></tr>"
        )
    return parts
