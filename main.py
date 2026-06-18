#!/usr/bin/env python3
"""Stock Autopilot CLI — run agent, start dashboard, or one-off scan."""

from __future__ import annotations

import argparse
import signal
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))


def _lan_ip() -> str | None:
    import socket

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return None


def _port_in_use(port: int) -> bool:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def _print_dashboard_urls(host: str, port: int) -> None:
    mac_url = f"http://127.0.0.1:{port}"
    print("\n── Dashboard URLs ──────────────────────────────")
    print(f"  Mac browser:     {mac_url}")
    if host in ("0.0.0.0", "::"):
        lan = _lan_ip()
        if lan:
            print(f"  Phone (same Wi‑Fi): http://{lan}:{port}")
            print(f"  Set in .env:     DASHBOARD_URL=http://{lan}:{port}")
        else:
            print("  Phone: connect to Wi‑Fi, then use your Mac's IP instead of 127.0.0.1")
    else:
        print("  Phone on Wi‑Fi:  won't work with --host 127.0.0.1")
        print("  Use instead:     python main.py serve --host 0.0.0.0")
    print("  Health check:    curl http://127.0.0.1:{}/health".format(port))
    print("────────────────────────────────────────────────\n")


def cmd_check_dashboard(args: argparse.Namespace) -> None:
    import urllib.error
    import urllib.request

    url = f"http://127.0.0.1:{args.port}/health"
    print(f"Checking {url} …")
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            body = resp.read().decode()
        print(f"✓ Dashboard is running ({body})")
        _print_dashboard_urls("127.0.0.1", args.port)
    except urllib.error.URLError:
        print("✗ Nothing responding on that port.")
        print("\nStart the server first (keep this terminal open):")
        print(f"  cd {ROOT}")
        print("  source .venv/bin/activate")
        print(f"  PYTHONPATH=src python main.py serve --port {args.port}")
        print("\nThen open: http://127.0.0.1:{}".format(args.port))
        sys.exit(1)


def cmd_run(_: argparse.Namespace) -> None:
    from stock_autopilot.agent.orchestrator import run_autopilot

    result = run_autopilot()
    print(f"\nCompleted: {result.run_id} — {len(result.picks)} picks")
    for i, p in enumerate(result.picks, 1):
        print(f"  {i}. {p.symbol} ({p.score:.2f}) — {p.name}")


def cmd_serve(args: argparse.Namespace) -> None:
    import uvicorn

    if _port_in_use(args.port):
        print(f"⚠ Port {args.port} is already in use.")
        print(f"  If the dashboard is already running, open: http://127.0.0.1:{args.port}")
        print("  Or stop the other process: lsof -i :{}".format(args.port))
        print("  Or use another port: --port 8081")
        print(f"  Stop old server:  PYTHONPATH=src python main.py stop --port {args.port}")
        sys.exit(1)

    _print_dashboard_urls(args.host, args.port)
    uvicorn.run(
        "stock_autopilot.api.app:app",
        host=args.host,
        port=args.port,
        reload=False,
    )


def cmd_autopilot(args: argparse.Namespace) -> None:
    import uvicorn

    if _port_in_use(args.port):
        print(f"⚠ Port {args.port} is already in use.")
        print(f"  Stop old server:  PYTHONPATH=src python main.py stop --port {args.port}")
        print("  Or use another port: --port 8081")
        sys.exit(1)

    _print_dashboard_urls(args.host, args.port)
    print("(Daily agent runs on schedule after startup)\n")
    uvicorn.run(
        "stock_autopilot.api.app:app",
        host=args.host,
        port=args.port,
        reload=False,
    )


def cmd_stop(args: argparse.Namespace) -> None:
    result = subprocess.run(
        ["lsof", "-ti", f":{args.port}"],
        capture_output=True,
        text=True,
    )
    pids = [p.strip() for p in result.stdout.splitlines() if p.strip()]
    if not pids:
        print(f"No process listening on port {args.port}")
        return

    for pid in pids:
        try:
            subprocess.run(["kill", pid], check=False)
            print(f"Stopped PID {pid}")
        except Exception as e:
            print(f"Could not stop PID {pid}: {e}")

    print(f"Port {args.port} is free. Start again with: PYTHONPATH=src python main.py serve")


def cmd_check_email(_: argparse.Namespace) -> None:
    from stock_autopilot.notifications.email import check_smtp_connection, get_recipients, validate_smtp_config
    from stock_autopilot.universe import load_config

    cfg = load_config()
    issues = validate_smtp_config(cfg)
    if issues:
        print("Configuration issues:")
        for i in issues:
            print(f"  • {i}")
        print()
    else:
        print("Config looks OK.")
        print(f"  SMTP_USER: {__import__('stock_autopilot.config', fromlist=['settings']).settings.smtp_user}")
        print(f"  Recipients: {', '.join(get_recipients(cfg))}")
        print()

    print("Testing SMTP login…")
    try:
        check_smtp_connection()
        print("✓ Gmail login successful — you can run: python main.py test-email")
    except ValueError as e:
        print(str(e))
        sys.exit(1)


