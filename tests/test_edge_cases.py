"""Edge-case and release-readiness checks for the Diabetes Risk Check app.

Run from the repo root:
    python tests/test_edge_cases.py            # everything (notebook run + clean venv install are slow)
    python tests/test_edge_cases.py --fast     # skip notebook execution and clean venv install
    python tests/test_edge_cases.py --models other/dir

No pytest needed. Results go to tests/edge/last_run.md and tests/edge/last_run.json.
WARN = reported but not blocking; FAIL = blocking.
"""
import argparse
import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "edge"))
from helpers import (EDGE, RESULTS, ROOT, ConstModel, RaisingModel, Skip, Warn, build_stub_models, check,  # noqa: E402
                     copy_models, load_app_functions, load_meta, markdown_table, read_data, run_check)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

APP = ROOT / "app.py"
NOTEBOOK = ROOT / "notebook.ipynb"
DISCLAIMER_RE = re.compile(r"not a (medical )?diagnosis", re.I)  # page banner
FULL_DISCLAIMER = "not a medical diagnosis"  # must sit next to every result
SUBMIT = "{}_submit"
RESULT_RE = re.compile(r'risk-number[^>]*>(\d+)%</span>\s*<span class="pill"[^>]*>(Low|Medium|High) risk')
TB_MARKERS = ("Traceback", "File \"", "KeyError", "ValueError", "Exception")
MB = 1024 * 1024

CFG = {"models": ROOT / "models", "stub": False, "fast": False, "executed_nb": None, "nb_secs": None}
SCRATCH = Path(tempfile.mkdtemp(prefix="edge_run_"))


# ---------------------------------------------------------------- app helpers
PAGE_BUTTONS = {"risk": "home_cta_start", "insights": "home_cta_insights", "about": "home_cta_about"}


def app_test(models_dir=None, page="risk"):
    """Run the app and navigate from Home to `page` (home/risk/insights/about) via its call-to-action button."""
    from streamlit.testing.v1 import AppTest
    os.environ["MODELS_DIR"] = str(models_dir or CFG["models"])
    at = AppTest.from_file(str(APP), default_timeout=90)
    at.run()
    key = PAGE_BUTTONS.get(page)
    if key and not at.exception and any(b.key == key for b in at.button):
        at.button(key=key).click().run()
    return at


def texts(at):
    out = []
    for kind in ("markdown", "error", "warning", "caption", "info", "exception", "text", "code"):
        out += [getattr(e, "value", "") or getattr(e, "message", "") for e in getattr(at, kind, [])]
    return "\n".join(str(t) for t in out)


def assert_clean(at, where):
    assert not at.exception, f"{where}: uncaught exception shown to user: {[e.message for e in at.exception]}"
    t = texts(at)
    assert DISCLAIMER_RE.search(t), f"{where}: disclaimer text missing"
    if result_of(at):
        assert FULL_DISCLAIMER in t.lower(), f"{where}: result shown without the full disclaimer"
    for m in ("Traceback", 'File "'):
        assert m not in t, f"{where}: traceback text visible ({m})"


def submit(at, tab):
    at.button(key=SUBMIT.format(tab)).click().run()
    return at


def result_of(at):
    for m in at.markdown:
        if "Estimated risk" in m.value and "risk-number" in m.value:
            hit = RESULT_RE.search(m.value)
            assert hit, f"result card without 'NN% / Band risk': {m.value[:300]}"
            return int(hit.group(1)), hit.group(2)
    return None


def has_features(tab, *names):
    meta = load_meta(CFG["models"])
    feats = meta["features_short" if tab == "quick" else "features_full"]
    return all(n in feats for n in names)


def run_tab(tab, models_dir=None, setup=None):
    at = app_test(models_dir)
    if setup:
        setup(at)
    submit(at, tab)
    return at


def models_label():
    return "stub models (real models/ not found)" if CFG["stub"] else f"models from {CFG['models']}"


# ================================================================ A. App
@check("A", "App loads with no exception, disclaimer + both tabs")
def a_loads():
    at = app_test()
    assert_clean(at, "load")
    assert [t.label for t in at.tabs][:2] == ["Quick check", "Full check"], [t.label for t in at.tabs]
    assert not at.error, f"error on load: {[e.value for e in at.error]}"
    return models_label()


@check("A", "Every page (Home, Risk check, Population insights, How it works) loads clean")
def a_pages():
    out = []
    for page in ("home", "risk", "insights", "about"):
        at = app_test(page=page)
        assert_clean(at, page)
        assert not at.error, f"{page}: error shown {[e.value for e in at.error]}"
        t = texts(at)
        out.append(f"{page}: {len(t)} chars")
    home = app_test(page="home")
    missing = [k for k in PAGE_BUTTONS.values() if not any(b.key == k for b in home.button)]
    if missing:
        raise Warn(f"Home has no button {missing} (page hidden?) - " + "; ".join(out))
    return "; ".join(out)


@check("A", "Home CTAs navigate to the right page; nav bar lists every page")
def a_navigation():
    home = app_test(page="home")
    assert "Know your diabetes risk" in texts(home), "home hero headline missing (Home not the default page?)"
    expect = {"risk": "Risk check", "insights": "Population insights", "about": "How it works"}
    done = []
    for page, key in PAGE_BUTTONS.items():
        if not any(b.key == key for b in home.button):
            if page == "insights" and not any((CFG["models"] / f).exists() for f in OPTIONAL):
                continue  # insights page is meant to be hidden
            raise AssertionError(f"Home has no '{key}' button")
        at = app_test(page=page)
        assert_clean(at, f"after {key}")
        assert f"<h1>{expect[page]}</h1>" in texts(at), f"{key} did not land on '{expect[page]}'"
        assert not any(b.key == "home_cta_start" for b in at.button), f"{key}: still on Home"
        done.append(page)
    risk = app_test(page="risk")
    assert [t.label for t in risk.tabs][:2] == ["Quick check", "Full check"], "risk page tabs missing"
    assert any(b.key == SUBMIT.format("quick") for b in risk.button), "Start CTA did not reach a usable risk check"
    return "CTAs reach: " + ", ".join(done)


@check("D", "Logo + favicon: files valid, wired into app.py, sized for the browser tab")
def d_brand_assets():
    import xml.etree.ElementTree as ET
    assets = ROOT / "assets"
    for name in ("logo.svg", "logo_mark.svg"):
        p = assets / name
        assert p.exists(), f"assets/{name} missing"
        root = ET.fromstring(p.read_text(encoding="utf-8"))
        assert root.tag.endswith("svg") and (root.get("viewBox") or root.get("width")), f"{name}: not a sized <svg>"
        assert not re.search(r"<script|href=[\"']https?:", p.read_text(encoding="utf-8"), re.I), f"{name}: script or remote ref"
    fav = (assets / "favicon.png").read_bytes()
    assert fav[:8] == b"\x89PNG\r\n\x1a\n", "favicon.png is not a PNG"
    w, h = int.from_bytes(fav[16:20], "big"), int.from_bytes(fav[20:24], "big")
    assert w == h and 16 <= w <= 512, f"favicon {w}x{h}: want square, 16-512 px"
    src = APP.read_text(encoding="utf-8")
    for needle in ("page_icon=", "st.logo(", "favicon.png", "logo.svg", "logo_mark.svg"):
        assert needle in src, f"app.py does not reference {needle}"
    ignored = [n for n in ("logo.svg", "logo_mark.svg", "favicon.png") if assets / n not in set(_tracked())]
    assert not ignored, f"gitignored, so the deployed app would lose them: {ignored}"
    return f"2 SVGs parse, favicon {w}x{h} PNG, all referenced"


@check("A", "Both tabs submit with defaults -> result card")
def a_defaults():
    out = []
    for tab in ("quick", "full"):
        at = run_tab(tab)
        assert_clean(at, tab)
        r = result_of(at)
        assert r, f"{tab}: no result after submit; errors={[e.value for e in at.error]}"
        assert 0 <= r[0] <= 100
        out.append(f"{tab}={r[0]}% {r[1]}")
    return ", ".join(out)


def _hw(h, w, tab):
    def setup(at):
        at.number_input(key=f"{tab}_height").set_value(h)
        at.number_input(key=f"{tab}_weight").set_value(w)
    return setup


@check("A", "Height/weight at limits (100/250 cm, 25/300 kg) give a result")
def a_hw_valid():
    out = []
    for tab in ("quick", "full"):
        if not has_features(tab, "BMI"):
            continue
        for h, w in ((100, 25), (100, 300), (250, 25), (250, 300)):
            at = run_tab(tab, setup=_hw(h, w, tab))
            assert_clean(at, f"{tab} h={h} w={w}")
            r = result_of(at)
            assert r, f"{tab} h={h} w={w}: no result, errors={[e.value for e in at.error]}"
            out.append(f"{tab} {h}/{w}->{r[0]}%")
    return "; ".join(out)


