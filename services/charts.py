"""Plotly charts wrapped in white cards — mirrors components/visualizations.py."""
from __future__ import annotations

from typing import List, Sequence

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from deal_desk.data_model import (
    Filters,
    compute_metrics,
    filter_deals,
    filter_stores,
    fmt_compact,
    fmt_month,
    metrics_by_dimension,
)

_GREEN = "#06C167"


def _palette(theme: str) -> dict:
    if theme == "light":
        return {
            "green": _GREEN,
            "fg": "#1F2530",
            "neutral": "#3A4250",
            "muted": "rgba(31,37,48,0.45)",
            "grid": "rgba(0,0,0,0.08)",
        }
    return {
        "green": _GREEN,
        "fg": "#EAEAEA",
        "neutral": "#EAEAEA",
        "muted": "rgba(234,234,234,0.45)",
        "grid": "rgba(255,255,255,0.08)",
    }


def _is_known(s: str) -> bool:
    return bool(s) and str(s).strip() != "" and str(s).upper() != "UNKNOWN"


def _is_allowed_vertical(s: str) -> bool:
    return _is_known(s) and str(s).upper() != "RESTAURANT"


def _by_vertical(deals: pd.DataFrame, stores: pd.DataFrame) -> List[dict]:
    verts = sorted({v for v in deals["Vertical"] if v})
    out = []
    for v in verts:
        d = deals[deals["Vertical"] == v]
        m = compute_metrics(d, stores)
        out.append({
            "name": v,
            "netr_pct": m.netr_pct * 100,
            "mpf": m.mpf * 100,
            "markup": m.markup * 100,
            "take_rate": m.take_rate * 100,
            "vc_pct": m.vc_pct * 100,
            "avb": m.avb,
            "cpt": m.cpt,
            "gb": m.gross_bookings,
        })
    return out


def _pad(vals: Sequence[float], frac: float = 0.2) -> list[float]:
    """Padded [min, max] range so 'outside' value labels never collide."""
    nums = [float(v) for v in vals] + [0.0]
    vmax, vmin = max(nums), min(nums)
    span = (vmax - vmin) or (abs(vmax) or 1.0)
    return [vmin - span * frac, vmax + span * frac]


def _style(fig: go.Figure, pal: dict, height: int = 320) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=10, r=18, t=44, b=28),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=pal["fg"], size=11),
        legend=dict(orientation="h", yanchor="bottom", y=1.04, x=0),
    )
    fig.update_traces(textfont=dict(color=pal["fg"]))
    # Hide the raw column-name axis titles (e.g. "vc_pct", "cpt") and let long
    # category labels reserve their own room.
    fig.update_xaxes(gridcolor=pal["grid"], zerolinecolor=pal["grid"], title_text=None, automargin=True)
    fig.update_yaxes(gridcolor=pal["grid"], zerolinecolor=pal["grid"], title_text=None, automargin=True)
    return fig


def _hbar(fig: go.Figure, pal: dict, vals: Sequence[float], height: int) -> go.Figure:
    """Style a horizontal bar chart and pad the value (x) axis for labels."""
    fig = _style(fig, pal, height)
    fig.update_xaxes(range=_pad(vals, 0.22))
    return fig


def _fig_div(fig: go.Figure, div_id: str) -> str:
    return fig.to_html(full_html=False, include_plotlyjs=False, div_id=div_id,
                       config={"displayModeBar": False, "responsive": True})


def _card(title: str, subtitle: str, inner: str) -> str:
    sub = f'<div class="chart-sub">{subtitle}</div>' if subtitle else ""
    return f'<div class="viz-card"><div class="chart-card-title">{title}</div>{sub}{inner}</div>'


_EMPTY = '<div class="viz-empty">No data for current filters.</div>'


