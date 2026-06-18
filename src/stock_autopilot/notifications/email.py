from __future__ import annotations

import html
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from stock_autopilot.config import settings
from stock_autopilot.models.schemas import AgentRunResult, StockPick
from stock_autopilot.universe import brand_cfg, load_config


def _normalize_password(password: str) -> str:
    """Gmail App Passwords are often pasted with spaces — remove them."""
    return password.replace(" ", "").strip()


def _smtp_identity() -> tuple[str, str, str]:
    user = settings.smtp_user.strip()
    password = _normalize_password(settings.smtp_password)
    sender = (settings.smtp_from or user).strip()
    # From must match the authenticated Gmail account
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


def _tier_badge_color(tier: int) -> str:
    return {1: "#059669", 2: "#2563eb", 3: "#7c3aed", 4: "#ea580c", 5: "#dc2626"}.get(tier, "#64748b")


def _build_apex_pick_html(p: StockPick, rank: int) -> str:
    note = p.research_note
    if not note:
        return f"""
        <div style="border:1px solid #e2e8f0;border-radius:12px;padding:16px;margin-bottom:16px">
          <strong>#{rank} {html.escape(p.symbol)}</strong> · score {int(p.score * 100)}<br/>
          <span style="color:#64748b;font-size:13px">{html.escape(p.rationale[:220])}</span>
        </div>"""

    tier_color = _tier_badge_color(note.risk_tier)
    thesis = "".join(f"<li style='margin:4px 0'>{html.escape(t)}</li>" for t in note.thesis[:3])
    risks = "".join(
        f"<li style='margin:4px 0'>{html.escape(r[0])} <span style='color:#94a3b8'>({r[1]})</span></li>"
        for r in note.risks[:3]
    )

    return f"""
    <div style="border:1px solid #cbd5e1;border-radius:12px;margin-bottom:20px;overflow:hidden">
      <div style="background:linear-gradient(90deg,#0f172a,#1e293b);color:#fff;padding:14px 18px">
        <div style="font-size:11px;letter-spacing:1px;opacity:0.7">{html.escape(brand_cfg()['research_header'])}</div>
        <div style="font-size:18px;font-weight:700;margin-top:4px">#{rank} {html.escape(p.symbol)} · {html.escape(p.name)}</div>
        <div style="font-size:13px;opacity:0.85;margin-top:4px">{html.escape(p.sector)} · {html.escape(note.industry)}</div>
      </div>
      <div style="padding:16px 18px;background:#fff">
        <div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px">
          <span style="background:{tier_color};color:#fff;padding:4px 10px;border-radius:999px;font-size:11px;font-weight:700">TIER {note.risk_tier}</span>
          <span style="background:#dbeafe;color:#1d4ed8;padding:4px 10px;border-radius:999px;font-size:11px;font-weight:700">{html.escape(note.rating)}</span>
          <span style="background:#f1f5f9;color:#334155;padding:4px 10px;border-radius:999px;font-size:11px">{html.escape(note.conviction)} conviction</span>
          <span style="background:#ecfdf5;color:#047857;padding:4px 10px;border-radius:999px;font-size:11px">Target ${note.price_target:.2f} (+{note.upside_pct:.0f}%)</span>
        </div>
        <p style="margin:0 0 10px;font-size:12px;color:#64748b">Current ${note.current_price:.2f} · Downside -{note.downside_pct:.0f}% · Score {int(p.score * 100)}</p>
        <p style="margin:0 0 6px;font-size:12px;font-weight:700;color:#0f172a">INVESTMENT THESIS</p>
        <ul style="margin:0 0 14px;padding-left:18px;font-size:13px;color:#334155;line-height:1.5">{thesis}</ul>
        <p style="margin:0 0 6px;font-size:12px;font-weight:700;color:#0f172a">TECHNICAL SETUP</p>
        <p style="margin:0 0 14px;font-size:13px;color:#334155">{html.escape(note.trend)} · RSI {note.rsi:.0f} · {html.escape(note.macd_signal)} · Support ${note.support:.2f} / Resistance ${note.resistance:.2f}</p>
        <p style="margin:0 0 6px;font-size:12px;font-weight:700;color:#0f172a">RISK FACTORS</p>
        <ul style="margin:0 0 14px;padding-left:18px;font-size:13px;color:#334155">{risks}</ul>
        <p style="margin:0 0 6px;font-size:12px;font-weight:700;color:#0f172a">POSITION SIZING</p>
        <p style="margin:0 0 14px;font-size:13px;color:#334155">Conservative {note.size_conservative} · Balanced {note.size_balanced} · Aggressive {note.size_aggressive}</p>
        <p style="margin:0;padding:10px 12px;background:#f8fafc;border-left:3px solid #6366f1;font-size:13px;color:#334155"><strong>Desk comment:</strong> {html.escape(note.desk_comment)}</p>
      </div>
    </div>"""


