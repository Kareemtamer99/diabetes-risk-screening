"""Rebuild the 21 CDC Diabetes Health Indicators features from raw BRFSS annual files.

Usage:  python scripts/build_multiyear.py [year ...]
Reads   data/brfss/raw/LLCP<year>XPT.zip
Writes  data/brfss/brfss_<year>.parquet  (21 features + Diabetes_binary + _STATE + year)
        data/brfss/source_vars.json      (which raw variable fed each feature, per year)

Cleaning follows the Kaggle "CDC Diabetes Health Indicators" (BRFSS 2015) logic:
recode yes/no to 1/0, drop refused / don't know / missing codes, then drop any row
with a missing value. Target: 1 = told they have diabetes, 0 = no, prediabetes or
only during pregnancy. That is what data/diabetes.csv actually contains (35,346
positives of 253,680 in 2015); see the sanity check in multiyear_validation.ipynb.
"""
import json
import os
import sys
import zipfile
from pathlib import Path

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "brfss"
RAW = OUT / "raw"
CHUNK = 20_000  # rows per chunk; a chunk holds every raw column as float64

# feature -> (candidate raw names, newest first is not required; first present wins, recode rule)
SPEC = {
    "HighBP": (["_RFHYPE5", "_RFHYPE6"], "rf"),
    "HighChol": (["TOLDHI2", "TOLDHI3"], "yn"),
    "CholCheck": (["_CHOLCHK", "_CHOLCH1", "_CHOLCH2", "_CHOLCH3"], "cholchk"),
    "BMI": (["_BMI5"], "bmi"),
    "Smoker": (["SMOKE100"], "yn"),
    "Stroke": (["CVDSTRK3"], "yn"),
    "HeartDiseaseorAttack": (["_MICHD"], "yn"),
    "PhysActivity": (["_TOTINDA"], "yn"),
    "Fruits": (["_FRTLT1", "_FRTLT1A"], "yn"),
    "Veggies": (["_VEGLT1", "_VEGLT1A"], "yn"),
    "HvyAlcoholConsump": (["_RFDRHV5", "_RFDRHV6", "_RFDRHV7", "_RFDRHV8", "_RFDRHV9"], "rf"),
    "AnyHealthcare": (["HLTHPLN1", "_HLTHPLN", "_HLTHPL1", "_HLTHPL2"], "yn"),
    "NoDocbcCost": (["MEDCOST", "MEDCOST1"], "yn"),
    "GenHlth": (["GENHLTH"], "range1_5"),
    "MentHlth": (["MENTHLTH"], "days"),
    "PhysHlth": (["PHYSHLTH"], "days"),
    "DiffWalk": (["DIFFWALK"], "yn"),
    "Sex": (["SEX", "SEX1", "SEXVAR", "_SEX"], "yn"),  # 1 male -> 1, 2 female -> 0
    "Age": (["_AGEG5YR"], "age"),
    "Education": (["EDUCA"], "educ"),
    "Income": (["INCOME2", "INCOME3", "INCOME4"], "income"),
    "Diabetes_binary": (["DIABETE3", "DIABETE4", "DIABETE5"], "diab"),
}
FEATURES = [f for f in SPEC if f != "Diabetes_binary"]


def recode(s: pd.Series, rule: str, raw_name: str) -> pd.Series:
    """Map raw BRFSS codes to dataset codes; anything else becomes NaN (dropped later)."""
    if rule == "yn":  # 1 yes -> 1, 2 no -> 0, 7/9/blank -> NaN
        return s.map({1: 1, 2: 0})
    if rule == "rf":  # calculated risk flags: 1 no -> 0, 2 yes -> 1, 9 -> NaN
        return s.map({1: 0, 2: 1})
    if rule == "cholchk":  # 1 checked within 5 years -> 1; 2 older, 3 never -> 0
        return s.map({1: 1, 2: 0, 3: 0})
    if rule == "bmi":  # _BMI5 has 2 implied decimals; dataset stores whole numbers
        return (s / 100).round()
    if rule == "range1_5":
        return s.where(s.between(1, 5))
    if rule == "days":  # 88 = none -> 0, 1-30 kept, 77/99 -> NaN
        return s.replace(88, 0).where(lambda v: v.between(0, 30))
    if rule == "age":  # 13 five-year groups, 14 = unknown
        return s.where(s.between(1, 13))
    if rule == "educ":
        return s.where(s.between(1, 6))
    if rule == "income":
        if raw_name == "INCOME2":
            return s.where(s.between(1, 8))
        # INCOME3 (2021+) splits $75k+ into 8-11; fold back into the old top level 8
        return s.where(s.between(1, 11)).clip(upper=8)
    if rule == "diab":  # 1 yes -> 1; 2 pregnancy only, 3 no, 4 prediabetes -> 0; 7/9 -> NaN
        return s.map({1: 1, 2: 0, 3: 0, 4: 0})
    raise ValueError(rule)


def pick_columns(columns) -> dict:
    cols = set(columns)
    found = {feat: next((c for c in names if c in cols), None) for feat, (names, _) in SPEC.items()}
    return found


def build_year(year: int) -> dict:
    zpath = RAW / f"LLCP{year}XPT.zip"
    with zipfile.ZipFile(zpath) as zf:
        member = next(n for n in zf.namelist() if n.strip().upper().endswith(".XPT"))
        xpt = RAW / f"LLCP{year}.XPT"
        if not xpt.exists():
            with zf.open(member) as src, open(xpt, "wb") as dst:
                while block := src.read(1 << 24):
                    dst.write(block)

    reader = pd.read_sas(xpt, format="xport", chunksize=CHUNK, encoding="infer")
    found = pick_columns(reader.columns)
    missing = [f for f, c in found.items() if c is None]
    info = {"year": year, "source_vars": found, "missing": missing}
    if missing:
        reader.close()
        xpt.unlink()
        info["status"] = "skipped"
        print(f"{year}: skipped, not asked this year -> {missing}", flush=True)
        return info

    parts, n_raw = [], 0
    for chunk in reader:
        n_raw += len(chunk)
        out = pd.DataFrame({f: recode(chunk[c], SPEC[f][1], c) for f, c in found.items()})
        out["_STATE"] = chunk["_STATE"]
        out = out.dropna()
        parts.append(out.astype("int16"))
    reader.close()
    df = pd.concat(parts, ignore_index=True)
    df["year"] = np.int16(year)
    df = df[FEATURES + ["Diabetes_binary", "_STATE", "year"]]
    df.to_parquet(OUT / f"brfss_{year}.parquet", index=False)
    xpt.unlink()  # raw XPT is about 1 GB; the zip stays for reruns
    info.update(status="ok", n_raw=n_raw, n=len(df), rate=float(df.Diabetes_binary.mean()))
    print(f"{year}: {n_raw:,} raw -> {len(df):,} clean, diabetes rate {info['rate']:.4f}", flush=True)
    return info


def main(years):
    OUT.mkdir(parents=True, exist_ok=True)
    meta_path = OUT / "source_vars.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    for y in years:
        if not (RAW / f"LLCP{y}XPT.zip").exists():
            meta[str(y)] = {"year": y, "status": "skipped", "reason": "download failed"}
            print(f"{y}: no download, skipped", flush=True)
            continue
        meta[str(y)] = build_year(y)
        meta_path.write_text(json.dumps(meta, indent=1))


if __name__ == "__main__":
    main([int(a) for a in sys.argv[1:]] or list(range(2015, 2026)))
