# Deal Desk — Metrics Calculation Reference

This document explains exactly how every number on the US&C dashboard is computed:
the top-line KPI cards, the Regional P&L summary table, how aggregates are
weighted, and how store counts are handled.

All logic lives in [`deal_desk/data_model.py`](../deal_desk/data_model.py)
(`compute_metrics`, `filter_deals`, `filter_stores`), and is surfaced by
[`services/kpis.py`](../services/kpis.py) (KPI cards) and
[`services/summary.py`](../services/summary.py) (summary table). The numbers are a
1:1 port of the shared TypeScript/Streamlit data model, so they match other Deal
Desk tooling for the same inputs.

---

## 1. Core principles (read this first)

These five rules explain 90% of the behavior:

1. **Everything is dollar-weighted, not row-averaged.**
   Every ratio metric is computed as **sum of the numerator ÷ sum of the
   denominator across all selected rows** — *not* the simple average of each
   row's percentage. We first add up the raw dollar columns over all rows, then
   divide once. This automatically weights larger merchants/regions more.

   > Example: Take Rate for a region is `total fees ÷ total basket` for that
   > region — **not** the average of each merchant's individual take rate.

2. **Two grains of data feed the metrics.**
   - **Deals rows** carry the dollar amounts (trips, basket, fees, costs, …).
   - **Store rows** carry pre-aggregated `active_stores` counts only. They are
     used *exclusively* for the store-count and per-store metrics.

3. **Store counts are summed, then divided by the number of months** → they are
   an **average monthly active-store count**, never a raw multi-month sum.

4. **Sign conventions come straight from the source data.**
   Costs are stored **negative** (`courier_payment`, `tf_disbursed`, `EuP`,
   `pass_net`, `trip_insurance`, `support`, `money`, `tech`, `other_variable`,
   and `resto_payments`). Revenue/volume fields are positive. So CpT, Marketing
   %, EuP %, Uber One %, and the variable-cost lines display as negative.

5. **Divide-by-zero is safe.** `_safe(n, d)` returns `0` when `d = 0`; the table's
   `_ratio` returns `NaN`, which renders as `—`.

Notation used below: for a selected set of deal rows, **Σx** = the sum of column
`x` over those rows.

---

## 2. Filtering: what rows feed a calculation

Before any metric is computed, the active filters (Date Range, Merchant Type,
Segment, Region, **Country**, Fulfillment) select the rows.

### Deals (`filter_deals`)
A row is kept if it matches **all** active filters:

| Filter | Match rule |
|---|---|
| Date Range | `date ∈ selected months` |
| Merchant Type | `pretty(merchant_type) ∈ selected` |
| Segment | `merchant_segment ∈ selected` |
| Region | `territory ∈ selected` |
| Country | `country ∈ selected` (US / Canada) |
| Fulfillment | `fulfillment(merchant_type) == CPP/MPP` |

`fulfillment` is derived: **MPP** for `GROCERY`, `RETAIL`, `PET_SUPPLY`; **CPP**
otherwise.

### Stores (`filter_stores`) — grain selection matters
Store rows are pre-aggregated at four grains via `store_level`:
`terr`, `seg_terr`, `ver_terr`, `ver_terr-seg`. The app picks the grain that
matches what you're slicing by, so distinct-merchant counts aren't double-counted:

| Active segment filter/breakdown? | Active type filter/breakdown? | `store_level` used |
|:--:|:--:|---|
| no | no | `terr` |
| yes | no | `seg_terr` |
| no | yes | `ver_terr` |
| yes | yes | `ver_terr-seg` |

