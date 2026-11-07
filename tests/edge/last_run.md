Run 2026-11-07 14:20-14:30 (final, combined C + A/B/F + D runs) - models from models/ - PASS 51, FAIL 0, WARN 1, SKIP 0

READY TO PUSH: yes

| # | Section | Check | Result | Detail |
|---|---|---|---|---|
| 1 | C | Notebook Restart & Run All (temp copy) - zero errors, runtime | **PASS** | ran clean in 210s |
| 2 | C | Re-executed notebook reproduces committed meta.json metrics | **PASS** |  |
| 3 | C | Train/test split happens before any fit (code read) | **PASS** | first split in cell 23; random_state values ['RS'] |
| 4 | C | No target leakage (target not a feature, no fit on test data) | **PASS** | no fit/threshold on test data found by pattern scan; thresholds picked on y_train, oof, y_train, oof_s |
| 5 | C | Markdown numbers agree with executed outputs / results | **PASS** | 5 numbers checked |
| 6 | A | App loads with no exception, disclaimer + both tabs | **PASS** | models from G:\Nextgen_intern\models |
| 7 | A | Every page (Home, Risk check, Population insights, How it works) loads clean | **PASS** | home: 11659 chars; risk: 9705 chars; insights: 11520 chars; about: 10734 chars |
| 8 | A | Home CTAs navigate to the right page; nav bar lists every page | **PASS** | CTAs reach: risk, insights, about |
| 9 | A | Both tabs submit with defaults -> result card | **PASS** | quick=4% Low, full=1% Low |
| 10 | A | Height/weight at limits (100/250 cm, 25/300 kg) give a result | **PASS** | quick 100/25->4%; quick 100/300->7%; quick 250/25->2%; quick 250/300->13%; full 100/25->1%; full 100/300->1%; full 250/25->1%; full 250/300->2% |
| 11 | A | Out-of-range height/weight -> friendly message, no result, no crash | **PASS** | 14 invalid combos rejected with a message |
| 12 | A | BMI computed and clipped to 12-98 | **PASS** | all grid points in [12, 98], ints |
| 13 | A | Age buckets at boundaries (18, 24, 25, 79, 80, 100) + app submit | **PASS** | buckets OK; 18:1% 24:1% 25:1% 79:12% 80:12% 100:12% 18:0% 24:0% 25:0% 79:2% 80:2% 100:2% |
| 14 | A | Every option of GenHlth / Education / Income submits; codes are 1..N | **PASS** | 24 option submissions OK |
| 15 | A | All-yes and all-no answers (both tabs) | **PASS** | quick all-yes=34% Medium; quick all-no=0% Low; full all-yes=25% Medium; full all-no=1% Low |
| 16 | A | Missing models/ dir -> friendly error | **PASS** |  |
| 17 | A | Missing one model file -> friendly error | **PASS** | each of the 3 files removed in turn |
| 18 | A | Corrupt meta.json / corrupt joblib -> friendly error | **PASS** | 5 corrupt variants |
| 19 | A | meta.json missing a required key -> friendly error | **PASS** | 5 keys |
| 20 | A | Partial meta.json (bad nested values) -> no traceback after submit | **PASS** |  |
| 21 | A | Model that raises during predict -> friendly error | **PASS** |  |
| 22 | A | Risk band matches risk_bands at and around the cut points | **PASS** | 0.000->0% Low 0.130->13% Low 0.139->14% Medium 0.140->14% Medium 0.141->14% Medium 0.320->32% Medium 0.499->50% High 0.500->50% High 0.501->50% High 1.000->100% |
| 23 | A | Disclaimer visible in Low / Medium / High / error states | **PASS** | 6 result states + validation error |
| 24 | A | Factor list: no NaN/empty labels, only risk-raising, <=5, sorted | **PASS** | 1000 random answer sets; 5 produced no factors (fallback text verified) |
| 25 | A | Result chart shows only listed factors with real labels | **PASS** | Sex: Male; Heart disease or heart attack: Yes; High cholesterol: Yes; High blood pressure: Yes; General health: Poor |
| 26 | B | Both models load with the pinned scikit-learn; meta records it | **PASS** | sklearn 1.9.1 |
| 27 | B | Probabilities in [0,1], no NaN (5000 real rows) | **PASS** | full mean=0.147 min=0.000 max=0.800; short mean=0.146 min=0.000 max=0.918 |
| 28 | B | Model feature names/order equal meta feature lists | **PASS** |  |
| 29 | B | Column order / name mismatch is rejected, never silently wrong | **PASS** | full reversed order: reordered internally, same output; full renamed column: raises ValueError; full missing column: raises ValueError; short reversed order: re |
| 30 | B | Batch of 1 vs 1000 rows give identical predictions | **PASS** | single-row predict ~17 ms |
| 31 | B | Monotonicity sanity: BMI up, HighBP 0->1, GenHlth worse, Age older | **PASS** | full.BMI: mean +0.039, lowered 0%; full.HighBP: mean +0.029, lowered 0%; full.GenHlth: mean +0.050, lowered 0%; full.Age: mean +0.015, lowered 19%; short.BMI: m |
| 32 | B | Explainer direction agrees with model (factors shown really raise risk) | **PASS** |  |
| 33 | B | meta metrics/threshold sane (values in [0,1], model beats baseline) | **PASS** | {"full": {"recall": 0.7988317424134492, "precision": 0.313730975828111, "f1": 0.450524285886465, "roc_auc": 0.8186628166568187, "pr_auc": 0.44447273498060047, " |
| 34 | B | Threshold / recall claims in meta reproduce on the notebook's test split | **PASS** | n_test=45895; full: recall=0.799, precision=0.314, roc_auc=0.819; short: recall=0.812, precision=0.302, roc_auc=0.812 |
| 35 | B | Model size / load time / memory fit Streamlit Cloud (~1 GB) | **PASS** | full_model.joblib: 0.4 MB on disk, load 0.18s, peak 4 MB; short_model.joblib: 0.4 MB on disk, load 0.14s, peak 4 MB |
| 36 | F | Multi-year trend + state map: shown with both files, each hides alone, bad files hide, no crash | **PASS** | 6 file combos on synthetic fixtures + map year switch |
| 37 | F | Each optional file missing or corrupt -> its section hides, no crash | **PASS** | hidden cleanly: segments.joblib, segments.json, threshold_curve.json, multiyear.json, state_prevalence.csv; insights page/link hidden when all are absent |
| 38 | F | Cost planner math: per-1000 counts consistent, no divide-by-zero | **PASS** | full: 79 pts, positives/1000=153, recall@thr 0.796 vs meta 0.799; short: 79 pts, positives/1000=153, recall@thr 0.815 vs meta 0.812 |
| 39 | F | Cost planner UI at extreme cut-offs and costs -> finite values, no crash | **PASS** | full@0.02/$0: $0.00; full@0.02/$10000: $52,507.29; full@0.80/$0: $0.00; full@0.80/$10000: $11,176.47; short@0.02/$0: $0.00; short@0.02/$10000: $54,155.08; short |
| 40 | F | What-if: before/after in [0,1] for every change, both tabs, extreme weights | **PASS** | quick yes w=25: 34%/0%; quick yes w=300: 34%/1%; quick no w=25: 0%/0%; quick no w=300: 0%/1%; full yes w=25: 25%/1%; full yes w=300: 25%/3%; full no w=25: 1%/0% |
| 41 | F | Segments: predict on extreme inputs returns a known segment; json sane | **PASS** | k=4; extremes -> 0/2; random spread {3: 897, 2: 824, 1: 155, 0: 126} |
| 42 | D | Logo + favicon: files valid, wired into app.py, sized for the browser tab | **PASS** | 2 SVGs parse, favicon 64x64 PNG, all referenced |
| 43 | D | Files to be committed are < 100 MB each | **PASS** | 68 files, 8.1 MB total |
| 44 | D | git ignores .venv/, data/, the project-ideas PDF; keeps models/ + notebook | **PASS** |  |
| 45 | D | No assistant/tool attribution text anywhere (outside the tool settings dir) | **PASS** | 0 hits |
| 46 | D | No user-facing claim that the model predicts prediabetes; data_year == 2015 | **PASS** | 7 sources scanned, data_year=2015 |
| 47 | D | Renamed to SugarScope: no 'Riskwell' left; page title and header say SugarScope | **PASS** | 17 files clean; BRAND_NAME, page_title and rendered header say SugarScope |
| 48 | D | No emojis in app.py, README, .streamlit/, docs/ or rendered app | **PASS** | 6 files + 5 rendered views (both results, home, insights, about) scanned |
| 49 | D | commit-msg hook rejects attribution lines, accepts normal messages | **PASS** | 6 bad rejected, 2 good accepted |
| 50 | D | requirements.txt pins every third-party import of app.py, matching the venv | **PASS** | streamlit==1.67.0, scikit-learn==1.9.1, pandas==3.1.1, numpy==2.5.4, joblib==1.6.0, plotly==7.1.0 |
| 51 | D | README: no TODO results, every number matches results.csv / meta | WARN | live app link still a placeholder (allowed until first deploy); re-run after check fix |
| 52 | D | Clean venv: pip install -r requirements.txt -> import, load models, AppTest | **PASS** | install + check in 295s |
