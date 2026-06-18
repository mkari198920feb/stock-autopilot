# Stock Autopilot

A **global stock analysis agent** that runs on autopilot: scans macro conditions worldwide, pulls news (partnerships, M&A, earnings themes), scores a liquid global universe, and surfaces **daily stock suggestions** tuned toward a **12–15% annual return profile**.

> **Disclaimer:** This is research software, not financial advice. **No returns are guaranteed.** The 12–15% band is a screening target, not a promise. Always do your own due diligence.

## What it does

1. **Global macro** — S&P, VIX, rates, oil, gold, EM vs developed (via Yahoo Finance)
2. **Stock scan** — Configurable universe across North America, Europe, Asia-Pacific, global ETFs
3. **News analysis** — Headlines per symbol; sentiment + themes (partnerships, M&A, earnings, regulatory)
4. **Scoring agent** — Momentum, valuation, volatility fit, news, macro alignment
5. **Daily autopilot** — Scheduled run + SQLite history + web dashboard
6. **Optional LLM** — Set `OPENAI_API_KEY` for richer macro summaries

## Quick start

```bash
cd ~/Projects/stock-autopilot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

# One-off agent run (CLI)
python main.py run

# Dashboard + daily autopilot scheduler (recommended)
python main.py autopilot
```

Open http://127.0.0.1:8080

Click **Run agent now** for an immediate scan, or wait for the daily schedule (default **13:30 UTC**).

## Commands

| Command | Description |
|---------|-------------|
| `python main.py run` | Run agent once, print picks |
| `python main.py serve` | Dashboard only (no scheduler) |
| `python main.py autopilot` | Dashboard + daily scheduled agent |

## Configuration

Edit `config.yaml`:

- **`regions`** — tickers to scan (Yahoo Finance symbols)
- **`macro_symbols`** — global indicators
- **`agent.daily_picks`** — how many suggestions per run
- **`scoring.weights`** — factor weights

Environment (`.env`):

- `AUTOPILOT_HOUR` / `AUTOPILOT_MINUTE` — daily run time (UTC)
- `TARGET_RETURN_MIN` / `TARGET_RETURN_MAX` — screening band (default 0.12–0.15)
- `OPENAI_API_KEY` — optional LLM summaries

### Daily email to friends

Add friend emails in `config.yaml` under `notifications.email.recipients`, then set SMTP in `.env`:

```bash
cp .env.example .env
# Edit .env: SMTP_USER, SMTP_PASSWORD (Gmail App Password), EMAIL_RECIPIENTS
```

Gmail: create an [App Password](https://myaccount.google.com/apppasswords) (2FA required).

```bash
# Test email with your last agent run
PYTHONPATH=src python main.py test-email

# Autopilot sends email automatically after each daily run
PYTHONPATH=src python main.py autopilot
```

Each email includes global regime, daily picks, scores, and rationale — no dashboard URL required.

## Architecture

```
Autopilot Agent (daily)
  ├─ Macro collector → regime (Risk-On / Neutral / Risk-Off)
  ├─ Market collector → returns, vol, RSI, momentum
  ├─ News collector → sentiment, partnership/M&A themes
  ├─ Scorer → ranked picks with rationale
  └─ SQLite → dashboard API
```

## API

- `GET /` — Dashboard
- `GET /api/latest` — Latest run JSON
- `POST /api/run-now` — Trigger agent immediately
- `GET /health` — Health check

## Limitations

- Uses free Yahoo Finance data (delays, occasional gaps)
- Rule-based news sentiment (not a substitute for reading primary sources)
- Cannot predict markets or guarantee 12–15% returns
- Not licensed investment advice — for educational/research use

## Extend

- Add your watchlist in `config.yaml`
- Wire a broker API for paper trading (not included)
- Add email/Slack alerts on new picks
- Expand LLM analysis for collaboration detection
