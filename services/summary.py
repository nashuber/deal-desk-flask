"""REGIONAL P&L summary table HTML — mirrors components/summary_table.py."""
from __future__ import annotations

import html
from typing import Callable, List, Optional, Tuple

import pandas as pd

from deal_desk.data_model import (
    Filters,
    Metrics,
    compute_metrics,
    filter_deals,
    filter_stores,
    fmt_compact,
    fmt_money,
    fmt_num,
    fmt_pct,
    pretty_merchant_type,
)


def _ratio(n: float, d: float) -> float:
    return n / d if d else float("nan")


RowFn = Callable[[Metrics, Metrics], str]


def _rows() -> List[Tuple[Optional[str], str, RowFn, bool, bool]]:
    r: List[Tuple[Optional[str], str, RowFn, bool, bool]] = []
    r.append(("Volume", "# of Merchants", lambda m, t: fmt_num(m.merchants), False, False))
    r.append((None, "Active Stores", lambda m, t: fmt_num(m.active_stores), False, False))
    r.append((None, "Average Basket (AvB)", lambda m, t: f"${m.avb:.2f}", False, False))
    r.append((None, "AvB % of National", lambda m, t: fmt_pct(_ratio(m.avb, t.avb), 0), False, True))
    r.append((None, "Orders", lambda m, t: fmt_num(m.trips), False, False))
    r.append((None, "Orders % of National", lambda m, t: fmt_pct(_ratio(m.trips, t.trips), 0), False, True))

    r.append(("Per Store Statistics", "Orders per Store / month", lambda m, t: fmt_num(m.orders_per_store), False, False))
    r.append((None, "Sales per Store / month", lambda m, t: fmt_compact(m.sales_per_store), False, False))
    r.append((None, "GB per Store / month", lambda m, t: fmt_compact(m.gb_per_store), False, False))

    r.append(("Eater Fees", "Delivery Fee % Basket", lambda m, t: fmt_pct(m.delivery_fee_pct_basket), False, False))
    r.append((None, "Service Fee % Basket", lambda m, t: fmt_pct(m.service_fee_pct_basket), False, False))
    r.append((None, "Eater Fees % Basket", lambda m, t: fmt_pct(m.eater_fees_pct_basket), False, False))

    r.append(("Sales / GBs", "Total Sales", lambda m, t: fmt_money(m.basket), False, False))
    r.append((None, "Total Sales % across REGIONs", lambda m, t: fmt_pct(_ratio(m.basket, t.basket), 0), False, True))
    r.append((None, "Total Gross Bookings", lambda m, t: fmt_money(m.gross_bookings), False, False))
    r.append((None, "GB % across REGIONs", lambda m, t: fmt_pct(_ratio(m.gross_bookings, t.gross_bookings), 0), False, True))

    r.append(("Commercials", "Total Take Rate", lambda m, t: fmt_pct(m.take_rate), True, False))
    r.append((None, "Aggregate Markup", lambda m, t: fmt_pct(m.markup), False, False))
    r.append((None, "Aggregate MPF", lambda m, t: fmt_pct(m.mpf), False, False))

    r.append(("Expenses", "CpT ($/trip)", lambda m, t: f"${m.cpt:.2f}", False, False))
    r.append((None, "Marketing (% GB)", lambda m, t: fmt_pct(m.marketing_pct_gb), False, False))
    r.append((None, "EUP (% GB)", lambda m, t: fmt_pct(m.eup_pct_gb), False, False))
    r.append((None, "Uber One Discount (% GB)", lambda m, t: fmt_pct(m.uber_one_discount_pct_gb), False, False))

    r.append(("Other Revenue (% GB)", "Ad Revenue", lambda m, t: fmt_pct(m.ads_rev_pct_gb), False, False))
    r.append((None, "Other Revenue", lambda m, t: fmt_pct(m.other_rev_pct_gb), False, False))
    r.append((None, "NETR %", lambda m, t: fmt_pct(m.netr_pct), True, False))

    r.append(("Variable Cost (% GB)", "Insurance", lambda m, t: fmt_pct(m.insurance_pct_gb), False, False))
    r.append((None, "Support", lambda m, t: fmt_pct(m.support_pct_gb), False, False))
    r.append((None, "Money", lambda m, t: fmt_pct(m.money_pct_gb), False, False))
    r.append((None, "Tech", lambda m, t: fmt_pct(m.tech_pct_gb), False, False))
    r.append((None, "Other", lambda m, t: fmt_pct(m.other_var_cost_pct_gb), False, False))
    r.append((None, "Total Variable Costs", lambda m, t: fmt_pct(m.total_var_cost_pct_gb), True, False))

    r.append(("Bottom Line", "VC %", lambda m, t: fmt_pct(m.vc_pct), True, False))
    return r


