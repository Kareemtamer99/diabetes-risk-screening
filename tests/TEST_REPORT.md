# Test report (FINAL)

Run on 2026-11-07, 14:20 to 14:30, against the final data, models, multi-year artifacts and app (SugarScope rename, slider and map fixes, `missing_states` in `multiyear.json`). Interpreter: the project `.venv` (Python 3.12, pandas 3.1.1, scikit-learn 1.9.1, streamlit 1.67.0). Env: `OPENBLAS_NUM_THREADS=1`, temp files on `G:\Temp\edge_final`. The combined per-check table is in `tests/edge/last_run.md`.

**READY TO PUSH: yes** (updated 20:15 after the V2 fixes; see V4)

On the post-fix app (`app.py` saved 20:02):
- the visual asserts pass 15/15 at 1366, 768 and 375, with all 4 insights charts present and no WebGL;
- sections A and F pass 26/26;
- the emoji, rename, attribution and prediabetes checks pass;
- V2 #1-11 are fixed in the screenshots.

The only WARN is still the README live-app placeholder. The remaining notes in V4 are cosmetic and don't block the push.

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

## V. Visual QA (design pass 3, 2026-11-07 15:05 to 15:25)

Tool: `tests/visual_check.py` (Playwright Chromium against its own Streamlit on a free port from 8650; it does not use :8501). It covers 5 page states (Home; Risk check Quick and Full, each with a submitted result; Population insights with the map; How it works) at 4 sizes: 1920x1080, 1366x768, 768x1024 and 375x812. That makes 20 full-page screenshots in `G:/Temp/edge_final/visual/`, plus `contact_<size>.png` for each width and `results.json`. Layout and screenshots come from a reduced-motion pass, so end states are deterministic. Count-ups and reveals are checked on a second pass with motion on.

### V1. Automated asserts: 20/20 PASS

| Assert | Result |
|---|---|
| H1 top is at or below the nav bar's bottom, and the H1 is fully inside the viewport | PASS, all 20 |
| No element past the viewport width (`scrollWidth`, plus unclipped elements) | PASS, all 20 |
| Nav first item is at least 12 px from the left | PASS (75 px at 1366) |
| No overlapping text nodes in the header band and the cards (HTML text; SVG charts excluded) | PASS |
| Slider value bubbles fit on one line | PASS |
| No "Page not found" dialog | PASS, all 20. The 1st run opened Home at `/home`; Home is `default=True`, so its URL is `/`. Fixed in the script. |
| Count-ups (`[data-count]`) end on `data-final` and match the reduced-motion values | PASS (3 on Home: 229,474 / 81% / 6) |
| Hero preview card labelled "Example" (`.pv-ex`) | PASS |
| No `.rv` without `.rv-in`, and nothing with text at opacity 0 after scrolling to the bottom | PASS. Streamlit's slider min/max tick labels are excluded: they are opacity 0 until hover by design, and caused 12 false FAILs in run 1. |

### V2. Screenshot review: all 20 screenshots, 375 px cut into full-resolution strips

The automated asserts cannot see inside Plotly SVG charts, `st.dataframe` scroll areas, or truncated select values. Everything below was found by looking.

**Content clipped or hidden** (fix before push; owner: app-design)

1. **Factor-chart labels clipped** at 768 and 375, on both tabs. "General health: Good" shows as "…al health: Good". In the Full tab at 768, all 5 labels are cut ("…vy drinking: No", "…sical activity: No", "…school graduate"). The Plotly y-axis left margin is fixed and too small for the narrow column. Shots: `risk_quick_768x1024.png`, `risk_full_768x1024.png`, `risk_full_375x812.png`.
2. **Multi-year table cut off** at 768 and 375. Only "Trained on" is visible; Tested on, ROC-AUC and Recall are hidden in a scroll area with no visible hint. Shots: `insights_768x1024.png`, `insights_375x812.png`.
3. **The PCA scatter needs WebGL** (`go.Scattergl`, `app.py:836`), and there is no fallback. At 1366 the chart rendered as the grey box "WebGL is not supported by your browser". Users with hardware acceleration off, on VMs or in locked-down browsers see the same. About 3k points draw fine with `go.Scatter` (SVG). Shot: `insights_1366x768.png`.

**Overlap and truncation** (should fix; owner: app-design)

4. Cost-planner chart: the cut-off line runs up through the legend, and the "Cut-off 15%" label sits on the line, so the line strikes through it. At 375 the legend also covers the top of the plot. All widths.
5. Scatter legend: at 768 and 375 it sits over the data, and at 375 its text is cut at the right edge ("…good genera", "…no mobil").
6. At 768: the segmented controls are cut ("Quick che", "Actual | Pr"). The selectboxes truncate ("High school gradu", "$50,000 – $75,00"). The profile label truncates ("Reported a diabetes diagno…" at 1366 and wider, "Reported a d…" at 768).
7. At 768 the risk page stays two columns, which squeezes the right column to about 210 px: "What raised / your score", narrow wrapped text and the cramped meter labels. The trend card and map are side by side, so the map is small. Stacking below about 900 px would fix this, together with #1 and #6.

**Spacing and polish** (minor)

8. On the risk page, the disclaimer card touches the cards above and below it with no gap, and the what-if card's bottom edge runs straight into the footer band. All widths.
9. Brier score tile (How it works): lower is better, yet the Baseline (0.130) gets the longest bar, so the worst model looks best. Either invert the bar or label it "lower is better" next to the bar.
10. The 1% risk marker is half cut at the left end of the meter (Full tab, 768 and 375).
11. The Home sparkline has no values, only years. At 375 its year labels are about 7 px and unreadable.
12. Content to review: the full-tab factors list "Heavy drinking: No" and "Days of poor physical health: 0 days" as raising the score. That's correct for the model (it reflects associations in the survey), but readers will find it confusing.
13. At 375 the top nav collapses to a lone "»" button; the page links are only in the sidebar.