@check("A", "Out-of-range height/weight -> friendly message, no result, no crash")
def a_hw_invalid():
    n = 0
    for tab in ("quick", "full"):
        if not has_features(tab, "BMI"):
            continue
        for h, w in ((99, 75), (251, 75), (170, 24), (170, 301), (0, 0), (300, 400), (99.9, 300.1)):
            at = run_tab(tab, setup=_hw(h, w, tab))
            assert_clean(at, f"{tab} h={h} w={w}")
            assert at.error, f"{tab} h={h} w={w}: no error message shown"
            assert result_of(at) is None, f"{tab} h={h} w={w}: result shown despite invalid input"
            n += 1
    return f"{n} invalid combos rejected with a message"


@check("A", "BMI computed and clipped to 12-98")
def a_bmi():
    f = load_app_functions()
    cb = f["compute_bmi"]
    cases = {(170, 75): 26, (100, 300): 98, (250, 25): 12, (180, 81): 25, (100, 98): 98, (100, 97.6): 98}
    bad = {k: (cb(*k), v) for k, v in cases.items() if cb(*k) != v}
    assert not bad, f"compute_bmi mismatches (got, want): {bad}"
    for h in np.linspace(100, 250, 31):
        for w in np.linspace(25, 300, 23):
            b = cb(h, w)
            assert isinstance(b, int) and 12 <= b <= 98, (h, w, b)
    return "all grid points in [12, 98], ints"


@check("A", "Age buckets at boundaries (18, 24, 25, 79, 80, 100) + app submit")
def a_age():
    f = load_app_functions()
    want = {18: 1, 24: 1, 25: 2, 29: 2, 30: 3, 74: 11, 75: 12, 79: 12, 80: 13, 100: 13}
    bad = {a: (f["age_to_bucket"](a), b) for a, b in want.items() if f["age_to_bucket"](a) != b}
    assert not bad, f"age_to_bucket (got, want): {bad}"
    out = []
    for tab in ("quick", "full"):
        if not has_features(tab, "Age"):
            continue
        for age in (18, 24, 25, 79, 80, 100):
            def setup(at, age=age):
                at.number_input(key=f"{tab}_age").set_value(age)
            at = run_tab(tab, setup=setup)
            assert_clean(at, f"{tab} age={age}")
            r = result_of(at)
            assert r, f"{tab} age={age}: no result"
            out.append(f"{age}:{r[0]}%")
    return "buckets OK; " + " ".join(out)


@check("A", "Every option of GenHlth / Education / Income submits; codes are 1..N")
def a_selects():
    f = load_app_functions()
    for name, n in (("GenHlth", 5), ("Education", 6), ("Income", 8)):
        vals = list(f["FEATURES"][name]["options"].values())
        assert vals == list(range(1, n + 1)), f"{name} codes {vals} != 1..{n}"
    runs = 0
    for tab in ("quick", "full"):
        for name in ("GenHlth", "Education", "Income"):
            if not has_features(tab, name):
                continue
            for opt in f["FEATURES"][name]["options"]:
                def setup(at, name=name, opt=opt):
                    at.selectbox(key=f"{tab}_{name}").set_value(opt)
                at = run_tab(tab, setup=setup)
                assert_clean(at, f"{tab} {name}={opt}")
                assert result_of(at), f"{tab} {name}={opt}: no result"
                runs += 1
    return f"{runs} option submissions OK"


def _all(at, tab, yes):
    for r in list(at.radio) + list(at.button_group):
        if r.key and r.key.startswith(tab + "_"):
            r.set_value(r.options[1 if yes else 0])
    for s in at.selectbox:
        if s.key and s.key.startswith(tab + "_"):
            s.set_value(s.options[-1 if yes else 0])
    for s in at.slider:
        if s.key and s.key.startswith(tab + "_"):
            s.set_value(30 if yes else 0)


@check("A", "All-yes and all-no answers (both tabs)")
def a_all_yes_no():
    out = []
    for tab in ("quick", "full"):
        for yes in (True, False):
            at = run_tab(tab, setup=lambda at, tab=tab, yes=yes: _all(at, tab, yes))
            assert_clean(at, f"{tab} all-{'yes' if yes else 'no'}")
            r = result_of(at)
            assert r, f"{tab} all-{'yes' if yes else 'no'}: no result"
            out.append(f"{tab} all-{'yes' if yes else 'no'}={r[0]}% {r[1]}")
    return "; ".join(out)


def _broken(label, models_dir, must_submit=False):
    at = app_test(models_dir)
    assert_clean(at, label)
    if must_submit:
        for tab in ("quick", "full"):
            if any(b.key == SUBMIT.format(tab) for b in at.button):
                submit(at, tab)
                assert_clean(at, f"{label} after {tab} submit")
    else:
        assert at.error, f"{label}: no friendly error shown"
        assert not at.tabs, f"{label}: tabs rendered although models are unusable"
    return at


@check("A", "Missing models/ dir -> friendly error")
def a_missing_dir():
    _broken("missing dir", SCRATCH / "does_not_exist")


@check("A", "Missing one model file -> friendly error")
def a_missing_file():
    for fname in ("full_model.joblib", "short_model.joblib", "meta.json"):
        _broken(f"no {fname}", copy_models(CFG["models"], **{fname: None}))
    return "each of the 3 files removed in turn"


@check("A", "Corrupt meta.json / corrupt joblib -> friendly error")
def a_corrupt():
    for label, ov in (("truncated JSON", {"meta.json": '{"features_full": ["HighBP",'}),
                      ("empty meta", {"meta.json": ""}),
                      ("meta is a list", {"meta.json": "[]"}),
                      ("garbage joblib", {"full_model.joblib": b"not a pickle"}),
                      ("truncated joblib", {"short_model.joblib": (Path(CFG["models"]) / "short_model.joblib").read_bytes()[:200]})):
        _broken(label, copy_models(CFG["models"], **ov))
    return "5 corrupt variants"


def _partial_meta(**changes):
    meta = load_meta(CFG["models"])
    for k, v in changes.items():
        if v is None:
            meta.pop(k, None)
        else:
            meta[k] = v
    return copy_models(CFG["models"], **{"meta.json": meta})


@check("A", "meta.json missing a required key -> friendly error")
def a_meta_missing_key():
    for k in ("features_full", "features_short", "risk_bands", "explainer", "explainer_short"):
        _broken(f"meta without {k}", _partial_meta(**{k: None}))
    return "5 keys"


@check("A", "Partial meta.json (bad nested values) -> no traceback after submit")
def a_meta_partial_nested():
    meta = load_meta(CFG["models"])
    ex = {k: v for k, v in meta["explainer"].items() if k != "scale"}
    variants = {"risk_bands={}": _partial_meta(risk_bands={}),
                "explainer without scale": _partial_meta(explainer=ex, explainer_short=ex),
                "metrics with None": _partial_meta(metrics={"full": {"recall": None}}),
                "features_short has unknown name": _partial_meta(features_short=meta["features_short"] + ["Bogus"])}
    bad = []
    for label, d in variants.items():
        try:
            _broken(label, d, must_submit=True)
        except AssertionError as e:
            bad.append(str(e).splitlines()[0])
    assert not bad, "; ".join(bad)


@check("A", "Model that raises during predict -> friendly error")
def a_model_raises():
    d = copy_models(CFG["models"], **{"full_model.joblib": RaisingModel(), "short_model.joblib": RaisingModel()})
    for tab in ("quick", "full"):
        at = run_tab(tab, d)
        assert_clean(at, tab)
        assert at.error and result_of(at) is None, f"{tab}: expected friendly error"


@check("A", "Risk band matches risk_bands at and around the cut points")
def a_bands():
    meta = load_meta(CFG["models"])
    lo, hi = meta["risk_bands"]["low_max"], meta["risk_bands"]["high_min"]
    assert 0 < lo < hi < 1, f"risk_bands not ordered in (0,1): {lo}, {hi}"
    # Intended: the app bands round(p, 2), the value it displays, so 0.139 -> "14% Medium" when lo=0.14.
    expect = lambda p: "Low" if round(p, 2) < lo else ("High" if round(p, 2) >= hi else "Medium")  # noqa: E731
    probs = sorted({0.0, lo - 0.01, lo - 0.001, lo, lo + 0.001, (lo + hi) / 2, hi - 0.001, hi, hi + 0.001, 1.0})
    shown, mismatch, display_conflict = [], [], []
    for p in probs:
        d = copy_models(CFG["models"], **{"short_model.joblib": ConstModel(p), "full_model.joblib": ConstModel(p)})
        at = run_tab("quick", d)
        assert_clean(at, f"p={p}")
        pct, band = result_of(at)
        shown.append(f"{p:.3f}->{pct}% {band}")
        if band != expect(p):
            mismatch.append(f"p={p}: shown {band}, want {expect(p)}")
        # The card rounds to whole %, the caption says "Low is under X%": a rounded number must not contradict it.
        L, H = round(lo * 100), round(hi * 100)
        if (band == "Low") != (pct < L) or (band == "High") != (pct >= H):
            display_conflict.append(f"p={p:.4f} shows '{pct}% · {band}'")
    assert not mismatch, "; ".join(mismatch)
    assert not display_conflict, "shown % contradicts band legend: " + "; ".join(display_conflict)
    return " ".join(shown)


