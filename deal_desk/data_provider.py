"""Flask dataset provider (no Streamlit). Demo JSON, XLSX upload, Google Sheet."""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

from .data_model import FilterOptions, derive_options, normalize_deals, normalize_stores
from .excel_parser import parse_excel_file
from . import gsheet

DEMO_LABEL = "Demo data"
_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_JSON = _DATA_DIR / "deals.json"
# Committed seed used for local dev / fresh clones. The live deals.json is
# gitignored and generated on the box by run_extract.py, so it may be absent
# in a fresh checkout; fall back to the seed so the app still boots.
DATA_SAMPLE_JSON = _DATA_DIR / "deals.sample.json"


def _resolve_data_path() -> Path:
    return DATA_JSON if DATA_JSON.exists() else DATA_SAMPLE_JSON


@dataclass
class Dataset:
    deals: pd.DataFrame
    stores: pd.DataFrame
    source_label: str
    updated_at: Optional[str]


def load_demo() -> Dataset:
    with open(_resolve_data_path(), "r", encoding="utf-8") as f:
        raw = json.load(f)
    deals = normalize_deals(pd.DataFrame(raw.get("deals", [])))
    stores = normalize_stores(pd.DataFrame(raw.get("stores", [])))
    return Dataset(deals, stores, DEMO_LABEL, None)


def load_upload_bytes(filename: str, buf: bytes) -> Dataset:
    import io

    deals, stores = parse_excel_file(io.BytesIO(buf))
    return Dataset(
        deals,
        stores,
        filename,
        datetime.utcnow().isoformat(timespec="seconds") + "Z",
    )


def load_gsheet(url: str) -> Dataset:
    deals, stores = gsheet.fetch(url)
    return Dataset(
        deals,
        stores,
        f"Google Sheet · {url[:60]}…",
        datetime.utcnow().isoformat(timespec="seconds") + "Z",
    )


class DatasetCache:
    """In-memory store for uploaded datasets and short-lived gsheet cache."""

    def __init__(self) -> None:
        self._uploads: Dict[str, Dataset] = {}
        self._gsheet: Dict[str, tuple[Dataset, float]] = {}

    def put_upload(self, key: str, ds: Dataset) -> None:
        self._uploads[key] = ds

    def get_upload(self, key: str) -> Optional[Dataset]:
        return self._uploads.get(key)

    def get_gsheet(self, url: str, ttl_seconds: int) -> Optional[Dataset]:
        hit = self._gsheet.get(url)
        if not hit:
            return None
        ds, ts = hit
        if time.time() - ts > ttl_seconds:
            del self._gsheet[url]
            return None
        return ds

    def set_gsheet(self, url: str, ds: Dataset) -> None:
        self._gsheet[url] = (ds, time.time())


def get_cached_gsheet(cache: DatasetCache, url: str) -> Dataset:
    ttl = int(os.getenv("GSHEET_TTL_SECONDS", "300") or 300)
    ds = cache.get_gsheet(url, ttl)
    if ds is None:
        ds = load_gsheet(url)
        cache.set_gsheet(url, ds)
    return ds