Clean: H1 and nav placement, hero and "Example" card, full-bleed bands, bento count-ups, the How it works pipeline and tiles, the CTA band, the 4-column footer (2 columns at 768, 1 at 375), and the band-tinted result cards (green for Low). No dialog, overflow or stuck reveal at any width.

### V3. Not covered

- **What-if "open" state.** The script did not move the what-if slider, so the risk screenshots show the panel unchanged (BMI 26 → 26). Cause: Streamlit 1.67 sliders are an `input[type=range]`, not `role=slider`. The script now drives the input the way `demo/record.py` does, but this is **unverified**. Three debug attempts failed on Chromium itself (timeout, page crash, click timeout) while the machine had about 300 to 600 MB of RAM free. Re-run when RAM allows.
- **Suite after the redesign.** A and F: 26/26 PASS (15:19). Prediabetes claims: PASS. **Attribution: PASS (15:35)** after a lead decision. It first failed on the bare word "AI" at `deliverables/LINKEDIN_POST.md:12`, `:38` and `:48`, which are the internship's official name and `#AI`. The lead ruled those allowed: the rule is no claim of assistant authorship. The check now flags authorship phrases (a creation verb, then "with", "by" or "using", then an assistant, an LLM or a vendor), plus assistant and vendor names and commit co-author trailers. It no longer flags the bare word "AI". The same pattern replaced the "AI" word check in the rendered-app emoji scan. A self-check confirms it flags 6 authorship phrases and passes 5 allowed ones, including a sentence naming the Streamlit framework. Emoji and rename: PASS on the post-fix app (see V4).
- Windows high-contrast mode, and a real touch device.

### V4. Re-run after the V2 fixes (20:05 to 20:15)

`tests/visual_check.py --sizes 768,375,1366` was run against the post-fix app, with one Streamlit and one Chromium, both stopped afterwards. The shots are in `G:/Temp/edge_final/visual2/`, with contact sheets `contact_1366x768.png`, `contact_768x1024.png` and `contact_375x812.png`.

- **Automated:** 15/15 PASS.
- **New assert:** Population insights must show at least 4 visible `.js-plotly-plot` charts (scatter, cost, trend, map) and no WebGL canvas or "WebGL is not supported" text. This matters because the section swallows chart errors, so AppTest can't see a chart that silently disappears. Result: 4 charts and 0 WebGL at all 3 widths.
- **What-if open state is now verified:** the slider moves to 60 kg, BMI shows 26 → 21, and the before/after values appear.
- **Suite:** A and F 26/26 PASS (20:12). Emoji PASS (5 rendered views). Rename PASS (17 files). Attribution PASS (0 hits). Prediabetes claims PASS.

V2 items, checked by looking at the screenshots:

| # | Item | Status |
|---|---|---|
| 1 | Factor-chart labels clipped (768 and 375) | Fixed. Labels wrap in full, for example "Education: High school graduate". |
| 2 | Multi-year table cut off | Fixed. All 5 columns are visible at 768 and 375, including the new Precision column. |
| 3 | Scatter needs WebGL | Fixed. It's now SVG and renders at 1366; the assert above enforces this. |
| 4 | Cost-chart cut-off line through its label and the legend | Fixed. The label is boxed beside the line, and the legend is below the chart. |
| 5 | Scatter legend over the data or cut off | Fixed. The legend is below the chart and wraps. At 375 the x-axis title sits flush against the first legend line: crowded, but readable. |
| 6 | Truncated toggles, selects and profile label | Fixed ("Full check / Quick check", "Actual / Predicted", "$50,000 – $75,000", "Reported a diabetes diagnosis"). |
| 7 | Two columns squeezed at 768 | Fixed. The risk page and the trend/map stack into one column at 768. |
| 8 | Cards touching each other and the footer | Fixed. All gaps are consistent. |
| 9 | Brier bar encoding | Fixed. The tile is labelled "lower is better, longest bar = best". |
| 10 | 1% marker half cut at the left of the meter | Fixed. The marker sits inside the bar. |
| 11 | Sparkline without values, unreadable at 375 | Fixed. It shows 0.82 / 0.80 at the ends, and the year labels are readable. |

New minor notes (cosmetic, not blocking; owner: app-design):
- **What-if delta.** Moving the slider from 75 to 60 kg gives "↑ +0.0 points" in red, and "Now" shows a grey "↑ Low" delta. A zero change shouldn't show as a red increase. Hide the delta, or make it neutral, when the change rounds to 0.0.
- **Population profiles at 1366 and 768:** the 4 cards sit in a 3+1 arrangement, leaving a gap at the bottom right.
- **At 375 the top nav is a lone "»" button** (V2 #13; not in the fix list).
- The scatter at 375 is crowded (#5 above).

Housekeeping: `tests/edge/last_run.md` now holds the 20:12 A and F run only. It says "READY TO PUSH: no" because any `--only` run does. This report is the verdict of record.

## How to rerun

```bash
OPENBLAS_NUM_THREADS=1 .venv/Scripts/python.exe tests/test_edge_cases.py
```

A full run without `--only` prints its own `READY TO PUSH` line. This final pass ran the sections separately in the order requested, so the verdict above is from the combined results.