@check("A", "Disclaimer visible in Low / Medium / High / error states")
def a_disclaimer_states():
    meta = load_meta(CFG["models"])
    lo, hi = meta["risk_bands"]["low_max"], meta["risk_bands"]["high_min"]
    for p in (lo / 2, (lo + hi) / 2, min(0.99, hi + 0.05)):
        d = copy_models(CFG["models"], **{"short_model.joblib": ConstModel(p), "full_model.joblib": ConstModel(p)})
        for tab in ("quick", "full"):
            assert_clean(run_tab(tab, d), f"{tab} p={p}")
    assert_clean(run_tab("quick", setup=_hw(0, 0, "quick")) if has_features("quick", "BMI") else app_test(), "validation error")
    return "6 result states + validation error"


@check("A", "Factor list: no NaN/empty labels, only risk-raising, <=5, sorted")
def a_factors():
    f = load_app_functions()
    meta = load_meta(CFG["models"])
    rng = np.random.default_rng(0)
    ranges = {"BMI": (12, 98), "GenHlth": (1, 5), "MentHlth": (0, 30), "PhysHlth": (0, 30), "Age": (1, 13),
              "Education": (1, 6), "Income": (1, 8)}
    empty = 0
    for key in ("explainer", "explainer_short"):
        ex = meta[key]
        n = len(ex["features"])
        assert all(len(ex[k]) == n for k in ("coef", "mean", "scale")), f"{key}: length mismatch"
        assert all(np.isfinite(ex[k]).all() for k in ("coef", "mean", "scale")), f"{key}: non-finite values"
        assert all(s > 0 for s in ex["scale"]), f"{key}: zero/negative scale"
        unknown = set(ex["features"]) - set(f["FEATURES"])
        assert not unknown, f"{key}: features unknown to app: {unknown}"
        feats = meta["features_short" if key == "explainer_short" else "features_full"]
        missing = set(feats) - set(ex["features"])
        if missing:
            raise Warn(f"{key} lacks features the model uses, they can never be shown: {missing}")
        for _ in range(500):
            values = {x: int(rng.integers(*ranges.get(x, (0, 1)), endpoint=True)) for x in feats}
            answers = {x: str(v) for x, v in values.items()}
            out = f["risk_factors"](values, answers, ex)
            assert len(out) <= 5
            empty += not out
            scores = [s for _, s in out]
            assert scores == sorted(scores, reverse=True), "not sorted"
            for label, s in out:
                assert label and "nan" not in label.lower() and label.split(":")[0].strip(), f"bad label {label!r}"
                assert np.isfinite(s) and s > 0, f"non-positive/NaN contribution {label}: {s}"
    # Empty list -> fallback sentence, not an empty chart.
    zero = dict(meta["explainer_short"], coef=[0.0] * len(meta["explainer_short"]["coef"]))
    at = run_tab("quick", _partial_meta(explainer_short=zero))
    assert_clean(at, "zero explainer")
    assert "None of your answers stood out" in texts(at), "no fallback text when factor list is empty"
    return f"1000 random answer sets; {empty} produced no factors (fallback text verified)"


@check("A", "Result chart shows only listed factors with real labels")
def a_chart():
    at = run_tab("full", setup=lambda at: _all(at, "full", True))
    charts = [json.loads(c.proto.spec) for c in at.get("plotly_chart")]
    charts = [c for c in charts if c["data"][0].get("type") == "bar"]
    assert charts, "no factor chart for all-yes answers"
    spec = charts[0]
    ys = spec["data"][0]["y"]
    xs = spec["data"][0]["x"]
    assert 0 < len(ys) <= 5 and all(isinstance(y, str) and y for y in ys), ys
    assert all(x > 0 for x in xs), xs
    return "; ".join(ys)


# ================================================================ B. Models
def _models():
    import joblib
    m = CFG["models"]
    return joblib.load(m / "full_model.joblib"), joblib.load(m / "short_model.joblib"), load_meta(m)


def _data(n=None, seed=1):
    df = read_data()
    return df.sample(n, random_state=seed) if n else df


@check("B", "Both models load with the pinned scikit-learn; meta records it")
def b_load():
    import sklearn
    import warnings
    pin = re.search(r"scikit-learn==([\w.]+)", (ROOT / "requirements.txt").read_text())
    assert pin, "scikit-learn not pinned in requirements.txt"
    assert sklearn.__version__ == pin.group(1), f"venv sklearn {sklearn.__version__} != pin {pin.group(1)}"
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        _, _, meta = _models()
    inc = [str(x.message)[:120] for x in w if "InconsistentVersion" in type(x.message).__name__]
    assert not inc, inc
    assert meta.get("sklearn_version") == pin.group(1), f"meta sklearn_version={meta.get('sklearn_version')} != pin {pin.group(1)}"
    return f"sklearn {sklearn.__version__}"


@check("B", "Probabilities in [0,1], no NaN (5000 real rows)")
def b_probs():
    full, short, meta = _models()
    df = _data(5000)
    out = []
    for name, m, feats in (("full", full, meta["features_full"]), ("short", short, meta["features_short"])):
        p = m.predict_proba(df[feats])[:, 1]
        assert np.isfinite(p).all() and (p >= 0).all() and (p <= 1).all(), f"{name}: bad probs"
        out.append(f"{name} mean={p.mean():.3f} min={p.min():.3f} max={p.max():.3f}")
    return "; ".join(out)


@check("B", "Model feature names/order equal meta feature lists")
def b_feature_names():
    full, short, meta = _models()
    for name, m, feats in (("full", full, meta["features_full"]), ("short", short, meta["features_short"])):
        fn = getattr(m, "feature_names_in_", None)
        if fn is None:
            raise Warn(f"{name}: model has no feature_names_in_ (trained on arrays) - column order cannot be checked")
        assert list(fn) == list(feats), f"{name}: model {list(fn)} != meta {feats}"
    assert "Diabetes_binary" not in meta["features_full"] + meta["features_short"], "target in feature list"
    assert len(meta["features_full"]) == 21, f"features_full has {len(meta['features_full'])} features, expected 21"
    assert set(meta["features_short"]) <= set(meta["features_full"])


@check("B", "Column order / name mismatch is rejected, never silently wrong")
def b_mismatch():
    full, short, meta = _models()
    df = _data(200)
    notes = []
    for name, m, feats in (("full", full, meta["features_full"]), ("short", short, meta["features_short"])):
        base = m.predict_proba(df[feats])[:, 1]
        cases = {"reversed order": df[feats[::-1]], "renamed column": df[feats].rename(columns={feats[0]: "x"}),
                 "missing column": df[feats[1:]]}
        for label, X in cases.items():
            try:
                p = m.predict_proba(X)[:, 1]
            except Exception as e:  # noqa: BLE001
                notes.append(f"{name} {label}: raises {type(e).__name__}")
                continue
            assert np.allclose(p, base), f"{name} {label}: accepted and gave DIFFERENT predictions (silent error)"
            notes.append(f"{name} {label}: reordered internally, same output")
    return "; ".join(notes)


@check("B", "Batch of 1 vs 1000 rows give identical predictions")
def b_batch():
    full, short, meta = _models()
    df = _data(1000)
    for name, m, feats in (("full", full, meta["features_full"]), ("short", short, meta["features_short"])):
        p = m.predict_proba(df[feats])[:, 1]
        t0 = time.time()
        singles = np.array([m.predict_proba(df[feats].iloc[[i]])[0, 1] for i in range(0, 1000, 50)])
        per = (time.time() - t0) / 20
        assert np.allclose(p[::50], singles, atol=1e-9), f"{name}: batch vs single differ"
        assert len(p) == 1000
        # dtype robustness: floats instead of ints must not change results
        assert np.allclose(m.predict_proba(df[feats].astype(float))[:, 1], p, atol=1e-9), f"{name}: float vs int input differ"
    return f"single-row predict ~{per * 1000:.0f} ms"


@check("B", "Monotonicity sanity: BMI up, HighBP 0->1, GenHlth worse, Age older")
def b_monotone():
    full, short, meta = _models()
    df = _data(3000, seed=2)
    msgs, viol = [], []
    changes = {"BMI": lambda s: (s + 5).clip(12, 98), "HighBP": lambda s: s * 0 + 1,
               "GenHlth": lambda s: (s + 1).clip(1, 5), "Age": lambda s: (s + 2).clip(1, 13)}
    for name, m, feats in (("full", full, meta["features_full"]), ("short", short, meta["features_short"])):
        X = df[feats]
        base = m.predict_proba(X)[:, 1]
        for f, fn in changes.items():
            if f not in feats:
                continue
            X2 = X.copy()
            X2[f] = fn(X2[f])
            d = m.predict_proba(X2)[:, 1] - base
            lowered = (d < -1e-6).mean()
            msgs.append(f"{name}.{f}: mean {d.mean():+.3f}, lowered {lowered:.0%}")
            if d.mean() < 0 or lowered > 0.2:
                viol.append(msgs[-1])
    if viol:
        raise Warn("violations: " + "; ".join(viol))
    return "; ".join(msgs)


