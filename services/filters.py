"""Filter state — same rules as components/filter_bar.py."""
from __future__ import annotations

from datetime import datetime
from typing import Any, List

from deal_desk.data_model import Filters, default_filters, fmt_month

_RANGES = ["3M", "6M", "12M", "YTD", "All"]


def months_for_range(all_months: List[str], r: str) -> List[str]:
    if r == "All" or not all_months:
        return []
    if r == "YTD":
        latest_year = datetime.fromisoformat(all_months[-1][:10]).year
        return [m for m in all_months if datetime.fromisoformat(m[:10]).year == latest_year]
    n = {"3M": 3, "6M": 6, "12M": 12}[r]
    return all_months[-n:]


def range_for_months(all_months: List[str], months: List[str]) -> str:
    if not months:
        return "All"
    for r in _RANGES:
        if r != "All" and months_for_range(all_months, r) == months:
            return r
    return "All"


def filters_from_session(sess: dict[str, Any], all_months: List[str]) -> Filters:
    raw = sess.get("filters")
    if not isinstance(raw, dict):
        return default_filters()
    dr = raw.get("date_range") or "All"
    if dr not in _RANGES:
        dr = "All"
    months = months_for_range(all_months, dr) if dr != "All" else []
    ful = raw.get("fulfillment") or "All"
    if ful not in ("All", "CPP", "MPP"):
        ful = "All"
    return Filters(
        months=months,
        merchant_types=list(raw.get("merchant_types") or []),
        segments=list(raw.get("segments") or []),
        markets=list(raw.get("markets") or []),
        fulfillment=ful,  # type: ignore[arg-type]
    )


def session_filters_dict(
    date_range: str,
    merchant_types: List[str],
    segments: List[str],
    markets: List[str],
    fulfillment: str,
    all_months: List[str],
) -> dict[str, Any]:
    if date_range not in _RANGES:
        date_range = "All"
    if fulfillment not in ("All", "CPP", "MPP"):
        fulfillment = "All"
    return {
        "date_range": date_range,
        "merchant_types": merchant_types,
        "segments": segments,
        "markets": markets,
        "fulfillment": fulfillment,
    }


def filter_chips(f: Filters) -> str:
    if not f.is_active():
        return ""
    chips: List[str] = []
    if f.months:
        chips.append(f"{fmt_month(f.months[0])} → {fmt_month(f.months[-1])}")
    chips.extend(f.merchant_types)
    chips.extend(f.segments)
    chips.extend(f.markets)
    if f.fulfillment != "All":
        chips.append(f.fulfillment)
    return " · ".join(chips)
