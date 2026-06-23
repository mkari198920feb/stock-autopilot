from __future__ import annotations

from stock_autopilot.collectors.amfi import fetch_amfi_nav_map, lookup_amfi_nav
from stock_autopilot.collectors.india_rates import fetch_india_market_rates
from stock_autopilot.models.schemas import IndiaFixedIncomeNote, IndiaMFNote


def _fmt_nav(nav: float) -> str:
    return f"₹{nav:,.4f}" if nav < 1000 else f"₹{nav:,.2f}"


def build_mutual_fund_notes(cfg: dict, *, live: bool = True) -> list[IndiaMFNote]:
    funds = cfg.get("india_desk", {}).get("mutual_funds") or []
    nav_rows = fetch_amfi_nav_map() if live else {}
    from stock_autopilot.collectors.amfi import _name_index

    idx = _name_index(nav_rows) if nav_rows else {}
    notes: list[IndiaMFNote] = []

    for f in funds:
        live_nav = None
        live_date = None
        data_source = "config"
        if live and nav_rows:
            hit = lookup_amfi_nav(f, nav_rows, idx)
            if hit:
                live_nav = _fmt_nav(hit["nav"])
                live_date = hit.get("nav_date")
                data_source = "amfi"

        returns_1y = f.get("returns_1y", "—")
        if live_nav:
            returns_1y = f"{returns_1y} · NAV {live_nav}" if returns_1y != "—" else f"NAV {live_nav}"

        notes.append(
            IndiaMFNote(
                fund_name=f["name"],
                amc=f.get("amc", ""),
                category=f.get("category", ""),
                rating_label=f.get("rating", "RECOMMENDED"),
                returns_1y=returns_1y,
                returns_3y=f.get("returns_3y", "—"),
                sharpe=f.get("sharpe", "—"),
                expense_direct=f.get("expense_direct", "—"),
                who_should_invest=f.get("who", ""),
                tax_note=f.get("tax", "Equity MF: LTCG 12.5% above ₹1.25L (>1Y); STCG 20% (<1Y)."),
                sip_note=f.get("sip", "Direct Plan SIP preferred."),
                desk_note=f.get("desk_note", ""),
                risk_class=f.get("risk_class", "green"),
                nav=live_nav,
                nav_date=live_date,
                data_source=data_source,
            )
        )
    return notes


def build_bond_notes(cfg: dict, *, live: bool = True) -> list[IndiaFixedIncomeNote]:
    bonds = cfg.get("india_desk", {}).get("bonds") or []
    rates = fetch_india_market_rates() if live else {}
    notes: list[IndiaFixedIncomeNote] = []

    for b in bonds:
        yield_label = b.get("yield", "—")
        data_source = "config"
        as_of = None
        inst_type = (b.get("type") or "").upper()

        if live and rates.get("gsec_yield_pct") is not None and inst_type in ("G-SEC", "GSEC"):
            y = rates["gsec_yield_pct"]
            yield_label = f"{y:.2f}% YTM (live proxy)"
            data_source = "yfinance"
            as_of = rates.get("gsec_as_of")

        if live and rates.get("gold_1m_pct") is not None and inst_type == "SGB":
            g = rates["gold_1m_pct"]
            yield_label = f"2.5% coupon + gold {g:+.1f}% (1M proxy)"
            data_source = "yfinance"
            as_of = rates.get("captured_at", "")[:10]

        notes.append(
            IndiaFixedIncomeNote(
                instrument=b["name"],
                issuer=b.get("issuer", ""),
                instrument_type=b.get("type", "Bond"),
                yield_label=yield_label,
                tenor=b.get("tenor", "—"),
                credit_rating=b.get("rating", "Sovereign"),
                tax_note=b.get("tax", "Interest taxable per slab unless tax-free u/s 10."),
                who_should_invest=b.get("who", ""),
                desk_note=b.get("desk_note", ""),
                risk_class=b.get("risk_class", "green"),
                category="bond",
                data_source=data_source,
                as_of=as_of,
            )
        )
    return notes


def build_fd_notes(cfg: dict) -> list[IndiaFixedIncomeNote]:
    fds = cfg.get("india_desk", {}).get("fixed_deposits") or []
    notes: list[IndiaFixedIncomeNote] = []
    for fd in fds:
        verified = fd.get("last_verified", "curated")
        notes.append(
            IndiaFixedIncomeNote(
                instrument=fd["name"],
                issuer=fd.get("issuer", ""),
                instrument_type=fd.get("type", "Bank FD"),
                yield_label=fd.get("rate", "—"),
                tenor=fd.get("tenor", "1–3 years"),
                credit_rating=fd.get("rating", "DICGC ₹5L"),
                tax_note=fd.get("tax", "Interest taxable per slab; TDS @10% if interest > ₹40K/yr."),
                who_should_invest=fd.get("who", ""),
                desk_note=fd.get("desk_note", ""),
                risk_class=fd.get("risk_class", "green"),
                category="fd",
                data_source="curated",
                as_of=verified,
            )
        )
    return notes