def cmd_test_email(args: argparse.Namespace) -> None:
    from stock_autopilot.db import init_db
    from stock_autopilot.notifications.email import get_recipients, is_email_enabled, load_digest_bundle, send_daily_digest
    from stock_autopilot.universe import load_config

    init_db()
    cfg = load_config()
    if not is_email_enabled(cfg):
        print("Email not configured. Set notifications.email in config.yaml and SMTP_* in .env")
        print(f"Recipients: {get_recipients(cfg)}")
        sys.exit(1)

    refresh = getattr(args, "refresh", False)
    if refresh:
        from stock_autopilot.agent.commodities_desk import run_commodities_desk
        from stock_autopilot.agent.crypto_pulse import run_crypto_pulse
        from stock_autopilot.agent.global_desk import run_global_desk
        from stock_autopilot.agent.india_desk import run_india_desk
        from stock_autopilot.agent.orchestrator import run_autopilot

        print("Refreshing all desks before send…")
        result = run_autopilot()
        run_commodities_desk()
        global_snap = run_global_desk()
        india_snap = run_india_desk()
        crypto_snap = run_crypto_pulse()
        count = send_daily_digest(
            result, cfg, global_desk=global_snap, india_desk=india_snap, crypto_pulse=crypto_snap
        )
    else:
        try:
            bundle = load_digest_bundle()
        except ValueError as e:
            print(str(e), "— run `python main.py run` first, or use `test-email --refresh`.")
            sys.exit(1)
        count = send_daily_digest(
            bundle.result,
            cfg,
            global_desk=bundle.global_desk,
            india_desk=bundle.india_desk,
            crypto_pulse=bundle.crypto_pulse,
        )

    print(f"Sent full desk digest to {count} recipient(s): {', '.join(get_recipients(cfg))}")


def cmd_india_desk(_: argparse.Namespace) -> None:
    from stock_autopilot.agent.india_desk import run_india_desk

    snap = run_india_desk()
    print(f"\n🇮🇳 LUMIQ India Desk — {snap.captured_at.strftime('%Y-%m-%d %H:%M UTC')}")
    print(snap.macro.ticker_text)
    print(f"\nEquity picks ({len(snap.equities)}):")
    for eq in snap.equities:
        print(f"  {eq.rating} {eq.nse} ₹{eq.cmp:,.0f} → ₹{eq.target_12m:,.0f} (+{eq.upside_pct}%) Tier {eq.risk_tier}")
    print(f"\nMF: {len(snap.mutual_funds)} | Bonds: {len(snap.bonds)} | FDs: {len(snap.fixed_deposits)}")
    print(f"\n{snap.disclaimer}")


def cmd_validate_tickers(args: argparse.Namespace) -> None:
    from stock_autopilot.collectors.ticker_validate import invalid_symbols, validate_universe

    sources = None if args.source == "all" else [args.source]
    if args.invalid_only:
        rows = invalid_symbols(sources)
    else:
        rows = validate_universe(sources)

    ok_n = sum(1 for r in rows if r.ok)
    print(f"\nTicker validation — {ok_n}/{len(rows)} OK\n")
    for r in rows:
        if args.invalid_only or not r.ok:
            mark = "✓" if r.ok else "✗"
            print(f"  {mark} {r.symbol:<16} [{r.source}] {r.reason}")
    bad = [r for r in rows if not r.ok]
    if bad:
        print(f"\n{len(bad)} invalid symbol(s). Update config/global_desk.yaml or regions in config.yaml.")
        sys.exit(1)


def cmd_resolve_outcomes(_: argparse.Namespace) -> None:
    from stock_autopilot.analysis.outcomes import resolve_due_outcomes, track_record_summary
    from stock_autopilot.db import init_db

    init_db()
    n = resolve_due_outcomes()
    stats = track_record_summary()
    print(f"Resolved {n} outcome(s)")
    print(f"Total resolved: {stats.get('total_resolved')} | Hit rate: {stats.get('hit_rate_pct')}%")
    live = stats.get("live_open", {})
    print(f"Open calls: {live.get('count')} | Avg return: {live.get('avg_return_pct')}%")


def cmd_global_desk(_: argparse.Namespace) -> None:
    from stock_autopilot.agent.global_desk import run_global_desk

    snap = run_global_desk()
    print(f"\n🌍 Global Desk — {snap.captured_at.strftime('%Y-%m-%d %H:%M UTC')}")
    print(snap.opening_statement[:200] + "...")
    print(f"\nRegional boards: {len(snap.regional_boards)} | Crypto categories: {len(snap.crypto_board)}")
    for board in snap.regional_boards[:4]:
        print(f"\n{board.label} — {board.theme}")
        for p in board.picks[:3]:
            print(f"  #{p.rank} {p.symbol} {p.rating} +{p.upside_pct}% T{p.risk_tier}")
    print(f"\nGlobal top picks ({len(snap.global_top_picks)}):")
    for p in snap.global_top_picks[:5]:
        print(f"  {p.symbol} ({p.country}) score {p.score:.2f} +{p.upside_pct}%")
    print(f"\n{snap.disclaimer}")


