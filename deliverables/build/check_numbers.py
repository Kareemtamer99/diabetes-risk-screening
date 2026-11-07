"""Check deck table and NUMBERS.md metrics against models/meta.json and reports/results.csv.
One rule: format(x, ".3f"). Run from the repo root: python deliverables/build/check_numbers.py"""
import csv, json, re
from pptx import Presentation

f3 = lambda x: format(float(x), ".3f")
K = ["recall", "precision", "f1", "roc_auc", "pr_auc", "brier"]
meta = json.load(open("models/meta.json"))
test = {r["model"]: r for r in csv.DictReader(open("reports/results.csv")) if r["stage"] == "test"}
row = lambda prefix: next(v for k, v in test.items() if k.startswith(prefix))
want = {
    "Baseline": meta["metrics"]["baseline"], "Logistic regression": row("LogisticRegression"),
    "Random forest": row("RandomForest"), "Gradient boosting": row("HistGradientBoosting tuned"),
    "Final": meta["metrics"]["full"], "Short": meta["metrics"]["short"],
}
errs = []
slide = Presentation("deliverables/presentation.pptx").slides[6]
table = next(sh.table for sh in slide.shapes if sh.has_table)
for r in list(table.rows)[1:]:
    cells = [c.text for c in r.cells]
    name = next(k for k in want if cells[0].startswith(k))
    exp = [f3(want[name][k]) for k in K]
    if cells[1:] != exp: errs.append(f"deck S7 {name}: {cells[1:]} != {exp}")

md = open("deliverables/NUMBERS.md", encoding="utf-8").read()
def md_has(label, vals):
    line = next((l for l in md.splitlines() if l.startswith("| " + label)), None)
    if line is None: errs.append(f"NUMBERS.md: no row starting {label!r}"); return
    for v in vals:
        if v not in line: errs.append(f"NUMBERS.md {label!r}: missing {v}")
for label, src in [("Baseline 0", want["Baseline"]), ("Logistic regression", want["Logistic regression"]),
                   ("Random forest", want["Random forest"]), ("Gradient boosting", want["Gradient boosting"])]:
    md_has(label, [f3(src[k]) for k in K])
md_has("Final precision", [f3(meta["metrics"]["full"][k]) for k in K[1:]])
md_has("Short precision", [f3(meta["metrics"]["short"][k]) for k in K[1:]])
md_has("Final cut-off", [f3(meta["threshold_full"])])
md_has("Short cut-off", [f3(meta["threshold_short"])])
md_has("229,474", [f"{meta['n_rows']:,}"])
md_has("253,680", [f"{meta['n_rows_raw']:,}"])
md_has("Survey year", [str(meta["data_year"])])
print("\n".join(errs) or "OK: deck S7 table and NUMBERS.md metrics match the files")
raise SystemExit(bool(errs))