def build_chart_divs(
    deals: pd.DataFrame,
    stores: pd.DataFrame,
    filters: Filters,
    theme: str,
) -> List[str]:
    """Return a list of HTML blocks (white cards / 2-col grids) for the template."""
    pal = _palette(theme)
    f_deals = filter_deals(deals, filters)
    f_deals = f_deals[f_deals["Vertical"].map(_is_allowed_vertical) & f_deals["territory"].map(_is_known)]
    f_stores = filter_stores(stores, filters)
    f_stores = f_stores[f_stores["territory"].map(_is_known)] if not f_stores.empty else f_stores

    by_vertical = _by_vertical(f_deals, f_stores)
    by_region_rows = metrics_by_dimension(f_deals, f_stores, "territory")
    by_region = sorted(
        [{
            "name": r["key"],
            "gb": r["gross_bookings"],
            "netr_pct": r["netr_pct"] * 100,
            "mpf": r["mpf"] * 100,
            "markup": r["markup"] * 100,
            "vc_pct": r["vc_pct"] * 100,
            "take_rate": r["take_rate"] * 100,
            "cpt": r["cpt"],
        } for r in by_region_rows],
        key=lambda r: -r["gb"],
    )

    trend_filters = Filters(
        months=[],
        merchant_types=filters.merchant_types,
        segments=filters.segments,
        markets=filters.markets,
        fulfillment=filters.fulfillment,
    )
    f_all = filter_deals(deals, trend_filters)
    f_all = f_all[f_all["Vertical"].map(_is_allowed_vertical) & f_all["territory"].map(_is_known)]
    months = sorted(f_all["date"].unique())
    trend = []
    for m in months:
        sub = f_all[f_all["date"] == m]
        sub_stores = filter_stores(
            stores,
            Filters(
                months=[m],
                merchant_types=filters.merchant_types,
                segments=filters.segments,
                markets=filters.markets,
                fulfillment=filters.fulfillment,
            ),
        )
        x = compute_metrics(sub, sub_stores)
        trend.append({
            "month": fmt_month(str(m)),
            "Total Take Rate": x.take_rate * 100,
            "MPF": x.mpf * 100,
            "Markup": x.markup * 100,
        })
    trend_df = pd.DataFrame(trend)
    bv_df = pd.DataFrame(by_vertical)
    br_df = pd.DataFrame(by_region)

    blocks: List[str] = []

    # 1. Trend
    if not trend_df.empty:
        fig = go.Figure()
        fig.add_scatter(
            x=trend_df["month"], y=trend_df["Total Take Rate"], name="Total Take Rate",
            mode="lines+markers+text", line=dict(color=pal["green"], width=2.5),
            text=trend_df["Total Take Rate"].map(lambda v: f"{v:.1f}%"), textposition="top center",
        )
        fig.add_scatter(
            x=trend_df["month"], y=trend_df["MPF"], name="MPF",
            mode="lines+markers+text", line=dict(color=pal["neutral"], width=2),
            text=trend_df["MPF"].map(lambda v: f"{v:.1f}%"), textposition="bottom center",
        )
        fig.add_scatter(
            x=trend_df["month"], y=trend_df["Markup"], name="Markup",
            mode="lines+markers+text", line=dict(color=pal["muted"], width=2, dash="dash"),
            text=trend_df["Markup"].map(lambda v: f"{v:.1f}%"), textposition="top center",
        )
        fig.update_yaxes(ticksuffix="%")
        inner = _fig_div(_style(fig, pal, 300), "chart-trend")
    else:
        inner = _EMPTY
    blocks.append(_card("Month-over-Month Trend", "Total Take rate, MPF &amp; Markup across months", inner))

    # 2. VC ranking + AvB
    d = bv_df.sort_values("vc_pct", ascending=True) if not bv_df.empty else bv_df
    if not d.empty:
        fig = px.bar(d, x="vc_pct", y="name", orientation="h", text=d["vc_pct"].map(lambda v: f"{v:.1f}%"))
        fig.update_traces(marker_color=pal["green"], textposition="outside", cliponaxis=False)
        fig.update_xaxes(ticksuffix="%")
        left = _fig_div(_hbar(fig, pal, d["vc_pct"], max(260, len(d) * 40)), "chart-vc")
    else:
        left = _EMPTY
    d = bv_df.sort_values("avb", ascending=False) if not bv_df.empty else bv_df
    if not d.empty:
        fig = px.bar(d, x="name", y="avb", text=d["avb"].map(lambda v: f"${v:.2f}"))
        fig.update_traces(marker_color=pal["neutral"], textposition="outside", cliponaxis=False)
        fig.update_yaxes(tickprefix="$", range=[0, float(d["avb"].max()) * 1.2])
        fig.update_xaxes(tickangle=-20)
        right = _fig_div(_style(fig, pal, 300), "chart-avb")
    else:
        right = _EMPTY
    blocks.append(
        '<div class="chart-grid-2">'
        + _card("VC % — Vertical Ranking", "VC % of Gross Bookings, by vertical", left)
        + _card("Average Basket (AvB) by Vertical", "USD", right)
        + "</div>"
    )

    # 3. MPF + Markup by vertical
    d = bv_df.sort_values("mpf", ascending=True) if not bv_df.empty else bv_df
    if not d.empty:
        fig = px.bar(d, x="mpf", y="name", orientation="h", text=d["mpf"].map(lambda v: f"{v:.1f}%"))
        fig.update_traces(marker_color=pal["neutral"], textposition="outside", cliponaxis=False)
        fig.update_xaxes(ticksuffix="%")
        left = _fig_div(_hbar(fig, pal, d["mpf"], max(260, len(d) * 38)), "chart-mpf-v")
    else:
        left = _EMPTY
    d = bv_df.sort_values("markup", ascending=True) if not bv_df.empty else bv_df
    if not d.empty:
        fig = px.bar(d, x="markup", y="name", orientation="h", text=d["markup"].map(lambda v: f"{v:.1f}%"))
        fig.update_traces(marker_color=pal["green"], textposition="outside", cliponaxis=False)
        fig.update_xaxes(ticksuffix="%")
        right = _fig_div(_hbar(fig, pal, d["markup"], max(260, len(d) * 38)), "chart-markup-v")
    else:
        right = _EMPTY
    blocks.append(
        '<div class="chart-grid-2">'
        + _card("MPF by Vertical (%)", "", left)
        + _card("Markup by Vertical (%)", "", right)
        + "</div>"
    )

    # 4. GB by vertical + GB by region
    d = bv_df.sort_values("gb", ascending=True) if not bv_df.empty else bv_df
    if not d.empty:
        fig = px.bar(d, x="gb", y="name", orientation="h", text=d["gb"].map(fmt_compact))
        fig.update_traces(marker_color=pal["neutral"], textposition="outside", cliponaxis=False)
        left = _fig_div(_hbar(fig, pal, d["gb"], max(260, len(d) * 40)), "chart-gb-v")
    else:
        left = _EMPTY
    if not br_df.empty:
        d = br_df.sort_values("gb", ascending=True)
        fig = px.bar(d, x="gb", y="name", orientation="h", text=d["gb"].map(fmt_compact))
        fig.update_traces(marker_color=pal["green"], textposition="outside", cliponaxis=False)
        right = _fig_div(_hbar(fig, pal, d["gb"], max(260, len(d) * 40)), "chart-gb-r")
    else:
        right = _EMPTY
    blocks.append(
        '<div class="chart-grid-2">'
        + _card("Total Gross Bookings by Vertical", "GB, $", left)
        + _card("Total Gross Bookings by REGION", "GB, $", right)
        + "</div>"
    )

    # 5. Metrics by REGION
    if not br_df.empty:
        d = br_df.sort_values("vc_pct", ascending=False)
        allv = list(d["mpf"]) + list(d["markup"]) + list(d["vc_pct"])
        fig = go.Figure()
        fig.add_bar(x=d["name"], y=d["mpf"], name="MPF", marker_color=pal["green"], text=d["mpf"].map(lambda v: f"{v:.1f}%"))
        fig.add_bar(x=d["name"], y=d["markup"], name="Markup", marker_color=pal["muted"], text=d["markup"].map(lambda v: f"{v:.1f}%"))
        fig.add_bar(x=d["name"], y=d["vc_pct"], name="VC %", marker_color=pal["neutral"], text=d["vc_pct"].map(lambda v: f"{v:.1f}%"))
        fig.update_traces(textposition="outside", textfont_size=9, cliponaxis=False)
        fig.update_layout(barmode="group")
        fig.update_yaxes(ticksuffix="%", range=_pad(allv, 0.28))
        inner = _fig_div(_style(fig, pal, 370), "chart-metrics-r")
    else:
        inner = _EMPTY
    blocks.append(_card("Metrics by REGION", "MPF, Markup &amp; VC % (NetR − Variable Costs) across REGIONs", inner))

    # 6. Metrics by VERTICAL
    if not bv_df.empty:
        d = bv_df.sort_values("vc_pct", ascending=False)
        allv = list(d["mpf"]) + list(d["markup"]) + list(d["vc_pct"])
        fig = go.Figure()
        fig.add_bar(x=d["name"], y=d["mpf"], name="MPF", marker_color=pal["green"], text=d["mpf"].map(lambda v: f"{v:.1f}%"))
        fig.add_bar(x=d["name"], y=d["markup"], name="Markup", marker_color=pal["muted"], text=d["markup"].map(lambda v: f"{v:.1f}%"))
        fig.add_bar(x=d["name"], y=d["vc_pct"], name="VC %", marker_color=pal["neutral"], text=d["vc_pct"].map(lambda v: f"{v:.1f}%"))
        fig.update_traces(textposition="outside", textfont_size=9, cliponaxis=False)
        fig.update_layout(barmode="group")
        fig.update_yaxes(ticksuffix="%", range=_pad(allv, 0.28))
        inner = _fig_div(_style(fig, pal, 370), "chart-metrics-v")
    else:
        inner = _EMPTY
    blocks.append(_card("METRICS BY VERTICAL", "MPF, Markup &amp; VC % compared side-by-side by vertical", inner))

    # 7. CpT by vertical + region
    d = bv_df.sort_values("cpt", ascending=True) if not bv_df.empty else bv_df
    if not d.empty:
        fig = px.bar(d, x="cpt", y="name", orientation="h", text=d["cpt"].map(lambda v: f"${v:.2f}"))
        fig.update_traces(marker_color=pal["neutral"], textposition="outside", cliponaxis=False)
        fig.update_xaxes(tickprefix="$")
        left = _fig_div(_hbar(fig, pal, d["cpt"], max(260, len(d) * 40)), "chart-cpt-v")
    else:
        left = _EMPTY
    if not br_df.empty:
        d = br_df.sort_values("cpt", ascending=True)
        fig = px.bar(d, x="cpt", y="name", orientation="h", text=d["cpt"].map(lambda v: f"${v:.2f}"))
        fig.update_traces(marker_color=pal["green"], textposition="outside", cliponaxis=False)
        fig.update_xaxes(tickprefix="$")
        right = _fig_div(_hbar(fig, pal, d["cpt"], max(260, len(d) * 40)), "chart-cpt-r")
    else:
        right = _EMPTY
    blocks.append(
        '<div class="chart-grid-2">'
        + _card("CpT by Vertical", "Cost per Trip ($/trip)", left)
        + _card("CpT by REGION", "Cost per Trip ($/trip)", right)
        + "</div>"
    )

    return blocks
