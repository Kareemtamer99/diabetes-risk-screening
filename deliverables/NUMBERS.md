# Numbers used in the deliverables

Each number in `presentation.pptx`, `LINKEDIN_POST.md` and `CV_BULLETS.md`, with its source.
Where: S = slide number, LI = LinkedIn post, CV = CV bullets.

The deck reads these values from the files when it is built, so the slides refresh by rebuilding (see "Refresh" below). The post and CV bullets are plain text: re-check them by hand against this table.
`deliverables/build/numbers.json` is written on every build and holds the exact values the deck used.

## Data

| Number shown | Where | Source file | Key or derivation |
|---|---|---|---|
| 253,680 raw responses ("~250K") | S4, CV1 | `models/meta.json` | `n_rows_raw` |
| 24,206 duplicates dropped | S4 | `models/meta.json` | `n_rows_raw - n_rows` |
| 229,474 rows used | S1, S2, S4, LI, CV2, CV3, portfolio | `models/meta.json` | `n_rows` |
| 21 questions | S4, S8, S11, LI, CV1 | `models/meta.json` | `len(features_full)` |
| 6 questions, and which six | S1, S8, S11, S12, LI, CV | `models/meta.json` | `features_short` (HighBP, HighChol, BMI, GenHlth, Sex, Age) |
| 15.3% positive (diagnosed diabetes; prediabetes coded 0); "15% overall" | S2, S4 chart, CV3 | `models/meta.json` | `positive_rate` = 0.15295 |
| 84.7% / 84.7% "neither" | S3, S4 chart | `models/meta.json` | `1 - positive_rate` (accuracy of always predicting "no") |
| Survey year BRFSS 2015 | S4 | `models/meta.json` | `data_year` = 2015 (see `data_year_note`: UCI page says 2014, but a rebuild from raw BRFSS 2015 matches `data/diabetes.csv` row for row) |
| 45,895 test-set people | S7 note, LI, CV1 | `models/meta.json` | `round(n_rows * 0.2)`; notebook split uses `test_size=0.2`. Confirmed in `side-session-notes/data-models-handover.md` |
| 80 / 20 split | S6 | `notebook.ipynb` | `test_size=0.2` |

## Model results (test set)

| Number shown | Where | Source file | Key or derivation |
|---|---|---|---|
| Recall target 80% | S3, S6, S10 | `models/meta.json` | `target_recall` |
| Final model recall 79.9% ("80%") | S7, S8, LI, CV2 | `models/meta.json` | `metrics.full.recall` (= `reports/results.csv` row "FINAL: HistGradientBoosting calibrated") |
| Final precision 0.314, F1 0.451, ROC-AUC 0.819, PR-AUC 0.444, Brier 0.105 | S7, S8 | `models/meta.json` | `metrics.full.*` |
| Final cut-off 0.147 | S7 | `models/meta.json` | `threshold_full` |
| Short model recall 81.2% ("81%") | S7, S8, S12, LI, CV1, portfolio | `models/meta.json` | `metrics.short.recall` (= results.csv row "SHORT (6 questions)") |
| Short precision 0.302, F1 0.440, ROC-AUC 0.812, PR-AUC 0.433, Brier 0.106 | S7, S8, CV1 | `models/meta.json` | `metrics.short.*` |
| Short cut-off 0.143 | S7, S12 | `models/meta.json` | `threshold_short` |
| Baseline 0.000 / 0.000 / 0.000 / 0.500 / 0.153 / 0.130 | S7 | `models/meta.json` | `metrics.baseline.*` |
| Baseline recall 0% | S3 | `models/meta.json` | `metrics.baseline.recall` |
| Logistic regression at 0.5: 0.154 / 0.539 / 0.239 / 0.810 / 0.414 / 0.107 | S7 | `reports/results.csv` | stage `test`, model "LogisticRegression tuned, uncalibrated @0.5" |
| Random forest at 0.5: 0.105 / 0.632 / 0.181 / 0.817 / 0.444 / 0.105 | S7 | `reports/results.csv` | stage `test`, model "RandomForest tuned, uncalibrated @0.5" |
| Gradient boosting at 0.5: 0.154 / 0.606 / 0.245 / 0.818 / 0.445 / 0.105; "15.4%" and "only 15%" | S7, LI, CV2 | `reports/results.csv` | stage `test`, model "HistGradientBoosting tuned, uncalibrated @0.5", column `recall` |
| Share of people flagged, short model, "about 41%" | S12 | derived | `metrics.short.recall * positive_rate / metrics.short.precision` = 0.411 |