def _is_known(s: str) -> bool:
    return bool(s) and s.strip() != "" and s.upper() != "UNKNOWN"


def theme_colors(theme: str) -> dict[str, str]:
    if theme == "light":
        return dict(panel="#ffffff", panel2="#eef0f3", line="rgba(0,0,0,.10)",
                    fg="#1f2530", muted="#5f6b76", green="#07a857")
    return dict(panel="#16191e", panel2="#1b1f26", line="rgba(255,255,255,.08)",
                fg="#eaeaea", muted="#9aa3ad", green="#06c167")


def render_summary_table(
    deals: pd.DataFrame,
    stores: pd.DataFrame,
    filters: Filters,
    dimension: str,
    theme: str,
) -> str:
    base = filter_deals(deals, filters)
    base_stores = filter_stores(stores, filters)

    if dimension == "merchant_type":
        deal_key = base["merchant_type"].map(pretty_merchant_type)
        store_key = base_stores["merchant_type"].map(pretty_merchant_type) if not base_stores.empty else pd.Series(dtype=str)
    else:
        deal_key = base[dimension].astype(str)
        store_key = (
            base_stores[dimension].astype(str)
            if not base_stores.empty and dimension in base_stores.columns
            else pd.Series(dtype=str)
        )

    cols = sorted({c for c in deal_key.unique() if _is_known(str(c))})

    col_metrics: List[Tuple[str, Metrics]] = []
    for c in cols:
        d = base[deal_key == c]
        s = base_stores[store_key == c] if not base_stores.empty else base_stores
        col_metrics.append((str(c), compute_metrics(d, s)))
    total = compute_metrics(base, base_stores)

    title_map = {"territory": "REGION", "merchant_type": "Merchant Type", "merchant_segment": "Segment"}
    title = title_map.get(dimension, dimension)

    c = theme_colors(theme)
    n_cols = len(col_metrics) + 2
    col_names = [name for name, _ in col_metrics]

    css = f"""<style>
.ddst-wrap{{overflow:auto;max-height:720px;border:1px solid {c['line']};border-radius:8px}}
.ddst{{border-collapse:collapse;width:100%;font-size:13px;color:{c['fg']};background:{c['panel']}}}
.ddst th,.ddst td{{padding:7px 12px;text-align:right;white-space:nowrap;border-bottom:1px solid {c['line']}}}
.ddst thead th{{position:sticky;top:0;background:{c['panel2']};text-align:right;font-size:11px;
  text-transform:uppercase;letter-spacing:.04em;color:{c['muted']};z-index:1}}
.ddst th.m,.ddst td.m{{text-align:left;position:sticky;left:0;background:{c['panel']};min-width:240px}}
.ddst thead th.m{{background:{c['panel2']}}}
.ddst td.total{{color:{c['green']}}}
.ddst tr.section td{{background:{c['panel2']};color:{c['muted']};font-size:11px;font-weight:700;
  text-transform:uppercase;letter-spacing:.06em;text-align:left}}
.ddst tr.bold td{{font-weight:700}}
.ddst td.muted{{color:{c['muted']}}}
</style>"""

    head = "<th class='m'>Metric</th>" + "".join(
        f"<th>{html.escape(str(name))}</th>" for name in col_names
    ) + "<th class='total'>National Total</th>"

    body_rows: List[str] = []
    for section, label, fmt, bold, muted in _rows():
        if section:
            body_rows.append(
                f"<tr class='section'><td colspan='{n_cols}'>&#9473; {html.escape(section.upper())}</td></tr>"
            )
        cells = "".join(f"<td>{html.escape(fmt(m, total))}</td>" for _, m in col_metrics)
        metric_cls = "m muted" if muted else "m"
        tr_cls = "bold" if bold else ""
        body_rows.append(
            f"<tr class='{tr_cls}'><td class='{metric_cls}'>{html.escape(label)}</td>"
            f"{cells}<td class='total'>{html.escape(fmt(total, total))}</td></tr>"
        )

    table = (
        css
        + "<div class='ddst-wrap'><table class='ddst'><thead><tr>"
        + head
        + "</tr></thead><tbody>"
        + "".join(body_rows)
        + "</tbody></table></div>"
    )
    cap = f"Breakdown by {title} · {fmt_num(len(base))} rows · {len(col_metrics)} {title.lower()}s"
    header = f"""<h4 class="section-title">REGIONAL P&amp;L Summary</h4>
<p class="caption">{html.escape(cap)}</p>"""
    footer = '<p class="caption">VC % = NETR % − Total Variable Costs. Mirrors the React US MPF &amp; Take Rate Analysis sheet.</p>'
    return header + table + footer
