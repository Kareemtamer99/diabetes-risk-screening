"""Smoke tests: the Streamlit app starts cleanly and both saved models predict a probability.

Run from the repo root: python tests/test_app.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "models"

# Defaults for one plausible respondent; any feature not listed is a binary 0.
DEFAULTS = {"BMI": 27, "GenHlth": 3, "Age": 7, "Education": 5, "Income": 6, "MentHlth": 0, "PhysHlth": 0}


def test_app_runs():
    if not (ROOT / "app.py").exists():
        print("SKIP test_app_runs: app.py not found")
        return
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.run()
    assert not at.exception, f"app raised: {[e.message for e in at.exception]}"
    print("PASS test_app_runs")


def test_models_predict():
    meta_path = MODELS / "meta.json"
    if not meta_path.exists():
        print("SKIP test_models_predict: models/meta.json not found")
        return
    import joblib
    import pandas as pd

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    for name, key in (("full_model.joblib", "features_full"), ("short_model.joblib", "features_short")):
        model = joblib.load(MODELS / name)
        features = meta[key]
        row = pd.DataFrame([[DEFAULTS.get(f, 0) for f in features]], columns=features)
        p = float(model.predict_proba(row)[0, 1])
        assert 0 <= p <= 1, f"{name}: probability out of range: {p}"
        print(f"PASS test_models_predict[{name}]: p={p:.3f}")


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    test_app_runs()
    test_models_predict()
    print("All tests finished.")
