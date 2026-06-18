from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from stock_autopilot.config import settings
from stock_autopilot.models.schemas import (
    AgentRunResult,
    CommoditiesDeskSnapshot,
    CryptoPulseSnapshot,
    GlobalDeskSnapshot,
    IndiaDeskSnapshot,
)
from stock_autopilot.notifications.digest_builder import (
    DailyDigestBundle,
    build_digest_html,
    build_digest_plain,
    load_digest_bundle,
)
from stock_autopilot.universe import load_config


def _normalize_password(password: str) -> str:
    """Gmail App Passwords are often pasted with spaces — remove them."""
    return password.replace(" ", "").strip()


def _smtp_identity() -> tuple[str, str, str]:
    user = settings.smtp_user.strip()
    password = _normalize_password(settings.smtp_password)
    sender = (settings.smtp_from or user).strip()
    if "@" in sender and sender.lower() != user.lower():
        sender = user
    return user, password, sender


def validate_smtp_config(cfg: dict | None = None) -> list[str]:
    """Return list of configuration problems (empty = OK)."""
    cfg = cfg or load_config()
    issues: list[str] = []

    if not (settings.project_root / ".env").exists():
        issues.append(f"Missing .env file at {settings.project_root / '.env'}")

    if not get_recipients(cfg):
        issues.append("No recipients — add emails in config.yaml or EMAIL_RECIPIENTS in .env")

    if not settings.smtp_user:
        issues.append("SMTP_USER is empty in .env")
    elif "@" not in settings.smtp_user:
        issues.append("SMTP_USER must be a full email address")

    if not settings.smtp_password:
        issues.append("SMTP_PASSWORD is empty in .env")
    elif len(_normalize_password(settings.smtp_password)) < 16 and "gmail" in settings.smtp_host.lower():
        issues.append(
            "SMTP_PASSWORD looks too short for Gmail — use a 16-character App Password, "
            "not your normal Gmail password"
        )

    if settings.smtp_from and settings.smtp_from.strip().lower() != settings.smtp_user.strip().lower():
        issues.append(
            f"SMTP_FROM ({settings.smtp_from}) must match SMTP_USER ({settings.smtp_user}) for Gmail"
        )

    return issues


def check_smtp_connection() -> None:
    """Test SMTP login only. Raises with helpful message on failure."""
    issues = validate_smtp_config()
    if issues:
        raise ValueError("Email config problems:\n  • " + "\n  • ".join(issues))

    user, password, _ = _smtp_identity()
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(user, password)
    except smtplib.SMTPAuthenticationError as e:
        raise ValueError(
            "Gmail rejected login (535 BadCredentials).\n\n"
            "Fix checklist:\n"
            f"  1. SMTP_USER must be your exact Gmail: currently '{user}'\n"
            "  2. Enable 2-Step Verification on that Google account\n"
            "  3. Create App Password: https://myaccount.google.com/apppasswords\n"
            "  4. Put the 16-char App Password in SMTP_PASSWORD (spaces OK — we strip them)\n"
            "  5. SMTP_FROM must match SMTP_USER exactly\n"
            "  6. Do NOT use your normal Gmail password\n\n"
            f"Original error: {e}"
        ) from e


def get_recipients(cfg: dict | None = None) -> list[str]:
    cfg = cfg or load_config()
    email_cfg = cfg.get("notifications", {}).get("email", {})
    recipients = list(email_cfg.get("recipients") or [])
    if settings.email_recipients:
        recipients.extend(r.strip() for r in settings.email_recipients.split(",") if r.strip())
    return sorted(set(recipients))


def is_email_enabled(cfg: dict | None = None) -> bool:
    cfg = cfg or load_config()
    cfg_on = cfg.get("notifications", {}).get("email", {}).get("enabled", False)
    if not (cfg_on or settings.email_enabled):
        return False
    return bool(get_recipients(cfg)) and bool(settings.smtp_user and settings.smtp_password)


def make_digest_bundle(
    result: AgentRunResult,
    *,
    global_desk: GlobalDeskSnapshot | None = None,
    india_desk: IndiaDeskSnapshot | None = None,
    crypto_pulse: CryptoPulseSnapshot | None = None,
    commodities_desk: CommoditiesDeskSnapshot | None = None,
) -> DailyDigestBundle:
    if commodities_desk is None:
        from stock_autopilot.db import get_latest_commodities_desk

        commodities_desk = get_latest_commodities_desk()
    return DailyDigestBundle(
        result=result,
        global_desk=global_desk,
        india_desk=india_desk,
        crypto_pulse=crypto_pulse,
        commodities_desk=commodities_desk,
    )


def send_daily_digest(
    result: AgentRunResult,
    cfg: dict | None = None,
    *,
    global_desk: GlobalDeskSnapshot | None = None,
    india_desk: IndiaDeskSnapshot | None = None,
    crypto_pulse: CryptoPulseSnapshot | None = None,
) -> int:
    """Send full desk digest to all recipients. Returns count of emails sent."""
    cfg = cfg or load_config()
    recipients = get_recipients(cfg)
    if not recipients:
        return 0
    if not settings.smtp_user or not settings.smtp_password:
        raise ValueError("SMTP not configured — set SMTP_USER and SMTP_PASSWORD in .env")

    issues = validate_smtp_config(cfg)
    if issues:
        raise ValueError("Email config problems:\n  • " + "\n  • ".join(issues))

    user, password, sender = _smtp_identity()
    bundle = make_digest_bundle(
        result,
        global_desk=global_desk,
        india_desk=india_desk,
        crypto_pulse=crypto_pulse,
    )

    email_cfg = cfg.get("notifications", {}).get("email", {})
    prefix = email_cfg.get("subject_prefix", "LUMIQ Daily")
    date_str = result.finished_at.strftime("%Y-%m-%d")
    subject = f"{prefix} · {date_str} · {result.macro.regime}"
    dashboard_url = settings.dashboard_url or email_cfg.get("dashboard_url", "")

    html_body = build_digest_html(bundle, dashboard_url, cfg)
    plain_body = build_digest_plain(bundle, cfg)

    sent = 0
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        try:
            server.login(user, password)
        except smtplib.SMTPAuthenticationError as e:
            raise ValueError(
                "Gmail login failed. Use an App Password and ensure SMTP_USER/SMTP_FROM "
                "are the same Gmail address. Run: python main.py check-email"
            ) from e
        for recipient in recipients:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = sender
            msg["To"] = recipient
            msg.attach(MIMEText(plain_body, "plain", "utf-8"))
            msg.attach(MIMEText(html_body, "html", "utf-8"))
            server.sendmail(msg["From"], [recipient], msg.as_string())
            sent += 1
    return sent


__all__ = [
    "check_smtp_connection",
    "get_recipients",
    "is_email_enabled",
    "load_digest_bundle",
    "make_digest_bundle",
    "send_daily_digest",
    "validate_smtp_config",
    "build_digest_html",
]

# Re-export for preview route
from stock_autopilot.notifications.digest_builder import build_digest_html  # noqa: E402
