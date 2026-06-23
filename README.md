# LUMIQ — Stock Autopilot

[![LUMIQ CI](https://github.com/mkari198920feb/stock-autopilot/actions/workflows/ci.yml/badge.svg)](https://github.com/mkari198920feb/stock-autopilot/actions/workflows/ci.yml)

**LUMIQ** is a multi-desk research autopilot: global equities, India NSE, crypto signals, commodities, live market pulse, and daily email digest — tuned toward a configurable return profile.

Built by [Muralikrishna Kari](https://github.com/mkari198920feb).

> **Disclaimer:** Research software, not financial advice. Signals are rule-based heuristics, not ML predictions. No returns are guaranteed.

---

## Screenshots

> Add captures under [`docs/screenshots/`](docs/screenshots/) — see that folder for filenames and instructions.

<!-- Uncomment after adding images:
![LUMIQ dashboard](docs/screenshots/dashboard-overview.png)
![Market pulse](docs/screenshots/market-pulse.png)
-->

---

## Related projects (public)

| Project | Repo | Description |
|---------|------|-------------|
| **Agentic AI Academy** | [agentic-ai-academy](https://github.com/mkari198920feb/agentic-ai-academy) | AI/ML learning wiki |
| **Robinhood Agent** | [robinhood-trading-agent](https://github.com/mkari198920feb/robinhood-trading-agent) | Rules-based trading decision support |

Other portfolio repos (`hireflow`, `job-application-agent`) are private.

---

## Desks

| Desk | Command | Schedule |
|------|---------|----------|
| Global autopilot | `python main.py run` | Daily autopilot cron |
| Web dashboard | `python main.py autopilot --port 8080` | On demand |
| Global Intelligence | `python main.py global-desk` | Daily |
| India Desk | `python main.py india-desk` | Daily |
| Crypto Signals | `python main.py crypto-pulse` | Hourly |
| Commodities | `python main.py commodities-desk` | Hourly |
| Market Pulse | `python main.py market-pulse` | Every 30 min |
| Deep Brief | `python main.py deep-brief RELIANCE.NS` | On demand |
| Signal validation | `python main.py signal-backtest` | On demand |
| Data health | `python main.py data-health` | Hourly |
| Email digest | Built into autopilot cron | Daily |

---

## Quick start

```bash
git clone https://github.com/mkari198920feb/stock-autopilot.git
cd stock-autopilot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env — SMTP, EMAIL_RECIPIENTS, optional OPENAI_API_KEY

python main.py autopilot --host 0.0.0.0 --port 8080
```

Open **http://127.0.0.1:8080**

---

## Architecture

```
stock-autopilot/
├── main.py                      # CLI entry + FastAPI dashboard
├── config.yaml                  # Universes, crons, brand, auth/RBAC
├── src/stock_autopilot/
│   ├── agent/                   # Desk runners (global, india, crypto, …)
│   ├── analysis/                # Scoring, backtests, research notes
│   ├── api/                     # FastAPI app + dashboard templates
│   ├── collectors/              # Yahoo, CoinGecko, AMFI data feeds
│   ├── notifications/           # Email digest builder
│   └── db.py                    # SQLite persistence
├── tests/                       # pytest suite
├── docs/screenshots/            # Dashboard captures for README / LinkedIn
└── .env                         # Secrets (gitignored)
```

### Data sources

| Source | Used for |
|--------|----------|
| Yahoo Finance | Equities, indices, commodities proxies |
| CoinGecko | Crypto prices |
| AMFI | India mutual fund NAV |

---

## Configuration

### `config.yaml`

- **Universes** — watchlists per desk (US, NSE, crypto)
- **Desk crons** — schedule for each research desk
- **Brand** — `apex.brand_name: LUMIQ`
- **Auth/RBAC** — optional IAM federation scaffold
- **Email recipients** — keep empty in git; set via `.env` (`EMAIL_RECIPIENTS`)

### `.env`

| Variable | Purpose |
|----------|---------|
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS` | Email digest delivery |
| `EMAIL_RECIPIENTS` | Comma-separated recipient list |
| `OPENAI_API_KEY` | Optional AI narrative summaries |

---

## Security (production deployment)

Set in `config.yaml`:

```yaml
auth:
  enabled: true
  mode: iam_federation
```

Pass identity from your gateway:

- `X-LUMIQ-User` — user id from IAM federation
- `X-LUMIQ-Roles` — comma-separated roles (`admin`, `analyst`, `viewer`)

Mutating API routes require `desk:write`. Read-only dashboard works with `viewer`.

---

## API

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/health` | Service + data probe status |
| GET | `/api/data-health` | Yahoo, CoinGecko, AMFI probe results |
| POST | `/api/run-now` | Trigger autopilot (auth required when enabled) |

---

## Tests

```bash
pytest -q
```

---

## Limitations

- Yahoo Finance + CoinGecko + AMFI free tiers (delays, rate limits, no vendor-grade entitlements)
- India MF NAV from AMFI; G-Sec/SGB use Yahoo proxies; FD rates are curated with `last_verified` dates
- Rule-based RSI backtests and desk hit-rate tracking — **not ML forecasting**
- SQLite single-user store — use Postgres for multi-tenant production

---

## Author

**Muralikrishna Kari** — [GitHub](https://github.com/mkari198920feb)

## License

[MIT](LICENSE) — research tooling; not financial advice.
