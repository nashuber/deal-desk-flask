# Deal Desk (Flask)

Self-contained Flask dashboard for **Take Rate Analytics** (US&C), separate from `deal-desk-streamlit`.

## Run

```bash
cd deal-desk-flask
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # optional
python app.py
```

Open http://127.0.0.1:5000/ — pick **US & Canada** for the full dashboard.

## Features

- Same metrics, filters, summary P&L table, and Plotly charts as the Streamlit USC page (ported from the shared `deal_desk` data model).
- **Theme**: Dark (default) or Light (matches the Streamlit CSS palette).
- **Data**: Bundled `data/deals.json`, XLSX upload, or public Google Sheet URL (cached; see `GSHEET_TTL_SECONDS`).

## Layout

- `app.py` — Flask factory and routes
- `deal_desk/` — `data_model`, `excel_parser`, `gsheet`, `data_provider`
- `services/` — KPI HTML, summary table HTML, charts
- `templates/` / `static/` — UI