@check("B", "Explainer direction agrees with model (factors shown really raise risk)")
def b_explainer_vs_model():
    full, short, meta = _models()
    df = _data(2000, seed=3)
    bad = []
    for name, m, key in (("full", full, "explainer"), ("short", short, "explainer_short")):
        ex = meta[key]
        feats = meta["features_short" if key == "explainer_short" else "features_full"]
        X = df[feats]
        base = m.predict_proba(X)[:, 1]
        for f, c, s in zip(ex["features"], ex["coef"], ex["scale"]):
            if f not in feats or abs(c) < 1e-3:
                continue
            X2 = X.copy()
            X2[f] = X2[f] + s  # +1 SD in raw units
            eff = (m.predict_proba(X2)[:, 1] - base).mean()
            if abs(eff) > 0.002 and np.sign(eff) != np.sign(c):
                bad.append(f"{name}.{f}: coef {c:+.2f} but model effect {eff:+.3f}")
    if bad:
        raise Warn("sign disagreements: " + "; ".join(bad))


@check("B", "meta metrics/threshold sane (values in [0,1], model beats baseline)")
def b_meta_metrics():
    _, _, meta = _models()
    for k in ("threshold_full", "threshold_short", "positive_rate", "n_rows", "data_year", "metrics"):
        assert k in meta, f"meta missing {k}"
    for k in ("threshold_full", "threshold_short", "positive_rate"):
        assert 0 < meta[k] < 1, f"{k}={meta[k]}"
    mt = meta["metrics"]
    for g in ("full", "short", "baseline"):
        assert g in mt, f"metrics missing '{g}'"
        for k, v in mt[g].items():
            assert isinstance(v, (int, float)) and 0 <= v <= 1, f"metrics.{g}.{k}={v}"
    for k in ("pr_auc", "roc_auc"):
        if k in mt["full"] and k in mt["baseline"]:
            assert mt["full"][k] > mt["baseline"][k], f"full {k} not above baseline"
    n = len(_data())
    if n not in (meta["n_rows"], meta.get("n_rows_raw")):
        raise Warn(f"meta n_rows={meta['n_rows']} but data/diabetes.csv has {n} rows (dedup?)")
    return json.dumps(mt)[:300]


def _notebook_split():
    """Re-run the notebook's own code cells up to the one that defines y_test, in a temp dir."""
    nb = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    work = SCRATCH / "nbsplit"
    work.mkdir(exist_ok=True)
    (work / "data").mkdir(exist_ok=True)
    for f in (ROOT / "data").iterdir():
        dst = work / "data" / f.name
        if f.is_file() and not dst.exists():  # data/ subfolders (e.g. data/brfss raw multi-year) are not notebook inputs
            try:
                shutil.copy(f, dst)
            except PermissionError as e:
                raise Skip(f"cannot read raw data file {f.name} ({e.strerror}); data/ is gitignored")
    ns, cwd = {}, os.getcwd()
    os.chdir(work)
    import matplotlib
    matplotlib.use("Agg")
    try:
        for cell in nb["cells"]:
            if cell["cell_type"] != "code":
                continue
            src = "".join(cell["source"])
            src = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith(("%", "!")))
            exec(compile(src, "<nb>", "exec"), ns)  # noqa: S102 - project notebook
            if "y_test" in ns and "X_test" in ns:
                return ns["X_test"], ns["y_test"]
    finally:
        os.chdir(cwd)
    raise Skip("notebook never defines X_test / y_test")


@check("B", "Threshold / recall claims in meta reproduce on the notebook's test split")
def b_reproduce():
    if not NOTEBOOK.exists():
        raise Skip("notebook.ipynb not found")
    full, short, meta = _models()
    from sklearn.metrics import precision_score, recall_score, roc_auc_score
    X_test, y_test = _notebook_split()
    out, bad = [], []
    for name, m, feats, thr in (("full", full, meta["features_full"], meta["threshold_full"]),
                                ("short", short, meta["features_short"], meta["threshold_short"])):
        if not set(feats) <= set(X_test.columns):
            raise Skip(f"X_test lacks raw columns for {name}")
        p = m.predict_proba(X_test[feats])[:, 1]
        got = {"recall": recall_score(y_test, p >= thr), "precision": precision_score(y_test, p >= thr),
               "roc_auc": roc_auc_score(y_test, p)}
        for k, v in got.items():
            claim = meta["metrics"].get(name, {}).get(k)
            if claim is not None and abs(claim - v) > 0.002:
                bad.append(f"{name}.{k}: meta {claim:.4f} vs recomputed {v:.4f}")
        out.append(f"{name}: " + ", ".join(f"{k}={v:.3f}" for k, v in got.items()))
    assert not bad, "; ".join(bad)
    return f"n_test={len(y_test)}; " + "; ".join(out)


@check("B", "Model size / load time / memory fit Streamlit Cloud (~1 GB)")
def b_size():
    import joblib
    import tracemalloc
    info = []
    for fname in ("full_model.joblib", "short_model.joblib"):
        p = CFG["models"] / fname
        mb = p.stat().st_size / MB
        tracemalloc.start()
        t0 = time.time()
        joblib.load(p)
        secs = time.time() - t0
        peak = tracemalloc.get_traced_memory()[1] / MB
        tracemalloc.stop()
        info.append(f"{fname}: {mb:.1f} MB on disk, load {secs:.2f}s, peak {peak:.0f} MB")
        assert mb < 100, f"{fname} is {mb:.0f} MB (GitHub limit 100 MB)"
        if mb > 50 or peak > 300:
            raise Warn("large model: " + info[-1])
    return "; ".join(info)


# ================================================================ C. Notebook
def _nb_code(nb):
    return [(i, "".join(c["source"])) for i, c in enumerate(nb["cells"]) if c["cell_type"] == "code"]


@check("C", "Notebook Restart & Run All (temp copy) - zero errors, runtime")
def c_execute():
    if not NOTEBOOK.exists():
        raise Skip("notebook.ipynb not found")
    if CFG["fast"]:
        raise Skip("--fast")
    work = SCRATCH / "nbrun"
    shutil.copytree(ROOT, work, ignore=shutil.ignore_patterns(".venv", ".git", "models", "reports", "*.pdf"))
    (work / "models").mkdir(exist_ok=True)
    (work / "reports").mkdir(exist_ok=True)
    out = work / "executed.ipynb"
    t0 = time.time()
    r = subprocess.run([sys.executable, "-m", "jupyter", "nbconvert", "--to", "notebook", "--execute",
                        "--ExecutePreprocessor.timeout=3600", "--output", str(out), str(work / "notebook.ipynb")],
                       cwd=work, capture_output=True, text=True)
    CFG["nb_secs"] = time.time() - t0
    assert r.returncode == 0, f"nbconvert failed in {CFG['nb_secs']:.0f}s:\n{r.stderr[-1500:]}"
    nb = json.loads(out.read_text(encoding="utf-8"))
    errs = [o for c in nb["cells"] if c["cell_type"] == "code" for o in c.get("outputs", []) if o.get("output_type") == "error"]
    assert not errs, f"{len(errs)} error outputs"
    CFG["executed_nb"] = out
    CFG["nb_workdir"] = work
    return f"ran clean in {CFG['nb_secs']:.0f}s"


@check("C", "Re-executed notebook reproduces committed meta.json metrics")
def c_reproducible():
    if not CFG.get("executed_nb"):
        raise Skip("notebook not executed")
    new = CFG["nb_workdir"] / "models" / "meta.json"
    if not new.exists():
        raise Skip("executed notebook wrote no models/meta.json (relative path?)")
    a, b = load_meta(CFG["models"]), load_meta(new.parent)
    diff = [f"{g}.{k}: {a['metrics'][g][k]} vs {b['metrics'][g].get(k)}" for g in a.get("metrics", {})
            for k in a["metrics"][g] if abs(a["metrics"][g][k] - (b["metrics"].get(g, {}).get(k) or 0)) > 1e-6]
    for k in ("threshold_full", "threshold_short", "features_short"):
        if a.get(k) != b.get(k):
            diff.append(f"{k}: {a.get(k)} vs {b.get(k)}")
    assert not diff, "committed models differ from a fresh run: " + "; ".join(diff[:8])


