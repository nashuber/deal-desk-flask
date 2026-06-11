"""Port of src/lib/dataModel.ts.

Pure-python / pandas implementation. Field names and formulas mirror the
TypeScript version 1:1 so the React and Streamlit dashboards return identical
numbers for the same dataset.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from math import isfinite
from typing import Iterable, List, Dict, Any, Literal

import pandas as pd

# ---------- types ----------

DEAL_NUMERIC_FIELDS: List[str] = [
    "trips", "basket", "booking_fees", "service_fees", "other_uber_fees",
    "gross_bookings", "courier_payment", "resto_payments", "tf_disbursed",
    "EuP", "pass_net", "ads_rev", "other_rev", "netr",
    "trip_insurance", "support", "money", "tech", "other_variable",
]

DEAL_STRING_FIELDS: List[str] = [
    "date", "merchant_type", "merchant_segment", "grouped_parent_name",
    "territory", "Vertical",
]

STORE_NUMERIC_FIELDS: List[str] = ["active_stores"]
STORE_STRING_FIELDS: List[str] = [
    "accounting_date", "merchant_type", "merchant_segment", "territory",
    "store_level", "Vertical", "Region",
]

FulfillmentMode = Literal["All", "CPP", "MPP"]

# Same MPP set as getFulfillment() in dataModel.ts
_MPP_TYPES = {
    "MERCHANT_TYPE_GROCERY",
    "MERCHANT_TYPE_RETAIL",
    "MERCHANT_TYPE_PET_SUPPLY",
}


def get_fulfillment(merchant_type: str) -> str:
    return "MPP" if merchant_type in _MPP_TYPES else "CPP"


@dataclass
class Filters:
    months: List[str] = field(default_factory=list)
    merchant_types: List[str] = field(default_factory=list)  # pretty form
    segments: List[str] = field(default_factory=list)
    markets: List[str] = field(default_factory=list)
    fulfillment: FulfillmentMode = "All"

    def is_active(self) -> bool:
        return bool(
            self.months or self.merchant_types or self.segments
            or self.markets or self.fulfillment != "All"
        )


def default_filters() -> Filters:
    return Filters()


# ---------- helpers ----------

def pretty_merchant_type(m: str) -> str:
    if not isinstance(m, str):
        return ""
    return m.removeprefix("MERCHANT_TYPE_").replace("_", " ")


def _ensure_columns(df: pd.DataFrame, numeric: Iterable[str], string: Iterable[str]) -> pd.DataFrame:
    out = df.copy()
    for col in numeric:
        if col not in out.columns:
            out[col] = 0.0
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0)
    for col in string:
        if col not in out.columns:
            out[col] = ""
        out[col] = out[col].astype(str).fillna("")
    return out


def normalize_deals(df: pd.DataFrame) -> pd.DataFrame:
    return _ensure_columns(df, DEAL_NUMERIC_FIELDS, DEAL_STRING_FIELDS)


def normalize_stores(df: pd.DataFrame) -> pd.DataFrame:
    out = _ensure_columns(df, STORE_NUMERIC_FIELDS, STORE_STRING_FIELDS)
    out.loc[out["store_level"] == "", "store_level"] = "terr"
    return out


# ---------- filtering ----------

def filter_deals(df: pd.DataFrame, f: Filters) -> pd.DataFrame:
    if df.empty:
        return df
    mask = pd.Series(True, index=df.index)
    if f.months:
        mask &= df["date"].isin(f.months)
    if f.merchant_types:
        mask &= df["merchant_type"].map(pretty_merchant_type).isin(f.merchant_types)
    if f.segments:
        mask &= df["merchant_segment"].isin(f.segments)
    if f.markets:
        mask &= df["territory"].isin(f.markets)
    if f.fulfillment != "All":
        mask &= df["merchant_type"].map(get_fulfillment) == f.fulfillment
    return df[mask]


def filter_stores(df: pd.DataFrame, f: Filters) -> pd.DataFrame:
    if df.empty:
        return df
    has_seg = bool(f.segments)
    has_type = bool(f.merchant_types)
    if has_seg and has_type:
        level = "ver_terr-seg"
    elif has_seg:
        level = "seg_terr"
    elif has_type:
        level = "ver_terr"
    else:
        level = "terr"

    mask = df["store_level"] == level
    if f.months:
        mask &= df["accounting_date"].isin(f.months)
    if has_type:
        mask &= df["merchant_type"].map(pretty_merchant_type).isin(f.merchant_types)
    if has_seg:
        mask &= df["merchant_segment"].isin(f.segments)
    if f.markets:
        mask &= df["territory"].isin(f.markets)
    return df[mask]


# ---------- metrics ----------

@dataclass
class Metrics:
    merchants: int = 0
    trips: float = 0.0
    basket: float = 0.0
    gross_bookings: float = 0.0
    booking_fees: float = 0.0
    service_fees: float = 0.0
    other_uber_fees: float = 0.0
    resto_payments: float = 0.0
    courier_payment: float = 0.0
    tf_disbursed: float = 0.0
    eup: float = 0.0
    netr: float = 0.0
    ads_rev: float = 0.0
    other_rev: float = 0.0
    take_rate: float = 0.0
    markup: float = 0.0
    mpf: float = 0.0
    eater_fees_pct_basket: float = 0.0
    delivery_fee_pct_basket: float = 0.0
    service_fee_pct_basket: float = 0.0
    marketing_pct_gb: float = 0.0
    eup_pct_gb: float = 0.0
    uber_one_discount_pct_gb: float = 0.0
    ads_rev_pct_gb: float = 0.0
    other_rev_pct_gb: float = 0.0
    cpt: float = 0.0
    netr_pct: float = 0.0
    insurance_pct_gb: float = 0.0
    support_pct_gb: float = 0.0
    money_pct_gb: float = 0.0
    tech_pct_gb: float = 0.0
    other_var_cost_pct_gb: float = 0.0
    total_var_cost_pct_gb: float = 0.0
    vc_pct: float = 0.0
    avb: float = 0.0
    active_stores: int = 0
    orders_per_store: float = 0.0
    sales_per_store: float = 0.0
    gb_per_store: float = 0.0

    def as_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()


def _safe(n: float, d: float) -> float:
    return n / d if d else 0.0


def compute_metrics(deals: pd.DataFrame, stores: pd.DataFrame) -> Metrics:
    if deals.empty:
        s = {k: 0.0 for k in DEAL_NUMERIC_FIELDS}
        merchants = 0
    else:
        s = {k: float(deals[k].sum()) for k in DEAL_NUMERIC_FIELDS}
        merchants = int(deals["grouped_parent_name"].replace("", pd.NA).dropna().nunique())

    trips = s["trips"]
    basket = s["basket"]
    gb = s["gross_bookings"]

    markup = _safe(s["other_uber_fees"], basket)
    mpf = _safe(basket + s["resto_payments"], basket)
    take_rate = markup + mpf

    insurance_pct_gb = _safe(s["trip_insurance"], gb)
    support_pct_gb = _safe(s["support"], gb)
    money_pct_gb = _safe(s["money"], gb)
    tech_pct_gb = _safe(s["tech"], gb)
    other_var_pct_gb = _safe(s["other_variable"], gb)
    total_var = insurance_pct_gb + support_pct_gb + money_pct_gb + tech_pct_gb + other_var_pct_gb
    netr_pct = _safe(s["netr"], gb)
    vc_pct = netr_pct + total_var

    if stores.empty:
        active_stores = 0
        months_count = 1
    else:
        months = stores["accounting_date"].nunique()
        total = float(stores["active_stores"].sum())
        active_stores = round(total / months) if months else 0
        months_count = months or 1

    return Metrics(
        merchants=merchants,
        trips=trips, basket=basket, gross_bookings=gb,
        booking_fees=s["booking_fees"], service_fees=s["service_fees"],
        other_uber_fees=s["other_uber_fees"], resto_payments=s["resto_payments"],
        courier_payment=s["courier_payment"], tf_disbursed=s["tf_disbursed"],
        eup=s["EuP"], netr=s["netr"], ads_rev=s["ads_rev"], other_rev=s["other_rev"],
        take_rate=take_rate, markup=markup, mpf=mpf,
        eater_fees_pct_basket=_safe(s["booking_fees"] + s["service_fees"] + s["other_uber_fees"], basket),
        delivery_fee_pct_basket=_safe(s["booking_fees"], basket),
        service_fee_pct_basket=_safe(s["service_fees"], basket),
        marketing_pct_gb=_safe(s["tf_disbursed"], gb),
        eup_pct_gb=_safe(s["EuP"], gb),
        uber_one_discount_pct_gb=_safe(s["pass_net"], gb),
        ads_rev_pct_gb=_safe(s["ads_rev"], gb),
        other_rev_pct_gb=_safe(s["other_rev"], gb),
        cpt=_safe(s["courier_payment"], trips),
        netr_pct=netr_pct,
        insurance_pct_gb=insurance_pct_gb, support_pct_gb=support_pct_gb,
        money_pct_gb=money_pct_gb, tech_pct_gb=tech_pct_gb,
        other_var_cost_pct_gb=other_var_pct_gb,
        total_var_cost_pct_gb=total_var, vc_pct=vc_pct,
        avb=_safe(basket, trips),
        active_stores=active_stores,
        orders_per_store=_safe(trips / months_count, active_stores),
        sales_per_store=_safe(basket / months_count, active_stores),
        gb_per_store=_safe(gb / months_count, active_stores),
    )


# ---------- option lists ----------

@dataclass
class FilterOptions:
    months: List[str]
    merchant_types: List[str]
    segments: List[str]
    markets: List[str]


def derive_options(deals: pd.DataFrame) -> FilterOptions:
    if deals.empty:
        return FilterOptions([], [], [], [])
    return FilterOptions(
        months=sorted(set(deals["date"].dropna().astype(str))),
        merchant_types=sorted(set(deals["merchant_type"].map(pretty_merchant_type))),
        segments=sorted(set(deals["merchant_segment"].astype(str))),
        markets=sorted(set(deals["territory"].astype(str))),
    )


# ---------- breakdowns ----------

DimensionKey = Literal["territory", "merchant_type", "merchant_segment", "date", "Vertical"]


def metrics_by_dimension(deals: pd.DataFrame, stores: pd.DataFrame, dim: DimensionKey) -> List[Dict[str, Any]]:
    if deals.empty:
        return []
    if dim == "merchant_type":
        keys = deals["merchant_type"].map(pretty_merchant_type)
    else:
        keys = deals[dim].astype(str)
    out: List[Dict[str, Any]] = []
    for k, sub in deals.groupby(keys, sort=True):
        m = compute_metrics(sub, stores)
        out.append({"key": k, **m.as_dict()})
    return out


# ---------- formatters ----------

def fmt_pct(n: float, d: int = 2) -> str:
    if not isinstance(n, (int, float)) or not isfinite(n):
        return "—"
    return f"{n * 100:.{d}f}%"


def fmt_money(n: float) -> str:
    if not isinstance(n, (int, float)) or not isfinite(n):
        return "—"
    if n < 0:
        return f"(${abs(n):,.0f})"
    return f"${n:,.0f}"


def fmt_num(n: float) -> str:
    if not isinstance(n, (int, float)) or not isfinite(n):
        return "—"
    return f"{n:,.0f}"


def fmt_compact(n: float) -> str:
    if not isinstance(n, (int, float)) or not isfinite(n):
        return "—"
    sign = "-" if n < 0 else ""
    a = abs(n)
    if a >= 1e9:
        return f"{sign}${a/1e9:.2f}B"
    if a >= 1e6:
        return f"{sign}${a/1e6:.2f}M"
    if a >= 1e3:
        return f"{sign}${a/1e3:.1f}K"
    return f"{sign}${a:.0f}"


def fmt_month(s: str) -> str:
    try:
        d = datetime.fromisoformat(s[:10])
    except Exception:
        return s
    return d.strftime("%b %y")
