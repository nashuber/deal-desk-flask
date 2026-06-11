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

from services.charts import build_chart_divs
from services.filters import filter_chips, filters_from_session, session_filters_dict
from services.kpis import render_kpi_rows
from services.summary import render_summary_table

load_dotenv()


def create_app() -> Flask:
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.secret_key = os.environ.get("SECRET_KEY", "dev-deal-desk-change-me")
    app.config["MAX_CONTENT_LENGTH"] = 80 * 1024 * 1024
    app.config["DATA_CACHE"] = DatasetCache()
    app.config["DEMO_DATASET"] = load_demo()

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
                return app.config["DEMO_DATASET"]
            try:
                return get_cached_gsheet(cache, url.strip())
            except Exception:
                session["ds_mode"] = "demo"
                session.pop("gsheet_url", None)
        return app.config["DEMO_DATASET"]

    def ensure_session_defaults():
        session.setdefault("theme", "light")
        session.setdefault("ds_mode", "demo")
        session.setdefault("usc_tab", "summary")
        session.setdefault("usc_dim", "territory")
        if "filters" not in session:
            opts = derive_options(current_dataset().deals)
            session["filters"] = session_filters_dict(
                "All", [], [], [], "All", opts.months,
            )

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

        ds = current_dataset()
        deals, stores = ds.deals, ds.stores
        opts = derive_options(deals)
        ensure_session_defaults()
        f = filters_from_session(dict(session), opts.months)

        current = compute_metrics(filter_deals(deals, f), filter_stores(stores, f))

        previous = None  # delta vs previous window removed per request

        tab = session.get("usc_tab", "summary")
        dim = session.get("usc_dim", "territory")
        if tab not in ("summary", "viz"):
            tab = "summary"
        if dim not in ("territory", "merchant_type", "merchant_segment"):
            dim = "territory"

        theme = session.get("theme", "light")
        kpi_html = render_kpi_rows(current, previous, theme)

        summary_html = ""
        chart_fragments: list[str] = []
        if tab == "summary":
            summary_html = render_summary_table(deals, stores, f, dim, theme)
        else:
            chart_fragments = build_chart_divs(deals, stores, f, theme)

        date_range = session.get("filters", {}).get("date_range", "All")
        seg_opts = [s for s in opts.segments if s not in ("Missing Segment", "Strategic")]
        flash_error = session.pop("flash_error", None)

        return render_template(
            "usc.html",
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
            flash_error=flash_error,
            row_count_fmt=f"{len(deals):,}",
        )

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
        opts = derive_options(ds.deals)
        dr = request.form.get("date_range") or "All"
        mts = request.form.getlist("merchant_type")
        segs = request.form.getlist("segment")
        mkts = request.form.getlist("market")
        ful = request.form.get("fulfillment") or "All"
        session["filters"] = session_filters_dict(dr, mts, segs, mkts, ful, opts.months)
        session["usc_tab"] = request.form.get("tab") or "summary"
        session["usc_dim"] = request.form.get("dim") or "territory"
        return redirect_to_usc()

    @app.route("/usc/clear", methods=["POST"])
    def usc_clear():
        ds = current_dataset()
        opts = derive_options(ds.deals)
        session["filters"] = session_filters_dict("All", [], [], [], "All", opts.months)
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
            opts = derive_options(app.config["DEMO_DATASET"].deals)
            session["filters"] = session_filters_dict("All", [], [], [], "All", opts.months)
        elif action == "gsheet":
            url = (request.form.get("gsheet_url") or "").strip()
            if url:
                session["ds_mode"] = "gsheet"
                session["gsheet_url"] = url
                session.pop("upload_key", None)
                try:
                    ds = get_cached_gsheet(cache, url)
                    opts = derive_options(ds.deals)
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
                opts = derive_options(ds.deals)
                session["filters"] = session_filters_dict("All", [], [], [], "All", opts.months)
            except Exception as e:
                session["flash_error"] = str(e)
        return redirect_to_usc()

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=os.environ.get("FLASK_DEBUG") == "1")
