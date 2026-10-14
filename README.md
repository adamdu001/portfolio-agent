# portfolio-agent — deterministic data layer

Pure-pandas pipeline (no LLM) that turns Stonebridge Value Partners' quarterly 13F-style
holdings spreadsheets into tidy tables an analysis agent can query and cite.

## Run
```bash
pip install -r requirements.txt          # pandas, openpyxl, pytest, (optional) pyarrow
# CONFIDENTIAL inputs are NOT in the repo: drop them into data/raw/
#   data/raw/h_2025Q4.xlsx  data/raw/h_2026Q1.xlsx  data/raw/h_2026Q2.xlsx
python -m portfolio_agent.build          # -> data/processed/*.csv (+ .parquet if pyarrow)
pytest -q                                # real-data tests skip if data/raw/ is empty
```
`data/raw/` and `data/processed/` are git-ignored. Any `*.xlsx` in `data/raw` is loaded; the
quarter comes from the as-of date cell, not the file name.

## Input format & quirks handled
* Title rows, an as-of date cell in column A above the header, header row starting `Current Period`,
  data rows, then footer junk (`Comments`, `End of data`) — parsing stops at the footer.
* `Current Period` is the first of the month (e.g. 2025-12-01), not the period end — ignored;
  quarter = as-of date (2025-12-31 → `2025Q4`).
* `Previous Identifier` CUSIPs lost leading zeros (`13091103`) — zero-padded to 9 chars.
* `Weight` is in percent and includes a cash row (Ticker `USD`, Identifier `CASH`); weights sum to ~100
  (2026Q2 sums to 100.01 from rounding).
* Exited positions simply vanish from the next file; they are recovered by an outer join.
* The file's `∆`/`Previous` columns are **not** used. `reconciliation` reports any disagreement
  between them and values recomputed from consecutive files (currently 0 mismatches; the first
  file's ∆ columns refer to a quarter we don't have, so they are not checked).

## Tables (data/processed)
| table | grain | notes |
|---|---|---|
| `holdings` | quarter × cusip | file values only: quarter, as_of_date, cusip, ticker, name, security_type, shares, price, weight_pct, country, is_cash, source_file, source_row (1-based Excel row) |
| `security_reference` | cusip | latest ticker/name + `gics_sector` |
| `signals` | cusip × consecutive quarter pair | see below |
| `portfolio_summary` | quarter | n_positions (ex cash), cash_pct, hhi, effective_n, top10_weight_pct, max position, names in/out vs previous quarter |
| `sector_weights` | quarter × gics_sector | weight_pct (incl. Cash bucket), n_positions |
| `reconciliation` | mismatch | file ∆ columns vs recomputed |

### signals
`action`: initiate (0→>0), add, hold, trim, exit (>0→0). `d_shares_pct` is NaN for initiations.

**Active / passive decomposition.** Let `w_unchanged_i = 100 · s_prev,i · p_curr,i / Σ_j s_prev,j · p_curr,j`
(sum over *all* positions including cash) — the weight the stock would have had if the manager
had traded nothing and prices moved. Then
* `passive_w = w_unchanged − w_prev` (drift from price moves),
* `active_w  = w_curr − w_unchanged` (the manager's trading decision),
* `active_w + passive_w = d_w` exactly.

Exits have no current price, so `p_prev` is used and `price_imputed=True` (assumes flat price).
Cash price is 1.

`is_material` (configurable via `MaterialityConfig`): `|d_shares_pct| ≥ 25` or `|active_w| ≥ 0.5`
or action ∈ {initiate, exit}; never true for cash. `streak`: number of consecutive pairs, ending
at this one, moving in the same direction (initiate/add = up, trim/exit = down; hold → 0).
`prev_source_row`/`curr_source_row` point back to the spreadsheet rows for citations.

### portfolio_summary
`hhi = 10000 · Σ (w_i / Σ w)²` over non-cash positions (weights renormalised ex cash);
`effective_n = 10000 / hhi`; `top10_weight_pct` uses raw (incl.-cash-basis) weights.

## Assumptions
* **Sectors are a manual assumption, not vendor data**: `data/reference/sectors.csv` holds a
  hand-assigned GICS sector for every non-cash security seen (55); cash = `Cash`. The build fails
  loudly if a new CUSIP has no sector. Borderline calls: KD (Kyndryl) = IT, BRK/B = Financials,
  NSRGY (Nestlé ADR) = Consumer Staples, B (Barrick) = Materials.
* CUSIP is the key; ticker is descriptive only.
* Weights are taken as reported (rounded to 2 dp); w_unchanged is computed from shares × price.
