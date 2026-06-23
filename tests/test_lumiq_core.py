from unittest.mock import patch

import pytest

from stock_autopilot.analysis.india_advisory import build_bond_notes, build_mutual_fund_notes
from stock_autopilot.analysis.outcomes import _classify_crypto_bias, _classify_equity
from stock_autopilot.analysis.signal_backtest import (
    backtest_rsi_reversal,
    signal_validation_report,
)
from stock_autopilot.api.auth import auth_settings, permissions_for_roles
from stock_autopilot.collectors.amfi import lookup_amfi_nav, parse_amfi_nav_all as amfi_parse
from stock_autopilot.collectors.data_health import run_data_health_check
from stock_autopilot.universe import brand_cfg, load_nyse_tickers, north_america_tickers

SAMPLE_AMFI = """Scheme Code;ISIN Div Payout/ISIN Growth;ISIN Div Reinvestment;Scheme Name;Net Asset Value;Date
122639;INF879O01027;;Parag Parikh Flexi Cap Fund - Direct Plan - Growth;85.1234;17-Jun-2026
118834;INF769K01AX2;;Mirae Asset Large Cap Fund - Direct Plan - Growth;112.50;17-Jun-2026
"""


def test_brand_name_is_lumiq():
    cfg = brand_cfg()
    assert cfg["brand_name"] == "LUMIQ"
    assert "LUMIQ" in cfg["research_header"]


def test_nyse_universe_loaded():
    tickers = load_nyse_tickers()
    assert len(tickers) >= 1500
    assert "JPM" in tickers
    assert "BRK-B" in tickers
    assert all(" " not in t for t in tickers)


def test_north_america_merges_nyse_file():
    merged = north_america_tickers()
    assert len(merged) >= len(load_nyse_tickers())
    assert merged == sorted(set(merged))


def test_equity_hit_on_strong_gain():
    ret, outcome, hit = _classify_equity(100, 106, 10, "BUY", "7d")
    assert ret == 6.0
    assert outcome == "HIT"


def test_crypto_bullish_hit():
    ret, outcome, _ = _classify_crypto_bias(100, 101, "bullish")
    assert outcome == "HIT"


def test_rbac_admin_has_write():
    cfg = auth_settings({"auth": {"rbac": {"roles": {"admin": {"permissions": ["desk:write"]}}}}})
    perms = permissions_for_roles({"admin"}, cfg)
    assert "desk:write" in perms


def test_rbac_viewer_read_only():
    cfg = auth_settings({"auth": {"rbac": {"default_role": "viewer"}}})
    perms = permissions_for_roles({"viewer"}, cfg)
    assert "desk:read" in perms
    assert "desk:write" not in perms


def test_amfi_parse_and_lookup():
    rows = amfi_parse(SAMPLE_AMFI)
    assert "122639" in rows
    assert rows["122639"]["nav"] == pytest.approx(85.1234)
    hit = lookup_amfi_nav({"amfi_scheme_code": "118834"}, rows)
    assert hit is not None
    assert hit["nav"] == pytest.approx(112.50)


def test_build_mutual_fund_notes_with_amfi(monkeypatch):
    rows = amfi_parse(SAMPLE_AMFI)

    def fake_fetch(*args, **kwargs):
        return rows

    monkeypatch.setattr("stock_autopilot.analysis.india_advisory.fetch_amfi_nav_map", fake_fetch)
    cfg = {
        "india_desk": {
            "mutual_funds": [
                {
                    "name": "Parag Parikh Flexi Cap Fund — Direct Growth",
                    "amfi_scheme_code": "122639",
                    "category": "Flexi Cap",
                    "returns_1y": "22%",
                }
            ]
        }
    }
    notes = build_mutual_fund_notes(cfg)
    assert len(notes) == 1
    assert notes[0].data_source == "amfi"
    assert notes[0].nav is not None
    assert "85.12" in notes[0].nav


def test_build_bond_notes_live_gsec(monkeypatch):
    monkeypatch.setattr(
        "stock_autopilot.analysis.india_advisory.fetch_india_market_rates",
        lambda **kw: {"gsec_yield_pct": 7.12, "gsec_as_of": "2026-06-17"},
    )
    cfg = {
        "india_desk": {
            "bonds": [
                {"name": "10Y G-Sec", "type": "G-Sec", "yield": "7.0% YTM (approx)"},
            ]
        }
    }
    notes = build_bond_notes(cfg)
    assert "7.12" in notes[0].yield_label
    assert notes[0].data_source == "yfinance"


def test_data_health_structure(monkeypatch):
    monkeypatch.setattr(
        "stock_autopilot.collectors.data_health._probe_yahoo",
        lambda sym, **kw: {"symbol": sym, "ok": True, "price": 100.0, "bar_date": "2026-06-17", "stale_days": 0},
    )
    monkeypatch.setattr(
        "stock_autopilot.collectors.data_health._probe_coingecko",
        lambda: {"source": "coingecko", "ok": True, "label": "CoinGecko API"},
    )
    monkeypatch.setattr(
        "stock_autopilot.collectors.data_health._probe_amfi",
        lambda: {"source": "amfi", "ok": True, "label": "AMFI NAV", "schemes": 5000},
    )
    report = run_data_health_check(cfg={}, ttl=0, force=True)
    assert report["status"] == "healthy"
    assert report["ok_count"] == report["total"]
    assert len(report["feeds"]) == 2


def test_signal_validation_report_shape():
    report = signal_validation_report({"india_desk": {}})
    assert report["methodology"] == "rule_based"
    assert "resolved_outcomes" in report
    assert isinstance(report["rule_backtests"], list)


def test_backtest_rsi_reversal_no_history(monkeypatch):
    class EmptyHist:
        empty = True

        def __len__(self):
            return 0

    class FakeTicker:
        def history(self, **kwargs):
            return EmptyHist()

    monkeypatch.setattr("stock_autopilot.analysis.signal_backtest.yf.Ticker", lambda s: FakeTicker())
    result = backtest_rsi_reversal("FAKE")
    assert result["ok"] is False


def test_amfi_module_parse():
    assert callable(amfi_parse)
