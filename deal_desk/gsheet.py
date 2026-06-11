"""Google Sheet auto-refresh.

Accepts a 'Publish to web' CSV URL (single sheet) or an `/export?format=xlsx`
URL (full workbook). Both flow through the same alias/coercion pipeline as a
manual XLSX upload.
"""
from __future__ import annotations

import io
from typing import Tuple

import pandas as pd
import requests

from .data_model import normalize_deals, normalize_stores
from .excel_parser import parse_workbook


def fetch(url: str, timeout: int = 30) -> Tuple[pd.DataFrame, pd.DataFrame]:
    if not url:
        raise ValueError("Google Sheet URL is empty.")
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    ct = resp.headers.get("Content-Type", "").lower()
    body = resp.content

    if "spreadsheet" in ct or url.lower().endswith(".xlsx") or "format=xlsx" in url.lower():
        return parse_workbook(body)

    # Treat as CSV — single sheet shaped like the deals extract.
    df = pd.read_csv(io.BytesIO(body))
    # Lowercase-strip column names so the React-style aliases also catch them
    df.columns = [str(c).strip() for c in df.columns]
    deals = normalize_deals(df)
    return deals, normalize_stores(pd.DataFrame())