## Screening cost (assumed test price)

| Number shown | Where | Source file | Key or derivation |
|---|---|---|---|
| $20 per test (ASSUMPTION, not data) | S9, LI, CV2 | `notebook.ipynb` | `COST_PER_TEST = 20.0`; hard-coded as `COST_PER_TEST` in `build/build_deck.js` |
| $64 per case found, full model | S9, CV2 | derived | `20 / metrics.full.precision` = 63.75. Matches the notebook's cost example |
| $66 per case found, short model | LI | derived | `20 / metrics.short.precision` = 66.24 |
| $131 per case found when testing everyone | S9, LI, CV2 | derived | `20 / positive_rate` = 130.77 |
| 61% fewer tests than testing everyone | S9 | derived | `1 - metrics.full.recall * positive_rate / metrics.full.precision` = 0.611 |
| 20% of cases missed | S9 | derived | `1 - metrics.full.recall` = 0.201 |

## Population segments

| Number shown | Where | Source file | Key or derivation |
|---|---|---|---|
| 4 segments | S9 | `models/segments.json` | `k` |
| Rates 32%, 21%, 6%, 5% | S9 chart | `models/segments.json` | `segments[].diabetes_rate` |
| Sizes 19%, 30%, 6%, 45% of people | S9 chart, notes | `models/segments.json` | `segments[].size_share` |
| Highest-risk segment 32% prevalence | S9, CV3 | `models/segments.json` | `diabetes_rate` of segment id 2 (0.324) |
| Ten health answers used for clustering | S9 notes | `models/segments.json` | `len(features)` |

## Multi-year validation (S10)

| Number shown | Where | Source file | Key or derivation |
|---|---|---|---|
| Years 2015, 2017, 2019, 2021, 2025; "4 later survey years" | S10, LI | `models/multiyear.json` | `years` |
| 1,210,322 rows | S10 | `models/multiyear.json` | `total_rows` |
| Saved model ROC-AUC 0.831 / 0.824 / 0.819 / 0.803 (2017/2019/2021/2025; file stores 0.8305, so 3-decimal display is 0.831) | S10 | `models/multiyear.json` | `temporal_validation[train_years="BRFSS 2015"]`.roc_auc` = 0.8305 / 0.8242 / 0.8185 / 0.8033 |
| Recall 0.789 / 0.781 / 0.760 / 0.761 (2017/2019/2021/2025) | S10 | `models/multiyear.json` | same rows, `recall` = 0.7888 / 0.7811 / 0.7603 / 0.7613 |
| Retrained on 2015–2019: same AUC (0.818 on 2021, 0.804 on 2025) | S10 | `models/multiyear.json` | `temporal_validation[train_years="2015-2019…"].roc_auc` = 0.8183 / 0.8037. Drift is in the population, not the model |

## Limitations

| Item | Where | Source | Note |
|---|---|---|---|
| Prediabetes not captured | S12 | dataset coding | Target is diagnosed diabetes; prediabetes is coded 0 |

## Not yet available

| Item | Where | Source file | Status |
|---|---|---|---|
| Lower recall for young adults | S12 (qualitative only) | `reports/fairness_recall.png` | No JSON source; the slide states it without a number |

## Refresh

From the repo root:

```bash
NODE_PATH=<folder with pptxgenjs and sharp>/node_modules PPTX_SKILL=<pptx skill folder> node deliverables/build/build_deck.js
```

```bash
powershell -NoProfile -ExecutionPolicy Bypass -File deliverables/build/render.ps1 <output folder for slide PNGs>
```

Check the deck table and this file against the result files (one rule: Python `format(x, ".3f")`):

```bash
python deliverables/build/check_numbers.py
```

Then compare `deliverables/build/numbers.json` with the rounded values in the post and CV bullets.

## Screenshots (no numbers typed by hand)

| Image | Where | Source file | Note |
|---|---|---|---|
| State map, 2025 actual rate | S10 | `demo/screenshots/state_map.png` | Cropped to the map and legend; the year-slider value bubble is left out |
| Home, quick check result, what-if, population insights | S11 | `demo/screenshots/home.png`, `result.png`, `whatif.png`, `insights.png` | Cropped in `build_deck.js`; the what-if crop starts below the weight slider so its value bubble is not shown |
