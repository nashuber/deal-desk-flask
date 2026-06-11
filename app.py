"""Deal Desk · Take Rate Analytics — Flask dashboard."""
from __future__ import annotations

import os
import secrets

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    def load_dotenv(*_a, **_k):
        return False

from flask import Flask, redirect, render_template, request, session, url_for

from deal_desk.data_model import (
    Filters,
    compute_metrics,
    derive_options,
    filter_deals,
    filter_stores,
    fmt_month,
)
from deal_desk.data_provider import (
    Dataset,
    DatasetCache,
    DEMO_LABEL,
    get_cached_gsheet,
    load_demo,
    load_upload_bytes,
)
from deal_desk.data_provider import DATA_JSON


def _demo_mtime() -> float:
    try:
        return DATA_JSON.stat().st_mtime
    except OSError:
        return 0.0


from services.charts import build_chart_divs
from services.filters import filter_chips, filters_from_session, session_filters_dict
from services.kpis import render_kpi_rows
from services.summary import render_summary_table

load_dotenv()


def cached_options(ds: Dataset):
    """Memoize the filter option lists on the dataset (3ms × every request)."""
    opts = ds.cache.get("options")
    if opts is None:
        opts = derive_options(ds.deals)
        ds.cache["options"] = opts
    return opts


def cached_charts(ds: Dataset, f, theme: str) -> list[str]:
    """Memoize Plotly chart fragments per (filters, theme).

    ``build_chart_divs`` is the dominant server cost (~160-410ms) and is otherwise
    recomputed on every Visualizations render, including when revisiting a filter
    combination already viewed.
    """
    key = (
        "charts",
        tuple(f.months),
        tuple(sorted(f.merchant_types)),
        tuple(sorted(f.segments)),
        tuple(sorted(f.markets)),
        f.fulfillment,
        theme,
    )
    hit = ds.cache.get(key)
    if hit is None:
        hit = build_chart_divs(ds.deals, ds.stores, f, theme)
        ds.cache[key] = hit
    return hit


