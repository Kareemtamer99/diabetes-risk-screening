Run 2026-11-07 20:12 - models from G:\Nextgen_intern\models - PASS 26, FAIL 0, WARN 0, SKIP 0

READY TO PUSH: no

| # | Section | Check | Result | Detail |
|---|---|---|---|---|
| 1 | A | App loads with no exception, disclaimer + both tabs | **PASS** | models from G:\Nextgen_intern\models |
| 2 | A | Every page (Home, Risk check, Population insights, How it works) loads clean | **PASS** | home: 40843 chars; risk: 34758 chars; insights: 36111 chars; about: 36773 chars |
| 3 | A | Home CTAs navigate to the right page; nav bar lists every page | **PASS** | CTAs reach: risk, insights, about |
| 4 | A | Both tabs submit with defaults -> result card | **PASS** | quick=4% Low, full=1% Low |
| 5 | A | Height/weight at limits (100/250 cm, 25/300 kg) give a result | **PASS** | quick 100/25->4%; quick 100/300->7%; quick 250/25->2%; quick 250/300->13%; full 100/25->1%; full 100/300->1%; full 250/25->1%; full 250/300->2% |
| 6 | A | Out-of-range height/weight -> friendly message, no result, no crash | **PASS** | 14 invalid combos rejected with a message |
| 7 | A | BMI computed and clipped to 12-98 | **PASS** | all grid points in [12, 98], ints |
| 8 | A | Age buckets at boundaries (18, 24, 25, 79, 80, 100) + app submit | **PASS** | buckets OK; 18:1% 24:1% 25:1% 79:12% 80:12% 100:12% 18:0% 24:0% 25:0% 79:2% 80:2% 100:2% |
| 9 | A | Every option of GenHlth / Education / Income submits; codes are 1..N | **PASS** | 24 option submissions OK |
| 10 | A | All-yes and all-no answers (both tabs) | **PASS** | quick all-yes=34% Medium; quick all-no=0% Low; full all-yes=25% Medium; full all-no=1% Low |
| 11 | A | Missing models/ dir -> friendly error | **PASS** |  |
| 12 | A | Missing one model file -> friendly error | **PASS** | each of the 3 files removed in turn |
| 13 | A | Corrupt meta.json / corrupt joblib -> friendly error | **PASS** | 5 corrupt variants |
| 14 | A | meta.json missing a required key -> friendly error | **PASS** | 5 keys |
| 15 | A | Partial meta.json (bad nested values) -> no traceback after submit | **PASS** |  |
| 16 | A | Model that raises during predict -> friendly error | **PASS** |  |
| 17 | A | Risk band matches risk_bands at and around the cut points | **PASS** | 0.000->0% Low 0.130->13% Low 0.139->14% Medium 0.140->14% Medium 0.141->14% Medium 0.320->32% Medium 0.499->50% High 0.500->50% High 0.501->50% High 1.000->100% |
| 18 | A | Disclaimer visible in Low / Medium / High / error states | **PASS** | 6 result states + validation error |
| 19 | A | Factor list: no NaN/empty labels, only risk-raising, <=5, sorted | **PASS** | 1000 random answer sets; 7 produced no factors (fallback text verified) |
| 20 | A | Result chart shows only listed factors with real labels | **PASS** | Sex: Male; Heart disease or heart<br>attack: Yes; High cholesterol: Yes; High blood pressure:<br>Yes; General health: Poor |
| 21 | F | Multi-year trend + state map: shown with both files, each hides alone, bad files hide, no crash | **PASS** | 6 file combos on synthetic fixtures + map year switch |
| 22 | F | Each optional file missing or corrupt -> its section hides, no crash | **PASS** | hidden cleanly: segments.joblib, segments.json, threshold_curve.json, multiyear.json, state_prevalence.csv; insights page/link hidden when all are absent |
| 23 | F | Cost planner math: per-1000 counts consistent, no divide-by-zero | **PASS** | full: 79 pts, positives/1000=153, recall@thr 0.796 vs meta 0.799; short: 79 pts, positives/1000=153, recall@thr 0.815 vs meta 0.812 |
| 24 | F | Cost planner UI at extreme cut-offs and costs -> finite values, no crash | **PASS** | full@0.02/$0: $0.00; full@0.02/$10000: $52,507.29; full@0.80/$0: $0.00; full@0.80/$10000: $11,176.47; short@0.02/$0: $0.00; short@0.02/$10000: $54,155.08; short |
| 25 | F | What-if: before/after in [0,1] for every change, both tabs, extreme weights | **PASS** | quick yes w=25: 34%/0%; quick yes w=300: 34%/1%; quick no w=25: 0%/0%; quick no w=300: 0%/1%; full yes w=25: 25%/1%; full yes w=300: 25%/3%; full no w=25: 1%/0% |
| 26 | F | Segments: predict on extreme inputs returns a known segment; json sane | **PASS** | k=4; extremes -> 0/2; random spread {3: 897, 2: 824, 1: 155, 0: 126} |
