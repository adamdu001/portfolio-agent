# portfolio-agent

A pipeline that checks a fund manager's call commentary against their quarterly holdings and flags what needs a closer look. Calculations, comparisons, verdicts and the report are done by rule-based code. The language model is used for one step only: reading the call transcript and listing the claims in it.

The full design, a worked example and the limitations are in [BRIEF.md](BRIEF.md).

## Run

```bash
pip install -r requirements.txt
# put the three quarterly holdings workbooks (.xlsx) in data/raw/ (git-ignored, any file names)
# put the call transcript in data/transcripts/
python -m portfolio_agent.run                      # needs OPENAI_API_KEY in .env (see .env.example)
python -m portfolio_agent.run --extractor stub     # no API key: uses fixed example claims
python -m portfolio_agent.run --skip-claims        # holdings analysis only
pytest -q                                          # tests that need the real files skip without them
```

Outputs are written to `data/processed/`. The start point for reading them is `report.md`; `flags.json` holds the same items with all their source numbers. The quarter of each file is read from the as-of date cell inside the workbook, not from the file name.

## The nine steps

| # | Step | Script (`portfolio_agent/`) | Output (`data/processed/`) |
|---|---|---|---|
| 1 | Clean and standardise holdings | `load.py`, `reference.py`, `aliases.py` | `holdings.csv`, `security_reference.csv`, `reconciliation.csv` |
| 2 | Detect changes per stock | `signals.py` | `signals.csv` |
| 3 | Measure portfolio shape | `portfolio.py` | `portfolio_summary.csv`, `sector_weights.csv` |
| 4 | Read the transcript (model) | `extract.py`, `llm.py` | none (claims passed to the next step) |
| 5 | Check the model's output | `claims.py` | `claims_rejected.csv` |
| 6 | Match company names | `matching.py` | none (adds the CUSIP to each claim) |
| 7 | Compare claims with changes | `verdicts.py` | `claim_checks.csv` |
| 8 | Collect flags and write the report | `flags.py`, `render.py`, `report.py` | `flags.json`, `report.md` |
| 9 | Run everything end to end | `run.py` | all of the above |

Only step 4 uses a model. Every other step is deterministic, so the same inputs give the same report. To test how stable step 4 is, `python -m portfolio_agent.consistency --runs 5` repeats the extraction and shows how often each claim comes back.

## Where to read more

- **How each step works, and why:** [BRIEF.md](BRIEF.md), section "Data Model and Analytical Logics".
- **A real example traced from the Excel files to the report:** [BRIEF.md](BRIEF.md), section "Worked example".
- **What the approach cannot do:** [BRIEF.md](BRIEF.md), section "Limitations".
- **Defaults you can tune:** the thresholds (25% share change, 0.5 pp active weight, 3 pp sector tilt, minimum streak of 2) sit in config classes in `signals.py`, `portfolio.py` and `verdicts.py`. Sectors are hand-assigned in `data/reference/sectors.csv`.