def cmd_market_pulse(_: argparse.Namespace) -> None:
    from stock_autopilot.agent.market_pulse import run_market_pulse

    snap = run_market_pulse()
    print(f"\nMarket Pulse — {snap.captured_at.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"Session: {snap.session_label} · {len(snap.boards)} regional boards")
    if snap.crypto:
        print(f"Crypto MCap: ${snap.crypto.total_market_cap_usd/1e9:.0f}B · {snap.crypto.fear_greed_label}")
    india = next((b for b in snap.boards if b.market_id == "india"), None)
    if india:
        print(f"India: {len(india.top_gainers)} gainers · {len(india.week_52_highs)} at 52W high")


def cmd_deep_brief(args: argparse.Namespace) -> None:
    from stock_autopilot.analysis.deep_intelligence import build_deep_brief

    brief = build_deep_brief(args.symbol, trigger_context=args.context or "")
    if not brief:
        print(f"No data for {args.symbol}")
        sys.exit(1)
    print(brief.card_text)


def cmd_commodities_desk(_: argparse.Namespace) -> None:
    from stock_autopilot.agent.commodities_desk import run_commodities_desk

    snap = run_commodities_desk()
    print(f"\nCommodities Desk — {snap.captured_at.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"Regime: {snap.regime}")
    print(f"Pulse: {snap.commodity_pulse}")
    print(f"Categories: {len(snap.categories)} · Picks: {len(snap.desk_picks)}")
    for p in snap.desk_picks[:4]:
        print(f"  #{p.rank} {p.name} ({p.bias_label}) · 1D {p.change_1d_pct:+.1f}%")


def cmd_crypto_pulse(_: argparse.Namespace) -> None:
    from stock_autopilot.agent.crypto_pulse import run_crypto_pulse

    pulse = run_crypto_pulse()
    print(f"\nLUMIQ Crypto Desk — {pulse.captured_at.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"Session: {pulse.session_name}")
    for coin in (pulse.btc, pulse.eth):
        print(f"\n{coin.card_text}")
    if pulse.btc.prior_outcome:
        print(f"\nAccountability: BTC — {pulse.btc.prior_outcome}")
    if pulse.eth.prior_outcome:
        print(f"Accountability: ETH — {pulse.eth.prior_outcome}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Stock Autopilot — global analysis agent")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("run", help="Run one agent cycle now").set_defaults(func=cmd_run)

    sub.add_parser("check-email", help="Validate SMTP settings and test Gmail login").set_defaults(func=cmd_check_email)

    p_test = sub.add_parser("test-email", help="Send full desk digest using latest DB snapshots")
    p_test.add_argument("--refresh", action="store_true", help="Run all desks fresh before sending")
    p_test.set_defaults(func=cmd_test_email)

    sub.add_parser("crypto-pulse", help="Run BTC/ETH hourly crypto prediction now").set_defaults(func=cmd_crypto_pulse)

    sub.add_parser("commodities-desk", help="Run commodities futures & macro desk").set_defaults(func=cmd_commodities_desk)

    sub.add_parser("india-desk", help="Run LUMIQ India equities + MF/Bonds/FD desk").set_defaults(func=cmd_india_desk)

    sub.add_parser("global-desk", help="Run global regional boards + tiered crypto scan").set_defaults(func=cmd_global_desk)

    sub.add_parser("market-pulse", help="Run live market pulse boards (all regions + crypto)").set_defaults(func=cmd_market_pulse)

    p_deep = sub.add_parser("deep-brief", help="Print LUMIQ deep intelligence card for a symbol")
    p_deep.add_argument("symbol", help="Ticker e.g. AAPL or RELIANCE.NS")
    p_deep.add_argument("--context", default="", help="Trigger context: 52w_high, 52w_low, gainer")
    p_deep.set_defaults(func=cmd_deep_brief)

    vt = sub.add_parser("validate-tickers", help="Validate Yahoo/CoinGecko symbols in config")
    vt.add_argument("--source", default="all", choices=["all", "regions", "india", "global", "crypto"])
    vt.add_argument("--invalid-only", action="store_true")
    vt.set_defaults(func=cmd_validate_tickers)

    sub.add_parser("resolve-outcomes", help="Resolve due pick outcomes + print track record").set_defaults(func=cmd_resolve_outcomes)

    check_dash = sub.add_parser("check-dashboard", help="Test if dashboard is reachable locally")
    check_dash.add_argument("--port", type=int, default=8080)
    check_dash.set_defaults(func=cmd_check_dashboard)

    stop = sub.add_parser("stop", help="Stop dashboard server on a port (free stuck sessions)")
    stop.add_argument("--port", type=int, default=8080)
    stop.set_defaults(func=cmd_stop)

    serve = sub.add_parser("serve", help="Start dashboard only")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8080)
    serve.set_defaults(func=cmd_serve)

    auto = sub.add_parser("autopilot", help="Dashboard + daily scheduled agent (recommended)")
    auto.add_argument("--host", default="127.0.0.1")
    auto.add_argument("--port", type=int, default=8080)
    auto.set_defaults(func=cmd_autopilot)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()
