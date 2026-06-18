from __future__ import annotations

from stock_autopilot.models.schemas import IndiaFixedIncomeNote, IndiaMFNote


def build_mutual_fund_notes(cfg: dict) -> list[IndiaMFNote]:
    funds = cfg.get("india_desk", {}).get("mutual_funds") or []
    notes: list[IndiaMFNote] = []
    for f in funds:
        notes.append(
            IndiaMFNote(
                fund_name=f["name"],
                amc=f.get("amc", ""),
                category=f.get("category", ""),
                rating_label=f.get("rating", "RECOMMENDED"),
                returns_1y=f.get("returns_1y", "—"),
                returns_3y=f.get("returns_3y", "—"),
                sharpe=f.get("sharpe", "—"),
                expense_direct=f.get("expense_direct", "—"),
                who_should_invest=f.get("who", ""),
                tax_note=f.get("tax", "Equity MF: LTCG 12.5% above ₹1.25L (>1Y); STCG 20% (<1Y)."),
                sip_note=f.get("sip", "Direct Plan SIP preferred."),
                desk_note=f.get("desk_note", ""),
                risk_class=f.get("risk_class", "green"),
            )
        )
    return notes


def build_bond_notes(cfg: dict) -> list[IndiaFixedIncomeNote]:
    bonds = cfg.get("india_desk", {}).get("bonds") or []
    notes: list[IndiaFixedIncomeNote] = []
    for b in bonds:
        notes.append(
            IndiaFixedIncomeNote(
                instrument=b["name"],
                issuer=b.get("issuer", ""),
                instrument_type=b.get("type", "Bond"),
                yield_label=b.get("yield", "—"),
                tenor=b.get("tenor", "—"),
                credit_rating=b.get("rating", "Sovereign"),
                tax_note=b.get("tax", "Interest taxable per slab unless tax-free u/s 10."),
                who_should_invest=b.get("who", ""),
                desk_note=b.get("desk_note", ""),
                risk_class=b.get("risk_class", "green"),
                category="bond",
            )
        )
    return notes


def build_fd_notes(cfg: dict) -> list[IndiaFixedIncomeNote]:
    fds = cfg.get("india_desk", {}).get("fixed_deposits") or []
    notes: list[IndiaFixedIncomeNote] = []
    for fd in fds:
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
            )
        )
    return notes
