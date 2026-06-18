from __future__ import annotations

import html
from dataclasses import dataclass

from stock_autopilot.investor_profile import get_return_target_pct
from stock_autopilot.models.schemas import (
    AgentRunResult,
    CryptoHourlyPrediction,
    CryptoPulseSnapshot,
    GlobalDeskSnapshot,
    IndiaDeskSnapshot,
    StockPick,
)
from stock_autopilot.universe import brand_cfg, load_config


@dataclass
class DailyDigestBundle:
    result: AgentRunResult
    global_desk: GlobalDeskSnapshot | None = None
    india_desk: IndiaDeskSnapshot | None = None
    crypto_pulse: CryptoPulseSnapshot | None = None


def load_digest_bundle(result: AgentRunResult | None = None) -> DailyDigestBundle:
    """Build digest from an explicit run or latest DB snapshots."""
    from stock_autopilot.db import (
        get_latest_crypto_pulse,
        get_latest_global_desk,
        get_latest_india_desk,
        get_latest_run,
    )
    from stock_autopilot.models.schemas import MacroSnapshot, ModelPortfolio, ResearchNote, StockPick

    if result is None:
        latest = get_latest_run()
        if not latest:
            raise ValueError("No autopilot run data yet")
        from datetime import datetime

        result = AgentRunResult(
            run_id=latest["run_id"],
            started_at=datetime.fromisoformat(latest["started_at"]),
            finished_at=datetime.fromisoformat(latest["finished_at"]),
            macro=MacroSnapshot(**latest["macro"]),
            picks=[
                StockPick(
                    **{
                        **p,
                        "research_note": ResearchNote(**p["research_note"]) if p.get("research_note") else None,
                    }
                )
                for p in latest["picks"]
            ],
            model_portfolios=[ModelPortfolio(**m) for m in latest.get("model_portfolios", [])],
            scanned=latest["scanned"],
            status=latest["status"],
            log=latest.get("log", []),
        )

    return DailyDigestBundle(
        result=result,
        global_desk=get_latest_global_desk(),
        india_desk=get_latest_india_desk(),
        crypto_pulse=get_latest_crypto_pulse(),
    )


def _tier_badge_color(tier: int) -> str:
    return {1: "#059669", 2: "#2563eb", 3: "#7c3aed", 4: "#ea580c", 5: "#dc2626"}.get(tier, "#64748b")