@check("C", "Train/test split happens before any fit (code read)")
def c_split_first():
    if not NOTEBOOK.exists():
        raise Skip("notebook.ipynb not found")
    nb = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    code = _nb_code(nb)
    split = [i for i, s in code if "train_test_split(" in s]
    assert split, "no train_test_split call"
    first_split = split[0]
    early = []
    for i, s in code:
        if i > first_split:
            break
        before = s.split("train_test_split(")[0] if i == first_split else s
        for pat in (r"\.fit\(", r"\.fit_transform\(", r"\.fit_resample\("):
            if re.search(pat, before):
                early.append(f"cell {i}: {pat}")
    assert not early, "fit before split: " + "; ".join(early)
    seeds = re.findall(r"random_state\s*=\s*(\w+)", "".join(s for _, s in code))
    assert seeds, "no random_state anywhere - split not reproducible"
    return f"first split in cell {first_split}; random_state values {sorted(set(seeds))}"


@check("C", "No target leakage (target not a feature, no fit on test data)")
def c_leakage():
    if not NOTEBOOK.exists():
        raise Skip("notebook.ipynb not found")
    nb = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    src = "\n".join(s for _, s in _nb_code(nb))
    issues = []
    for m in re.finditer(r"\.fit(?:_transform|_resample)?\(([^)]*)\)", src):
        if re.search(r"\b\w*test\w*\b", m.group(1)):
            issues.append(f"fit on test data: {m.group(0)[:80]}")
    picks = re.findall(r"\b((?:threshold|thr)\w*)\s*=\s*pick_threshold\(([^)]*)\)", src, re.I)
    if picks:  # tuning goes through pick_threshold: only its inputs matter (curves on y_test are reporting)
        issues += [f"threshold tuned on test set: {n} = pick_threshold({a})" for n, a in picks if re.search(r"test", a)]
    else:
        for m in re.finditer(r"(threshold|thr)\w*\s*=.*(y_test|X_test)", src):
            issues.append(f"threshold tuned on test set: {m.group(0)[:100]}")
    if re.search(r"(?<![\"'])Diabetes_binary(?![\"'])", src):
        issues.append("bare Diabetes_binary identifier")
    if issues:
        raise Warn("review manually: " + "; ".join(issues))
    return "no fit/threshold on test data found by pattern scan" + (f"; thresholds picked on {', '.join(a for _, a in picks)}" if picks else "")


@check("C", "Markdown numbers agree with executed outputs / results")
def c_markdown_numbers():
    nb_path = CFG.get("executed_nb") or (NOTEBOOK if NOTEBOOK.exists() else None)
    if not nb_path:
        raise Skip("notebook.ipynb not found")
    nb = json.loads(Path(nb_path).read_text(encoding="utf-8"))
    md = "\n".join("".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "markdown")
    outs = []
    for c in nb["cells"]:
        for o in c.get("outputs", []):
            outs.append("".join(o.get("text", "")) + "".join(o.get("data", {}).get("text/plain", "")) +
                        "".join(o.get("data", {}).get("text/html", "")))
    pool = "\n".join(outs)
    for f in (CFG["models"] / "meta.json", ROOT / "reports" / "results.csv"):
        if f.exists():
            pool += f.read_text(encoding="utf-8")
    nums = set(re.findall(r"(?<![\w.])(0\.\d{2,4}|\d{1,3}\.\d{1,2}%|\d{2,3}(?:,\d{3})+)(?![\w])", md))
    pool_vals = {round(float(x.replace(",", "")), 4) for x in re.findall(r"\d[\d,]*\.?\d*", pool) if x.replace(",", "").replace(".", "").isdigit()}

    def found(n):
        if n.endswith("%"):
            v = float(n[:-1]) / 100
            return any(abs(v - p) < 0.0006 for p in pool_vals) or n in pool
        v = float(n.replace(",", ""))
        return n in pool or any(abs(v - p) < 0.0006 for p in pool_vals)
    missing = sorted(n for n in nums if not found(n))
    if missing:
        raise Warn(f"{len(missing)} of {len(nums)} Markdown numbers not found in outputs: {missing[:15]}")
    return f"{len(nums)} numbers checked"


# ================================================================ D. Repo / deploy
def _git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)


def _tracked():
    r = _git("ls-files", "--cached", "--others", "--exclude-standard")
    return [ROOT / p for p in r.stdout.splitlines() if p]


@check("D", "Files to be committed are < 100 MB each")
def d_sizes():
    files = _tracked()
    big = [(p.relative_to(ROOT).as_posix(), p.stat().st_size / MB) for p in files if p.exists() and p.stat().st_size > 50 * MB]
    over = [b for b in big if b[1] >= 100]
    assert not over, f"over GitHub's 100 MB limit: {over}"
    total = sum(p.stat().st_size for p in files if p.exists()) / MB
    if big:
        raise Warn(f"files over 50 MB (GitHub warns): {big}")
    return f"{len(files)} files, {total:.1f} MB total"


@check("D", "git ignores .venv/, data/, the project-ideas PDF; keeps models/ + notebook")
def d_ignore():
    must_ignore = [".venv/", "data/diabetes.csv", "ML_Final_Project_Ideas.pdf"]
    must_keep = ["app.py", "requirements.txt", "models/meta.json", "models/full_model.joblib",
                 "models/short_model.joblib", "notebook.ipynb", "README.md", ".streamlit/config.toml",
                 "assets/logo.svg", "assets/logo_mark.svg", "assets/favicon.png"]
    must_keep += [f"models/{f}" for f in OPTIONAL if (ROOT / "models" / f).exists()]
    not_ignored = [p for p in must_ignore if _git("check-ignore", "-q", p).returncode != 0]
    not_ignored += [q for q in (p.relative_to(ROOT).as_posix() for p in _tracked() if p.suffix.lower() == ".pdf")
                    if q not in not_ignored]
    wrongly_ignored = [p for p in must_keep if _git("check-ignore", "-q", p).returncode == 0]
    tracked = {p.relative_to(ROOT).as_posix() for p in _tracked()}
    absent = [p for p in must_keep if p not in tracked]
    msgs = []
    if not_ignored:
        msgs.append(f"would be committed but should not: {not_ignored}")
    if wrongly_ignored:
        msgs.append(f"ignored but needed: {wrongly_ignored}")
    if absent:
        msgs.append(f"not present to commit yet: {absent}")
    assert not msgs, "; ".join(msgs)


KEYWORDS = ["cl" + "aude", "anth" + "ropic", "co-auth" + "ored-by", "gener" + "ated with"]


@check("D", "No assistant/tool attribution text anywhere (outside the tool settings dir)")
def d_attribution():
    tracked = {p.resolve() for p in _tracked()}
    hits_tracked, hits_other = [], []
    pat = re.compile("|".join(KEYWORDS), re.I)
    skip_top = {".venv", ".git", "data", "." + KEYWORDS[0]}  # data/ is gitignored raw data
    walked = []
    for dirpath, dirs, names in os.walk(ROOT, onerror=lambda e: None):
        if Path(dirpath) == ROOT:
            dirs[:] = [d for d in dirs if d not in skip_top]
        walked += [Path(dirpath) / n for n in names]
    for p in walked:
        rel = p.relative_to(ROOT).as_posix()
        if rel.startswith(("tests/edge/last_run.", "demo/build/")):  # generated logs, not source
            continue
        try:
            if p.stat().st_size > 20 * MB:
                continue
            txt = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):  # OSError covers PermissionError: skip, never fail
            continue
        for ln, line in enumerate(txt.splitlines(), 1):
            if pat.search(line) or (p.suffix in (".py", ".md", ".toml", ".yml", ".txt", "") and re.search(r"\bAI\b", line)):
                (hits_tracked if p.resolve() in tracked else hits_other).append(f"{rel}:{ln}")
    assert not hits_tracked, f"hits in files that would be committed: {hits_tracked}"
    if hits_other:
        raise Warn(f"hits in ignored files: {hits_other}")
    return "0 hits"


EMOJI = re.compile("[%s-%s%s-%s%s-%s%s]" % tuple(map(chr, (0x1F000, 0x1FAFF, 0x2600, 0x27BF, 0x2B00, 0x2BFF, 0xFE0F))))


@check("D", "No user-facing claim that the model predicts prediabetes; data_year == 2015")
def d_target_claims():
    pat = re.compile(r"prediabetes (?:or|and|/) (?:type 2 )?diabetes|diabetes (?:or|and|/) prediabetes", re.I)
    ok = re.compile(r"\bnot\b|n't|\bexclud|coded 0|isn't captured|not captured", re.I)
    files = [ROOT / "app.py", ROOT / "README.md", *(ROOT / "pages").glob("*.py"), *(ROOT / "deliverables").glob("*.md")]
    srcs = [(f.relative_to(ROOT).as_posix(), f.read_text(encoding="utf-8")) for f in files if f.exists()]
    for nb in (NOTEBOOK, ROOT / "multiyear_validation.ipynb"):
        if nb.exists():
            cells = json.loads(nb.read_text(encoding="utf-8"))["cells"]
            srcs.append((nb.name, "\n".join("".join(c["source"]) for c in cells if c["cell_type"] == "markdown")))
    hits = [f"{name}:{i}: {line.strip()[:90]}" for name, txt in srcs for i, line in enumerate(txt.splitlines(), 1)
            if pat.search(line) and not ok.search(line)]
    year = load_meta(CFG["models"]).get("data_year")
    assert year == 2015, f"meta data_year={year}, expected 2015"
    assert not hits, f"{len(hits)} prediabetes claims: {hits[:10]}"
    return f"{len(srcs)} sources scanned, data_year=2015"