def _build_model_portfolios_html(result: AgentRunResult) -> str:
    if not result.model_portfolios:
        return ""

    blocks = ""
    for model in result.model_portfolios:
        rows = ""
        for h in model.holdings:
            rows += f"""
            <tr>
              <td style="padding:10px 12px;border-bottom:1px solid #e2e8f0;font-weight:700">{html.escape(h.symbol)}</td>
              <td style="padding:10px 12px;border-bottom:1px solid #e2e8f0">{int(h.weight * 100)}%</td>
              <td style="padding:10px 12px;border-bottom:1px solid #e2e8f0;text-align:center">{int(h.score * 100)}</td>
              <td style="padding:10px 12px;border-bottom:1px solid #e2e8f0;font-size:12px;color:#475569">{html.escape(h.sector)}</td>
            </tr>"""
        cash_line = f"<p style='margin:8px 0 0;font-size:13px;color:#64748b'>Cash sleeve: {int(model.cash_pct * 100)}% · Benchmark: {html.escape(model.benchmark)}</p>"
        blocks += f"""
      <div style="margin-top:28px;padding-top:20px;border-top:1px solid #e2e8f0">
        <h2 style="font-size:16px;margin:0 0 4px">{html.escape(model.label)} model</h2>
        <p style="margin:0 0 12px;color:#64748b;font-size:13px">{html.escape(model.description)}</p>
        {cash_line}
        <table style="width:100%;border-collapse:collapse;font-size:14px;margin-top:12px">
          <thead>
            <tr style="background:#f8fafc;text-align:left">
              <th style="padding:8px 12px;color:#64748b;font-size:11px">Symbol</th>
              <th style="padding:8px 12px;color:#64748b;font-size:11px">Weight</th>
              <th style="padding:8px 12px;color:#64748b;font-size:11px">Score</th>
              <th style="padding:8px 12px;color:#64748b;font-size:11px">Sector</th>
            </tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>
      </div>"""

    disclaimer = result.model_portfolios[0].disclaimer if result.model_portfolios else ""
    return f"""
      <h2 style="font-size:16px;margin:28px 0 8px">Model portfolios (pick your style)</h2>
      <p style="margin:0 0 8px;color:#64748b;font-size:13px">{html.escape(disclaimer)}</p>
      {blocks}"""