Then the same Date Range / Segment / Region / Country filters are applied to the
chosen grain. (Country uses the row's `country` column just like deals.)

> A `country` column is added to both deals and stores. Any row missing a country
> value defaults to **US** (the warehouse extract is US-centric).

---

## 3. Top-line KPI cards

Rendered by `render_kpi_rows`. Two rows of seven.

### Top Line

| Card | Formula | Notes |
|---|---|---|
| **Merchants** | `distinct(grouped_parent_name)` over selected deals, blanks excluded | Count of distinct **parent brands/accounts**, not stores. |
| **Active Stores** | `round( Σactive_stores ÷ months )` | Average monthly active storefronts (see §5). |
| **Orders** | `Σtrips` | Completed trips. |
| **Total Sales** | `Σbasket` | Eater subtotal / fares basket. |
| **Avg Basket** | `Σbasket ÷ Σtrips` | Dollar-weighted average order value. |
| **Eater Fees % Basket** | `(Σbooking_fees + Σservice_fees + Σother_uber_fees) ÷ Σbasket` | |
| **Gross Bookings** | `Σgross_bookings` | |

### Bottom Line

| Card | Formula |
|---|---|
| **Total Take Rate** | `markup + mpf` |
| **Aggregate MPF** | `(Σbasket + Σresto_payments) ÷ Σbasket` |
| **Aggregate Markup** | `Σother_uber_fees ÷ Σbasket` |
| **EuP % GB** | `ΣEuP ÷ Σgross_bookings` |
| **CpT ($/trip)** | `Σcourier_payment ÷ Σtrips` (negative) |
| **NETR %** | `Σnetr ÷ Σgross_bookings` |
| **VC %** | `NETR% + Total Variable Costs%` |

Because `resto_payments` is stored negative (merchant payout), **MPF** =
`(basket − payout) ÷ basket` = the share of basket retained. **Take Rate** =
Markup + MPF.

---

## 4. Regional P&L summary table

Built by `render_summary_table`. You choose a **Breakdown** dimension
(Market/Region, Merchant Type, or Merchant Segment). The table has:

- **One column per dimension value** (e.g. each region). Blank and `UNKNOWN`
  values are hidden as columns.
- **A `National Total` column** = `compute_metrics` over the **entire filtered
  base** (all rows, including hidden blank/unknown).

> **Important:** each column is an **independent dollar-weighted aggregate** of
> its own rows, and `National Total` is **recomputed from the full base** — it is
> *not* the arithmetic sum of the visible columns. Consequences:
> - Dollar rows (Orders, Sales, GB): visible columns may not add up to National
>   Total if some rows fall in hidden blank/`UNKNOWN` buckets.
> - **# of Merchants**: National Total **de-duplicates** parents across columns,
>   so it is usually **less** than the sum of the columns (one brand operates in
>   many regions).

Per-column store metrics use the grain chosen in §2 for the breakdown dimension,
so e.g. breaking down by Merchant Type pulls `ver_terr` store counts.

### Row-by-row

**Volume**
| Row | Formula |
|---|---|
| # of Merchants | `distinct(grouped_parent_name)` |
| Active Stores | `round(Σactive_stores ÷ months)` |
| Average Basket (AvB) | `Σbasket ÷ Σtrips` |
| AvB % of National | `column.avb ÷ total.avb` |
| Orders | `Σtrips` |
| Orders % of National | `column.trips ÷ total.trips` |

**Per Store Statistics** (all per-store-per-month — see §5)
| Row | Formula |
|---|---|
| Orders per Store / month | `(Σtrips ÷ months) ÷ active_stores` |
| Sales per Store / month | `(Σbasket ÷ months) ÷ active_stores` |
| GB per Store / month | `(Σgross_bookings ÷ months) ÷ active_stores` |

**Eater Fees** (all ÷ `Σbasket`)
| Row | Formula |
|---|---|
| Delivery Fee % Basket | `Σbooking_fees ÷ Σbasket` |
| Service Fee % Basket | `Σservice_fees ÷ Σbasket` |
| Eater Fees % Basket | `(Σbooking_fees + Σservice_fees + Σother_uber_fees) ÷ Σbasket` |

**Sales / GBs**
| Row | Formula |
|---|---|
| Total Sales | `Σbasket` |
| Total Sales % across regions | `column.basket ÷ total.basket` |
| Total Gross Bookings | `Σgross_bookings` |
| GB % across regions | `column.gb ÷ total.gb` |

**Commercials**
| Row | Formula |
|---|---|
| Total Take Rate | `markup + mpf` |
| Aggregate Markup | `Σother_uber_fees ÷ Σbasket` |
| Aggregate MPF | `(Σbasket + Σresto_payments) ÷ Σbasket` |

**Expenses** (÷ `Σgross_bookings`, negative)
| Row | Formula |
|---|---|
| CpT ($/trip) | `Σcourier_payment ÷ Σtrips` |
| Marketing (% GB) | `Σtf_disbursed ÷ Σgross_bookings` |
| EUP (% GB) | `ΣEuP ÷ Σgross_bookings` |
| Uber One Discount (% GB) | `Σpass_net ÷ Σgross_bookings` |

**Other Revenue (% GB)**
| Row | Formula |
|---|---|
| Ad Revenue | `Σads_rev ÷ Σgross_bookings` |
| Other Revenue | `Σother_rev ÷ Σgross_bookings` |
| NETR % | `Σnetr ÷ Σgross_bookings` |

**Variable Cost (% GB)** (each ÷ `Σgross_bookings`, negative)
| Row | Formula |
|---|---|
| Insurance | `Σtrip_insurance ÷ Σgross_bookings` |
| Support | `Σsupport ÷ Σgross_bookings` |
| Money | `Σmoney ÷ Σgross_bookings` |
| Tech | `Σtech ÷ Σgross_bookings` |
| Other | `Σother_variable ÷ Σgross_bookings` |
| Total Variable Costs | sum of the five lines above |

**Bottom Line**
| Row | Formula |
|---|---|
| VC % | `NETR% + Total Variable Costs%` |

> Note on **Marketing (% GB)**: the app maps this line to `tf_disbursed` (taxes &
> fees disbursed). Some reference workbooks instead label "Marketing" as the sum
> of `EuP % + Uber One %`. The other ~20 metrics reconcile to 0.000%; this one
> line is a definitional difference to be aware of when comparing.

---

## 5. Store math, in detail (the "is it a sum?" question)

**Short answer: it's a sum *and* an average.** Active stores are summed across
the selected store rows, then divided by the number of distinct months — giving
an **average monthly active-store count**.

```
months        = number of distinct accounting_date in the selected store rows
active_stores = round( Σactive_stores ÷ months )
```

Why not a plain sum? Each month already contains that month's distinct active
storefronts. Summing 12 months would count a store up to 12 times. Dividing by
the month count yields the typical number of stores active in a month.

The per-store metrics keep numerator and denominator on the **same monthly
basis**, so every "per store" figure is **per store per month**:

```
orders_per_store = (Σtrips            ÷ months) ÷ active_stores
sales_per_store  = (Σbasket           ÷ months) ÷ active_stores
gb_per_store     = (Σgross_bookings   ÷ months) ÷ active_stores
```

- `Σactive_stores` is itself a count of `DISTINCT merchant_uuid` per month at the
  chosen grain (computed in `queries/store_query.sql`), so stores are never
  double-counted within a month.
- **Merchants vs Active Stores** are different things: *Merchants* =
  distinct **parent brands** (from deals); *Active Stores* = average monthly
  distinct **storefront locations** (from store rows).

---

## 6. Formatting & sign conventions

| Helper | Output | Example |
|---|---|---|
| `fmt_pct(x)` | `x × 100` with `%` | `0.1415 → 14.15%` |
| `fmt_money(x)` | `$` with negatives in parentheses | `-1234 → ($1,234)` |
| `fmt_compact(x)` | `$` with B/M/K suffix | `4.20e9 → $4.20B` |
| `fmt_num(x)` | thousands-separated integer | `89683239 → 89,683,239` |
| `—` | shown when a ratio's denominator is 0 | |

Costs (CpT, Marketing, EuP, Uber One, Insurance/Support/Money/Tech/Other,
Total Variable Costs) display **negative** by design.

---

## 7. Worked example (single number)

Take Rate for *Country = US, Region = California*:

1. `filter_deals` keeps only US + California deal rows.
2. Sum the dollar columns: `Σbasket`, `Σother_uber_fees`, `Σresto_payments`.
3. `Markup = Σother_uber_fees ÷ Σbasket`
4. `MPF    = (Σbasket + Σresto_payments) ÷ Σbasket`
5. `Take Rate = Markup + MPF`

No per-merchant percentages are averaged at any point — it's one weighted ratio
over the whole California subset.

---

*Source of truth:* `deal_desk/data_model.py` → `compute_metrics`,
`filter_deals`, `filter_stores`; `services/kpis.py`; `services/summary.py`;
`queries/clean_raw_query.sql`; `queries/store_query.sql`.
