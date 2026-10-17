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

The split is only filled for continuing positions (add / trim / hold). For initiate and exit rows
`w_unchanged`, `active_w` and `passive_w` are left blank: the label itself is the signal.
Cash price is 1.

`is_material` (configurable via `MaterialityConfig`): `|d_shares_pct| ≥ 25` or `|active_w| ≥ 0.5` percentage points
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

## Column guide (plain-English)

### reconciliation — a safety check, not an analysis table
Compares the spreadsheet's own `∆ Shares` / `Previous Shares` / `Previous Weight` columns with
values recomputed from two consecutive files. **Empty = good**: the files are internally
consistent and the loader read them correctly. Rows would appear on e.g. a stock split,
ticker change or data error. It is a check on the input, not part of the agent's reasoning.

### signals — one row per stock per quarter step
| column | meaning | why we need it |
|---|---|---|
| `price_prev`, `price_curr` | quarter-end price in each file | needed for `w_unchanged` (old shares × new price) |
| `w_unchanged` | weight the stock would have at the new quarter end if **nobody traded anything** | the baseline that separates trading from price drift |
| `passive_w` | `w_unchanged − w_prev`: weight change from prices alone | stops the agent mistaking drift for a decision |
| `active_w` | `w_curr − w_unchanged`: weight change caused by the manager's trade | "how much the move mattered" to the whole portfolio |
| `is_material` | True if `|d_shares_pct| ≥ 25`, or `|active_w| ≥ 0.5` pp, or initiate/exit | short-lists the rows worth an analyst's attention |
| `streak` | consecutive quarter steps moving the same way (initiate/add = up, trim/exit = down; hold resets) | tests claims like "we've been reducing for a few quarters" |
| `prev_source_row`, `curr_source_row` | the spreadsheet rows each signal was computed from | traceability: every number the agent states must cite these |

**Why initiate and exit rows have blank active/passive.** For these rows the whole change is
obviously the manager's decision (buying from zero, or selling to zero), so splitting it adds
nothing. Also, an exited stock does not appear in the new file, so its new price is unknown.
One small assumption remains: when building the "nobody traded" portfolio total (the denominator
of `w_unchanged` for continuing stocks), an exited stock is valued at its *old* price, i.e. we
assume its price was flat. This slightly affects every continuing stock's split, usually by a
few hundredths of a percentage point.

**Materiality thresholds, stated precisely.** These are judgement-based defaults in
`MaterialityConfig`, not derived from data:
* `d_shares_pct` 25 means the share count changed by 25% or more (e.g. 16,495 to 12,995 is −21%,
  so not material on this test alone).
* `active_w` 0.5 means 0.5 **percentage points** of portfolio weight caused by trading
  (e.g. a position going from 2.78% to 2.28% through trading alone).
* Why 0.5: positions in this fund range from about 1.7% to 4% (average about 2.6%), so 0.5 pp is
  roughly a fifth of a typical position.
* Initiates and exits are always material, by label.

## Claims side (call transcript vs holdings)

Flow: transcript → **extractor** (language model; stub for now) → `claims` table → rule-based
checks against `signals` → `claim_checks.csv`. The model only reads and labels; every verdict
comes from code. Run `python -m portfolio_agent.build` first, then
`python -m portfolio_agent.check_claims`. The transcript is git-ignored (`data/transcripts/`).

### claims table (one row per stock-specific action the manager states)
| column | meaning |
|---|---|
| `claim_id` | stable id (C1, C2, ...) |
| `quote` | exact words from the call; code rejects rows whose quote is not in the transcript |
| `company` | company name as spoken (the model never outputs tickers or CUSIPs) |
| `action` | initiate, add, hold, trim or exit |
| `quarter`, `quarter_basis` | quarter the action happened in (`2026Q1`), and whether it was `stated` or `inferred_from_call_date` |
| `multi_quarter`, `duration_phrase` | true when the manager says it has gone on for several quarters, with their words |
| `rationale` | the manager's reasons, for traceability only; never used in the checks |

### Matching and verdicts
* `aliases.py` lists spoken name variants per CUSIP; they are stored in the `aliases` column of
  `security_reference` (separated by `|`). The build fails if a security has no entry or two
  securities share a variant. Names are matched after lowercasing and stripping punctuation and
  suffixes such as "Inc". No fuzzy or model matching yet.
* A claim is joined to the signals row for the same CUSIP whose `to_q` equals the claim's quarter.
* Verdicts: `consistent`; `contradicted` (observed action differs, or no position at either end
  of that step); `not_in_holdings` (name matches no security ever held, e.g. Kraft Heinz);
  `partially_supported` (direction right, but `multi_quarter` claim and `streak` below
  `ClaimCheckConfig.min_streak`, default 2; with three files the longest possible streak is 2).

### Known limits
* A stated action the extractor misses is never checked; trades the manager never mentions are
  not flagged either.
* Quarter-end snapshots show net change over the quarter, so "added in January" cannot be
  separated from later trades in the same quarter.
* Non-action commentary (risk views, themes) is out of scope.
* Names are matched by a hand-kept alias list; a new or oddly spelled name will come back as
  `not_in_holdings`, which a person should check.

### Running the real extractor
Put `OPENAI_API_KEY=...` in a git-ignored `.env` in the repo root (see `.env.example`); the model
defaults to `gpt-4o` (override with `OPENAI_MODEL`). `python -m portfolio_agent.check_claims`
uses it; `--extractor stub` uses fixed rows. `python -m portfolio_agent.consistency --runs 5
--temperature 1` repeats the extraction and reports how often each row appears.

Observed on the case excerpt: `gpt-4o` returned the same four rows in 5/5 runs at temperature 0
and at 1. `gpt-4o-mini` repeatedly dropped the word "also" from the Boeing quote, so the
verbatim-quote check rejected that row and the claim was lost. That is why quote validation
exists, and why a missed claim is a listed limitation.

### Sector concentration and tilts
* `portfolio_summary` now also has `n_sectors`, `sector_hhi`, `top_sector`, `top_sector_weight`,
  `sectors_in`, `sectors_out`. `sector_hhi` = 10000 · Σ (sector share of non-cash weight)², the same
  formula as the stock HHI. With the 11 GICS sectors its floor is 10000/11 ≈ 909 (perfectly even)
  and its ceiling is 10000 (one sector). It says how concentrated the fund is across sectors, not
  which sector is responsible.
* `sector_weights` has one row per quarter and sector (cash included as its own row), with
  `d_weight_pp` (change in percentage points since the previous quarter; a sector absent in a
  quarter counts as 0%) and `is_tilt` (`|d_weight_pp| >= SectorConfig.min_shift_pp`, default 3.0, a
  tunable default; never true for cash). Sectors exited entirely stay visible with weight 0.

## Report (no model)

`python -m portfolio_agent.report` reads the processed tables and writes `data/processed/flags.json` and `report.md`.
Claim inconsistencies are the `claim_checks` rows whose verdict is not `consistent`; stock flags are the `is_material`
rows of `signals`; sector flags are the `is_tilt` rows of `sector_weights`, with the per-quarter sector HHI alongside.
Each item has an id, all its source numbers and a template-written `summary`. The report states evidence only: no
questions, no recommendations, no reasons for the manager's actions.

## Tracing a claim back to the transcript

The claims table adds `source_id` (the transcript file name), `offsets` (start-end character positions), `paragraphs`
(1-based, non-empty lines) and `quote_multiple_occurrences`. Code fills these by searching the transcript for the quote.
If the quote occurs more than once, every match is listed (joined with `;`) and the flag is true.
