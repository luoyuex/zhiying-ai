"""邮件发送：SMTP 真实发信，未配置时降级为控制台输出。"""

from email.message import EmailMessage
from email.utils import formataddr

import aiosmtplib

from app.core import errors
from app.core.config import settings
from app.core.logging import get_logger
from app.services.otp_service import PURPOSE_LABELS

logger = get_logger(__name__)

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="zh-CN">
  <body style="margin:0;padding:0;background:#F7F8FA;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#F7F8FA;padding:32px 16px;">
      <tr>
        <td align="center">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:520px;background:#FFFFFF;border:1px solid #E6E8EB;border-radius:14px;padding:32px;">
            <tr>
              <td style="font-size:15px;font-weight:600;color:#16181D;letter-spacing:0.2px;">
                __APP_NAME__
              </td>
            </tr>
            <tr>
              <td style="padding-top:20px;font-size:20px;font-weight:600;color:#16181D;">
                你的__PURPOSE__验证码
              </td>
            </tr>
            <tr>
              <td style="padding-top:8px;font-size:13px;color:#5A6069;line-height:1.6;">
                请在页面中输入以下 6 位数字完成验证，验证码 __TTL__ 分钟内有效，且仅可使用一次。
              </td>
            </tr>
            <tr>
              <td style="padding-top:24px;">
                <div style="background:#EDF1FE;border-radius:10px;padding:20px;text-align:center;">
                  <span style="font-size:32px;font-weight:700;letter-spacing:10px;color:#2F5AF3;font-variant-numeric:tabular-nums;">__CODE__</span>
                </div>
              </td>
            </tr>
            <tr>
              <td style="padding-top:24px;font-size:12px;color:#8A9099;line-height:1.7;">
                如果这不是你本人的操作，请忽略本邮件，你的账号不会有任何变化。<br />
                为保障账号安全，请勿将验证码告知他人。
              </td>
            </tr>
            <tr>
              <td style="padding-top:24px;border-top:1px solid #E6E8EB;font-size:12px;color:#8A9099;">
                此邮件由系统自动发送，请勿直接回复。
              </td>
            </tr>
          </table>
          <div style="padding-top:16px;font-size:12px;color:#8A9099;">__APP_NAME__ · AI 股票研究工具</div>
        </td>
      </tr>
    </table>
  </body>
</html>
"""

_TEXT_TEMPLATE = """\
【__APP_NAME__】__PURPOSE__验证码：__CODE__

请在页面中输入该验证码完成验证，__TTL__ 分钟内有效，仅可使用一次。
如非本人操作请忽略本邮件。
"""


def _render(code: str, purpose: str, ttl_minutes: int) -> tuple[str, str]:
    values = {
        "__APP_NAME__": settings.app_name,
        "__PURPOSE__": PURPOSE_LABELS.get(purpose, "身份"),
        "__CODE__": code,
        "__TTL__": str(ttl_minutes),
    }
    html = _HTML_TEMPLATE
    text = _TEXT_TEMPLATE
    for key, value in values.items():
        html = html.replace(key, value)
        text = text.replace(key, value)
    return text, html


async def send_email(
    *,
    to: str,
    subject: str,
    text: str,
    html: str,
    console_detail: str = "",
) -> None:
    """发送一封邮件；SMTP 未配置时降级为日志输出，不抛错。"""
    if settings.email_mode == "console" or not settings.smtp_user or not settings.smtp_password:
        detail = f" {console_detail}" if console_detail else ""
        logger.warning(
            "[MAIL:console] to=%s subject=%s%s（未配置 SMTP，未真实发送）",
            to,
            subject,
            detail,
        )
        return

    message = EmailMessage()
    message["From"] = formataddr((settings.smtp_from_name, settings.smtp_user))
    message["To"] = to
    message["Subject"] = subject
    message.set_content(text)
    message.add_alternative(html, subtype="html")

    try:
        if settings.smtp_port == 465:
            await aiosmtplib.send(
                message,
                hostname=settings.smtp_host,
                port=settings.smtp_port,
                username=settings.smtp_user,
                password=settings.smtp_password,
                use_tls=True,
                timeout=15,
            )
        else:
            await aiosmtplib.send(
                message,
                hostname=settings.smtp_host,
                port=settings.smtp_port,
                username=settings.smtp_user,
                password=settings.smtp_password,
                start_tls=True,
                timeout=15,
            )
    except Exception as exc:  # noqa: BLE001
        logger.exception("发送邮件失败 to=%s host=%s subject=%s", to, settings.smtp_host, subject)
        raise errors.mail_send_failed() from exc

    logger.info("email sent to=%s subject=%s", to, subject)


async def send_otp_email(to: str, code: str, purpose: str, ttl_seconds: int) -> None:
    ttl_minutes = max(ttl_seconds // 60, 1)
    text, html = _render(code, purpose, ttl_minutes)
    await send_email(
        to=to,
        subject=f"{settings.app_name} {PURPOSE_LABELS.get(purpose, '')}验证码：{code}",
        text=text,
        html=html,
        console_detail=f"purpose={purpose} code={code}",
    )
    logger.info("OTP email handled to=%s purpose=%s", to, purpose)
