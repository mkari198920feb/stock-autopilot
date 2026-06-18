from __future__ import annotations

import uuid
from datetime import datetime, timezone

from stock_autopilot.analysis.portfolios import build_model_portfolios
from stock_autopilot.analysis.research_notes import format_macro_briefing
from stock_autopilot.analysis.scorer import rank_candidates
from stock_autopilot.collectors.macro import analyze_global_conditions
from stock_autopilot.collectors.market import batch_fetch_metrics
from stock_autopilot.collectors.news import aggregate_news_sentiment, fetch_news_for_symbol
from stock_autopilot.config import settings
from stock_autopilot.db import init_db, save_run
from stock_autopilot.analysis.outcomes import record_autopilot_picks, resolve_due_outcomes
from stock_autopilot.models.schemas import AgentRunResult
from stock_autopilot.universe import all_tickers, load_config, ticker_region_map
from stock_autopilot.notifications.email import is_email_enabled, send_daily_digest


class AutopilotAgent:
    """Daily agent loop: macro → scan → news → score → recommend → persist."""

    def __init__(self) -> None:
        self.cfg = load_config()
        self.log: list[str] = []

    def _log(self, msg: str) -> None:
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        self.log.append(line)
        print(line)

    def run(self) -> AgentRunResult:
        init_db()
        run_id = datetime.now(timezone.utc).strftime("%Y%m%d") + "-" + uuid.uuid4().hex[:8]
        started = datetime.now(timezone.utc)
        self.log = []
        self._log(f"Autopilot run {run_id} started")

        agent_cfg = self.cfg.get("agent", {})
        weights = self.cfg.get("scoring", {}).get("weights", {})

        self._log("Step 1/5: Analyzing global macro conditions")
        macro = analyze_global_conditions(self.cfg.get("macro_symbols", {}))
        macro.summary = format_macro_briefing(macro)
        self._log(f"Regime: {macro.regime} (risk {macro.risk_score})")

        symbols = all_tickers(self.cfg)
        region_map = ticker_region_map(self.cfg)
        lookback = agent_cfg.get("lookback_days", 252)

        self._log(f"Step 2/5: Scanning {len(symbols)} global symbols")
        metrics = batch_fetch_metrics(symbols, region_map, lookback)
        self._log(f"Loaded metrics for {len(metrics)} symbols")

        self._log("Step 3/5: Fetching news & collaboration themes")
        news_map: dict[str, tuple[float, list[str], list[str]]] = {}
        for m in metrics:
            news = fetch_news_for_symbol(m.symbol, limit=6)
            news_map[m.symbol] = aggregate_news_sentiment(news)

        self._log("Step 4/5: Scoring & ranking for return profile")
        from stock_autopilot.investor_profile import get_return_target_pct

        band = get_return_target_pct()
        self._log(f"Target band: {band['target_min_pct']}–{band['target_max_pct']}% / yr")
        picks = rank_candidates(
            metrics,
            macro,
            news_map,
            weights,
            daily_picks=agent_cfg.get("daily_picks", 8),
            max_per_region=agent_cfg.get("max_per_region", 3),
            max_per_sector=agent_cfg.get("max_per_sector", 2),
            min_avg_volume=agent_cfg.get("min_avg_volume", 500_000),
        )
        self._log(f"Selected {len(picks)} daily suggestions")

        self._log("Building model portfolios (Conservative / Balanced / Growth)")
        model_portfolios = build_model_portfolios(
            metrics,
            macro,
            news_map,
            self.cfg,
            min_avg_volume=agent_cfg.get("min_avg_volume", 500_000),
        )
        self._log(f"Published {len(model_portfolios)} model portfolios for friends")

        optional_summary = self._maybe_llm_summary(macro, picks)
        if optional_summary:
            macro.summary = optional_summary

        finished = datetime.now(timezone.utc)
        result = AgentRunResult(
            run_id=run_id,
            started_at=started,
            finished_at=finished,
            macro=macro,
            picks=picks,
            model_portfolios=model_portfolios,
            scanned=len(metrics),
            status="completed",
            log=self.log,
        )

        self._log("Step 5/5: Persisting results")
        save_run(result)
        try:
            record_autopilot_picks(result.run_id, result.finished_at, result.picks)
            n = resolve_due_outcomes()
            from stock_autopilot.investor_profile import mark_picks_ranked_for_target

            mark_picks_ranked_for_target()
            if n:
                self._log(f"Resolved {n} pick outcome(s)")
        except Exception as e:
            self._log(f"Outcome tracking skipped: {e}")

        try:
            from stock_autopilot.agent.india_desk import run_india_desk

            india = run_india_desk()
            self._log(f"India desk: {len(india.equities)} NSE picks + MF/Bonds/FD advisory")
        except Exception as e:
            self._log(f"India desk skipped: {e}")

        if is_email_enabled(self.cfg):
            try:
                count = send_daily_digest(result, self.cfg)
                self._log(f"Email digest sent to {count} recipient(s)")
            except Exception as e:
                self._log(f"Email failed: {e}")
        else:
            self._log("Email notifications disabled (see config.yaml + .env)")

        self._log("Autopilot run complete")
        return result

    def _maybe_llm_summary(self, macro, picks) -> str | None:
        if not settings.openai_api_key:
            return None
        try:
            from openai import OpenAI

            client = OpenAI(api_key=settings.openai_api_key)
            pick_lines = [f"- {p.symbol}: {p.rationale[:120]}" for p in picks[:5]]
            prompt = (
                "Summarize today's global market regime and stock screen in 3 sentences for a dashboard. "
                "Include risk disclaimer. Do not guarantee returns.\n\n"
                f"Regime: {macro.regime}\nIndicators: {macro.indicators}\nPicks:\n" + "\n".join(pick_lines)
            )
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
            )
            return resp.choices[0].message.content
        except Exception as e:
            self._log(f"LLM summary skipped: {e}")
            return None


def run_autopilot() -> AgentRunResult:
    return AutopilotAgent().run()
