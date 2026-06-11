"""KPI cards HTML — mirrors components/kpi_cards.py."""
from __future__ import annotations

import html
from typing import Optional

from deal_desk.data_model import Metrics, fmt_compact, fmt_num, fmt_pct


def _delta(a: float, b: Optional[float]) -> Optional[float]:
    if b is None or not b:
        return None
    return (a - b) / abs(b)


def _delta_html(d: Optional[float], inverse: bool = False) -> str:
    if d is None or abs(d) < 1e-4:
        return ""
    arrow = "▲" if d > 0 else "▼"
    bad = (d > 0) if inverse else (d < 0)
    color = "#c45c5c" if bad else "#07a857"
    return f'<span class="kpi-delta" style="color:{color}">{html.escape(arrow)} {html.escape(fmt_pct(abs(d), 1))}</span>'


def _card(label: str, value: str, delta: Optional[float], inverse: bool, muted: str, fg: str) -> str:
    dhtml = _delta_html(delta, inverse)
    return f"""<div class="kpi-card">
  <div class="kpi-label" style="color:{muted}">{html.escape(label)}</div>
  <div class="kpi-value" style="color:{fg}">{html.escape(value)}</div>
  {dhtml}
</div>"""


def render_kpi_rows(current: Metrics, previous: Optional[Metrics], theme: str) -> str:
    light = theme == "light"
    fg = "#1f2530" if light else "#eaeaea"
    muted = "#5f6b76" if light else "#9aa3ad"
    p = None  # delta percentages removed per request

    def dcur(a: float, pb: Optional[float]) -> Optional[float]:
        return _delta(a, pb)

    top = [
        ("Merchants", fmt_num(current.merchants), None, False),
        ("Active Stores", fmt_num(current.active_stores), None, False),
        ("Orders", fmt_num(current.trips), dcur(current.trips, p.trips if p else None), False),
        ("Total Sales", fmt_compact(current.basket), dcur(current.basket, p.basket if p else None), False),
        ("Avg Basket", f"${current.avb:.2f}", dcur(current.avb, p.avb if p else None), False),
        ("Eater Fees % Basket", fmt_pct(current.eater_fees_pct_basket),
         dcur(current.eater_fees_pct_basket, p.eater_fees_pct_basket if p else None), False),
        ("Gross Bookings", fmt_compact(current.gross_bookings),
         dcur(current.gross_bookings, p.gross_bookings if p else None), False),
    ]
    bottom = [
        ("Total Take Rate", fmt_pct(current.take_rate), dcur(current.take_rate, p.take_rate if p else None), False),
        ("Aggregate MPF", fmt_pct(current.mpf), dcur(current.mpf, p.mpf if p else None), False),
        ("Aggregate Markup", fmt_pct(current.markup), dcur(current.markup, p.markup if p else None), False),
        ("EuP % GB", fmt_pct(current.eup_pct_gb), dcur(current.eup_pct_gb, p.eup_pct_gb if p else None), False),
        ("CpT ($/trip)", f"${current.cpt:.2f}", dcur(current.cpt, p.cpt if p else None), True),
        ("NETR %", fmt_pct(current.netr_pct), dcur(current.netr_pct, p.netr_pct if p else None), False),
        ("VC %", fmt_pct(current.vc_pct), dcur(current.vc_pct, p.vc_pct if p else None), False),
    ]

    def row(title: str, cards: list) -> str:
        cells = "".join(_card(l, v, d, inv, muted, fg) for l, v, d, inv in cards)
        return f"""<div class="kpi-section-title" style="color:{muted}">{html.escape(title)}</div>
<div class="kpi-row">{cells}</div>"""

    return row("Top Line", top) + row("Bottom Line", bottom)