def _email_cfg(cfg: dict | None) -> dict:
    cfg = cfg or load_config()
    return cfg.get("notifications", {}).get("email", {})


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
      <h2 id="models" style="font-size:16px;margin:28px 0 8px">Model portfolios (pick your style)</h2>
      <p style="margin:0 0 8px;color:#64748b;font-size:13px">{html.escape(disclaimer)}</p>
      {blocks}"""


def _pick_table_row(cells: list[str]) -> str:
    tds = "".join(f"<td style='padding:8px 10px;border-bottom:1px solid #e2e8f0;font-size:13px'>{c}</td>" for c in cells)
    return f"<tr>{tds}</tr>"


def _build_global_desk_html(gd: GlobalDeskSnapshot, cfg: dict) -> str:
    ecfg = _email_cfg(cfg)
    max_boards = ecfg.get("max_regional_boards", 12)
    per_board = ecfg.get("picks_per_board_email", 3)
    stack = gd.signal_stack or {}
    signal_bits = [
        f"Risk: {stack.get('risk_regime', '—')}",
        f"USD: {stack.get('usd_strength', '—')}",
        f"Commodities: {stack.get('commodity_pulse', '—')}",
    ]
    if stack.get("crypto_pulse"):
        signal_bits.append(f"Crypto: {stack['crypto_pulse']}")

    top_rows = ""
    for p in gd.global_top_picks:
        top_rows += _pick_table_row([
            f"<strong>{html.escape(p.symbol)}</strong>",
            html.escape(p.country),
            html.escape(p.rating),
            f"T{p.risk_tier}",
            f"${p.cmp:,.2f}",
            f"${p.target:,.2f}",
            f"+{p.upside_pct:.0f}%",
            f"{int(p.score * 100)}",
        ])

    board_blocks = ""
    live_boards = [b for b in gd.regional_boards if b.picks][:max_boards]
    for board in live_boards:
        rows = ""
        for p in board.picks[:per_board]:
            rows += _pick_table_row([
                f"#{p.rank} {html.escape(p.symbol)}",
                html.escape(p.rating),
                f"${p.cmp:,.2f}",
                f"+{p.upside_pct:.0f}%",
                html.escape(p.thesis_line[:80] or p.desk_note[:80]),
            ])
        board_blocks += f"""
        <div style="margin-bottom:18px">
          <p style="margin:0 0 6px;font-size:14px;font-weight:700;color:#0f172a">{html.escape(board.label)} · {html.escape(board.exchange)}</p>
          <p style="margin:0 0 8px;font-size:12px;color:#64748b">{html.escape(board.theme)} · Top risk: {html.escape(board.top_risk)}</p>
          <table style="width:100%;border-collapse:collapse">
            <thead><tr style="background:#f8fafc;text-align:left">
              <th style="padding:6px 10px;font-size:11px;color:#64748b">Pick</th>
              <th style="padding:6px 10px;font-size:11px;color:#64748b">Rating</th>
              <th style="padding:6px 10px;font-size:11px;color:#64748b">CMP</th>
              <th style="padding:6px 10px;font-size:11px;color:#64748b">Upside</th>
              <th style="padding:6px 10px;font-size:11px;color:#64748b">Thesis</th>
            </tr></thead>
            <tbody>{rows}</tbody>
          </table>
        </div>"""

    return f"""
      <h2 id="global-desk" style="font-size:18px;margin:32px 0 8px;color:#0f172a;border-top:2px solid #e2e8f0;padding-top:24px">🌍 Global Intelligence Desk</h2>
      <p style="margin:0 0 8px;color:#475569;font-size:14px;line-height:1.5">{html.escape(gd.opening_statement[:320])}</p>
      <p style="margin:0 0 16px;font-size:12px;color:#6366f1;font-weight:600">Signal stack · {' · '.join(html.escape(s) for s in signal_bits)}</p>
      <h3 style="font-size:15px;margin:0 0 10px">Global top picks ({len(gd.global_top_picks)})</h3>
      <table style="width:100%;border-collapse:collapse;margin-bottom:24px">
        <thead><tr style="background:#0f172a;color:#fff;text-align:left">
          <th style="padding:8px 10px;font-size:11px">Symbol</th>
          <th style="padding:8px 10px;font-size:11px">Market</th>
          <th style="padding:8px 10px;font-size:11px">Rating</th>
          <th style="padding:8px 10px;font-size:11px">Tier</th>
          <th style="padding:8px 10px;font-size:11px">CMP</th>
          <th style="padding:8px 10px;font-size:11px">Target</th>
          <th style="padding:8px 10px;font-size:11px">Upside</th>
          <th style="padding:8px 10px;font-size:11px">Score</th>
        </tr></thead>
        <tbody>{top_rows}</tbody>
      </table>
      <h3 style="font-size:15px;margin:0 0 12px">Regional boards ({len(live_boards)} markets)</h3>
      {board_blocks or "<p style='color:#64748b;font-size:13px'>No regional picks in this scan.</p>"}
    """


def _build_india_desk_html(india: IndiaDeskSnapshot) -> str:
    eq_rows = ""
    for eq in india.equities:
        thesis = eq.thesis[0] if eq.thesis else eq.desk_note
        eq_rows += _pick_table_row([
            f"<strong>{html.escape(eq.nse)}</strong>",
            html.escape(eq.name[:28]),
            html.escape(eq.sector),
            html.escape(eq.rating),
            f"₹{eq.cmp:,.0f}",
            f"₹{eq.target_12m:,.0f}",
            f"+{eq.upside_pct:.0f}%",
            html.escape(thesis[:70]),
        ])

    advisory = []
    for mf in india.mutual_funds[:2]:
        advisory.append(f"MF · {html.escape(mf.fund_name)} ({html.escape(mf.category)}) — {html.escape(mf.desk_note[:100])}")
    for b in india.bonds[:1]:
        advisory.append(f"Bond · {html.escape(b.instrument)} — {html.escape(b.yield_label)} · {html.escape(b.desk_note[:80])}")
    for fd in india.fixed_deposits[:1]:
        advisory.append(f"FD · {html.escape(fd.instrument)} — {html.escape(fd.yield_label)} · {html.escape(fd.desk_note[:80])}")
    advisory_html = "".join(f"<li style='margin:6px 0;font-size:13px;color:#334155'>{line}</li>" for line in advisory)

    macro = india.macro
    macro_line = (
        f"Nifty {macro.nifty:,.0f} ({macro.nifty_change_pct:+.2f}%) · "
        f"Sensex {macro.sensex:,.0f} · RBI {macro.rbi_stance} · Repo {macro.repo_rate}%"
    )

    return f"""
      <h2 id="india-desk" style="font-size:18px;margin:32px 0 8px;color:#0f172a;border-top:2px solid #e2e8f0;padding-top:24px">🇮🇳 India Intelligence Desk</h2>
      <p style="margin:0 0 8px;color:#475569;font-size:14px;line-height:1.5">{html.escape(india.opening_statement[:280])}</p>
      <p style="margin:0 0 16px;font-size:12px;color:#64748b">{html.escape(macro_line)}</p>
      <h3 style="font-size:15px;margin:0 0 10px">NSE equity picks ({len(india.equities)})</h3>
      <table style="width:100%;border-collapse:collapse;margin-bottom:20px">
        <thead><tr style="background:#ea580c;color:#fff;text-align:left">
          <th style="padding:8px 10px;font-size:11px">NSE</th>
          <th style="padding:8px 10px;font-size:11px">Name</th>
          <th style="padding:8px 10px;font-size:11px">Sector</th>
          <th style="padding:8px 10px;font-size:11px">Rating</th>
          <th style="padding:8px 10px;font-size:11px">CMP</th>
          <th style="padding:8px 10px;font-size:11px">Target</th>
          <th style="padding:8px 10px;font-size:11px">Upside</th>
          <th style="padding:8px 10px;font-size:11px">Thesis</th>
        </tr></thead>
        <tbody>{eq_rows or "<tr><td colspan='8' style='padding:12px;color:#64748b'>No equity picks</td></tr>"}</tbody>
      </table>
      <h3 style="font-size:15px;margin:0 0 8px">Fixed income &amp; MF advisory</h3>
      <ul style="margin:0 0 8px;padding-left:18px">{advisory_html or "<li style='color:#64748b;font-size:13px'>No advisory notes</li>"}</ul>
      <p style="margin:0;font-size:11px;color:#94a3b8">{html.escape(india.disclaimer)}</p>
    """


def _crypto_card(asset: CryptoHourlyPrediction) -> str:
    bias_color = {"bullish": "#059669", "bearish": "#dc2626"}.get(asset.bias_class, "#64748b")
    return f"""
    <div style="flex:1;min-width:240px;border:1px solid #e2e8f0;border-radius:12px;padding:16px;background:#fff">
      <div style="font-size:11px;color:#64748b;letter-spacing:1px">{html.escape(asset.asset)} · {html.escape(asset.prediction_window)}</div>
      <div style="font-size:22px;font-weight:700;margin:6px 0">${asset.current_price:,.0f}</div>
      <div style="margin-bottom:8px"><span style="background:{bias_color};color:#fff;padding:3px 10px;border-radius:999px;font-size:11px;font-weight:700">{html.escape(asset.bias_label)}</span>
        <span style="font-size:12px;color:#64748b;margin-left:8px">{asset.confidence_pct}% confidence</span></div>
      <p style="margin:0 0 8px;font-size:13px;color:#334155">{html.escape(asset.key_driver[:120])}</p>
      <p style="margin:0;font-size:12px;color:#64748b">▲ ${asset.target_upside:,.0f} (+{asset.target_upside_pct:.1f}%) · ▼ ${asset.target_downside:,.0f} (-{asset.target_downside_pct:.1f}%)</p>
      <p style="margin:8px 0 0;font-size:12px;color:#475569;font-style:italic">{html.escape(asset.desk_note[:140])}</p>
    </div>"""


def _build_crypto_html(pulse: CryptoPulseSnapshot, crypto_board: list | None = None) -> str:
    board_rows = ""
    for c in (crypto_board or [])[:8]:
        board_rows += _pick_table_row([
            html.escape(c.category),
            f"T{c.tier}",
            html.escape(c.token),
            html.escape(c.bias),
            f"${c.price:,.2f}" if c.price else "—",
            f"{c.confidence_pct}%",
            html.escape(c.desk_note[:70]),
        ])

    board_table = ""
    if board_rows:
        board_table = f"""
      <h3 style="font-size:15px;margin:20px 0 10px">Tiered crypto universe</h3>
      <table style="width:100%;border-collapse:collapse">
        <thead><tr style="background:#f8fafc;text-align:left">
          <th style="padding:6px 10px;font-size:11px;color:#64748b">Category</th>
          <th style="padding:6px 10px;font-size:11px;color:#64748b">Tier</th>
          <th style="padding:6px 10px;font-size:11px;color:#64748b">Token</th>
          <th style="padding:6px 10px;font-size:11px;color:#64748b">Bias</th>
          <th style="padding:6px 10px;font-size:11px;color:#64748b">Price</th>
          <th style="padding:6px 10px;font-size:11px;color:#64748b">Conf.</th>
          <th style="padding:6px 10px;font-size:11px;color:#64748b">Desk note</th>
        </tr></thead>
        <tbody>{board_rows}</tbody>
      </table>"""

    return f"""
      <h2 id="crypto-desk" style="font-size:18px;margin:32px 0 8px;color:#0f172a;border-top:2px solid #e2e8f0;padding-top:24px">⚡ Crypto Pulse</h2>
      <p style="margin:0 0 6px;font-size:13px;color:#64748b">{html.escape(pulse.session_name)} · {html.escape(pulse.session_liquidity_note[:100])}</p>
      <p style="margin:0 0 16px;font-size:14px;color:#475569">{html.escape(pulse.opening_statement[:220])}</p>
      <div style="display:flex;flex-wrap:wrap;gap:16px;margin-bottom:8px">
        {_crypto_card(pulse.btc)}
        {_crypto_card(pulse.eth)}
      </div>
      <p style="margin:12px 0 0;font-size:12px;color:#64748b">ETH/BTC trend: {html.escape(pulse.eth_btc_trend)}</p>
      {board_table}
    """


def _build_toc_html(bundle: DailyDigestBundle, cfg: dict) -> str:
    ecfg = _email_cfg(cfg)
    links = ['<a href="#macro" style="color:#2563eb;text-decoration:none;margin-right:12px">Macro</a>']
    if ecfg.get("include_global_desk", True) and bundle.global_desk:
        links.append('<a href="#global-desk" style="color:#2563eb;text-decoration:none;margin-right:12px">Global Desk</a>')
    if ecfg.get("include_india_desk", True) and bundle.india_desk:
        links.append('<a href="#india-desk" style="color:#2563eb;text-decoration:none;margin-right:12px">India Desk</a>')
    if ecfg.get("include_crypto_pulse", True) and bundle.crypto_pulse:
        links.append('<a href="#crypto-desk" style="color:#2563eb;text-decoration:none;margin-right:12px">Crypto</a>')
    links.append('<a href="#equity-notes" style="color:#2563eb;text-decoration:none;margin-right:12px">Equity notes</a>')
    if ecfg.get("include_model_portfolios", True) and bundle.result.model_portfolios:
        links.append('<a href="#models" style="color:#2563eb;text-decoration:none">Model books</a>')
    return f"""
      <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:12px 14px;margin-bottom:20px">
        <p style="margin:0 0 8px;font-size:11px;font-weight:700;color:#64748b;letter-spacing:1px">TODAY&apos;S DESK · JUMP TO</p>
        <p style="margin:0;font-size:13px">{''.join(links)}</p>
      </div>"""


def build_digest_html(bundle: DailyDigestBundle, dashboard_url: str = "", cfg: dict | None = None) -> str:
    cfg = cfg or load_config()
    ecfg = _email_cfg(cfg)
    result = bundle.result
    macro = result.macro
    apex = brand_cfg()
    brand = apex["brand_name"]
    target = get_return_target_pct()
    brief_url = f"{dashboard_url.rstrip('/')}#morning-brief" if dashboard_url else ""

    sections: list[str] = [_build_toc_html(bundle, cfg)]

    sections.append(f"""
      <h2 id="macro" style="font-size:16px;margin:0 0 8px">Macro briefing</h2>
      <p style="margin:0 0 6px"><strong>{html.escape(macro.regime)}</strong> · Risk score {macro.risk_score}</p>
      <p style="margin:0 0 8px;font-size:13px;color:#6366f1">Return target band: {html.escape(target['label'])} · {result.scanned} symbols scanned in core universe</p>
      <p style="margin:0 0 24px;color:#475569;font-size:14px;line-height:1.5">{html.escape(macro.summary)}</p>
    """)

    if ecfg.get("include_global_desk", True) and bundle.global_desk:
        sections.append(_build_global_desk_html(bundle.global_desk, cfg))

    if ecfg.get("include_india_desk", True) and bundle.india_desk:
        sections.append(_build_india_desk_html(bundle.india_desk))

    if ecfg.get("include_crypto_pulse", True) and bundle.crypto_pulse:
        crypto_board = bundle.global_desk.crypto_board if bundle.global_desk else None
        sections.append(_build_crypto_html(bundle.crypto_pulse, crypto_board))

    apex_cards = "".join(_build_apex_pick_html(p, i) for i, p in enumerate(result.picks, 1))
    sections.append(f"""
      <h2 id="equity-notes" style="font-size:18px;margin:32px 0 12px;color:#0f172a;border-top:2px solid #e2e8f0;padding-top:24px">📊 Core equity research notes ({len(result.picks)})</h2>
      <p style="margin:0 0 16px;font-size:13px;color:#64748b">Autopilot universe — full institutional notes with thesis, technicals, and sizing.</p>
      {apex_cards}
    """)

    if ecfg.get("include_model_portfolios", True):
        sections.append(_build_model_portfolios_html(result))

    dashboard_link = ""
    if brief_url:
        dashboard_link = f"<p style='margin-top:24px'><a href='{html.escape(brief_url)}' style='color:#2563eb;font-weight:600'>Open live morning brief on dashboard →</a></p>"

    body = "".join(sections) + dashboard_link

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"/></head>
<body style="margin:0;background:#f1f5f9;font-family:Segoe UI,Helvetica,Arial,sans-serif">
  <div style="max-width:720px;margin:0 auto;padding:24px">
    <div style="background:linear-gradient(135deg,#0f172a,#312e81);padding:28px;border-radius:16px 16px 0 0;color:white">
      <div style="font-size:11px;letter-spacing:1.5px;opacity:0.75">STOCK AUTOPILOT · FULL DESK DIGEST</div>
      <h1 style="margin:8px 0 0;font-size:22px">{html.escape(brand)}</h1>
      <p style="margin:6px 0 0;opacity:0.9;font-size:14px">Global · India · Crypto · Equity Research · {result.finished_at.strftime('%A, %B %d, %Y')} UTC</p>
      <p style="margin:8px 0 0;opacity:0.8;font-size:12px">Target {html.escape(target['label'])}</p>
    </div>
    <div style="background:white;padding:24px;border:1px solid #e2e8f0;border-top:none">
      <div style="background:#fef3c7;border:1px solid #fcd34d;border-radius:10px;padding:12px 14px;font-size:13px;color:#92400e;margin-bottom:20px">
        ⚠ Research publisher only — not financial advice. Returns are not guaranteed. You self-direct all trades.
      </div>
      {body}
    </div>
    <p style="text-align:center;color:#94a3b8;font-size:12px;margin-top:16px">
      Stock Autopilot · Run {html.escape(result.run_id)} · {result.scanned} core symbols · Global + India + Crypto desks included
    </p>
  </div>
</body>
</html>"""


