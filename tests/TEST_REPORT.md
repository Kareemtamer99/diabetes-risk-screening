# Test report (FINAL)

Run on 2026-11-07, 14:20 to 14:30, against the final data, models, multi-year artifacts and app (SugarScope rename, slider and map fixes, `missing_states` in `multiyear.json`). Interpreter: the project `.venv` (Python 3.12, pandas 3.1.1, scikit-learn 1.9.1, streamlit 1.67.0). Env: `OPENBLAS_NUM_THREADS=1`, temp files on `G:\Temp\edge_final`. The combined per-check table is in `tests/edge/last_run.md`.

**READY TO PUSH: yes**

0 FAIL, 0 SKIP, 1 WARN. The one WARN is the README live-app link placeholder. It is allowed until the first deploy, because the URL doesn't exist yet.

## Runs, in order

| # | Run | Result | Time |
|---|---|---|---|
| 1 | `notebook.ipynb` alone: Restart & Run All in a temp copy, plus section C checks | 5 PASS | 210 s |
| 2 | `multiyear_validation.ipynb` executed in a temp copy, with `data/brfss` linked read-only | 0 error outputs; the regenerated `models/multiyear.json` is identical to the committed one, and `missing_states` is present | 43 s |
| 3 | Sections A (app), B (models), F (optional features) | 36 PASS | 126 s |
| 4 | Section D (repo, deploy, new checks), including a clean venv: `pip install -r requirements.txt`, load models, AppTest | 10 PASS, 1 FAIL (fixed in the check, see below) | 304 s (venv 295 s) |
| 5 | Run last, after the parallel deliverables/demo edits: README, prediabetes claims, SugarScope rename, attribution, emoji | 4 PASS, 1 WARN | 12 s |

## New and changed checks in this pass

- **Prediabetes claims plus data year.** No user-facing text in `app.py`, `pages/`, `README.md`, `deliverables/*.md` or the Markdown of either notebook says the model predicts prediabetes. `meta["data_year"] == 2015`. Result: PASS (7 sources).
- **SugarScope rename.** No "riskwell", in any capitalisation, in `app.py`, `assets/`, `README.md`, `deliverables/` (including text inside the `.pptx`), `demo/STORYBOARD.md`, `demo/record.py`, `notebook.ipynb` or `docs/`. `BRAND_NAME`, `page_title` and the rendered home header say SugarScope. Result: PASS (17 files).
- **Risk band (#18).** The band is now expected on `round(p, 2)`, matching the app: 0.139 shows "14% Medium" and 0.499 shows "50% High". The shown percent never contradicts the band legend; a contradiction is now a FAIL instead of a WARN. Result: PASS.
- **Threshold leakage (#35).** The thresholds come from `pick_threshold(y_train, oof)` and `pick_threshold(y_train, oof_s)`, out-of-fold on train. The test-set `curve_points` calls only report results. Result: PASS.
- **File scans (#30).** `data/`, `.venv/` and the generated logs (`tests/edge/last_run.*`, `demo/build/`) are excluded. Unreadable files are skipped and never cause a FAIL. `_notebook_split` copies only files from `data/`, not the `data/brfss` folder.
- **README (#44).** Exactly one placeholder is allowed: the `**Live app:**` URL line. Any other TODO fails. The emoji check now covers both result views, the home, insights and about pages, and the SVGs.

## The one failure in run 4 and how it was resolved

- **D README numbers.** `tests/test_edge_cases.py:1069` (owner: testing). The check compared README numbers only against `reports/results.csv` and `meta.json`. The new multi-year table (`README.md:54-59`: 0.760, 0.761, 0.781, 0.789, 0.790, 0.795, 0.824, 0.831) comes from `models/multiyear.json`; all 8 values are in that file. "20%" (`README.md:39`) is the held-out split size (`test_size=0.2`, notebook cell 23). The README was correct and the check was stale. The check now also reads `multiyear.json` and allows the split size. It passed in run 5.

## Warnings (not blocking)

- **W1: README live-app link is a placeholder** (`README.md:7`, owner: lead/deploy). Replace it with the `*.streamlit.app` URL after the first deploy, then re-run `d_readme`.

## Not covered by this run

- **Section E (browser):** dark mode, 375 px phone width, bad input in a real browser. Not in the final order. Its last results (all PASS) are from the interim run at 11:55 against the older app.
- **The global Python on this machine:** its user-site `pandas` is broken (`pandas.util` is missing, and there is no dist-info under `AppData\Roaming\Python\Python312`). The suite was run with `.venv` instead. This doesn't affect the deploy, because the clean venv install passed from `requirements.txt` alone.

## How to rerun

```bash
OPENBLAS_NUM_THREADS=1 .venv/Scripts/python.exe tests/test_edge_cases.py
```

A full run without `--only` prints its own `READY TO PUSH` line. This final pass ran the sections separately in the order requested, so the verdict above is from the combined results.