def create_app() -> Flask:
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.secret_key = os.environ.get("SECRET_KEY", "dev-deal-desk-change-me")
    app.config["MAX_CONTENT_LENGTH"] = 80 * 1024 * 1024
    # Let the browser cache static assets (css, vendored htmx) so tab navigations
    # don't re-validate them each time. 1h keeps post-deploy staleness bounded.
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 3600
    app.config["DATA_CACHE"] = DatasetCache()
    app.config["DEMO_DATASET"] = load_demo()
    app.config["DEMO_MTIME"] = _demo_mtime()

    @app.context_processor
    def inject_globals():
        return {"DEMO_LABEL": DEMO_LABEL}

    @app.template_global()
    def rel_for(endpoint: str, **values) -> str:
        """App-root-relative URL (leading slash stripped).

        The DSW gateway mounts this app under a session-specific path prefix that
        it strips before forwarding, so the server never sees it and cannot make
        ``url_for`` emit it. Instead we emit root-relative URLs; the browser
        resolves them against the ``<base>`` tag that ``base.html`` computes from
        ``window.location`` at load time, keeping every asset, link, and form
        request inside the proxied path.
        """
        return url_for(endpoint, **values).lstrip("/") or "."

    def demo_dataset() -> Dataset:
        current = _demo_mtime()
        if current != app.config.get("DEMO_MTIME"):
            app.config["DEMO_DATASET"] = load_demo()
            app.config["DEMO_MTIME"] = current
        return app.config["DEMO_DATASET"]

    def current_dataset() -> Dataset:
        mode = session.get("ds_mode", "demo")
        cache: DatasetCache = app.config["DATA_CACHE"]
        if mode == "upload" and session.get("upload_key"):
            ds = cache.get_upload(session["upload_key"])
            if ds is not None:
                return ds
        if mode == "gsheet":
            url = session.get("gsheet_url") or ""
            if not url.strip():
                session["ds_mode"] = "demo"
                return demo_dataset()
            try:
                return get_cached_gsheet(cache, url.strip())
            except Exception:
                session["ds_mode"] = "demo"
                session.pop("gsheet_url", None)
        return demo_dataset()

    def ensure_session_defaults():
        session.setdefault("theme", "light")
        session.setdefault("ds_mode", "demo")
        session.setdefault("usc_tab", "summary")
        session.setdefault("usc_dim", "territory")
        if "filters" not in session:
            opts = cached_options(current_dataset())
            session["filters"] = session_filters_dict(
                "All", [], [], [], "All", opts.months,
            )

    def usc_payload() -> dict:
        """Build the full template context for the dashboard region.

        Shared by the GET view (full page) and the POST handlers (HTMX partial),
        so a filter/breakdown change re-renders only ``_dashboard.html`` instead of
        the whole page — avoiding a fresh Plotly download/parse on every click.
        """
        ds = current_dataset()
        deals, stores = ds.deals, ds.stores
        opts = cached_options(ds)
        ensure_session_defaults()
        f = filters_from_session(dict(session), opts.months)

        current = compute_metrics(filter_deals(deals, f), filter_stores(stores, f))

        tab = session.get("usc_tab", "summary")
        dim = session.get("usc_dim", "territory")
        if tab not in ("summary", "viz"):
            tab = "summary"
        if dim not in ("territory", "merchant_type", "merchant_segment"):
            dim = "territory"

        theme = session.get("theme", "light")
        kpi_html = render_kpi_rows(current, None, theme)

        summary_html = ""
        chart_fragments: list[str] = []
        if tab == "summary":
            summary_html = render_summary_table(deals, stores, f, dim, theme)
        else:
            chart_fragments = cached_charts(ds, f, theme)

        date_range = session.get("filters", {}).get("date_range", "All")
        seg_opts = [s for s in opts.segments if s not in ("Missing Segment", "Strategic")]

        return dict(
            theme=theme,
            ds=ds,
            opts=opts,
            filters=f,
            date_range=date_range,
            seg_opts=seg_opts,
            chips=filter_chips(f),
            kpi_html=kpi_html,
            tab=tab,
            dim=dim,
            summary_html=summary_html,
            chart_fragments=chart_fragments,
            row_count=len(deals),
            latest_month=fmt_month(opts.months[-1]) if opts.months else "—",
            row_count_fmt=f"{len(deals):,}",
        )

    def render_dashboard():
        """Return the partial (``#dashboard``) for HTMX requests, full page otherwise."""
        ctx = usc_payload()
        if request.headers.get("HX-Request"):
            return render_template("_dashboard.html", **ctx)
        ctx["flash_error"] = session.pop("flash_error", None)
        return render_template("usc.html", **ctx)

    @app.before_request
    def _before():
        if request.endpoint and not request.endpoint.startswith("static"):
            ensure_session_defaults()

    @app.route("/")
    def index():
        return render_template("index.html", theme=session.get("theme", "light"))

    @app.route("/region/<slug>")
    def region_stub(slug: str):
        titles = {
            "latam": "LATAM",
            "emea": "EMEA",
            "apac": "APAC",
        }
        title = titles.get(slug, slug.upper())
        return render_template("stub.html", title=title, theme=session.get("theme", "light"))

    @app.route("/usc", methods=["GET"])
    def usc():
        tq = request.args.get("tab")
        if tq in ("summary", "viz"):
            session["usc_tab"] = tq
        dq = request.args.get("dim")
        if dq in ("territory", "merchant_type", "merchant_segment"):
            session["usc_dim"] = dq
        return render_dashboard()

    def redirect_to_usc():
        """Relative redirect back to the dashboard.

        All these routes live one level below ``/usc`` (``/usc/apply`` etc.). A
        relative ``../usc`` Location is resolved by the browser against the full
        request URL — which still carries the DSW session prefix — so it lands on
        the prefixed dashboard without the server needing to know the prefix. The
        selected tab/dim/theme are persisted in the session, so no query is needed.
        """
        return redirect("../usc")

    @app.route("/usc/apply", methods=["POST"])
    def usc_apply():
        ds = current_dataset()
        opts = cached_options(ds)
        dr = request.form.get("date_range") or "All"
        mts = request.form.getlist("merchant_type")
        segs = request.form.getlist("segment")
        mkts = request.form.getlist("market")
        ful = request.form.get("fulfillment") or "All"
        session["filters"] = session_filters_dict(dr, mts, segs, mkts, ful, opts.months)
        session["usc_tab"] = request.form.get("tab") or "summary"
        session["usc_dim"] = request.form.get("dim") or "territory"
        if request.headers.get("HX-Request"):
            return render_dashboard()
        return redirect_to_usc()

    @app.route("/usc/clear", methods=["POST"])
    def usc_clear():
        ds = current_dataset()
        opts = cached_options(ds)
        session["filters"] = session_filters_dict("All", [], [], [], "All", opts.months)
        if request.headers.get("HX-Request"):
            return render_dashboard()
        return redirect_to_usc()

    @app.route("/usc/theme", methods=["POST"])
    def usc_theme():
        t = request.form.get("theme", "dark")
        session["theme"] = "dark" if t == "dark" else "light"
        return redirect_to_usc()

    @app.route("/usc/data", methods=["POST"])
    def usc_data():
        action = request.form.get("action", "")
        cache: DatasetCache = app.config["DATA_CACHE"]
        if action == "reset":
            session["ds_mode"] = "demo"
            session.pop("upload_key", None)
            session.pop("gsheet_url", None)
            opts = cached_options(demo_dataset())
            session["filters"] = session_filters_dict("All", [], [], [], "All", opts.months)
        elif action == "gsheet":
            url = (request.form.get("gsheet_url") or "").strip()
            if url:
                session["ds_mode"] = "gsheet"
                session["gsheet_url"] = url
                session.pop("upload_key", None)
                try:
                    ds = get_cached_gsheet(cache, url)
                    opts = cached_options(ds)
                    session["filters"] = session_filters_dict("All", [], [], [], "All", opts.months)
                except Exception as e:
                    session["flash_error"] = str(e)
                    session["ds_mode"] = "demo"
        elif action == "upload" and request.files.get("file"):
            uf = request.files["file"]
            raw = uf.read()
            key = secrets.token_hex(16)
            try:
                ds = load_upload_bytes(uf.filename or "upload.xlsx", raw)
                cache.put_upload(key, ds)
                session["ds_mode"] = "upload"
                session["upload_key"] = key
                session.pop("gsheet_url", None)
                opts = cached_options(ds)
                session["filters"] = session_filters_dict("All", [], [], [], "All", opts.months)
            except Exception as e:
                session["flash_error"] = str(e)
        return redirect_to_usc()

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=os.environ.get("FLASK_DEBUG") == "1")
