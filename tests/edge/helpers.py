"""Shared helpers for tests/test_edge_cases.py (no pytest needed)."""
import ast
import json
import shutil
import tempfile
import time
import traceback
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
EDGE = Path(__file__).resolve().parent


class Skip(Exception):
    pass


class Warn(Exception):
    """Soft failure: reported, does not block READY TO PUSH."""


RESULTS = []  # dicts: id, section, name, status, detail, secs


def check(section, name):
    def deco(fn):
        fn._check = (section, name)
        return fn
    return deco


def run_check(fn):
    section, name = fn._check
    t0 = time.time()
    try:
        detail = fn() or ""
        status = "PASS"
    except Skip as e:
        status, detail = "SKIP", str(e)
    except Warn as e:
        status, detail = "WARN", str(e)
    except AssertionError as e:
        status, detail = "FAIL", str(e) or traceback.format_exc(limit=2)
    except Exception as e:  # noqa: BLE001 - any crash is a failure of the check
        status, detail = "FAIL", f"{type(e).__name__}: {e}\n{traceback.format_exc(limit=3)}"
    r = dict(section=section, name=name, status=status, detail=str(detail).strip(), secs=round(time.time() - t0, 1))
    RESULTS.append(r)
    print(f"[{status}] {section} {name} ({r['secs']}s){(' - ' + r['detail'].splitlines()[0]) if r['detail'] else ''}", flush=True)
    return r


def load_app_functions(app_path=ROOT / "app.py"):
    """Exec app.py without its module-level main() call, so helpers can be unit-tested."""
    tree = ast.parse(Path(app_path).read_text(encoding="utf-8"))
    tree.body = [n for n in tree.body if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Call))]
    ns = {"__file__": str(app_path), "__name__": "app_under_test"}
    exec(compile(tree, str(app_path), "exec"), ns)  # noqa: S102 - our own source
    return ns


class ConstModel:
    """Returns a fixed probability; used to test risk-band display at the cut points."""

    def __init__(self, p):
        self.p = p

    def predict_proba(self, X):
        return np.tile([1 - self.p, self.p], (len(X), 1))


class RaisingModel:
    def predict_proba(self, X):
        raise RuntimeError("boom")


def load_meta(models_dir):
    return json.loads((Path(models_dir) / "meta.json").read_text(encoding="utf-8"))


def copy_models(src, **overrides):
    """Copy a models dir to a fresh temp dir. overrides: filename -> object|bytes|None (None deletes)."""
    d = Path(tempfile.mkdtemp(prefix="edge_models_"))
    if src and Path(src).exists():
        for f in Path(src).iterdir():
            if f.is_file():
                shutil.copy(f, d / f.name)
    for fname, obj in overrides.items():
        p = d / fname
        if obj is None:
            p.unlink(missing_ok=True)
        elif isinstance(obj, (bytes, str)):
            p.write_bytes(obj.encode() if isinstance(obj, str) else obj)
        elif fname.endswith(".json"):
            p.write_text(json.dumps(obj), encoding="utf-8")
        else:
            joblib.dump(obj, p)
    return d


_DATA = {}


def read_data():
    """data/diabetes.csv as int16 (all columns are small integer codes) - keeps RAM low."""
    if "df" not in _DATA:
        _DATA["df"] = pd.read_csv(ROOT / "data" / "diabetes.csv", dtype="int16", engine="c")
    return _DATA["df"]


def build_stub_models(out_dir, n=20000, seed=0):
    """Contract-shaped stand-in models (scaler + logistic regression) for when models/ is not ready."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    df = read_data().sample(n, random_state=seed)
    full = [c for c in df.columns if c != "Diabetes_binary"]
    short = ["Age", "BMI", "HighBP", "HighChol", "GenHlth", "DiffWalk", "HeartDiseaseorAttack"]
    meta = {"features_full": full, "features_short": short, "risk_bands": {"low_max": 0.1, "high_min": 0.3},
            "threshold_full": 0.15, "threshold_short": 0.15, "positive_rate": float(df.Diabetes_binary.mean()),
            "n_rows": len(df), "data_year": 2015, "metrics": {}}
    for feats, fname, ekey in ((full, "full_model.joblib", "explainer"), (short, "short_model.joblib", "explainer_short")):
        m = make_pipeline(StandardScaler(), LogisticRegression(max_iter=500)).fit(df[feats], df.Diabetes_binary)
        sc, lr = m[0], m[1]
        meta[ekey] = {"features": feats, "coef": lr.coef_[0].tolist(), "mean": sc.mean_.tolist(),
                      "scale": sc.scale_.tolist(), "intercept": float(lr.intercept_[0])}
        joblib.dump(m, out / fname)
    import sklearn
    meta["sklearn_version"] = sklearn.__version__
    (out / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return out


def markdown_table(results):
    lines = ["| # | Section | Check | Result | Detail |", "|---|---|---|---|---|"]
    for i, r in enumerate(results, 1):
        d = r["detail"].splitlines()[0][:160].replace("|", "\\|") if r["detail"] else ""
        lines.append(f"| {i} | {r['section']} | {r['name']} | **{r['status']}** | {d} |")
    return "\n".join(lines)