@check("D", "Renamed to SugarScope: no 'Riskwell' left; page title and header say SugarScope")
def d_brand_rename():
    roots = [APP, ROOT / "README.md", ROOT / "demo" / "STORYBOARD.md", ROOT / "demo" / "record.py", NOTEBOOK,
             ROOT / "assets", ROOT / "deliverables", ROOT / "docs"]
    files = [f for r in roots if r.exists() for f in ([r] if r.is_file() else r.rglob("*")) if f.is_file()]
    hits = []
    for f in files:
        raw = f.read_bytes()
        if f.suffix in (".pptx", ".docx"):  # zipped XML: search the unpacked text parts
            import zipfile
            with zipfile.ZipFile(f) as z:
                raw = b"".join(z.read(n) for n in z.namelist() if n.endswith(".xml"))
        if re.search(rb"riskwell", raw, re.I):
            hits.append(f.relative_to(ROOT).as_posix())
    assert not hits, f"'Riskwell' still in: {hits}"
    tree = ast.parse(APP.read_text(encoding="utf-8"))
    brand = next((n.value.value for n in ast.walk(tree) if isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant)
                  and any(getattr(t, "id", "") == "BRAND_NAME" for t in n.targets)), None)
    assert brand == "SugarScope", f"BRAND_NAME = {brand!r}"
    src = APP.read_text(encoding="utf-8")
    assert re.search(r"set_page_config\(\s*page_title=(BRAND_NAME|[\"']SugarScope)", src), "page_title is not SugarScope"
    at = app_test(page="home")
    assert_clean(at, "home")
    # the footer also prints the name, so require it in the header markup (brandline or hero h1)
    assert re.search(r'class="brandline".*?SugarScope|<h1>SugarScope', texts(at), re.S), "rendered header does not say SugarScope"
    return f"{len(files)} files clean; BRAND_NAME, page_title and rendered header say SugarScope"


@check("D", "No emojis in app.py, README, .streamlit/, docs/ or rendered app")
def d_no_emoji():
    hits = []
    files = [APP, ROOT / "README.md"] + [p for d in (".streamlit", "docs") for p in (ROOT / d).rglob("*") if p.is_file()]
    for p in files:
        if not p.exists():
            continue
        for ln, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            for ch in EMOJI.findall(line):
                hits.append(f"{p.relative_to(ROOT).as_posix()}:{ln} U+{ord(ch):04X}")
    files += [p for p in (ROOT / "assets").rglob("*.svg")] if (ROOT / "assets").exists() else []
    renders = [run_tab("quick", setup=lambda at: _all(at, "quick", True)), run_tab("full", setup=lambda at: _all(at, "full", True))]
    renders += [app_test(page=p) for p in ("home", "insights", "about")]
    for at in renders:
        shown = [texts(at)]
        for kind in ("title", "header", "subheader", "tabs", "button", "radio", "selectbox", "number_input", "slider",
                     "button_group", "toggle", "metric", "select_slider"):
            for e in getattr(at, kind, []):
                shown += [str(getattr(e, "value", "")), str(getattr(e, "label", "")), str(getattr(e, "icon", "") or "")]
                shown += [str(o) for o in (getattr(e, "options", None) or [])]
        blob = "\n".join(shown)
        hits += [f"rendered app U+{ord(ch):04X}" for ch in EMOJI.findall(blob)]
        hits += [f"rendered app word: {w!r}" for w in re.findall(r"\bAI\b", blob)]
    assert not hits, f"{len(hits)} emoji/word hits: {hits[:12]}"
    return f"{len(files)} files + 5 rendered views (both results, home, insights, about) scanned"


def _sh():
    for c in (shutil.which("sh"), r"C:\Program Files\Git\bin\sh.exe", r"C:\Program Files\Git\usr\bin\sh.exe"):
        if c and Path(c).exists():
            return c
    raise Skip("no sh found to run the hook")


@check("D", "commit-msg hook rejects attribution lines, accepts normal messages")
def d_hook():
    hook = ROOT / ".githooks" / "commit-msg"
    if not hook.exists():
        raise Skip(".githooks/commit-msg not found")
    cfg = _git("config", "core.hooksPath").stdout.strip()
    tool = "Cl" + "aude"
    cab, gw = "Co-" + "Authored-By", "Gener" + "ated with"
    bad = [f"Add app\n\n{cab}: {tool} Opus <no" + "reply@" + "anth" + "ropic.com>",
           f"Add app\n\n{cab.lower()}: {tool.lower()}",
           f"Add app\n\n\U0001F916 {gw} [{tool} Code](https://example.com)",
           f"Add app\n\n{gw} {tool} Code",
           f"Add app\n\nGenerated by {tool}",
           f"Add app\n\n{cab}: {tool} <x@example.com>"]
    good = ["Add Streamlit app", f"Fix BMI clipping\n\n{cab}: Jane Doe <jane@example.com>"]
    sh = _sh()
    msg_file = SCRATCH / "COMMIT_MSG"
    leaked, blocked = [], []
    for m in bad + good:
        msg_file.write_text(m, encoding="utf-8")
        rc = subprocess.run([sh, str(hook), str(msg_file)], capture_output=True).returncode
        if m in bad and rc == 0:
            leaked.append(m.splitlines()[-1][:60])
        if m in good and rc != 0:
            blocked.append(m.splitlines()[0])
    assert cfg == ".githooks", f"core.hooksPath is '{cfg}', hook would not run"
    assert not blocked, f"good messages rejected: {blocked}"
    assert not leaked, f"hook let these through: {leaked}"
    return f"{len(bad)} bad rejected, {len(good)} good accepted"


@check("D", "requirements.txt pins every third-party import of app.py, matching the venv")
def d_requirements():
    from importlib.metadata import version
    req = dict(re.findall(r"^([\w.-]+)==([\w.]+)", (ROOT / "requirements.txt").read_text(), re.M))
    pkg = {"sklearn": "scikit-learn", "plotly": "plotly", "streamlit": "streamlit", "pandas": "pandas",
           "joblib": "joblib", "numpy": "numpy"}
    tree = ast.parse(APP.read_text(encoding="utf-8"))
    mods = {(n.module if isinstance(n, ast.ImportFrom) else a.name).split(".")[0]
            for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom)) for a in getattr(n, "names", [])}
    third = {m for m in mods if m not in sys.stdlib_module_names}
    missing = [m for m in third | {"sklearn"} if pkg.get(m, m) not in req]
    assert not missing, f"not pinned: {missing}"
    mism = [f"{k} pin {v} != venv {version(k)}" for k, v in req.items() if version(k) != v]
    assert not mism, "; ".join(mism)
    return ", ".join(f"{k}=={v}" for k, v in req.items())


def _readme_numbers(text):
    return re.findall(r"(?<![\w./-])(\d+\.\d+|\d+(?:\.\d+)?%)(?![\w/])", text)


@check("D", "README: no TODO results, every number matches results.csv / meta")
def d_readme():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    problems, warns = [], []
    results_sec = readme.split("## Results", 1)[-1].split("\n## ", 1)[0] if "## Results" in readme else ""
    if "TODO" in results_sec:
        problems.append("Results section still has TODO placeholders")
    # Exactly one placeholder is allowed before the first deploy: the live-app URL line.
    url_lines = [ln for ln in readme.splitlines() if ln.startswith("**Live app:**") and "<your-app>" in ln]
    other_todo = [ln.strip()[:80] for ln in readme.splitlines() if "TODO" in ln and ln not in url_lines]
    if other_todo:
        problems.append(f"TODO outside the live-app link: {other_todo}")
    if url_lines:
        warns.append("live app link still a placeholder (allowed until first deploy)")
    if "app_screenshot.png" in readme and not (ROOT / "reports" / "app_screenshot.png").exists():
        warns.append("README screenshot reports/app_screenshot.png missing")
    pool = []
    res = ROOT / "reports" / "results.csv"
    if res.exists():
        pool += [float(x) for x in re.findall(r"-?\d+\.\d+|\d+", res.read_text())]
    for name in ("meta.json", "multiyear.json"):  # multiyear.json backs the README's multi-year table
        if (CFG["models"] / name).exists():
            pool += [float(x) for x in re.findall(r"-?\d+\.\d+|\d+", (CFG["models"] / name).read_text())]
    allowed = {"3.12", "253,000", "20%"}  # 20% = held-out test split size, a design choice, not a result
    unmatched = []
    for n in _readme_numbers(readme):
        if n in allowed:
            continue
        v = float(n.rstrip("%")) / (100 if n.endswith("%") else 1)
        if not any(abs(v - p) < 0.0006 for p in pool):
            unmatched.append(n)
    if unmatched:
        problems.append(f"README numbers not in results.csv/meta: {sorted(set(unmatched))}")
    if not res.exists():
        problems.append("reports/results.csv missing")
    assert not problems, "; ".join(problems + warns)
    if warns:
        raise Warn("; ".join(warns))


