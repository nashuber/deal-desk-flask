#!/usr/bin/env python3
"""
run_extract.py — Monthly refresh for the Deal Desk Flask dashboard (Path B, automated).

Flow
----
1. Compute the month window (defaults to the *previous* calendar month, UTC).
2. Substitute {{rate_type}}, {{date_interval}}, {{Start_date}}, {{End_date}}
   into the two SQL templates in ./queries/.
3. Execute both against Presto via Queryrunner (run_sql()).
4. Transform results into the EXACT JSON the app reads (data/deals.json:
   {"deals":[...], "stores":[...]}).
5. Write data/deals.json atomically.

Designed to be the Command of a DSW Scheduled Job:
       python /path/to/deal-desk-flask/run_extract.py
Run it monthly via the DSW cron fields (see RUNBOOK).

Only two queries run:
  - clean_raw_query.sql -> deals.json["deals"]
  - store_query.sql     -> deals.json["stores"]
The bigger "Raw PnL Query" is a superset the app never reads; skipped on purpose.

NOTE: If the Flask app is long-running, it caches deals.json at startup. Apply the
app.py patch so the dashboard re-reads on change — then no restart is needed after
this job runs.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

# ----------------------------------------------------------------------------
# Paths
# ----------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
QUERY_DIR = ROOT / "queries"
DATA_JSON = ROOT / "data" / "deals.json"

# ----------------------------------------------------------------------------
# Config (override via env vars or CLI flags)
# ----------------------------------------------------------------------------
RATE_TYPE = os.getenv("DD_RATE_TYPE", "USD at 2026 Plan v2")
DATE_INTERVAL = os.getenv("DD_DATE_INTERVAL", "month")
# Presto cluster name as used by Queryrunner. The QueryBuilder run bar showed
# "Atlanta - Presto"; the Queryrunner datasource for that is typically "presto".
DATASOURCE = os.getenv("DD_DATASOURCE", "presto")
# Email used to attribute the Queryrunner execution (DSW job runs as you).
USER_EMAIL = os.getenv("DD_USER_EMAIL", os.getenv("UBER_USER_EMAIL", "ndodti@ext.uber.com"))

DEAL_NUMERIC_FIELDS = [
    "trips", "basket", "booking_fees", "service_fees", "other_uber_fees",
    "gross_bookings", "courier_payment", "resto_payments", "tf_disbursed",
    "EuP", "pass_net", "ads_rev", "other_rev", "netr",
    "trip_insurance", "support", "money", "tech", "other_variable",
]


# ----------------------------------------------------------------------------
# Date window
# ----------------------------------------------------------------------------
def previous_month_window(today: dt.date | None = None) -> tuple[str, str]:
    """First and last day of the previous calendar month as 'YYYY-MM-DD'."""
    today = today or dt.datetime.utcnow().date()
    first_of_this_month = today.replace(day=1)
    last_of_prev = first_of_this_month - dt.timedelta(days=1)
    first_of_prev = last_of_prev.replace(day=1)
    return first_of_prev.isoformat(), last_of_prev.isoformat()


# ----------------------------------------------------------------------------
# SQL templating
# ----------------------------------------------------------------------------
def render_sql(template_path: Path, params: Dict[str, str]) -> str:
    sql = template_path.read_text(encoding="utf-8")
    for key, val in params.items():
        sql = sql.replace("{{" + key + "}}", str(val))
    if "{{" in sql:
        raise ValueError(f"Unsubstituted placeholder remains in {template_path.name}")
    return sql


# ----------------------------------------------------------------------------
# SQL execution via Queryrunner (same engine QueryBuilder uses)
# ----------------------------------------------------------------------------
def run_sql(sql: str) -> List[Dict[str, Any]]:
    """
    Execute `sql` on Presto via Queryrunner and return a list of row dicts
    keyed by the column aliases in the SQL.

    Requires the queryrunner client in the DSW session's virtual environment:
        pip install queryrunner-client

    The client API name can vary slightly by internal version. The block below
    tries the common shapes and raises a clear error if none match, so you can
    adjust one line rather than guess.
    """
    from queryrunner_client import Client  # type: ignore

    client = Client(user_email=USER_EMAIL)

    # Most builds expose .execute(datasource, query) returning an iterable of
    # dict-like rows. Some expose .execute_query(...) or require .load_data().
    if hasattr(client, "execute"):
        result = client.execute(DATASOURCE, sql)
    elif hasattr(client, "execute_query"):
        result = client.execute_query(datasource=DATASOURCE, query=sql)
    else:  # pragma: no cover
        raise RuntimeError(
            "queryrunner_client.Client has no execute()/execute_query(). "
            "Check the installed version and adjust run_sql()."
        )

    rows: List[Dict[str, Any]] = []
    for row in result:
        if isinstance(row, dict):
            rows.append(dict(row))
        elif hasattr(row, "_asdict"):       # namedtuple-style
            rows.append(dict(row._asdict()))
        elif hasattr(row, "keys"):          # mapping-like
            rows.append({k: row[k] for k in row.keys()})
        else:
            raise RuntimeError(
                "Unrecognized row type from queryrunner; expected dict-like rows."
            )
    return rows


# ----------------------------------------------------------------------------
# Transform rows -> app JSON records
# ----------------------------------------------------------------------------
def _num(v: Any) -> float:
    try:
        if v is None or str(v).strip() == "":
            return 0.0
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


def _str(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _date_str(v: Any) -> str:
    if v is None or v == "":
        return ""
    if isinstance(v, (dt.date, dt.datetime)):
        return v.date().isoformat() if isinstance(v, dt.datetime) else v.isoformat()
    return str(v)[:10]


def to_deal_records(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in rows:
        rec: Dict[str, Any] = {
            "date": _date_str(r.get("date") or r.get("accounting_date")),
            "merchant_type": _str(r.get("merchant_type")),
            "merchant_segment": _str(r.get("merchant_segment")),
            "grouped_parent_name": _str(r.get("grouped_parent_name")),
            "territory": _str(r.get("territory")),
            "Vertical": _str(r.get("Vertical")) or "*",
        }
        for f in DEAL_NUMERIC_FIELDS:
            rec[f] = _num(r.get(f))
        out.append(rec)
    return out


def to_store_records(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in rows:
        territory = _str(r.get("territory"))
        out.append({
            "accounting_date": _date_str(r.get("accounting_date")),
            "merchant_type": _str(r.get("merchant_type")) or "*",
            "merchant_segment": _str(r.get("merchant_segment")) or "*",
            "territory": territory,
            "active_stores": int(_num(r.get("active_stores"))),
            "store_level": _str(r.get("store_level")) or "terr",
            "Vertical": _str(r.get("Vertical")) or "*",
            "Region": _str(r.get("Region")) or territory,
        })
    return out


# ----------------------------------------------------------------------------
# Atomic write
# ----------------------------------------------------------------------------
def write_json_atomic(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="Monthly Deal Desk extract -> data/deals.json")
    ap.add_argument("--start", help="Start_date YYYY-MM-DD (overrides previous-month default)")
    ap.add_argument("--end", help="End_date YYYY-MM-DD (overrides previous-month default)")
    ap.add_argument("--rate-type", default=RATE_TYPE)
    ap.add_argument("--date-interval", default=DATE_INTERVAL)
    ap.add_argument("--dry-run", action="store_true",
                    help="Render SQL and print, but do not execute or write.")
    args = ap.parse_args()

    if args.start and args.end:
        start, end = args.start, args.end
    else:
        start, end = previous_month_window()

    params = {
        "rate_type": args.rate_type,
        "date_interval": args.date_interval,
        "Start_date": start,
        "End_date": end,
    }
    print(f"[run_extract] window {start} .. {end}  rate_type={params['rate_type']!r} "
          f"interval={params['date_interval']}  datasource={DATASOURCE}")

    deals_sql = render_sql(QUERY_DIR / "clean_raw_query.sql", params)
    stores_sql = render_sql(QUERY_DIR / "store_query.sql", params)

    if args.dry_run:
        print("\n----- clean_raw_query.sql (rendered) -----\n", deals_sql)
        print("\n----- store_query.sql (rendered) -----\n", stores_sql)
        return 0

    print("[run_extract] executing deals query...")
    deal_rows = run_sql(deals_sql)
    print(f"[run_extract]   deals rows: {len(deal_rows)}")

    print("[run_extract] executing stores query...")
    store_rows = run_sql(stores_sql)
    print(f"[run_extract]   stores rows: {len(store_rows)}")

    payload = {
        "deals": to_deal_records(deal_rows),
        "stores": to_store_records(store_rows),
    }

    if not payload["deals"]:
        print("[run_extract] ABORT: deals query returned 0 rows; refusing to overwrite "
              "deals.json with empty data.", file=sys.stderr)
        return 2

    write_json_atomic(DATA_JSON, payload)
    print(f"[run_extract] wrote {DATA_JSON}  "
          f"({len(payload['deals'])} deals, {len(payload['stores'])} stores)")
    print("[run_extract] DONE.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
