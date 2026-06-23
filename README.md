# LUMIQ

[![CI](https://github.com/mkari198920feb/stock-autopilot/actions/workflows/ci.yml/badge.svg)](https://github.com/mkari198920feb/stock-autopilot/actions/workflows/ci.yml)

Side project I use to watch markets without living in twelve tabs. **LUMIQ** runs a bunch of small "desks" on a schedule — US/global equities, India (NSE + MF via AMFI), crypto, commodities — pulls quotes from Yahoo Finance and CoinGecko, applies dumb rule-based scoring (RSI, momentum, that kind of thing), and can email a daily digest. There's a FastAPI dashboard if you want to poke at it locally.

**Not financial advice.** This is research tooling for myself and a few friends. Signals are heuristics, not predictions. Past backtests don't mean future returns.

## Quick start

```bash
git clone https://github.com/mkari198920feb/stock-autopilot.git
cd stock-autopilot
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # SMTP + recipients if you want email

python main.py autopilot --port 8080
```

Browser: http://127.0.0.1:8080

## Commands worth knowing

| What | Command |
|------|---------|
| Dashboard + scheduler | `python main.py autopilot --port 8080` |
| One-shot daily run | `python main.py run` |
| Global desk | `python main.py global-desk` |
| India desk | `python main.py india-desk` |
| Crypto pulse | `python main.py crypto-pulse` |
| Commodities | `python main.py commodities-desk` |
| Market pulse (30m) | `python main.py market-pulse` |
| Single ticker deep dive | `python main.py deep-brief RELIANCE.NS` |
| Rule backtest sanity check | `python main.py signal-backtest` |
| Feed health | `python main.py data-health` |
| Test SMTP | `python main.py check-email` |

Email digest fires after the autopilot cron if SMTP is configured.

## Layout

```
main.py                 CLI + serves the web UI
config.yaml             watchlists, crons, brand, auth toggle
data/universe/nyse.txt  full NYSE common-stock list (Yahoo symbols)
scripts/                refresh_nyse_universe.py
src/stock_autopilot/
  agent/                desk runners
  collectors/           yfinance, coingecko, amfi
  analysis/             scoring, notes, backtests
  api/                  FastAPI + dashboard HTML
  notifications/        digest email builder
  db.py                 sqlite
tests/
```

Data: mostly Yahoo Finance + CoinGecko + AMFI NAV files. Free tiers — expect delays and occasional gaps.

## Config

**`config.yaml`** — universes, desk schedules, `apex.brand_name` (LUMIQ), optional RBAC if you put this behind a gateway. Keep `notifications.email.recipients` empty in git; use env vars for actual addresses.

### NYSE universe

The full NYSE common-stock list lives in **`data/universe/nyse.txt`** (~2,000 symbols, one per line, Yahoo format). Autopilot and the global US desk merge it at runtime — no need to paste tickers into `config.yaml`.

Refresh when listings change (IPO/delisting season):

```bash
python scripts/refresh_nyse_universe.py
```

Source: [NASDAQ Trader otherlisted.txt](https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt) — filtered to NYSE (`Exchange=N`) common equities; ETFs, preferreds, warrants, units, and test symbols are dropped. Class shares use Yahoo dashes (`BRK-B`).

Large scans use batched yfinance pulls (`agent.scan_batch_size`) and cap news fetch (`agent.max_news_symbols`). Volume filtering still happens at pick time, not when loading the universe.

**`.env`** — `SMTP_*`, `EMAIL_RECIPIENTS`, optional `OPENAI_API_KEY` for slightly nicer narrative blurbs in emails. See `.env.example`.

## If you deploy it publicly

Flip `auth.enabled: true` in `config.yaml` and pass headers from your reverse proxy / IAM:

- `X-LUMIQ-User`
- `X-LUMIQ-Roles` (`admin`, `analyst`, `viewer`)

Write operations need `desk:write`.

Handy routes: `GET /health`, `GET /api/data-health`, `POST /api/run-now`.

## Tests

```bash
pytest -q
```

## Screenshots

PNG dumps go in `docs/screenshots/` (`dashboard-overview.png`, etc.) if you want them in the README. Nothing there yet — run the dashboard and grab your own.

## License

MIT — see [LICENSE](LICENSE).

(Unrelated: I also have a public [agentic-ai-academy](https://github.com/mkari198920feb/agentic-ai-academy) wiki for ML stuff.)