def build_digest_plain(bundle: DailyDigestBundle, cfg: dict | None = None) -> str:
    cfg = cfg or load_config()
    ecfg = _email_cfg(cfg)
    result = bundle.result
    brand = brand_cfg()["brand_name"]
    target = get_return_target_pct()
    lines = [
        "Stock Autopilot — Full Desk Digest",
        f"{brand} · Global · India · Crypto · Equity Research",
        result.finished_at.strftime("%Y-%m-%d %H:%M UTC"),
        f"Return target: {target['label']}",
        "",
        "DISCLAIMER: Research publisher only. Not financial advice. No guaranteed returns.",
        "",
        f"Macro: {result.macro.regime} (risk {result.macro.risk_score})",
        result.macro.summary,
        "",
    ]

    if ecfg.get("include_global_desk", True) and bundle.global_desk:
        gd = bundle.global_desk
        lines.append(f"GLOBAL DESK — top {len(gd.global_top_picks)} picks")
        for p in gd.global_top_picks:
            lines.append(f"  • {p.symbol} ({p.country}) {p.rating} T{p.risk_tier} +{p.upside_pct:.0f}% — {p.desk_note[:80]}")
        lines.append("")

    if ecfg.get("include_india_desk", True) and bundle.india_desk:
        india = bundle.india_desk
        lines.append(f"INDIA DESK — {len(india.equities)} NSE picks")
        for eq in india.equities:
            lines.append(f"  • {eq.nse} {eq.rating} CMP ₹{eq.cmp:,.0f} → ₹{eq.target_12m:,.0f} (+{eq.upside_pct:.0f}%)")
        lines.append("")

    if ecfg.get("include_crypto_pulse", True) and bundle.crypto_pulse:
        pulse = bundle.crypto_pulse
        lines.append(f"CRYPTO PULSE — {pulse.session_name}")
        for asset in (pulse.btc, pulse.eth):
            lines.append(
                f"  • {asset.asset} ${asset.current_price:,.0f} {asset.bias_label} "
                f"({asset.confidence_pct}%) — {asset.desk_note[:80]}"
            )
        lines.append("")

    lines.append(f"CORE EQUITY NOTES ({len(result.picks)}):")
    lines.append("")
    for i, p in enumerate(result.picks, 1):
        if p.research_note_text:
            lines.append(p.research_note_text)
        else:
            lines.append(f"{i}. {p.symbol} — score {int(p.score*100)} — {p.name}")
            lines.append(f"   {p.rationale[:180]}")
        lines.append("")

    if ecfg.get("include_model_portfolios", True) and result.model_portfolios:
        lines.append("Model portfolios (illustrative — pick your style):")
        lines.append("")
        for model in result.model_portfolios:
            lines.append(f"{model.label}: cash {int(model.cash_pct*100)}%, benchmark {model.benchmark}")
            for h in model.holdings:
                lines.append(f"  • {h.symbol} {int(h.weight*100)}% (score {int(h.score*100)})")
            lines.append("")

    lines.append(f"Run: {result.run_id}")
    return "\n".join(lines)