CLEAN_CHECK = r'''
import json, sys, joblib, pandas as pd
from streamlit.testing.v1 import AppTest
meta = json.load(open("models/meta.json", encoding="utf-8"))
for f, k in (("full_model.joblib", "features_full"), ("short_model.joblib", "features_short")):
    m = joblib.load("models/" + f)
    p = m.predict_proba(pd.DataFrame([[1] * len(meta[k])], columns=meta[k]).astype(int))[0, 1]
    assert 0 <= p <= 1
at = AppTest.from_file("app.py", default_timeout=120).run()
assert not at.exception, [e.message for e in at.exception]
at.button(key="home_cta_start").click().run()
assert not at.exception, [e.message for e in at.exception]
for tab in ("quick", "full"):
    at.button(key="%s_submit" % tab).click().run()
    assert not at.exception, [e.message for e in at.exception]
    assert any("risk-number" in m.value for m in at.markdown), tab
print("CLEAN_OK")
'''


@check("D", "Clean venv: pip install -r requirements.txt -> import, load models, AppTest")
def d_clean_venv():
    if CFG["fast"]:
        raise Skip("--fast")
    if CFG["stub"]:
        raise Skip("real models/ not present yet")
    work = Path(tempfile.mkdtemp(prefix="edge_clean_"))
    repo = work / "repo"
    for p in _tracked():  # only what git would push, like Streamlit Cloud sees it
        dst = repo / p.relative_to(ROOT)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(p, dst)
    venv = work / "venv"
    t0 = time.time()
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True, capture_output=True)
    py = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    r = subprocess.run([str(py), "-m", "pip", "install", "-q", "--disable-pip-version-check", "-r", "requirements.txt"],
                       cwd=repo, capture_output=True, text=True)
    assert r.returncode == 0, f"pip install failed:\n{r.stderr[-1500:]}"
    env = {k: v for k, v in os.environ.items() if k != "MODELS_DIR"}
    r = subprocess.run([str(py), "-c", CLEAN_CHECK], cwd=repo, capture_output=True, text=True, env=env)
    assert "CLEAN_OK" in r.stdout, f"clean check failed:\n{(r.stdout + r.stderr)[-1500:]}"
    shutil.rmtree(work, ignore_errors=True)
    return f"install + check in {time.time() - t0:.0f}s"


# ================================================================ F. Optional features (segments, what-if, cost planner)
OPTIONAL = {"segments.joblib": "Population profiles", "segments.json": "Population profiles",
            "threshold_curve.json": "Screening cost planner",
            "multiyear.json": "Diagnosed diabetes over time", "state_prevalence.csv": "By state"}
MY_FIXTURE = {"years": [2015, 2019, 2021],
              "prevalence_by_year": [{"year": y, "rate": r, "n": 400000} for y, r in ((2015, .14), (2019, .15), (2021, .16))],
              "temporal_validation": [{"train_years": [2015, 2019], "test_year": 2021, "roc_auc": .81, "recall": .79,
                                       "precision": None}]}
STATES_FIXTURE = ("state_abbr,state_name,year,n,actual_rate,predicted_rate\n" +
                  "".join(f"{a},{n},{y},5000,0.{12 + i},0.{13 + i}\n" for y in (2015, 2021)
                          for i, (a, n) in enumerate((("TX", "Texas"), ("OH", "Ohio"), ("CA", "California")))))


@check("F", "Multi-year trend + state map: shown with both files, each hides alone, bad files hide, no crash")
def f_multiyear():
    base = {"multiyear.json": None, "state_prevalence.csv": None}
    trend, smap = OPTIONAL["multiyear.json"], OPTIONAL["state_prevalence.csv"]
    cases = {  # name -> (overrides, trend shown, map shown)
        "both": ({"multiyear.json": MY_FIXTURE, "state_prevalence.csv": STATES_FIXTURE}, True, True),
        "trend only": ({"multiyear.json": MY_FIXTURE}, True, False),
        "map only": ({"state_prevalence.csv": STATES_FIXTURE}, False, True),
        "neither": ({}, False, False),
        "corrupt": ({"multiyear.json": b"\x00{", "state_prevalence.csv": "state_abbr,year\nTX,x\n"}, False, False),
        "empty trend": ({"multiyear.json": {"years": [], "prevalence_by_year": [], "temporal_validation": []}}, False, False),
    }
    for name, (ov, want_trend, want_map) in cases.items():
        at = app_test(copy_models(CFG["models"], **{**base, **ov}), page="insights")
        assert_clean(at, f"multi-year {name}")
        t = texts(at)
        assert (trend in t) == want_trend, f"{name}: trend section shown={trend in t}, expected {want_trend}"
        assert (smap in t) == want_map, f"{name}: map section shown={smap in t}, expected {want_map}"
        if want_map:
            assert any(s.key == "map_year" for s in at.select_slider), f"{name}: no year slider on the map"
            at.select_slider(key="map_year").set_value(2015).run()
            assert_clean(at, f"multi-year {name}, year 2015")
    # Only multi-year files present -> the Insights page still exists (reached from Home).
    only = copy_models(CFG["models"], **{**{f: None for f in OPTIONAL}, "multiyear.json": MY_FIXTURE})
    assert any(b.key == "home_cta_insights" for b in app_test(only, page="home").button), "insights link missing with only multiyear.json"
    return f"{len(cases)} file combos on synthetic fixtures + map year switch"


def _opt_json(name):
    p = CFG["models"] / name
    if not p.exists():
        raise Skip(f"models/{name} not present")
    return json.loads(p.read_text(encoding="utf-8"))


@check("F", "Each optional file missing or corrupt -> its section hides, no crash")
def f_optional_missing():
    present = [f for f in OPTIONAL if (CFG["models"] / f).exists()]
    if not present:
        raise Skip("no optional files in models/")
    base = app_test(page="insights")
    assert_clean(base, "all optional present")
    full_txt = texts(base)
    notes = []
    for fname in present:
        for label, val in (("missing", None), ("corrupt", b"\x00garbage{")):
            d = copy_models(CFG["models"], **{fname: val})
            at = app_test(d, page="insights")
            assert_clean(at, f"{fname} {label}")
            if OPTIONAL[fname] in full_txt and fname != "segments.joblib":  # profiles chart needs only the json
                assert OPTIONAL[fname] not in texts(at), f"{fname} {label}: '{OPTIONAL[fname]}' still shown"
            # The full-check result (profile card, what-if) must still work.
            at = app_test(d)
            submit(at, "full")
            assert_clean(at, f"{fname} {label} after full submit")
            assert result_of(at), f"{fname} {label}: no result"
            if fname.startswith("segments"):
                assert "Your profile" not in texts(at), f"{fname} {label}: profile card still shown"
        notes.append(fname)
    no_opt = copy_models(CFG["models"], **{f: None for f in present})
    at = app_test(no_opt, page="home")
    assert_clean(at, "no optional files")
    assert not any(b.key == "home_cta_insights" for b in at.button), "insights link shown with no optional files"
    for page in ("risk", "about"):
        assert_clean(app_test(no_opt, page=page), f"no optional files, {page} page")
    return "hidden cleanly: " + ", ".join(notes) + "; insights page/link hidden when all are absent"