def _build_html(result: AgentRunResult, dashboard_url: str) -> str:
    macro = result.macro
    apex = brand_cfg()
    brand = apex["brand_name"]
    brief_url = f"{dashboard_url.rstrip('/')}#morning-brief" if dashboard_url else ""
    apex_cards = "".join(_build_apex_pick_html(p, i) for i, p in enumerate(result.picks, 1))

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"/></head>
<body style="margin:0;background:#f1f5f9;font-family:Segoe UI,Helvetica,Arial,sans-serif">
  <div style="max-width:680px;margin:0 auto;padding:24px">
    <div style="background:linear-gradient(135deg,#0f172a,#312e81);padding:28px;border-radius:16px 16px 0 0;color:white">
      <div style="font-size:11px;letter-spacing:1.5px;opacity:0.75">STOCK AUTOPILOT · DAILY BRIEF</div>
      <h1 style="margin:8px 0 0;font-size:22px">{html.escape(brand)}</h1>
      <p style="margin:6px 0 0;opacity:0.9;font-size:14px">Equity Research Desk · {result.finished_at.strftime('%A, %B %d, %Y')} UTC</p>
    </div>
    <div style="background:white;padding:24px;border:1px solid #e2e8f0;border-top:none">
      <div style="background:#fef3c7;border:1px solid #fcd34d;border-radius:10px;padding:12px 14px;font-size:13px;color:#92400e;margin-bottom:20px">
        ⚠ Research publisher only — not financial advice. Returns are not guaranteed. You self-direct all trades.
      </div>
      <h2 style="font-size:16px;margin:0 0 8px">Macro briefing</h2>
      <p style="margin:0 0 6px"><strong>{html.escape(macro.regime)}</strong> · Risk score {macro.risk_score}</p>
      <p style="margin:0 0 24px;color:#475569;font-size:14px;line-height:1.5">{html.escape(macro.summary)}</p>
      <h2 style="font-size:16px;margin:0 0 12px">Equity research notes ({len(result.picks)})</h2>
      {apex_cards}
      {_build_model_portfolios_html(result)}
      {"<p style='margin-top:20px'><a href='" + html.escape(brief_url) + "' style='color:#2563eb;font-weight:600'>Open morning brief on dashboard →</a></p>" if brief_url else ""}
    </div>
    <p style="text-align:center;color:#94a3b8;font-size:12px;margin-top:16px">
      Stock Autopilot · Run {html.escape(result.run_id)} · {result.scanned} symbols scanned
    </p>
  </div>
</body>
</html>"""


def _build_plain(result: AgentRunResult) -> str:
    brand = brand_cfg()["brand_name"]
    lines = [
        "Stock Autopilot — Daily Brief",
        f"{brand} · Equity Research Desk",
        result.finished_at.strftime("%Y-%m-%d %H:%M UTC"),
        "",
        "DISCLAIMER: Research publisher only. Not financial advice. No guaranteed returns.",
        "",
        f"Macro: {result.macro.regime} (risk {result.macro.risk_score})",
        result.macro.summary,
        "",
        f"Equity research notes ({len(result.picks)}):",
        "",
    ]
    for i, p in enumerate(result.picks, 1):
        if p.research_note_text:
            lines.append(p.research_note_text)
        else:
            lines.append(f"{i}. {p.symbol} — score {int(p.score*100)} — {p.name}")
            lines.append(f"   {p.rationale[:180]}")
        lines.append("")
    if result.model_portfolios:
        lines.append("Model portfolios (illustrative — pick your style):")
        lines.append("")
        for model in result.model_portfolios:
            lines.append(f"{model.label}: cash {int(model.cash_pct*100)}%, benchmark {model.benchmark}")
            for h in model.holdings:
                lines.append(f"  • {h.symbol} {int(h.weight*100)}% (score {int(h.score*100)})")
            lines.append("")
    lines.append(f"Run: {result.run_id}")
    return "\n".join(lines)


def send_daily_digest(result: AgentRunResult, cfg: dict | None = None) -> int:
    """Send digest to all recipients. Returns count of emails sent."""
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

    email_cfg = cfg.get("notifications", {}).get("email", {})
    prefix = email_cfg.get("subject_prefix", "Stock Autopilot Daily")
    date_str = result.finished_at.strftime("%Y-%m-%d")
    subject = f"{prefix} · {date_str} · {result.macro.regime}"
    dashboard_url = settings.dashboard_url or email_cfg.get("dashboard_url", "")

    html_body = _build_html(result, dashboard_url)
    plain_body = _build_plain(result)

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