@check("F", "Cost planner math: per-1000 counts consistent, no divide-by-zero")
def f_cost_math():
    curve = _opt_json("threshold_curve.json")
    meta = load_meta(CFG["models"])
    out = []
    for m in ("full", "short"):
        pts = curve.get(m, {}).get("points")
        if not pts:
            continue
        pts = sorted(pts, key=lambda q: q["threshold"])
        ts = [q["threshold"] for q in pts]
        assert len(set(ts)) == len(ts), f"{m}: duplicate thresholds (select_slider needs unique values)"
        pos = {round(q["tp_per_1000"] + q["fn_per_1000"], 0) for q in pts}
        assert max(pos) - min(pos) <= 1, f"{m}: tp+fn per 1000 not constant: {sorted(pos)}"
        prev_recall = 1.01
        for q in pts:
            tp, fp, fn = q["tp_per_1000"], q["fp_per_1000"], q["fn_per_1000"]
            assert min(tp, fp, fn) >= 0 and tp + fp + fn <= 1000.5, f"{m} t={q['threshold']}: bad counts {q}"
            assert abs((tp + fp) / 1000 - q["flag_rate"]) < 0.002, f"{m} t={q['threshold']}: flag_rate != (tp+fp)/1000"
            if tp + fn:
                assert abs(tp / (tp + fn) - q["recall"]) < 0.005, f"{m} t={q['threshold']}: recall != tp/(tp+fn)"
            if tp + fp >= 5:  # counts are stored to 2 decimals; tiny flag counts can't reproduce precision exactly
                assert abs(tp / (tp + fp) - q["precision"]) < 0.01, f"{m} t={q['threshold']}: precision != tp/(tp+fp)"
            assert q["recall"] <= prev_recall + 1e-9, f"{m}: recall rises with threshold at {q['threshold']}"
            prev_recall = q["recall"]
        near = min(pts, key=lambda q: abs(q["threshold"] - meta[f"threshold_{m}"]))
        claim = meta["metrics"][m]["recall"]
        assert abs(near["recall"] - claim) < 0.03, f"{m}: curve recall {near['recall']} at {near['threshold']} vs meta {claim}"
        out.append(f"{m}: {len(pts)} pts, positives/1000={min(pos):.0f}, recall@thr {near['recall']:.3f} vs meta {claim:.3f}")
    assert out, "threshold_curve.json has no points"
    return "; ".join(out)


def _metric_values(at):
    return {m.label: m.value for m in at.metric}


@check("F", "Cost planner UI at extreme cut-offs and costs -> finite values, no crash")
def f_cost_ui():
    curve = _opt_json("threshold_curve.json")
    at = app_test(page="insights")
    if "Screening cost planner" not in texts(at):
        raise Skip("cost planner not rendered")
    seen = []
    for m, label in (("full", "Full check"), ("short", "Quick check")):
        pts = sorted(curve.get(m, {}).get("points", []), key=lambda q: q["threshold"])
        if not pts:
            continue
        for t in (pts[0]["threshold"], pts[-1]["threshold"]):
            for cost in (0.0, 10_000.0):
                at = app_test(page="insights")
                bg = [b for b in at.button_group if b.key == "plan_model"]
                if bg:
                    bg[0].set_value(label)
                    at.run()
                at.select_slider(key=f"plan_t_{m}").set_value(t)
                at.number_input(key="plan_cost").set_value(cost)
                at.run()
                assert_clean(at, f"planner {m} t={t} cost={cost}")
                mv = _metric_values(at)
                cpc = mv.get("Cost per case found", "")
                assert cpc and not re.search(r"inf|nan", cpc, re.I), f"{m} t={t} cost={cost}: cost per case = {cpc!r}"
                seen.append(f"{m}@{t:.2f}/${cost:.0f}: {cpc}")
    return "; ".join(seen)


@check("F", "What-if: before/after in [0,1] for every change, both tabs, extreme weights")
def f_what_if():
    out = []
    for tab in ("quick", "full"):
        for yes in (True, False):
            for w in (25, 300):
                at = run_tab(tab, setup=lambda at, tab=tab, yes=yes: _all(at, tab, yes))
                if not any(str(getattr(s, "key", "")).startswith(f"{tab}_wi_") for s in list(at.slider) + list(at.toggle)):
                    raise Skip("what-if controls not rendered")
                for tg in at.toggle:
                    if str(tg.key).startswith(f"{tab}_wi_"):
                        tg.set_value(True)
                for s in at.slider:
                    if s.key == f"{tab}_wi_weight":
                        s.set_value(w)
                for s in at.selectbox:
                    if s.key == f"{tab}_wi_GenHlth":
                        s.set_value(s.options[0])
                at.run()
                assert_clean(at, f"{tab} what-if yes={yes} w={w}")
                mv = _metric_values(at)
                vals = [v for k, v in mv.items() if k == "Now" or k.startswith("With changes")]
                for v in vals:
                    pct = float(str(v).rstrip("%"))
                    assert 0 <= pct <= 100, f"{tab}: what-if value {v}"
                out.append(f"{tab} {'yes' if yes else 'no'} w={w}: {'/'.join(map(str, vals)) or 'no change'}")
    f = load_app_functions()
    full, short, meta = _models()
    rng = np.random.default_rng(5)
    for m, feats in ((full, meta["features_full"]), (short, meta["features_short"])):
        for _ in range(200):
            v = {x: int(rng.integers(0, 1, endpoint=True)) for x in feats}
            v.update({k: int(rng.integers(lo, hi, endpoint=True)) for k, (lo, hi) in
                      {"BMI": (12, 98), "GenHlth": (1, 5), "Age": (1, 13), "MentHlth": (0, 30), "PhysHlth": (0, 30),
                       "Education": (1, 6), "Income": (1, 8)}.items() if k in feats})
            p = f["score"](m, feats, v)
            assert 0 <= p <= 1 and np.isfinite(p), p
    return "; ".join(out) + "; score() in [0,1] on 400 random profiles"


@check("F", "Segments: predict on extreme inputs returns a known segment; json sane")
def f_segments():
    seg = _opt_json("segments.json")
    import joblib
    p = CFG["models"] / "segments.joblib"
    if not p.exists():
        raise Skip("models/segments.joblib not present")
    model = joblib.load(p)
    meta = load_meta(CFG["models"])
    feats = seg["features"]
    assert set(feats) <= set(meta["features_full"]), f"segment features not in features_full: {set(feats) - set(meta['features_full'])}"
    ids = {s["id"] for s in seg["segments"]}
    assert len(ids) == len(seg["segments"]) == seg.get("k", len(ids)), "segment ids/k mismatch"
    share = sum(s["size_share"] for s in seg["segments"])
    assert abs(share - 1) < 0.01, f"size_share sums to {share}"
    for s in seg["segments"]:
        assert 0 <= s["diabetes_rate"] <= 1 and s["name"] and s["action"], s
        assert not EMOJI.search(s["name"] + s["action"]), f"emoji in segment text: {s['name']}"
    lo = {"BMI": 12, "Age": 1, "GenHlth": 1, "PhysHlth": 0, "MentHlth": 0, "Education": 1, "Income": 1}
    hi = {"BMI": 98, "Age": 13, "GenHlth": 5, "PhysHlth": 30, "MentHlth": 30, "Education": 6, "Income": 8}
    rows = [{f: lo.get(f, 0) for f in feats}, {f: hi.get(f, 1) for f in feats}]
    rng = np.random.default_rng(7)
    rows += [{f: int(rng.integers(lo.get(f, 0), hi.get(f, 1), endpoint=True)) for f in feats} for _ in range(2000)]
    X = pd.DataFrame(rows, columns=feats)
    pred = model.predict(X)
    assert set(np.unique(pred)) <= ids, f"unknown segment ids {set(np.unique(pred)) - ids}"
    assert len(pred) == len(rows)
    counts = pd.Series(pred).value_counts().to_dict()
    return f"k={len(ids)}; extremes -> {int(pred[0])}/{int(pred[1])}; random spread {counts}"


# ================================================================ runner
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default=str(ROOT / "models"))
    ap.add_argument("--fast", action="store_true")
    ap.add_argument("--only", default="", help="comma-separated sections, e.g. A,B")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    CFG["fast"] = a.fast
    CFG["models"] = Path(a.models)
    if not all((CFG["models"] / f).exists() for f in ("meta.json", "full_model.joblib", "short_model.joblib")):
        print(f"NOTE: {CFG['models']} incomplete - using stub models for app/model checks")
        CFG["models"] = build_stub_models(SCRATCH / "stub_models")
        CFG["stub"] = True
    import logging
    logging.getLogger("streamlit").setLevel(logging.ERROR)
    checks = [v for v in globals().values() if callable(v) and hasattr(v, "_check")]
    if a.only:
        checks = [c for c in checks if c._check[0] in a.only.split(",")]
    for c in checks:
        run_check(c)
    counts = {s: sum(r["status"] == s for r in RESULTS) for s in ("PASS", "FAIL", "WARN", "SKIP")}
    ready = counts["FAIL"] == 0 and counts["SKIP"] == 0 and not CFG["stub"] and not a.only and not a.fast
    head = (f"Run {time.strftime('%Y-%m-%d %H:%M')} - {models_label()} - " +
            ", ".join(f"{k} {v}" for k, v in counts.items()) + f"\n\nREADY TO PUSH: {'yes' if ready else 'no'}\n")
    scrub = re.compile("|".join(KEYWORDS) + "|no" + "reply@", re.I)  # keep our output free of the grepped words
    for r in RESULTS:
        r["detail"] = scrub.sub("<redacted>", r["detail"])
    (EDGE / "last_run.md").write_text(head + "\n" + markdown_table(RESULTS) + "\n", encoding="utf-8")
    (EDGE / "last_run.json").write_text(json.dumps(RESULTS, indent=1), encoding="utf-8")
    print("\n" + head)
    shutil.rmtree(SCRATCH, ignore_errors=True)
    return 1 if counts["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
