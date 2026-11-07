"""Diabetes Risk Screening Tool — Streamlit app.

Reads trained models and metadata from MODELS_DIR (default: ./models).
"""
import base64
import html
import json
import math
import textwrap
import os
from pathlib import Path

import joblib
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

MODELS_DIR = Path(os.environ.get("MODELS_DIR", Path(__file__).parent / "models"))
DATA_URL = "https://archive.ics.uci.edu/dataset/891"
BRAND_NAME = "SugarScope"
ASSETS = Path(__file__).parent / "assets"
LOGO, LOGO_MARK, FAVICON = ASSETS / "logo.svg", ASSETS / "logo_mark.svg", ASSETS / "favicon.png"
BMI_MIN, BMI_MAX = 12, 98
HEIGHT_RANGE, WEIGHT_RANGE, AGE_RANGE = (100, 250), (25, 300), (18, 100)

YES_NO = {"No": 0, "Yes": 1}

# One spec for all 21 model features. "options" maps answer text -> encoded value.
# BMI and Age are special-cased (computed from height/weight and years).
FEATURES = {
    "HighBP": {"label": "Has a doctor ever told you that you have high blood pressure?", "short": "High blood pressure", "options": YES_NO},
    "HighChol": {"label": "Has a doctor ever told you that you have high cholesterol?", "short": "High cholesterol", "options": YES_NO},
    "CholCheck": {"label": "Have you had your cholesterol checked in the past 5 years?", "short": "Cholesterol check in last 5 years", "options": YES_NO},
    "BMI": {"label": "Height and weight", "short": "Body mass index (BMI)"},
    "Smoker": {"label": "Have you smoked at least 100 cigarettes in your whole life?", "short": "Smoking history", "options": YES_NO},
    "Stroke": {"label": "Have you ever had a stroke?", "short": "Past stroke", "options": YES_NO},
    "HeartDiseaseorAttack": {"label": "Have you ever had coronary heart disease or a heart attack?", "short": "Heart disease or heart attack", "options": YES_NO},
    "PhysActivity": {"label": "In the past 30 days, did you exercise or do physical activity outside your job?", "short": "Physical activity", "options": YES_NO},
    "Fruits": {"label": "Do you eat fruit at least once a day?", "short": "Daily fruit", "options": YES_NO},
    "Veggies": {"label": "Do you eat vegetables at least once a day?", "short": "Daily vegetables", "options": YES_NO},
    "HvyAlcoholConsump": {"label": "Do you drink heavily? (men: over 14 drinks a week, women: over 7)", "short": "Heavy drinking", "options": YES_NO},
    "AnyHealthcare": {"label": "Do you have any health coverage (insurance, prepaid plan, Medicare)?", "short": "Health coverage", "options": YES_NO},
    "NoDocbcCost": {"label": "In the past 12 months, did cost stop you from seeing a doctor when you needed to?", "short": "Skipped a doctor due to cost", "options": YES_NO},
    "GenHlth": {"label": "In general, how would you rate your health?", "short": "General health",
                "options": {"Excellent": 1, "Very good": 2, "Good": 3, "Fair": 4, "Poor": 5}, "default": 2},
    "MentHlth": {"label": "Days in the past 30 when your mental health was not good", "short": "Days of poor mental health", "days": True},
    "PhysHlth": {"label": "Days in the past 30 when your physical health was not good", "short": "Days of poor physical health", "days": True},
    "DiffWalk": {"label": "Do you have serious difficulty walking or climbing stairs?", "short": "Difficulty walking", "options": YES_NO},
    "Sex": {"label": "Sex", "short": "Sex", "options": {"Female": 0, "Male": 1}},
    "Age": {"label": "Age (years)", "short": "Age"},
    "Education": {"label": "Highest level of school completed", "short": "Education",
                  "options": {"Never attended school or kindergarten only": 1, "Grades 1–8 (elementary)": 2,
                              "Grades 9–11 (some high school)": 3, "High school graduate": 4,
                              "Some college or technical school": 5, "College graduate": 6}, "default": 3},
    "Income": {"label": "Yearly household income", "short": "Household income",
               "options": {"Less than $10,000": 1, "$10,000 – $15,000": 2, "$15,000 – $20,000": 3,
                           "$20,000 – $25,000": 4, "$25,000 – $35,000": 5, "$35,000 – $50,000": 6,
                           "$50,000 – $75,000": 7, "$75,000 or more": 8}, "default": 6},
}
GROUPS = {
    "About you": ["Age", "Sex", "BMI"],
    "Health history": ["HighBP", "HighChol", "CholCheck", "Stroke", "HeartDiseaseorAttack", "DiffWalk"],
    "Lifestyle": ["PhysActivity", "Smoker", "HvyAlcoholConsump", "Fruits", "Veggies"],
    "Wellbeing & access": ["GenHlth", "MentHlth", "PhysHlth", "AnyHealthcare", "NoDocbcCost", "Education", "Income"],
}

RISK = {  # mark color, tint, text color (>= 4.5:1 on tint), one-sentence advice
    "Low": ("#1E7F4F", "#E7F4EC", "#17663F", "Your answers look similar to people who did not report a diabetes diagnosis."),
    "Medium": ("#B7791F", "#FBF1DF", "#7A4E0F", "Some of your answers are linked with a higher chance of diabetes. "
               "Consider asking a doctor about a blood sugar test."),
    "High": ("#B42318", "#FBE9E7", "#B42318", "Your answers are similar to many people who reported a diabetes diagnosis. "
             "Please talk to a doctor about a blood sugar test soon."),
}
INK, INK_2, SURFACE, LINE, BAR = "#172B36", "#4A5D68", "#FFFFFF", "#DCE5EA", "#0891B2"
# Categorical slots 1-6 in fixed order (validated reference palette); extra groups fold into OTHER.
CATEGORICAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"]
NO_DATA = "#D5DCE1"  # neutral grey for states with no survey rows in the selected year
LOW_N = 500  # fewer respondents than this: rate is noisy, flagged in the map hover
SEQUENTIAL = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]  # one hue, light to dark
OTHER = "#9AA5AE"
OPTIONAL_FILES = {"segments_model": "segments.joblib", "segments": "segments.json", "curve": "threshold_curve.json",
                  "multiyear": "multiyear.json", "states": "state_prevalence.csv"}
BASE_FILES = ("meta.json", "full_model.joblib", "short_model.joblib")
WHAT_IF = [  # feature, answer that raises risk, toggle label, value if changed
    ("PhysActivity", 0, "If you exercised regularly", 1),
    ("HighBP", 1, "If your blood pressure were treated and under control", 0),
    ("HighChol", 1, "If your cholesterol were treated and under control", 0),
    ("Smoker", 1, "If you had never smoked", 0),
    ("HvyAlcoholConsump", 1, "If you cut down to moderate drinking", 0),
    ("Fruits", 0, "If you ate fruit every day", 1),
    ("Veggies", 0, "If you ate vegetables every day", 1),
]
NEXT_STEPS = {
    "Low": ["Keep up regular activity and a balanced diet.", "Keep routine check-ups with your doctor.",
            "Check again if your health or weight changes."],
    "Medium": ["Ask your doctor about an A1C or fasting blood sugar test.", "Bring this result to your next appointment.",
               "Small changes help: 150 minutes of activity a week and a healthy weight."],
    "High": ["Book an appointment and ask for an A1C or fasting blood sugar test.",
             "Mention the answers listed under \"What raised your score\".",
             "Do not change medication based on this result."],
}
DISCLAIMER = ("This is a screening aid, not a medical diagnosis. It compares your answers with self-reported "
              "answers from a US health survey and can be wrong. Only a blood test can confirm diabetes.")

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Figtree:wght@500;600;700&family=Noto+Sans:wght@400;500;600&display=swap');
:root { --ink: #172B36; --ink-2: #4A5D68; --bg: #F3F7F9; --surface: #FFFFFF; --line: #DCE5EA;
        --primary: #0E7490; --primary-hover: #155E75; --ring: #0891B2; --brand: #0C3646;
        --shadow-card: 0 0 0 1px rgba(12,54,70,0.07), 0 1px 2px rgba(12,54,70,0.05), 0 4px 12px rgba(12,54,70,0.04); }
html, body, .stApp { -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; }
html, body { font-family: 'Noto Sans', system-ui, -apple-system, 'Segoe UI', sans-serif; }  /* widgets get it from the theme; icons keep their font */
h1, .card-title, .risk-number, .empty-title { font-family: 'Figtree', 'Noto Sans', system-ui, sans-serif; text-wrap: balance; }
p, li, .muted, .note { text-wrap: pretty; }
footer, [data-testid="stDecoration"], [data-testid="stMainMenu"], [data-testid="stAppDeployButton"],
[data-testid="stMarkdownContainer"] h1 a, [data-testid="stMarkdownContainer"] h1 svg { display: none; }
header[data-testid="stHeader"] { background: var(--surface); box-shadow: 0 1px 0 var(--line); }
/* Streamlit's header (holding the top nav) is position:absolute and 3.75rem tall: start content below it */
[data-testid="stMainBlockContainer"] { max-width: 1280px; padding: 3.75rem 32px 48px; }
/* Nav row shares the content column, so the logo and "Home" line up with the band instead of the viewport edge */
[data-testid="stToolbar"] > div { max-width: 1280px; margin: 0 auto; padding: 0 16px; box-sizing: border-box; }
.stApp { background: var(--bg); color: var(--ink); }
.hero { background: var(--brand); color: #FFFFFF; margin: 0 0 24px; padding: 32px 40px; border-radius: 24px; }
.hero h1 { color: #FFFFFF; font-size: 34px; font-weight: 700; letter-spacing: -0.015em; line-height: 1.15; margin: 0; padding: 0; }
.hero p { color: #C6DCE4; font-size: 17px; line-height: 1.5; margin: 8px 0 0; max-width: 60ch; }
.pill { display: inline-block; padding: 4px 12px; border-radius: 999px; font-size: 13px; font-weight: 600; line-height: 1.4; }
.hero .pill { background: rgba(255,255,255,0.10); box-shadow: inset 0 0 0 1px rgba(255,255,255,0.35); color: #FFFFFF; margin-top: 16px; }
div[class*="st-key-card"] { background: var(--surface); border-radius: 16px; box-shadow: var(--shadow-card); padding: 24px; gap: 16px; }
.card-title { font-size: 21px; font-weight: 600; color: var(--ink); line-height: 1.3; margin: 0; }
.muted { color: var(--ink-2); font-size: 14px; line-height: 1.5; }
[data-testid="stWidgetLabel"] p { font-size: 15px; font-weight: 500; color: var(--ink); line-height: 1.45; }
[data-testid="stTab"] { min-height: 44px; }
/* Slider value bubbles: one line at natural width ("80", "2025"), never clipped or wrapped per digit */
[data-testid="stSliderThumbValue"], [data-testid="stSliderTickBarMin"], [data-testid="stSliderTickBarMax"] {
    white-space: nowrap; width: max-content; max-width: none; overflow: visible; word-break: normal; overflow-wrap: normal; }
[data-testid="stSlider"] [role="slider"] { overflow: visible; }
[data-testid="stTab"] p { font-size: 16px; font-weight: 600; }
/* Segmented Yes/No: 44px targets and a clear selected state */
[data-testid="stButtonGroup"] button { min-height: 44px; font-size: 15px; transition: background-color 150ms ease-out, color 150ms ease-out; }
[data-testid="stButtonGroup"] button[aria-checked="true"] { background: #E3F1F5; color: var(--primary-hover); font-weight: 600; }
[data-testid="stButtonGroup"] button[aria-checked="false"]:hover { background: var(--bg); }
[data-testid="stBaseButton-primary"] { min-height: 48px; font-size: 16px; font-weight: 600; border-radius: 10px;
    transition: background-color 150ms ease-out, transform 120ms ease-out; }
[data-testid="stBaseButton-primary"]:hover { background: var(--primary-hover); border-color: var(--primary-hover); }
[data-testid="stBaseButton-primary"]:active { transform: scale(0.96); }
button:focus-visible, input:focus-visible, [role="radio"]:focus-visible, [role="tab"]:focus-visible, a:focus-visible {
    outline: 2px solid var(--ring) !important; outline-offset: 2px; }
div[data-testid="stColumn"]:has(div[class*="st-key-result"]) { position: sticky; top: 16px; align-self: flex-start; }
@media (max-width: 768px) {
  div[data-testid="stColumn"]:has(div[class*="st-key-result"]) { position: static; }
  [data-testid="stMainBlockContainer"] { padding: 3.75rem 16px 40px; }
  .hero { padding: 24px 20px; border-radius: 16px; }
  [data-testid="stToolbar"] > div { padding: 0; }
  .hero h1 { font-size: 28px; }
}
@media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
.risk-label { font-size: 13px; font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase; color: var(--ink-2); }
.risk-number { font-size: 64px; font-weight: 700; line-height: 1; font-variant-numeric: tabular-nums; letter-spacing: -0.03em; }
.stat { background: var(--bg); border-radius: 8px; padding: 8px 16px; box-shadow: inset 0 0 0 1px var(--line); }
.stat b { font-size: 24px; font-variant-numeric: tabular-nums; color: var(--ink); }
[data-testid="stMetricValue"] { font-variant-numeric: tabular-nums; font-family: 'Figtree', sans-serif; }
.note { border-radius: 8px; padding: 12px 16px; color: var(--ink-2); font-size: 14px;
    line-height: 1.5; background: var(--surface); box-shadow: var(--shadow-card); }
.empty { text-align: center; padding: 48px 16px; color: var(--ink-2); line-height: 1.5; }
.empty-title { display: block; color: var(--ink); font-size: 19px; font-weight: 600; margin-bottom: 8px; }
.site-footer { border-top: 1px solid var(--line); margin-top: 40px; padding-top: 16px; color: var(--ink-2); font-size: 13px; line-height: 1.6; }
.site-footer a, .note a { color: var(--primary); text-underline-offset: 2px; }
.dot { display: inline-block; width: 10px; height: 10px; border-radius: 999px; margin-right: 8px; vertical-align: 1px; }
div[class*="st-key-card_seg_"] { box-shadow: inset 0 0 0 1px var(--line); border-radius: 12px; padding: 16px; gap: 4px; }
div[class*="st-key-home_hero"] { background: var(--brand); border-radius: 24px; padding: 56px 56px 48px; gap: 20px;
    margin-top: 16px; box-shadow: 0 8px 24px rgba(12,54,70,0.18); }
.brandline { display: flex; align-items: center; gap: 12px; color: #FFFFFF; font-family: 'Figtree', sans-serif;
    font-weight: 700; font-size: 24px; letter-spacing: -0.01em; }
.brandline img { border-radius: 11px; box-shadow: 0 0 0 1px rgba(255,255,255,0.18); }
div[class*="st-key-home_hero"] h1 { color: #FFFFFF; font-size: 52px; font-weight: 700; line-height: 1.08; letter-spacing: -0.025em;
    max-width: 16ch; margin: 8px 0 0; padding: 0; }
.lead { color: #C6DCE4; font-size: 19px; line-height: 1.55; max-width: 58ch; margin: 0; }
div[class*="st-key-home_hero"] [data-testid="stBaseButton-secondary"] { background: transparent; color: #FFFFFF; min-height: 48px;
    font-size: 16px; font-weight: 600; border-radius: 10px; border: 1px solid rgba(255,255,255,0.5);
    transition: background-color 150ms ease-out, transform 120ms ease-out; }
div[class*="st-key-home_hero"] [data-testid="stBaseButton-secondary"]:hover { background: rgba(255,255,255,0.10); color: #FFFFFF; border-color: #FFFFFF; }
div[class*="st-key-home_hero"] [data-testid="stBaseButton-secondary"]:active { transform: scale(0.96); }
.hero-pill { background: rgba(255,255,255,0.10); box-shadow: inset 0 0 0 1px rgba(255,255,255,0.35); color: #FFFFFF; }
.section-title { font-family: 'Figtree', sans-serif; font-size: 26px; font-weight: 700; color: var(--ink); letter-spacing: -0.01em;
    margin: 40px 0 8px; text-wrap: balance; }
.step-num { display: inline-flex; align-items: center; justify-content: center; width: 36px; height: 36px; border-radius: 999px;
    background: #E3F1F5; color: var(--primary-hover); font-family: 'Figtree', sans-serif; font-weight: 700; font-size: 17px;
    font-variant-numeric: tabular-nums; }
div[class*="st-key-home_stat"] [data-testid="stMetricValue"] { font-size: 40px; font-weight: 700; color: var(--ink); }
[data-testid="stBaseButton-tertiary"] { min-height: 44px; color: var(--primary); font-weight: 600; }
@media (max-width: 640px) {
  div[class*="st-key-home_hero"] { padding: 28px 20px; border-radius: 16px; }
  div[class*="st-key-home_hero"] h1 { font-size: 34px; }
  .lead { font-size: 17px; }
  .section-title { font-size: 22px; margin-top: 32px; }
}
/* ===== Product-site system: full-bleed bands, centred column, one motion vocabulary ===== */
:root { --tint: #EAF5F8; --on-dark: #D3E6ED; --on-dark-2: #A9C7D2; --cyan: #22D3EE; --ease-x: cubic-bezier(0.22, 1, 0.36, 1);
        --navy-glow: radial-gradient(120% 150% at 82% -10%, #155A73 0%, #0C3646 46%, #082733 100%); }
::selection { background: #BDE7F0; color: #0C3646; }
html { scrollbar-color: #A7BCC5 transparent; }
[data-testid="stMainBlockContainer"] { padding-bottom: 0; }
[data-testid="stMarkdownContainer"] h2 a, [data-testid="stMarkdownContainer"] h3 a, [data-testid="stHeaderActionElements"] { display: none; }
/* Bands paint edge to edge with border-image outset (no scroll overflow); the extra 1rem on top fills the block gap */
div[class*="st-key-band_"] { --band: linear-gradient(#FFFFFF, #FFFFFF); border-image: var(--band) fill 0 / / 1rem 100vmax 0; }
div[class*="st-key-band_hero"] { --band: var(--navy-glow); padding: 64px 0 80px; }
div[class*="st-key-band_how"] { padding: 96px 0 72px; gap: 24px; }
div[class*="st-key-band_built"] { --band: linear-gradient(180deg, #EAF5F8, #E2F1F5); padding: 88px 0 96px; }
div[class*="st-key-band_stats"] { --band: var(--navy-glow); padding: 96px 0 104px; }
div[class*="st-key-band_cta"] { --band: radial-gradient(70% 120% at 50% 0%, #E6F4F8 0%, #FFFFFF 70%); padding: 96px 0 104px; gap: 24px; }

/* Section heads: the heading carries its own weight */
.sec-head { margin: 0 0 32px; }
.sec-head.center { text-align: center; max-width: 760px; margin-left: auto; margin-right: auto; margin-bottom: 56px; }
.sec-head h2 { font-family: 'Figtree', sans-serif; font-size: clamp(30px, 3.1vw, 44px); font-weight: 700; letter-spacing: -0.02em;
    line-height: 1.1; color: var(--ink); margin: 0; padding: 0; text-wrap: balance; }
.sec-head p { font-size: 18px; line-height: 1.55; color: var(--ink-2); margin: 14px 0 0; text-wrap: pretty; }
.sec-head.center p { max-width: 56ch; margin-left: auto; margin-right: auto; }
div[class*="st-key-band_stats"] .sec-head h2, .cta-inner h2 { color: inherit; }
div[class*="st-key-band_stats"] .sec-head h2 { color: #FFFFFF; }
div[class*="st-key-band_stats"] .sec-head p { color: var(--on-dark); }

/* Hero: copy left, product preview right */
div[class*="st-key-home_hero"] { background: none; box-shadow: none; border-radius: 0; padding: 0; margin: 0; gap: 22px; }
div[class*="st-key-home_hero"] h1 { font-size: clamp(40px, 4.4vw, 60px); max-width: 13ch; }
.pv-wrap { perspective: 1400px; display: flex; justify-content: center; padding: 12px 0; }
.pv { width: min(100%, 440px); background: #FFFFFF; border-radius: 22px; padding: 26px 26px 22px; color: var(--ink);
    box-shadow: 0 1px 2px rgba(3,20,28,0.25), 0 24px 48px -8px rgba(3,20,28,0.55), 0 0 0 1px rgba(255,255,255,0.6);
    transform: rotateY(-9deg) rotateX(4deg) rotate(-1deg); transform-origin: 40% 50%; }
.pv-top { display: flex; justify-content: space-between; align-items: center; }
.pv-k { font-size: 12px; font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase; color: var(--ink-2); }
.pv-ex { font-size: 12px; font-weight: 700; color: #0C3646; background: #E3F1F5; padding: 4px 10px; border-radius: 999px;
    box-shadow: inset 0 0 0 1px #9FD0DC; }
.pv-row { display: flex; align-items: center; gap: 14px; margin-top: 8px; }
.pv-num { font-family: 'Figtree', sans-serif; font-size: 60px; font-weight: 700; line-height: 1; letter-spacing: -0.03em;
    font-variant-numeric: tabular-nums; }
.pv-pill { font-size: 14px; font-weight: 600; padding: 5px 12px; border-radius: 999px; box-shadow: inset 0 0 0 1px #B7791F44; }
.pv-meter { position: relative; height: 12px; margin-top: 22px; }
.pv-meter span { position: absolute; top: 0; bottom: 0; border-radius: 3px; box-shadow: inset -2px 0 0 #FFFFFF; }
.pv-meter em { position: absolute; top: 50%; width: 22px; height: 22px; border-radius: 50%; background: var(--ink);
    border: 3px solid #FFFFFF; transform: translate(-50%, -50%); box-shadow: 0 2px 6px rgba(3,20,28,0.35); }
.pv-ticks { position: relative; height: 18px; margin-top: 10px; font-size: 12px; color: var(--ink-2); }
.pv-ticks span { position: absolute; transform: translateX(-50%); }
.pv-f { display: grid; grid-template-columns: 1fr 104px 40px; align-items: center; gap: 12px; margin-top: 11px; font-size: 14px; }
.pv-f i { position: relative; height: 8px; border-radius: 4px; background: #E6EEF1; overflow: hidden; }
.pv-f i::after { content: ""; position: absolute; inset: 0 auto 0 0; width: var(--w); border-radius: 4px; background: #0891B2; transform-origin: left; }
.pv-f b { text-align: right; font-size: 13px; font-weight: 600; color: var(--ink-2); font-variant-numeric: tabular-nums; }
.pv-note { margin-top: 18px; padding-top: 14px; border-top: 1px solid var(--line); font-size: 12px; color: var(--ink-2); }

/* How it works: connected stepper */
.stepper { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(3, 1fr); gap: 40px; position: relative; }
.stepper::before { content: ""; position: absolute; top: 34px; height: 2px; left: calc((100% - 80px) / 6); right: calc((100% - 80px) / 6);
    background: linear-gradient(90deg, #BFE0E8, #0E7490 50%, #BFE0E8); border-radius: 2px; }
.stepper li { position: relative; text-align: center; margin: 0; padding: 0 8px; }
.st-ico { position: relative; z-index: 1; width: 68px; height: 68px; border-radius: 50%; display: inline-flex; align-items: center;
    justify-content: center; background: #FFFFFF; color: var(--primary); box-shadow: 0 0 0 1px #CFE3EA, 0 6px 16px rgba(12,54,70,0.08);
    transition: transform 250ms var(--ease-x), box-shadow 250ms var(--ease-x), color 250ms var(--ease-x); }
.stepper h3, .aud-tile h3 { font-family: 'Figtree', sans-serif; font-size: 21px; font-weight: 600; color: var(--ink); margin: 22px 0 6px; padding: 0; }
.stepper p, .aud-tile p { color: var(--ink-2); font-size: 16px; line-height: 1.55; margin: 0 auto; max-width: 30ch; text-wrap: pretty; }
div[class*="st-key-band_how"] [data-testid="stBaseButton-tertiary"] { margin-top: 8px; }

/* Built for */
.aud { display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; }
.aud-tile { background: #FFFFFF; border-radius: 20px; padding: 30px 28px; box-shadow: var(--shadow-card);
    transition: transform 250ms var(--ease-x), box-shadow 250ms var(--ease-x); }
.aud-tile p { margin: 0; }
.aud-ico, .sec-ico, .pl-ico { display: inline-flex; align-items: center; justify-content: center; flex: none; background: #E3F1F5; color: var(--primary-hover); }
.aud-ico { width: 52px; height: 52px; border-radius: 14px; }

/* By the numbers: uneven bento on the dark band */
.bento { display: grid; grid-template-columns: 1.35fr 1fr 1fr; gap: 20px; }
.t-a { grid-row: span 2; justify-content: center; }
.t-d { grid-column: 2 / span 2; }
.tile { display: flex; flex-direction: column; gap: 10px; padding: 30px; border-radius: 22px; color: #FFFFFF;
    background: linear-gradient(180deg, rgba(255,255,255,0.075), rgba(255,255,255,0.035));
    box-shadow: inset 0 0 0 1px rgba(255,255,255,0.13), 0 10px 30px rgba(2,14,20,0.25);
    transition: transform 250ms var(--ease-x), box-shadow 250ms var(--ease-x); }
.tile-num { font-family: 'Figtree', sans-serif; font-size: clamp(46px, 4.6vw, 72px); font-weight: 700; line-height: 1;
    letter-spacing: -0.03em; font-variant-numeric: tabular-nums; color: #FFFFFF; }
.tile-num small { font-size: 0.4em; font-weight: 600; letter-spacing: 0; color: var(--on-dark-2); }
.tile-num.sm { font-size: clamp(24px, 2.2vw, 30px); line-height: 1.2; letter-spacing: -0.015em; text-wrap: balance; }
.tile-label { font-size: 16px; line-height: 1.5; color: var(--on-dark); max-width: 38ch; }
.tile-sub { font-size: 14px; color: var(--on-dark-2); }
.dots { display: grid; grid-template-columns: repeat(10, 1fr); gap: 8px; max-width: 300px; margin-top: 20px; }
.dots i { aspect-ratio: 1; border-radius: 50%; background: rgba(255,255,255,0.18); }
.dots i.on { background: var(--cyan); }
.minibar { height: 10px; margin-top: auto; border-radius: 5px; background: rgba(255,255,255,0.14); overflow: hidden; }
.minibar i { display: block; height: 100%; width: var(--w); border-radius: 5px; background: var(--cyan); transform-origin: left; }
.segpill { display: flex; gap: 3px; margin-top: auto; }
.segpill i { flex: 1; height: 14px; border-radius: 2px; background: rgba(255,255,255,0.16); }
.segpill i:first-child { border-radius: 7px 2px 2px 7px; } .segpill i:last-child { border-radius: 2px 7px 7px 2px; }
.segpill i.on { background: var(--cyan); }
.spark { width: 100%; max-width: 560px; height: auto; overflow: visible; margin-top: 6px; }
.spark polyline { fill: none; stroke: var(--cyan); stroke-width: 1.75; stroke-linejoin: round; stroke-linecap: round; }
.spark circle { fill: var(--cyan); stroke: var(--cyan); stroke-width: 1.5; }
.spark circle.base { fill: #0C3646; stroke: var(--on-dark-2); }
.spark text { fill: var(--on-dark-2); font-size: 7px; text-anchor: middle; font-variant-numeric: tabular-nums; }
.note { border-left: none; box-shadow: inset 0 0 0 1px var(--line); }
.band-note { margin-top: 32px; background: rgba(255,255,255,0.05); color: var(--on-dark); box-shadow: inset 0 0 0 1px rgba(255,255,255,0.14); }

/* CTA band and footer */
.cta-inner { text-align: center; }
.cta-inner h2 { font-family: 'Figtree', sans-serif; font-size: clamp(30px, 3.1vw, 44px); font-weight: 700; letter-spacing: -0.02em;
    line-height: 1.1; color: var(--ink); margin: 0; padding: 0; }
.cta-inner p { font-size: 18px; color: var(--ink-2); margin: 12px 0 8px; }
.site-footer { border-top: none; margin: 0; padding: 64px 0 48px; color: var(--on-dark); font-size: 14px; line-height: 1.6;
    border-image: var(--navy-glow) fill 0 / / 1rem 100vmax 100vmax; }
.ft-grid { display: grid; grid-template-columns: 1.3fr 1fr 1.5fr 0.9fr; gap: 40px; }
.ft-grid h3 { font-family: 'Noto Sans', sans-serif; font-size: 13px; font-weight: 600; letter-spacing: 0.04em; color: #FFFFFF; margin: 0 0 10px; padding: 0; }
.ft-grid p { margin: 0; color: var(--on-dark); }
.ft-brand { display: flex; align-items: center; gap: 10px; color: #FFFFFF; font-family: 'Figtree', sans-serif; font-weight: 700; font-size: 20px; margin-bottom: 10px; }
.ft-brand img { border-radius: 8px; }
.site-footer a { color: #8BE6F5; text-underline-offset: 3px; display: inline-flex; align-items: center; gap: 6px; }
.site-footer a:focus-visible { outline-color: #8BE6F5 !important; }

/* Inner pages: compact dark header band */
.hero { border-image: var(--navy-glow) fill 0 / / 1rem 100vmax 0; background: none; border-radius: 0; margin: 0 0 36px; padding: 48px 0 52px; }
.hero h1 { font-size: clamp(32px, 3.2vw, 46px); letter-spacing: -0.02em; }
.hero p { color: var(--on-dark); font-size: 18px; }

/* Risk check: section icons, counters, a result that leads */
.card-title:has(.sec-ico) { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.sec-ico { width: 38px; height: 38px; border-radius: 11px; }
.sec-count { margin-left: auto; font-family: 'Noto Sans', sans-serif; font-size: 13px; font-weight: 600; color: var(--ink-2);
    background: var(--bg); padding: 4px 10px; border-radius: 999px; white-space: nowrap; box-shadow: inset 0 0 0 1px var(--line); }
div[class*="st-key-card_"][class*="_risk"]:has(.band-Low) { background: linear-gradient(180deg, #E7F4EC 0%, #FFFFFF 62%); box-shadow: inset 0 0 0 1px #1E7F4F40, 0 12px 32px rgba(12,54,70,0.10); }
div[class*="st-key-card_"][class*="_risk"]:has(.band-Medium) { background: linear-gradient(180deg, #FBF1DF 0%, #FFFFFF 62%); box-shadow: inset 0 0 0 1px #B7791F40, 0 12px 32px rgba(12,54,70,0.10); }
div[class*="st-key-card_"][class*="_risk"]:has(.band-High) { background: linear-gradient(180deg, #FBE9E7 0%, #FFFFFF 62%); box-shadow: inset 0 0 0 1px #B4231840, 0 12px 32px rgba(12,54,70,0.10); }
div[class*="st-key-card_"][class*="_risk"] .risk-number { font-size: 76px; }
div[class*="st-key-card_"][class*="_empty"] { background: repeating-linear-gradient(135deg, #FFFFFF 0 14px, #F7FAFB 14px 28px); box-shadow: inset 0 0 0 1px var(--line); }
[data-baseweb="tab-highlight"] { background-color: var(--primary); height: 3px; border-radius: 3px;
    transition: left 250ms var(--ease-x), width 250ms var(--ease-x), transform 250ms var(--ease-x); }

/* Population insights: the planner is a calculator panel */
div[class*="st-key-card_ins_cost"] { background: linear-gradient(180deg, #EAF5F8, #F7FBFC); box-shadow: inset 0 0 0 1px #BFE0E8, 0 10px 28px rgba(12,54,70,0.07); }
div[class*="st-key-card_ins_cost"] [data-testid="stMetric"] { background: #FFFFFF; border-radius: 12px; padding: 12px 16px; box-shadow: inset 0 0 0 1px var(--line); }

/* How it works: pipeline and metric tiles */
.pipeline { list-style: none; margin: 0 0 56px; padding: 0; display: grid; grid-template-columns: repeat(6, 1fr); gap: 14px; }
.pipeline li { position: relative; margin: 0; display: flex; flex-direction: column; gap: 6px; padding: 20px 18px; border-radius: 16px;
    background: #FFFFFF; box-shadow: var(--shadow-card); }
.pipeline li:not(:last-child)::after { content: ""; position: absolute; top: 39px; right: -14px; width: 14px; height: 2px; background: #7CC3D3; }
.pl-ico { width: 40px; height: 40px; border-radius: 12px; margin-bottom: 8px; }
.pipeline b { font-family: 'Figtree', sans-serif; font-size: 17px; color: var(--ink); }
.pipeline span:not(.pl-ico) { font-size: 14px; line-height: 1.45; color: var(--ink-2); }
.mtiles { display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; margin-bottom: 16px; }
.mtile { background: #FFFFFF; border-radius: 18px; padding: 24px; box-shadow: var(--shadow-card); }
.mt-label { font-family: 'Figtree', sans-serif; font-size: 18px; font-weight: 600; color: var(--ink); margin-bottom: 6px; }
.mt-row { display: grid; grid-template-columns: 92px 1fr 54px; align-items: center; gap: 12px; margin-top: 12px; font-size: 14px; color: var(--ink-2); }
.mt-row i { position: relative; height: 10px; border-radius: 5px; background: #E8EEF1; overflow: hidden; }
.mt-row i::after { content: ""; position: absolute; inset: 0 auto 0 0; width: var(--w); border-radius: 5px; background: var(--primary); }
.mt-row.base i::after { background: #9AA5AE; }
.mt-row b { text-align: right; font-size: 15px; color: var(--ink); font-variant-numeric: tabular-nums; }

/* Motion: allowed only when the visitor has not asked for less */
@media (prefers-reduced-motion: no-preference) {
  .ss-motion .rv { opacity: 0; transform: translateY(8px);
      transition: opacity 400ms var(--ease-x), transform 400ms var(--ease-x); transition-delay: calc(var(--i, 0) * 60ms); }
  .ss-motion .rv.rv-in { opacity: 1; transform: none; }
  .ss-motion .pv { animation: pv-in 700ms var(--ease-x) 120ms both; }
  .ss-motion .pv-meter em { animation: pv-mark 900ms var(--ease-x) 520ms both; }
  .ss-motion .pv-f i::after, .ss-motion .rv-in .minibar i { animation: grow 800ms var(--ease-x) 600ms both; }
  @keyframes pv-in { from { opacity: 0; filter: blur(6px); transform: rotateY(-9deg) rotateX(4deg) rotate(-1deg) translateY(18px); } }
  @keyframes pv-mark { from { left: 0; } }
  @keyframes grow { from { transform: scaleX(0); } }
}
@media (hover: hover) and (prefers-reduced-motion: no-preference) {
  .aud-tile:hover, .mtile:hover, .pipeline li:hover { transform: translateY(-3px); box-shadow: 0 2px 4px rgba(12,54,70,0.06), 0 16px 32px rgba(12,54,70,0.12); }
  .tile:hover { transform: translateY(-3px); box-shadow: inset 0 0 0 1px rgba(255,255,255,0.22), 0 16px 36px rgba(2,14,20,0.35); }
  .stepper li:hover .st-ico { transform: translateY(-3px); color: var(--primary-hover); box-shadow: 0 0 0 1px #9FD0DC, 0 12px 24px rgba(12,54,70,0.14); }
  [data-testid="stBaseButton-primary"]:hover { transform: translateY(-1px); box-shadow: 0 8px 18px rgba(14,116,144,0.30); }
  .mtile, .pipeline li { transition: transform 250ms var(--ease-x), box-shadow 250ms var(--ease-x); }
}

@media (max-width: 1100px) {
  .pipeline { grid-template-columns: repeat(3, 1fr); }
  .pipeline li::after { display: none; }
  .bento { grid-template-columns: 1fr 1fr; }
  .t-a { grid-row: auto; grid-column: span 2; }
  .t-d { grid-column: span 2; }
  .ft-grid { grid-template-columns: 1fr 1fr; }
}
@media (max-width: 900px) {
  div[class*="st-key-band_hero"] > div > [data-testid="stHorizontalBlock"], div[class*="st-key-band_hero"] > [data-testid="stHorizontalBlock"] { flex-wrap: wrap; gap: 40px; }
  div[class*="st-key-band_hero"] [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:has(.pv-wrap),
  div[class*="st-key-band_hero"] [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:has(div[class*="st-key-home_hero"]) { width: 100% !important; flex: 1 1 100% !important; }
  div[class*="st-key-home_hero"] h1 { max-width: 16ch; }
}
@media (max-width: 768px) {
  div[class*="st-key-band_hero"] { padding: 40px 0 56px; }
  .stepper p, .aud-tile p { max-width: 60ch; }
  div[class*="st-key-band_how"], div[class*="st-key-band_built"], div[class*="st-key-band_stats"], div[class*="st-key-band_cta"] { padding: 64px 0 72px; }
  .sec-head.center { margin-bottom: 36px; }
  .stepper { grid-template-columns: 1fr; gap: 28px; }
  .stepper::before { top: 34px; bottom: 34px; left: 33px; right: auto; width: 2px; height: auto; background: linear-gradient(180deg, #BFE0E8, #0E7490, #BFE0E8); }
  .stepper li { display: grid; grid-template-columns: 68px 1fr; column-gap: 18px; text-align: left; padding: 0; }
  .st-ico { grid-row: span 2; }
  .stepper h3 { margin: 8px 0 4px; }
  .stepper p { margin: 0; }
  .aud, .mtiles { grid-template-columns: 1fr; }
  .pipeline { grid-template-columns: 1fr 1fr; }
  .hero { padding: 32px 0 36px; margin-bottom: 28px; }
  .pv { transform: none; }
}
@media (max-width: 560px) {
  .bento { grid-template-columns: 1fr; }
  .t-a, .t-d { grid-column: auto; }
  .tile { padding: 24px; }
  .ft-grid { grid-template-columns: 1fr; gap: 28px; }
  .pipeline { grid-template-columns: 1fr; }
  .sec-count { margin-left: 50px; }
}
/* QA fixes: stack two-column layouts below 900px, let controls and labels wrap */
@media (max-width: 900px) {
  [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] div[class*="st-key-result_"]),
  [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] div[class*="st-key-card_ins_map"]),
  [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] div[class*="st-key-plan_model"]) { flex-wrap: wrap; gap: 24px; }
  [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] div[class*="st-key-result_"]) > [data-testid="stColumn"],
  [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] div[class*="st-key-card_ins_map"]) > [data-testid="stColumn"],
  [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] div[class*="st-key-plan_model"]) > [data-testid="stColumn"] {
      width: 100% !important; flex: 1 1 100% !important; min-width: 0; }
  div[data-testid="stColumn"]:has(div[class*="st-key-result"]) { position: static; }
}
[data-testid="stButtonGroup"] button { min-width: 0; }
[data-testid="stButtonGroup"] button p, [data-testid="stMetricLabel"] p, [data-testid="stMetricLabel"] div {
    white-space: normal; overflow: visible; text-overflow: clip; line-height: 1.25; }
[data-baseweb="select"] [title], [data-baseweb="select"] div[class*="ValueContainer"] div { white-space: normal; overflow: visible; text-overflow: clip; }
div[class*="st-key-result_"] .note { margin: 8px 0; }
[data-testid="stMainBlockContainer"]:has(div[class*="st-key-quick_submit"]) .site-footer { margin-top: 64px; }
.vtable { width: 100%; border-collapse: collapse; font-size: 14px; font-variant-numeric: tabular-nums; margin: 8px 0; }
.vtable th { text-align: left; font-weight: 600; color: var(--ink-2); font-size: 13px; padding: 8px 8px 8px 0; border-bottom: 1px solid var(--line); }
.vtable td { padding: 8px 8px 8px 0; border-bottom: 1px solid var(--line); color: var(--ink); vertical-align: top; }
.vtable td:first-child { overflow-wrap: anywhere; }
.mt-note { display: block; font-family: 'Noto Sans', sans-serif; font-size: 12px; font-weight: 500; color: var(--ink-2); margin-top: 2px; }
.spark text.val { fill: #FFFFFF; font-weight: 600; }
@media (max-width: 560px) {
  .vtable { font-size: 13px; }
  .vtable th, .vtable td { padding-right: 6px; }
  .spark text { font-size: 11.5px; }
}
</style>
"""


def age_to_bucket(years: int) -> int:
    """BRFSS 13-level age code: 1 = 18–24, 2 = 25–29, … 12 = 75–79, 13 = 80+."""
    return 1 if years < 25 else min(13, (years - 25) // 5 + 2)


def compute_bmi(height_cm: float, weight_kg: float) -> int:
    return int(round(min(BMI_MAX, max(BMI_MIN, weight_kg / (height_cm / 100) ** 2))))


def risk_band(p: float, bands: dict) -> str:
    p = round(p, 2)  # band the value we display, so the card and the legend never disagree at a cut point
    if p < bands["low_max"]:
        return "Low"
    return "High" if p >= bands["high_min"] else "Medium"


def is_num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def require(ok: bool, msg: str):
    if not ok:
        raise ValueError(msg)


def validate_meta(meta: dict):
    """Raise ValueError if meta.json cannot drive the app; the caller shows the friendly error."""
    require(isinstance(meta, dict), "meta.json is not an object")
    for key in ("features_full", "features_short", "risk_bands", "explainer", "explainer_short"):
        require(key in meta, f"meta.json is missing '{key}'")
    for key in ("features_full", "features_short"):
        feats = meta[key]
        require(isinstance(feats, list) and feats and all(f in FEATURES for f in feats), f"{key} lists unknown features")
    b = meta["risk_bands"]
    require(isinstance(b, dict) and is_num(b.get("low_max")) and is_num(b.get("high_min"))
            and 0 <= b["low_max"] < b["high_min"] <= 1, "risk_bands needs numeric 0 <= low_max < high_min <= 1")
    for key in ("explainer", "explainer_short"):
        e = meta[key]
        require(isinstance(e, dict), f"{key} is not an object")
        cols = [e.get(k) for k in ("features", "coef", "mean", "scale")]
        require(all(isinstance(c, list) for c in cols) and len({len(c) for c in cols}) == 1 and cols[0],
                f"{key} needs features/coef/mean/scale lists of equal length")
        require(all(f in FEATURES for f in e["features"]), f"{key} lists unknown features")
        require(all(is_num(v) for v in e["coef"] + e["mean"] + e["scale"]), f"{key} has non-numeric values")
        require(is_num(e.get("intercept")), f"{key} needs a numeric intercept")
    metrics = meta.get("metrics", {})
    require(isinstance(metrics, dict) and all(isinstance(m, dict) for m in metrics.values()), "metrics must map names to objects")
    require(all(v is None or is_num(v) for m in metrics.values() for v in m.values()), "metrics values must be numbers or null")


def valid_segments(seg) -> dict | None:
    try:
        require(isinstance(seg, dict) and isinstance(seg.get("features"), list) and seg["features"], "features")
        require(all(f in FEATURES for f in seg["features"]), "unknown features")
        segs = seg.get("segments")
        require(isinstance(segs, list) and segs, "segments")
        for x in segs:
            require(isinstance(x, dict) and isinstance(x.get("name"), str) and isinstance(x.get("action"), str)
                    and "id" in x and is_num(x.get("size_share")) and is_num(x.get("diabetes_rate")), "segment entry")
        pca = seg.get("pca")
        if pca is not None:
            ok = (isinstance(pca, dict) and isinstance(pca.get("points"), list)
                  and all(isinstance(q, dict) and is_num(q.get("x")) and is_num(q.get("y")) and "segment" in q
                          for q in pca["points"])
                  and (isinstance(pca.get("explained_variance"), list) and len(pca["explained_variance"]) >= 2
                       and all(is_num(v) for v in pca["explained_variance"])))
            if not ok:
                seg = {**seg, "pca": None}  # keep the cards, drop only the broken scatter
        return seg
    except ValueError:
        return None


CURVE_KEYS = ("threshold", "recall", "precision", "flag_rate", "tp_per_1000", "fp_per_1000", "fn_per_1000")


def valid_curve(curve) -> dict | None:
    if not isinstance(curve, dict):
        return None
    good = {}
    for k in ("full", "short"):
        pts = (curve.get(k) or {}).get("points") if isinstance(curve.get(k), dict) else None
        if isinstance(pts, list) and pts and all(isinstance(q, dict) and all(is_num(q.get(c)) for c in CURVE_KEYS) for q in pts):
            good[k] = {**curve[k], "points": pts}
    return good or None


def valid_multiyear(my) -> dict | None:
    try:
        require(isinstance(my, dict), "object")
        prev = my.get("prevalence_by_year") or []
        require(isinstance(prev, list) and all(isinstance(r, dict) and is_num(r.get("year")) and is_num(r.get("rate"))
                                               and is_num(r.get("n")) for r in prev), "prevalence_by_year")
        tv = my.get("temporal_validation") or []
        require(isinstance(tv, list) and all(
            isinstance(r, dict) and "train_years" in r and is_num(r.get("test_year"))
            and all(r.get(k) is None or is_num(r.get(k)) for k in ("roc_auc", "recall", "precision")) for r in tv),
            "temporal_validation")
        years = my.get("years") or []
        require(isinstance(years, list) and all(is_num(y) for y in years), "years")
        require(prev or tv, "empty")
        return my
    except ValueError:
        return None


def valid_states(df) -> pd.DataFrame | None:
    cols = {"state_abbr", "state_name", "year", "n", "actual_rate", "predicted_rate"}
    if not isinstance(df, pd.DataFrame) or not cols <= set(df.columns):
        return None
    df = df.copy()
    for c in ("year", "n", "actual_rate", "predicted_rate"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["year", "actual_rate", "predicted_rate"])
    df["year"] = df["year"].astype(int)
    return df if not df.empty else None


VALIDATE_OPTIONAL = {"segments": valid_segments, "curve": valid_curve, "multiyear": valid_multiyear, "states": valid_states}


@st.cache_resource
def load_artifacts(models_dir: str, stamp: tuple = ()):
    d = Path(models_dir)
    meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    validate_meta(meta)
    return joblib.load(d / "full_model.joblib"), joblib.load(d / "short_model.joblib"), meta


def file_stamp(models_dir: Path, names=tuple(OPTIONAL_FILES.values())) -> tuple:
    """Modification times, so the caches reload when model files appear or change."""
    return tuple((f, (models_dir / f).stat().st_mtime if (models_dir / f).exists() else None) for f in names)


@st.cache_resource
def load_optional(models_dir: str, stamp: tuple = ()) -> dict:
    """Load each optional artifact; a missing or unreadable file becomes None and its section is hidden."""
    d, out = Path(models_dir), {}
    for key, name in OPTIONAL_FILES.items():
        try:
            path = d / name
            if name.endswith(".json"):
                data = json.loads(path.read_text(encoding="utf-8"))
                out[key] = data if isinstance(data, dict) else None
            elif name.endswith(".csv"):
                out[key] = pd.read_csv(path)
            else:
                out[key] = joblib.load(path)
        except Exception:
            out[key] = None
        if out[key] is not None and key in VALIDATE_OPTIONAL:
            out[key] = VALIDATE_OPTIONAL[key](out[key])
    return out


def card(key: str, title: str | None = None):
    c = st.container(key=f"card_{key}")
    if title:
        c.markdown(f'<div class="card-title">{title}</div>', unsafe_allow_html=True)
    return c


def render_widget(name: str, prefix: str) -> tuple[int, str]:
    spec = FEATURES[name]
    key = f"{prefix}_{name}"
    if name == "Age":
        years = int(st.number_input(spec["label"], 0, 150, 45, 1, key=f"{prefix}_age"))
        if not AGE_RANGE[0] <= years <= AGE_RANGE[1]:
            st.error(f"Age must be between {AGE_RANGE[0]} and {AGE_RANGE[1]} years.")
            return None, ""
        return age_to_bucket(years), f"{years} years"
    if spec.get("days"):
        v = st.slider(spec["label"], 0, 30, 0, key=key)
        return v, f"{v} days"
    opts = list(spec["options"])
    if len(opts) == 2:
        choice = st.segmented_control(spec["label"], opts, default=opts[0], required=True, key=key, width="stretch")
    else:
        choice = st.selectbox(spec["label"], opts, index=spec.get("default", 0), key=key)
    return spec["options"][choice], choice


def render_bmi(prefix: str) -> tuple[int | None, list[str]]:
    errors = []
    h_col, w_col, b_col = st.columns([1, 1, 0.8])
    h = h_col.number_input("Height (cm)", 0.0, 400.0, 170.0, 1.0, key=f"{prefix}_height")
    w = w_col.number_input("Weight (kg)", 0.0, 1000.0, 75.0, 0.5, key=f"{prefix}_weight")
    if not HEIGHT_RANGE[0] <= h <= HEIGHT_RANGE[1]:
        errors.append(f"Height must be between {HEIGHT_RANGE[0]} and {HEIGHT_RANGE[1]} cm.")
    if not WEIGHT_RANGE[0] <= w <= WEIGHT_RANGE[1]:
        errors.append(f"Weight must be between {WEIGHT_RANGE[0]} and {WEIGHT_RANGE[1]} kg.")
    bmi = None if errors else compute_bmi(h, w)
    b_col.markdown(f'<div class="stat"><span class="muted">Your BMI</span><br><b>{bmi if bmi else "–"}</b></div>',
                   unsafe_allow_html=True)
    for e in errors:
        st.error(e)
    return bmi, errors


def render_inputs(features: list[str], prefix: str) -> tuple[dict, dict, list[str]]:
    """Render grouped question cards. Returns (encoded values, answer text, validation errors)."""
    values, answers, errors = {}, {}, []
    used = [t for t, g in GROUPS.items() if any(f in features for f in g)]
    for title, group in GROUPS.items():
        wanted = [f for f in group if f in features]
        if not wanted:
            continue
        n = used.index(title) + 1
        head = (f'<span class="sec-ico">{icon(GROUP_ICONS.get(title, "questionnaire"), 20)}</span>{title}'
                f'<span class="sec-count">Section {n} of {len(used)}</span>')
        with card(f"{prefix}_{title.split()[0].lower()}", head):
            grid = [f for f in wanted if f != "BMI"]
            cols = st.columns(2, gap="medium")
            for i, name in enumerate(grid):
                with cols[i % 2]:
                    values[name], answers[name] = render_widget(name, prefix)
                    if values[name] is None:
                        errors.append(name)
            if "BMI" in wanted:
                bmi, errs = render_bmi(prefix)
                errors += errs
                if bmi is not None:
                    values["BMI"], answers["BMI"] = bmi, str(bmi)
    return values, answers, errors


# Answers that are plainly healthy are never listed as raising risk, even if the model nudges them up slightly.
HEALTHY = {**{f: (lambda v: v == 0) for f in ("HighBP", "HighChol", "Smoker", "Stroke", "HeartDiseaseorAttack",
                                              "HvyAlcoholConsump", "NoDocbcCost", "DiffWalk", "MentHlth", "PhysHlth")},
           **{f: (lambda v: v == 1) for f in ("PhysActivity", "Fruits", "Veggies", "AnyHealthcare", "CholCheck")},
           "GenHlth": lambda v: v <= 3, "BMI": lambda v: v < 25}


def risk_factors(values: dict, answers: dict, explainer: dict, top: int = 5) -> list[tuple[str, float]]:
    """Features whose answer pushes the linear score up and is not a plainly healthy answer, largest first."""
    out = []
    for f, c, m, s in zip(explainer["features"], explainer["coef"], explainer["mean"], explainer["scale"]):
        if f in values and s and not HEALTHY.get(f, lambda v: False)(values[f]):
            contrib = c * (values[f] - m) / s
            if contrib > 0:
                out.append((f"{FEATURES[f]['short']}: {answers[f]}", contrib))
    return sorted(out, key=lambda t: t[1], reverse=True)[:top]


def risk_meter(p: float, bands: dict) -> go.Figure:
    """Band meter: three status segments with a 2px surface gap and a ringed marker at the user's value."""
    lo, hi, gap = bands["low_max"], bands["high_min"], 0.004
    fig = go.Figure()
    for (name, (color, *_)), (x0, x1) in zip(RISK.items(), [(0, lo), (lo, hi), (hi, 1)]):
        fig.add_shape(type="rect", x0=x0 + (gap if x0 else 0), x1=x1 - (gap if x1 < 1 else 0), y0=-0.5, y1=0.5,
                      fillcolor=color, line_width=0, layer="below")
        fig.add_annotation(x=(x0 + x1) / 2, y=-1.15, text=name, showarrow=False, font=dict(size=13, color=INK_2))
    fig.add_trace(go.Scatter(x=[min(max(p, 0.03), 0.97)], y=[0], mode="markers", hovertemplate=f"Your estimate: {p:.0%}<extra></extra>",
                             marker=dict(size=18, color=INK, line=dict(color=SURFACE, width=3))))
    fig.update_layout(height=96, margin=dict(l=4, r=4, t=8, b=4), showlegend=False,
                      xaxis=dict(range=[-0.02, 1.02], tickvals=[lo, hi], ticktext=[f"{lo:.0%}", f"{hi:.0%}"], side="top",
                                 tickfont=dict(size=12, color=INK_2), showgrid=False, zeroline=False, fixedrange=True),
                      yaxis=dict(range=[-1.6, 0.9], visible=False, fixedrange=True),
                      plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
    return fig


def factors_chart(factors: list) -> go.Figure:
    """Ranked single-series bars: one color, value at the tip as share of the total increase."""
    labels, scores = zip(*reversed(factors))
    labels = ["<br>".join(textwrap.wrap(lb, 22)) for lb in labels]
    total = sum(scores)
    shares = [s / total for s in scores]
    fig = go.Figure(go.Bar(x=shares, y=labels, orientation="h", width=0.5,
                           marker=dict(color=BAR, cornerradius=4),
                           text=[f"{s:.0%}" for s in shares], textposition="outside", cliponaxis=False,
                           textfont=dict(size=13, color=INK),
                           hovertemplate="%{y}<br>%{x:.0%} of the increase<extra></extra>"))
    fig.update_layout(height=40 + 52 * len(factors), margin=dict(l=0, r=40, t=4, b=4),
                      xaxis=dict(visible=False, range=[0, max(shares) * 1.15], fixedrange=True),
                      yaxis=dict(tickfont=dict(size=13, color=INK), showgrid=False, ticks="", ticklabelstandoff=8, fixedrange=True,
                                 automargin=True),
                      plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                      hoverlabel=dict(bgcolor=SURFACE, bordercolor=LINE, font=dict(color=INK, size=13)))
    return fig


def render_result(p: float, factors: list, bands: dict, prefix: str):
    band = risk_band(p, bands)
    color, tint, text, advice = RISK[band]
    with card(f"{prefix}_risk"):
        st.markdown(
            f"""<div class="risk-label band-{band}">Estimated risk</div>
            <div style="display:flex;align-items:center;gap:16px;flex-wrap:wrap;margin-top:8px">
              <span class="risk-number" style="color:{color}">{p:.0%}</span>
              <span class="pill" style="background:{tint};color:{text};font-size:15px;box-shadow:inset 0 0 0 1px {color}33">{band} risk</span></div>
            <p style="color:{INK};font-size:16px;line-height:1.5;margin:12px 0 0">{advice}</p>""",
            unsafe_allow_html=True,
        )
        st.plotly_chart(risk_meter(p, bands), width="stretch", config={"displayModeBar": False}, key=f"{prefix}_meter")
        st.markdown('<div class="muted">The percentage is the share of survey respondents with similar answers '
                    'who reported a diabetes diagnosis.</div>', unsafe_allow_html=True)
    with card(f"{prefix}_factors", "What raised your score"):
        if factors:
            st.plotly_chart(factors_chart(factors), width="stretch", config={"displayModeBar": False}, key=f"{prefix}_bars")
            st.markdown("<div class=\"muted\">Each bar is that answer's share of the increase above an average respondent. "
                        "These answers are linked with higher risk in the survey data; they show association, not cause.</div>",
                        unsafe_allow_html=True)
        else:
            st.markdown('<div class="muted">None of your answers stood out as raising your estimated risk.</div>',
                        unsafe_allow_html=True)
    with card(f"{prefix}_next", "What to do next"):
        st.markdown("\n".join(f"- {s}" for s in NEXT_STEPS[band]))
    st.markdown(f'<div class="note">{DISCLAIMER}</div>', unsafe_allow_html=True)


def empty_result(prefix: str, message: str = "Answer the questions and press <b>Check my risk</b> to see your result."):
    with card(f"{prefix}_empty"):
        st.markdown(f'<div class="empty"><span class="empty-title">Your result will appear here</span>{message}</div>', unsafe_allow_html=True)


def score(model, features: list[str], values: dict) -> float:
    return float(model.predict_proba(pd.DataFrame([[values[f] for f in features]], columns=features))[0, 1])


def what_if(model, features: list[str], values: dict, bands: dict, prefix: str, p: float):
    """Re-score the same model with changed answers. Widget keys keep choices across reruns."""
    with card(f"{prefix}_whatif", "See how changes could affect your estimate"):
        new = dict(values)
        if "BMI" in features:
            h = st.session_state.get(f"{prefix}_height", 170.0)
            w = st.session_state.get(f"{prefix}_weight", 75.0)
            nw = st.slider("If your weight were (kg)", 25, 300, int(round(w)), key=f"{prefix}_wi_weight")
            new["BMI"] = compute_bmi(h, nw)
            st.markdown(f'<div class="muted">BMI {values["BMI"]} &rarr; {new["BMI"]}</div>', unsafe_allow_html=True)
        for f, risky, label, to in WHAT_IF:
            if f in features and values.get(f) == risky and st.toggle(label, key=f"{prefix}_wi_{f}"):
                new[f] = to
        if "GenHlth" in features and values.get("GenHlth", 1) > 1:
            opts = FEATURES["GenHlth"]["options"]
            choice = st.selectbox("If your general health were", list(opts), index=values["GenHlth"] - 1, key=f"{prefix}_wi_GenHlth")
            new["GenHlth"] = opts[choice]
        if new == values:
            st.markdown('<div class="muted">Choose a change above to see how your estimate could move.</div>', unsafe_allow_html=True)
        else:
            p2 = score(model, features, new)
            now, after = st.columns(2)
            now.metric("Now", f"{p:.0%}", risk_band(p, bands), delta_color="off")
            d = round((p2 - p) * 100, 1)
            # a change that rounds to 0 would show a red "+0.0" arrow, so show no delta then
            after.metric(f"With changes: {risk_band(p2, bands)}", f"{p2:.0%}", f"{d:+.1f} points" if d else "No change",
                         delta_color="inverse" if d else "off")
        st.markdown('<div class="note">This shows an association in survey data, not a guaranteed effect. '
                    'Talk to a doctor before making changes to treatment or lifestyle.</div>', unsafe_allow_html=True)


def profile_card(opt: dict, values: dict, prefix: str):
    seg_model, seg = opt.get("segments_model"), opt.get("segments")
    if seg_model is None or not seg:
        return
    try:
        feats = seg["features"]
        sid = int(seg_model.predict(pd.DataFrame([[values[f] for f in feats]], columns=feats))[0])
        s = next(x for x in seg["segments"] if x["id"] == sid)
    except Exception:
        return  # optional feature: hide quietly
    with card(f"{prefix}_profile", f"Your profile: {html.escape(s['name'])}"):
        a, b = st.columns(2)
        a.metric("Share of adults", f"{s['size_share']:.0%}")
        b.metric("Reported a diabetes diagnosis", f"{s['diabetes_rate']:.0%}")
        st.markdown(f'<p style="margin:0">{html.escape(s["action"])}</p>', unsafe_allow_html=True)


def check_tab(model, features: list[str], explainer: dict, bands: dict, prefix: str, intro: str, opt: dict):
    left, right = st.columns([3, 2], gap="large")
    with left:
        st.markdown(f'<p class="muted" style="font-size:15px;margin:0 0 8px">{intro}</p>', unsafe_allow_html=True)
        values, answers, errors = render_inputs(features, prefix)
        if st.button("Check my risk", type="primary", width="stretch", key=f"{prefix}_submit"):
            st.session_state[f"{prefix}_done"] = True
    with right, st.container(key=f"result_{prefix}"):
        if not st.session_state.get(f"{prefix}_done"):
            return empty_result(prefix)
        if errors:
            return empty_result(prefix, "Please fix the highlighted answers to see your result.")
        try:
            p = score(model, features, values)
        except Exception:
            st.error("Sorry, something went wrong while calculating your result. Please try again later.")
            return
        render_result(p, risk_factors(values, answers, explainer), bands, prefix)
        if set(features) >= set(FEATURES):
            profile_card(opt, values, prefix)
        what_if(model, features, values, bands, prefix, p)


# ---------- Population insights ----------

def chart_layout(fig: go.Figure, height: int, **kw) -> go.Figure:
    fig.update_layout(height=height, margin=dict(l=8, r=8, t=8, b=8), plot_bgcolor="rgba(0,0,0,0)",
                      paper_bgcolor="rgba(0,0,0,0)", font=dict(color=INK, size=13),
                      hoverlabel=dict(bgcolor=SURFACE, bordercolor=LINE, font=dict(color=INK, size=13)),
                      legend=kw.pop("legend", dict(orientation="h", y=1.08, x=0, font=dict(color=INK_2))), **kw)
    fig.update_xaxes(showgrid=False, linecolor=LINE, tickfont=dict(color=INK_2), fixedrange=True)
    fig.update_yaxes(gridcolor=LINE, gridwidth=1, zeroline=False, tickfont=dict(color=INK_2), fixedrange=True)
    return fig


def segment_color(i: int) -> tuple[str, bool]:
    """Fixed categorical order; anything past slot 6 folds into a gray 'Other'."""
    return (CATEGORICAL[i], False) if i < len(CATEGORICAL) else (OTHER, True)


def segments_section(seg: dict):
    segs = seg["segments"]
    with card("ins_segments", f'<span class="sec-ico">{icon("scatter", 20)}</span>Population profiles'):
        st.markdown(f'<div class="muted">Survey respondents grouped into {seg.get("k", len(segs))} profiles with similar answers.</div>',
                    unsafe_allow_html=True)
        cols = st.columns(min(3, len(segs)), gap="medium")
        for i, s in enumerate(segs):
            color, _ = segment_color(i)
            with cols[i % len(cols)], st.container(key=f"card_seg_{i}"):
                st.markdown(f'<div class="card-title" style="font-size:17px"><span class="dot" style="background:{color}"></span>'
                            f'{html.escape(s["name"])}</div>'
                            f'<div class="muted">{s["size_share"]:.0%} of adults &middot; {s["diabetes_rate"]:.0%} reported a diabetes diagnosis</div>'
                            f'<p style="margin:8px 0 0;font-size:14px">{html.escape(s["action"])}</p>', unsafe_allow_html=True)
        pca = seg.get("pca") or {}
        pts = pd.DataFrame(pca.get("points", []))
        if pts.empty:
            return
        ev = pca.get("explained_variance", [0, 0])
        fig = go.Figure()
        order = {s["id"]: i for i, s in enumerate(segs)}
        pts["slot"] = pts["segment"].map(order).fillna(len(CATEGORICAL)).astype(int)
        for slot, grp in pts.groupby("slot"):
            color, other = segment_color(slot)
            name = "<br>".join(textwrap.wrap("Other" if other else segs[slot]["name"], 34))  # plotly legends never wrap on their own
            fig.add_trace(go.Scatter(x=grp["x"], y=grp["y"], mode="markers", name=name, text=grp["label"],
                                       hovertemplate="%{text}<extra></extra>",
                                       marker=dict(size=8, color=color, opacity=0.75, line=dict(color=SURFACE, width=1))))
        chart_layout(fig, 440, legend=dict(orientation="h", x=0, y=-0.08, yanchor="top", font=dict(color=INK_2, size=12)))
        fig.update_layout(margin=dict(l=8, r=8, t=8, b=8))
        fig.update_xaxes(title=dict(text=f"Main pattern 1 ({ev[0]:.0%} of variation)", font=dict(color=INK_2, size=12)),
                         showticklabels=False)
        fig.update_yaxes(title=dict(text=f"Main pattern 2 ({ev[1]:.0%} of variation)", font=dict(color=INK_2, size=12)),
                         showticklabels=False, showgrid=False)
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False}, key="ins_pca")
        st.markdown('<div class="muted">Each dot is a sample of respondents placed by their answers; '
                    'dots close together answered similarly.</div>', unsafe_allow_html=True)


def cost_section(curve: dict, meta: dict):
    names = {"full": "Full check", "short": "Quick check"}
    available = [k for k in names if curve.get(k, {}).get("points")]
    if not available:
        return
    with card("ins_cost", f'<span class="sec-ico">{icon("calculator", 20)}</span>Screening cost planner'):
        st.markdown('<div class="muted">What screening 1,000 people would look like at different cut-offs, based on held-out test data.</div>',
                    unsafe_allow_html=True)
        a, b, c = st.columns([1, 1.4, 1], gap="medium")
        label = a.segmented_control("Model", [names[k] for k in available], default=names[available[0]], required=True,
                                    key="plan_model", width="stretch")
        model = next(k for k in available if names[k] == label)
        pts = sorted(curve[model]["points"], key=lambda q: q["threshold"])
        ts = [q["threshold"] for q in pts]
        target = meta.get(f"threshold_{model}")
        target = target if is_num(target) else ts[len(ts) // 2]
        default = min(ts, key=lambda t: abs(t - target))
        t = b.select_slider("Flag people whose estimate is at least", ts, value=default, format_func=lambda v: f"{v:.0%}",
                            key=f"plan_t_{model}")
        cost = c.number_input("Cost per blood test, USD (example assumption)", 0.0, 10_000.0, 10.0, 1.0, key="plan_cost",
                              help="An example figure for planning. Replace it with your local cost.")
        q = next(q for q in pts if q["threshold"] == t)
        tests = q["tp_per_1000"] + q["fp_per_1000"]
        total = tests * cost
        row1, row2 = st.columns(3), st.columns(3)
        row1[0].metric("Cases caught", f"{q['tp_per_1000']:,.0f}")
        row1[1].metric("Cases missed", f"{q['fn_per_1000']:,.0f}")
        row1[2].metric("False alarms", f"{q['fp_per_1000']:,.0f}")
        row2[0].metric("Blood tests needed", f"{tests:,.0f}")
        row2[1].metric("Total test cost", f"${total:,.0f}")
        row2[2].metric("Cost per case found", f"${total / q['tp_per_1000']:,.2f}" if q["tp_per_1000"] else "n/a")
        st.markdown('<div class="muted">Per 1,000 people screened. Tests needed = everyone flagged (cases caught + false alarms).</div>',
                    unsafe_allow_html=True)
        fig = go.Figure()
        for i, (key, name) in enumerate([("recall", "Recall (cases caught)"), ("precision", "Precision (flags that are real cases)")]):
            ys = [p[key] for p in pts]
            fig.add_trace(go.Scatter(x=ts, y=ys, mode="lines", name=name, line=dict(color=CATEGORICAL[i], width=2),
                                     hovertemplate=f"{name}: %{{y:.0%}}<extra></extra>"))
            fig.add_trace(go.Scatter(x=[t], y=[q[key]], mode="markers", showlegend=False, hoverinfo="skip",
                                     marker=dict(size=10, color=CATEGORICAL[i], line=dict(color=SURFACE, width=2))))
        fig.add_vline(x=t, line=dict(color=INK, width=1.5))
        fig.add_annotation(x=t, y=0.97, text=f"Cut-off {t:.0%}", showarrow=False, xanchor="left" if t < 0.6 else "right",
                           xshift=8 if t < 0.6 else -8, bgcolor=SURFACE, bordercolor=LINE, borderpad=4,
                           font=dict(color=INK, size=12), yref="y")
        chart_layout(fig, 360, hovermode="x unified",
                     legend=dict(orientation="h", x=0, y=-0.2, yanchor="top", font=dict(color=INK_2, size=12)))
        fig.update_xaxes(tickformat=".0%", title=dict(text="Cut-off", font=dict(color=INK_2, size=12)))
        fig.update_yaxes(tickformat=".0%", range=[0, 1.04])
        fig.update_layout(margin=dict(l=8, r=8, t=8, b=8))
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False}, key="ins_curve")


def trends_section(my: dict | None, states: pd.DataFrame | None):
    both = bool(my and my.get("prevalence_by_year")) and states is not None and not states.empty
    left, right = st.columns([5, 7], gap="medium") if both else (st.container(), st.container())
    if my and my.get("prevalence_by_year"):
        with left, card("ins_trend", f'<span class="sec-ico">{icon("trend", 20)}</span>Diagnosed diabetes over time'):
            prev = pd.DataFrame(my["prevalence_by_year"]).sort_values("year")
            fig = go.Figure(go.Scatter(x=prev["year"], y=prev["rate"], mode="lines+markers", name="Reported rate",
                                       line=dict(color=CATEGORICAL[0], width=2),
                                       marker=dict(size=9, color=CATEGORICAL[0], line=dict(color=SURFACE, width=2)),
                                       customdata=prev["n"], hovertemplate="%{x}: %{y:.1%} of %{customdata:,} respondents<extra></extra>"))
            chart_layout(fig, 280, showlegend=False)
            fig.update_xaxes(tickvals=prev["year"], tickformat="d")
            fig.update_yaxes(tickformat=".0%", rangemode="tozero")
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False}, key="ins_prev")
            tv = my.get("temporal_validation") or []
            if tv:
                st.markdown('<div class="card-title" style="font-size:17px">Does the model hold up in later years?</div>'
                            '<div class="muted">Trained on earlier survey years, then tested on a later year it never saw.</div>',
                            unsafe_allow_html=True)
                f = lambda v, fmt: "n/a" if v is None else fmt.format(v)  # noqa: E731
                rows = "".join(f'<tr><td>{html.escape(years_label(r["train_years"]))}</td><td>{r["test_year"]}</td>'
                               f'<td>{f(r.get("roc_auc"), "{:.3f}")}</td><td>{f(r.get("recall"), "{:.0%}")}</td>'
                               f'<td>{f(r.get("precision"), "{:.0%}")}</td></tr>' for r in tv)
                st.markdown('<table class="vtable"><thead><tr><th>Trained on</th><th>Tested on</th><th>ROC-AUC</th><th>Recall</th>'
                            f'<th>Precision</th></tr></thead><tbody>{rows}</tbody></table>', unsafe_allow_html=True)
                if summary := drift_summary(my):
                    st.markdown(summary)
    if states is not None and not states.empty:
        with right, card("ins_map", f'<span class="sec-ico">{icon("map", 20)}</span>By state'):
            years = sorted(states["year"].unique().tolist())
            a, b = st.columns([2, 1], gap="medium")
            year = a.select_slider("Survey year", years, value=years[-1], key="map_year") if len(years) > 1 else years[0]
            measure = b.segmented_control("Show", ["Actual", "Predicted"], default="Actual", required=True, key="map_measure",
                                          width="stretch")
            col = "actual_rate" if measure == "Actual" else "predicted_rate"
            lo = float(states[["actual_rate", "predicted_rate"]].min().min())
            hi = float(states[["actual_rate", "predicted_rate"]].max().max())
            d = states[states["year"] == year].copy()
            d["conf"] = (d["n"] < LOW_N).map({True: " · low confidence (few respondents)", False: ""})
            names = states.drop_duplicates("state_abbr").set_index("state_abbr")["state_name"]
            missing = sorted(set(names.index) - set(d["state_abbr"]))
            fig = go.Figure(go.Choropleth(
                locations=d["state_abbr"], z=d[col], locationmode="USA-states", zmin=lo, zmax=hi,
                colorscale=[[i / (len(SEQUENTIAL) - 1), c] for i, c in enumerate(SEQUENTIAL)],
                marker_line_color=SURFACE, marker_line_width=1,
                customdata=d[["state_name", "n", "conf"]],
                hovertemplate="%{customdata[0]}: %{z:.1%} (%{customdata[1]:,} respondents)%{customdata[2]}<extra></extra>",
                colorbar=dict(tickformat=".0%", thickness=12, outlinewidth=0, tickfont=dict(color=INK_2),
                              title=dict(text=f"{measure} rate", font=dict(color=INK_2, size=12)))))
            if missing:  # grey layer so states without survey rows read as "no data", not as a rendering bug
                fig.add_trace(go.Choropleth(
                    locations=missing, z=[0] * len(missing), locationmode="USA-states", name="No data", showlegend=True,
                    colorscale=[[0, NO_DATA], [1, NO_DATA]], showscale=False, marker_line_color=SURFACE, marker_line_width=1,
                    customdata=[names[m] for m in missing], hovertemplate="%{customdata}: no data this year<extra></extra>"))
            fig.update_geos(scope="usa", bgcolor="rgba(0,0,0,0)", showlakes=False, landcolor="#EEF2F4")
            chart_layout(fig, 420, showlegend=bool(missing))
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False}, key="ins_choropleth")
            st.markdown('<div class="muted">Predicted = the model\'s average estimate for respondents in that state. '
                        'The color scale is the same for every year and both views.</div>', unsafe_allow_html=True)
            if missing:
                st.markdown(f'<div class="muted">No data for {year}: {", ".join(names[m] for m in missing)} '
                            '(the survey has no usable rows for these states that year).</div>', unsafe_allow_html=True)


def drift_summary(my: dict) -> str:
    """Total rows and the saved model's recall from its earliest to latest test year, from multiyear.json."""
    tv = my.get("temporal_validation") or []
    out = [f"**{my['total_rows']:,}** survey responses in total."] if is_num(my.get("total_rows")) else []
    saved = sorted((r for r in tv if r.get("train_years") == tv[0].get("train_years") and is_num(r.get("recall"))),
                   key=lambda r: r["test_year"]) if tv else []
    if len(saved) > 1:
        out.append(f"Recall of the saved model went from **{saved[0]['recall']:.0%}** in {saved[0]['test_year']} "
                   f"to **{saved[-1]['recall']:.0%}** in {saved[-1]['test_year']}.")
    return " ".join(out)


def years_label(years) -> str:
    years = sorted(years) if isinstance(years, list) else [years]
    return str(years[0]) if len(years) == 1 else f"{years[0]}–{years[-1]}"


def insights_tab(opt: dict, meta: dict):
    sections = []
    if opt["segments"]:
        sections.append((segments_section, (opt["segments"],)))
    if opt["curve"]:
        sections.append((cost_section, (opt["curve"], meta)))
    if opt["multiyear"] or opt["states"] is not None:
        sections.append((trends_section, (opt["multiyear"], opt["states"])))
    for fn, args in sections:
        try:
            fn(*args)
        except Exception:
            pass  # malformed optional file: skip that section rather than break the page


# ---------- How it works ----------

def how_it_works(meta: dict, opt: dict):
    metrics = meta.get("metrics", {})
    names = {"full": "Full check", "short": "Quick check", "baseline": "Baseline"}
    shown = {"recall": ("Recall", "{:.0%}"), "roc_auc": ("ROC-AUC", "{:.3f}"), "brier": ("Brier score", "{:.3f}")}
    st.markdown(pipeline_html(meta), unsafe_allow_html=True)
    if metrics:
        st.markdown(section_head("Test results", "Scored on held-out survey answers the models never saw during training.",
                                 center=False) + metric_tiles(metrics, names, shown), unsafe_allow_html=True)
        st.markdown('<p class="muted">Recall: share of people with diagnosed diabetes the tool flags. '
                    'ROC-AUC: how well it ranks higher-risk people above lower-risk ones (1.0 is perfect). '
                    'Brier score: how far the percentages are from reality (lower is better).</p>', unsafe_allow_html=True)
        with st.expander("All test metrics"):
            table = pd.DataFrame({names.get(k, k): v for k, v in metrics.items()})
            table.index = [c.replace("_", "-").upper() if c in ("roc_auc", "pr_auc") else c.capitalize() for c in table.index]
            st.dataframe(table.style.format("{:.3f}", na_rep="n/a"), width="stretch")
    seg, my = opt.get("segments"), opt.get("multiyear")
    years = sorted(my.get("years") or []) if my else []
    left, right = st.columns(2, gap="medium")
    with left, card("data", "Data"):
        lines = [f"Trained on the [CDC Diabetes Health Indicators]({DATA_URL}) dataset from the BRFSS "
                 f"{meta.get('data_year', '')} telephone survey."]
        if "n_rows" in meta:
            lines.append(f"- **{meta['n_rows']:,}** survey responses")
        if "positive_rate" in meta:
            lines.append(f"- **{meta['positive_rate']:.1%}** reported a diabetes diagnosis")
        lines.append(f"- Quick check uses {len(meta['features_short'])} questions, full check uses {len(meta['features_full'])}")
        st.markdown("\n".join(lines))
    with right, card("limits", "Limitations"):
        st.markdown("- Not a diagnosis: only a blood test can confirm diabetes.\n"
                    "- Survey answers are self-reported, and some people do not know they have diabetes.\n"
                    "- The survey target does not include prediabetes, so a Low result does not rule out prediabetes. "
                    "If you are worried, talk to a doctor about a blood sugar test.\n"
                    f"- Data comes from {'US survey years ' + years_label(years) if years else 'one US survey year'} and may not apply elsewhere.\n"
                    "- Listed factors and what-if changes are associations, not causes.")
    if seg or my:
        try:
            methods(seg, my, years)
        except Exception:
            pass  # malformed optional file: skip the section


def methods(seg: dict | None, my: dict | None, years: list):
    left, right = st.columns(2, gap="medium")
    if seg:
        with left, card("method_seg", "Population profiles"):
            feats = ", ".join(FEATURES.get(f, {}).get("short", f) for f in seg.get("features", []))
            text = [f"A clustering model groups respondents into **{seg.get('k', len(seg.get('segments', [])))}** profiles "
                    f"based on: {feats}."]
            ev = (seg.get("pca") or {}).get("explained_variance")
            if ev:
                text.append(f"The scatter plot squeezes these answers into two main patterns, which together keep "
                            f"**{sum(ev[:2]):.0%}** of the variation.")
            text.append("Profiles describe groups, not individuals, and do not change your risk estimate.")
            st.markdown("\n\n".join(text))
    if my:
        with right, card("method_years", "Multi-year validation"):
            tv = my.get("temporal_validation") or []
            text = [f"Survey years used: **{years_label(years)}**." if years else ""]
            aucs = [r["roc_auc"] for r in tv if r.get("roc_auc") is not None]
            if aucs:
                text.append(f"The model was trained on earlier years and tested on a later year it never saw, {len(tv)} "
                            f"time{'s' if len(tv) != 1 else ''}. ROC-AUC on the unseen year ranged from "
                            f"**{min(aucs):.3f}** to **{max(aucs):.3f}**.")
            text.append(drift_summary(my))
            st.markdown("\n\n".join(t for t in text if t) or "Multi-year results are not available yet.")


# ---------- Visual system: icons, motion script, shared bands ----------

# Line icons (24px grid, round caps, stroke 1.75), drawn as one family.
ICONS = {
    "questionnaire": '<rect x="8" y="2" width="8" height="4" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><path d="M12 11h4M12 16h4M8 11h.01M8 16h.01"/>',
    "gauge": '<path d="m12 14 4-4"/><path d="M3.34 19a10 10 0 1 1 17.32 0"/>',
    "signpost": '<path d="M12 13v8M12 3v3"/><path d="M18 6a2 2 0 0 1 1.39.56l2.3 2.22a1 1 0 0 1 0 1.44l-2.3 2.22A2 2 0 0 1 18 13H6a2 2 0 0 1-1.39-.56l-2.3-2.22a1 1 0 0 1 0-1.44l2.3-2.22A2 2 0 0 1 6 6z"/>',
    "person": '<circle cx="12" cy="8" r="5"/><path d="M20 21a8 8 0 0 0-16 0"/>',
    "stethoscope": '<path d="M11 2v2M5 2v2"/><path d="M5 3H4a2 2 0 0 0-2 2v4a6 6 0 0 0 12 0V5a2 2 0 0 0-2-2h-1"/><path d="M8 15a6 6 0 0 0 12 0v-3"/><circle cx="20" cy="10" r="2"/>',
    "people": '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
    "heart": '<path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z"/><path d="M3.22 12H9.5l.5-1 2 4.5 2-7 1.5 3.5h5.27"/>',
    "activity": '<path d="M22 12h-2.48a2 2 0 0 0-1.93 1.46l-2.35 8.36a.25.25 0 0 1-.48 0L9.24 2.18a.25.25 0 0 0-.48 0l-2.35 8.36A2 2 0 0 1 4.49 12H2"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/>',
    "calculator": '<rect x="4" y="2" width="16" height="20" rx="2"/><path d="M8 6h8M16 14v4M16 10h.01M12 10h.01M8 10h.01M12 14h.01M8 14h.01M12 18h.01M8 18h.01"/>',
    "database": '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14a9 3 0 0 0 18 0V5"/><path d="M3 12a9 3 0 0 0 18 0"/>',
    "filter": '<path d="M22 3H2l8 9.46V19l4 2v-8.54L22 3z"/>',
    "layers": '<path d="M12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83Z"/><path d="m22 17.65-9.17 4.16a2 2 0 0 1-1.66 0L2 17.65M22 12.65l-9.17 4.16a2 2 0 0 1-1.66 0L2 12.65"/>',
    "sliders": '<path d="M21 4h-7M10 4H3M21 12h-9M8 12H3M21 20h-5M12 20H3M14 2v4M8 10v4M16 18v4"/>',
    "target": '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>',
    "devices": '<path d="M18 8V6a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h8M10 19v-4M7 19h5"/><rect x="16" y="12" width="6" height="10" rx="2"/>',
    "external": '<path d="M15 3h6v6M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
    "map": '<path d="M14.1 6.03a2 2 0 0 1 1.8 0l3.65 1.83A1 1 0 0 1 21 8.76v10.48a1 1 0 0 1-1.45.9l-3.65-1.83a2 2 0 0 0-1.8 0l-4.2 2.1a2 2 0 0 1-1.8 0l-3.65-1.83A1 1 0 0 1 3 17.24V6.76a1 1 0 0 1 1.45-.9l3.65 1.83a2 2 0 0 0 1.8 0z"/><path d="M15 6v15M9 3.5v15"/>',
    "trend": '<path d="M16 17h6v-6"/><path d="m22 17-8.5-8.5-5 5L2 7"/>',
    "scatter": '<circle cx="7.5" cy="7.5" r="1.5"/><circle cx="18.5" cy="5.5" r="1.5"/><circle cx="11.5" cy="11.5" r="1.5"/><circle cx="7.5" cy="16.5" r="1.5"/><circle cx="17.5" cy="14.5" r="1.5"/><path d="M3 3v16a2 2 0 0 0 2 2h16"/>',
}
REPO_URL = "https://github.com/Kareemtamer99/diabetes-risk-screening"
GROUP_ICONS = {"About you": "person", "Health history": "heart", "Lifestyle": "activity", "Wellbeing & access": "sun"}


def icon(name: str, size: int = 24, cls: str = "ico") -> str:
    return (f'<svg class="{cls}" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            f'stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{ICONS[name]}</svg>')


# Scroll reveal and count-up. Content is visible by default; this only adds motion when the visitor allows it,
# and re-attaches to elements Streamlit adds on later reruns.
MOTION_JS = """<script>
(() => {
  if (window.__ssMotion) return; window.__ssMotion = true;
  const doc = document;
  if (matchMedia('(prefers-reduced-motion: reduce)').matches || !('IntersectionObserver' in window)) return;
  doc.documentElement.classList.add('ss-motion');
  const fmt = (v, el) => el.dataset.fmt === 'pct' ? Math.round(v) + '%' : Math.round(v).toLocaleString('en-US');
  const count = el => {
    const to = parseFloat(el.dataset.count), t0 = performance.now(), dur = 1100;
    const step = t => { const k = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(2, -10 * k);
      el.textContent = k < 1 ? fmt(to * e, el) : el.dataset.final; if (k < 1) requestAnimationFrame(step); };
    requestAnimationFrame(step);
  };
  const io = new IntersectionObserver(es => es.forEach(e => { e.target.dataset.rv = 2; if (!e.isIntersecting) return;
    e.target.classList.add('rv-in'); e.target.querySelectorAll('[data-count]').forEach(count); io.unobserve(e.target); }),
    { rootMargin: '0px 0px -8% 0px', threshold: 0.12 });
  // Failsafe: an observer that never reports must not leave content hidden.
  const scan = () => doc.querySelectorAll('.rv:not([data-rv])').forEach(el => { el.dataset.rv = 1; io.observe(el);
    setTimeout(() => { if (el.dataset.rv === '1') el.classList.add('rv-in'); }, 1500); });
  scan(); new MutationObserver(scan).observe(doc.body, { childList: true, subtree: true });
})();
</script>"""


def section_head(title: str, lead: str = "", center: bool = True) -> str:
    return (f'<div class="sec-head{" center" if center else ""} rv"><h2>{title}</h2>'
            + (f'<p>{lead}</p>' if lead else "") + "</div>")


def hero_preview(bands: dict) -> str:
    """Product preview in the hero: a styled mock of a result card with fixed sample values, clearly labelled."""
    lo, hi, p = bands["low_max"], bands["high_min"], 0.27
    seg = lambda c, a, b: f'<span style="left:{a:.0%};width:{b - a:.0%};background:{c}"></span>'  # noqa: E731
    meter = seg(RISK["Low"][0], 0, lo) + seg(RISK["Medium"][0], lo, hi) + seg(RISK["High"][0], hi, 1)
    factors = [("High blood pressure", 0.46), ("Body mass index 31", 0.31), ("Age 60 to 64", 0.23)]
    bars = "".join(f'<div class="pv-f"><span>{n}</span><i style="--w:{v:.0%}"></i><b>{v:.0%}</b></div>' for n, v in factors)
    color, tint, text, _ = RISK["Medium"]
    return f"""<div class="pv-wrap"><div class="pv" role="img" aria-label="Example result card with sample values: 27 percent, Medium risk">
<div class="pv-top"><span class="pv-k">Estimated risk</span><span class="pv-ex">Example</span></div>
<div class="pv-row"><span class="pv-num" style="color:{color}">27%</span><span class="pv-pill" style="background:{tint};color:{text}">Medium risk</span></div>
<div class="pv-meter">{meter}<em style="left:{p:.0%}"></em></div>
<div class="pv-ticks"><span style="left:0;transform:none">Low</span><span style="left:{(lo + hi) / 2:.0%}">Medium</span><span style="left:{(hi + 1) / 2:.0%}">High</span></div>
<div class="pv-k" style="margin-top:20px">What raised the score</div>{bars}
<div class="pv-note">Sample values for illustration. Not a real result.</div></div></div>"""


def stats_bento(meta: dict, opt: dict) -> str:
    """Dark band: four uneven tiles, each number paired with a small picture of the same fact."""
    n_rows, n_quick, n_full = meta.get("n_rows"), len(meta["features_short"]), len(meta["features_full"])
    rate = meta.get("positive_rate")
    recall = meta.get("metrics", {}).get("short", {}).get("recall")
    tiles = []
    if is_num(n_rows):
        dots = ""
        if is_num(rate):
            hit = round(rate * 100)
            dots = ('<div class="dots" aria-hidden="true">' + "".join(f'<i class="{"on" if i < hit else ""}"></i>' for i in range(100))
                    + f'</div><div class="tile-sub">{hit} in 100 reported a diabetes diagnosis</div>')
        tiles.append(f'<div class="tile t-a rv" style="--i:0"><div class="tile-num" data-count="{n_rows}" data-final="{n_rows:,}">'
                     f'{n_rows:,}</div><div class="tile-label">CDC survey responses behind every estimate</div>{dots}</div>')
    if is_num(recall):
        tiles.append(f'<div class="tile t-b rv" style="--i:1"><div class="tile-num" data-count="{recall * 100:.0f}" data-fmt="pct" '
                     f'data-final="{recall:.0%}">{recall:.0%}</div><div class="tile-label">of people with diagnosed diabetes are flagged '
                     f'by the quick check, on held-out test data</div><div class="minibar" aria-hidden="true"><i style="--w:{recall:.0%}">'
                     f'</i></div></div>')
    segs = "".join(f'<i class="{"on" if i < n_quick else ""}"></i>' for i in range(n_full))
    tiles.append(f'<div class="tile t-c rv" style="--i:2"><div class="tile-num"><span data-count="{n_quick}" data-final="{n_quick}">'
                 f'{n_quick}</span><small> of {n_full}</small></div><div class="tile-label">questions in the quick check, about a minute</div>'
                 f'<div class="segpill" aria-hidden="true">{segs}</div></div>')
    my = opt.get("multiyear") or {}
    years = sorted(my.get("years") or [])
    if len(years) > 1:
        tv = my.get("temporal_validation") or []
        first = tv[0].get("train_years") if tv else None
        saved = sorted((r for r in tv if r.get("train_years") == first and is_num(r.get("roc_auc"))), key=lambda r: r["test_year"])
        pts = [(meta.get("data_year"), meta.get("metrics", {}).get("full", {}).get("roc_auc"))] + [(r["test_year"], r["roc_auc"]) for r in saved]
        pts = [(y, a) for y, a in pts if is_num(y) and is_num(a)]
        spark = ""
        if len(pts) > 1:
            x0, x1 = pts[0][0], pts[-1][0]
            sx = lambda y: 14 + (y - x0) / ((x1 - x0) or 1) * 272  # noqa: E731
            sy = lambda a: 10 + (0.85 - a) / 0.06 * 44  # noqa: E731
            line = " ".join(f"{sx(y):.1f},{sy(a):.1f}" for y, a in pts)
            # first point is the training year's held-out test split, not an unseen year: drawn hollow and labelled
            marks = "".join(f'<circle{" class=\"base\"" if i == 0 else ""} cx="{sx(y):.1f}" cy="{sy(a):.1f}" r="2.6"/>'
                            f'<text x="{sx(y):.1f}" y="78">{y}{f"<tspan x={sx(y):.1f} dy=1.15em>test</tspan>" if i == 0 else ""}</text>'
                            for i, (y, a) in enumerate(pts))
            marks += "".join(f'<text class="val" x="{sx(y):.1f}" y="{sy(a) - 7:.1f}">{a:.2f}</text>' for y, a in (pts[0], pts[-1]))
            spark = (f'<svg class="spark" viewBox="0 0 300 98" role="img" aria-label="ROC-AUC by survey year, from '
                     f'{pts[0][1]:.2f} to {pts[-1][1]:.2f}"><polyline points="{line}"/>{marks}</svg>')
        later = [y for y in years if y != meta.get("data_year")]
        tiles.append(f'<div class="tile t-d rv" style="--i:3"><div class="tile-num sm">Held up on {len(later)} later survey years, '
                     f'{years_label(later)}</div><div class="tile-label">ROC-AUC on the {meta.get("data_year", "")} held-out test set, '
                     f'then on later surveys the model never saw'
                     f'</div>{spark}</div>')
    return f'<div class="bento">{"".join(tiles)}</div>'


def cta_band():
    with st.container(key="band_cta"):
        n_quick = len(APP["meta"]["features_short"])
        st.markdown(f'<div class="cta-inner rv"><h2>Ready to check your risk?</h2>'
                    f'<p>{n_quick} questions, about a minute. No sign-up, and nothing is stored.</p></div>', unsafe_allow_html=True)
        _, mid, _ = st.columns([1, 1, 1])
        if mid.button("Start your risk check", type="primary", key="cta_band_start", width="stretch"):
            st.switch_page(APP["pages"]["risk"])


def site_footer():
    mark = svg_data_uri(LOGO_MARK)
    st.markdown(f"""<div class="site-footer" role="contentinfo"><div class="ft-grid">
<div><div class="ft-brand">{f'<img src="{mark}" width="32" height="32" alt="">' if mark else ''}{BRAND_NAME}</div>
<p>A one-minute diabetes risk screening questionnaire. Educational project.</p></div>
<div><h3>Data</h3><p>CDC Behavioral Risk Factor Surveillance System, via the <a href="{DATA_URL}">UCI Machine Learning Repository</a>.</p></div>
<div><h3>Important</h3><p>{DISCLAIMER}</p></div>
<div><h3>Source code</h3><p><a href="{REPO_URL}">GitHub repository{icon("external", 14, "ico-inline")}</a></p></div>
</div></div>""", unsafe_allow_html=True)


# ---------- Pages ----------

APP: dict = {}  # loaded artifacts and page objects, filled in main()


def page_header(title: str, subtitle: str):
    st.markdown(f'<div class="hero"><h1>{title}</h1><p>{subtitle}</p>'
                '<span class="pill">Screening aid, not a diagnosis</span></div>', unsafe_allow_html=True)


def pipeline_html(meta: dict) -> str:
    n_rows = meta.get("n_rows")
    steps = [("database", "Data", f"BRFSS {meta.get('data_year', '')}" + (f", {n_rows:,} responses" if is_num(n_rows) else "")),
             ("filter", "Cleaning", "Duplicates removed, answers recoded"),
             ("layers", "Models", "Logistic regression, random forest, gradient boosting"),
             ("sliders", "Calibration", "Percentages match observed rates"),
             ("target", "Threshold", "Cut-off chosen to catch about 80% of cases"),
             ("devices", "App", "Plain-language result and next steps")]
    items = "".join(f'<li class="rv" style="--i:{i}"><span class="pl-ico">{icon(ic, 22)}</span><b>{t}</b><span>{d}</span></li>'
                    for i, (ic, t, d) in enumerate(steps))
    return section_head("From survey answers to your result", center=False) + f'<ol class="pipeline">{items}</ol>'


def metric_tiles(metrics: dict, names: dict, shown: dict) -> str:
    tiles = []
    for mk, (label, fmt) in shown.items():
        rows = [(names.get(k, k), m.get(mk)) for k, m in metrics.items() if is_num(m.get(mk))]
        if not rows:
            continue
        low_best = mk == "brier"
        hi, lo = max(v for _, v in rows) or 1, min(v for _, v in rows)
        width = (lambda v: lo / v if v else 1) if low_best else (lambda v: v / hi)
        bars = "".join(f'<div class="mt-row{" base" if n == "Baseline" else ""}"><span>{n}</span><i style="--w:{width(v):.0%}"></i>'
                       f'<b>{fmt.format(v)}</b></div>' for n, v in rows)
        note = '<span class="mt-note">lower is better, longest bar = best</span>' if low_best else ""
        tiles.append(f'<div class="mtile rv"><div class="mt-label">{label}{note}</div>{bars}</div>')
    return f'<div class="mtiles">{"".join(tiles)}</div>'



def svg_data_uri(path: Path) -> str:
    try:
        return "data:image/svg+xml;base64," + base64.b64encode(path.read_bytes()).decode()
    except OSError:
        return ""


def home_page():
    meta, opt = APP["meta"], APP["opt"]
    n_rows, n_quick = meta.get("n_rows"), len(meta["features_short"])
    mark = svg_data_uri(LOGO_MARK)
    with st.container(key="band_hero"):
        left, right = st.columns([1.15, 1], gap="large", vertical_alignment="center")
        with left, st.container(key="home_hero"):
            st.markdown(
                f"""<div class="brandline">{f'<img src="{mark}" width="44" height="44" alt="">' if mark else ''}{BRAND_NAME}</div>
<h1>Know your diabetes risk in about a minute.</h1>
<p class="lead">A free screening questionnaire built on {f"{n_rows:,} " if n_rows else ""}CDC health survey responses.
See your estimated risk, which answers drive it, and whether to ask a doctor for a blood sugar test.</p>""",
                unsafe_allow_html=True)
            a, b = st.columns(2, gap="small")
            if a.button("Start your risk check", type="primary", key="home_cta_start", width="stretch"):
                st.switch_page(APP["pages"]["risk"])
            if "insights" in APP["pages"] and b.button("See population insights", key="home_cta_insights", width="stretch"):
                st.switch_page(APP["pages"]["insights"])
            st.markdown('<span class="pill hero-pill">Screening aid, not a diagnosis</span>', unsafe_allow_html=True)
        with right:
            st.markdown(hero_preview(meta["risk_bands"]), unsafe_allow_html=True)

    steps = [("questionnaire", f"Answer {n_quick} questions", "About your health, habits and background. No sign-up, and nothing is stored."),
             ("gauge", "See your estimate", "A percentage and a Low, Medium or High level, with the answers that raised it."),
             ("signpost", "Know your next step", "Plain advice on whether to ask for a blood sugar test, plus what-if changes to explore.")]
    with st.container(key="band_how"):
        st.markdown(section_head("How it works", "Three steps, one minute, and a clear answer about whether to get tested.")
                    + '<ol class="stepper">' + "".join(
                        f'<li class="rv" style="--i:{i}"><span class="st-ico">{icon(ic, 26)}</span><h3>{t}</h3><p>{d}</p></li>'
                        for i, (ic, t, d) in enumerate(steps)) + "</ol>", unsafe_allow_html=True)
        _, mid, _ = st.columns([1, 1, 1])
        if mid.button("Learn how the model works", type="tertiary", key="home_cta_about", width="stretch"):
            st.switch_page(APP["pages"]["about"])

    audiences = [("person", "Individuals", "A private, one-minute check before deciding whether to book a blood test."),
                 ("stethoscope", "Clinics", "A plain-language conversation starter for intake and waiting rooms."),
                 ("people", "Public-health teams", "Population profiles and a screening cost planner for outreach programs.")]
    with st.container(key="band_built"):
        st.markdown(section_head("Built for", "One questionnaire, three ways to use it.") + '<div class="aud">' + "".join(
            f'<div class="aud-tile rv" style="--i:{i}"><span class="aud-ico">{icon(ic, 24)}</span><h3>{t}</h3><p>{d}</p></div>'
            for i, (ic, t, d) in enumerate(audiences)) + "</div>", unsafe_allow_html=True)

    with st.container(key="band_stats"):
        st.markdown(section_head("By the numbers", "Every figure comes from held-out test data or the survey itself.")
                    + stats_bento(meta, opt), unsafe_allow_html=True)
        st.markdown(f'<div class="note band-note">{DISCLAIMER}</div>', unsafe_allow_html=True)


def risk_page():
    meta, opt = APP["meta"], APP["opt"]
    page_header("Risk check", "Answer a few questions to see how your answers compare with people who reported "
                "a diabetes diagnosis.")
    quick, full = st.tabs(["Quick check", "Full check"], key="risk_tabs")
    with quick:
        check_tab(APP["short_model"], meta["features_short"], meta["explainer_short"], meta["risk_bands"], "quick",
                  f"{len(meta['features_short'])} questions, about a minute.", opt)
    with full:
        check_tab(APP["full_model"], meta["features_full"], meta["explainer"], meta["risk_bands"], "full",
                  f"All {len(meta['features_full'])} questions for a more detailed estimate, plus your population profile.", opt)


def insights_page():
    page_header("Population insights", "Who tends to be at risk, and what screening a population would involve.")
    insights_tab(APP["opt"], APP["meta"])


def about_page():
    page_header("How it works", "The data, the models, how well they perform, and their limits.")
    how_it_works(APP["meta"], APP["opt"])


def main():
    st.set_page_config(page_title=BRAND_NAME, page_icon=str(FAVICON) if FAVICON.exists() else None,
                       layout="wide", initial_sidebar_state="collapsed")
    st.markdown(CSS, unsafe_allow_html=True)
    st.html(MOTION_JS, unsafe_allow_javascript=True)
    if LOGO.exists():
        st.logo(str(LOGO), icon_image=str(LOGO_MARK) if LOGO_MARK.exists() else None, size="large")

    try:
        APP["full_model"], APP["short_model"], APP["meta"] = load_artifacts(str(MODELS_DIR), file_stamp(MODELS_DIR, BASE_FILES))
    except Exception:
        page_header(BRAND_NAME, "Diabetes risk screening")
        st.error("The risk model isn't available right now, so the check can't run. "
                 "If you run this app, make sure the trained model files are in the `models/` folder.")
        st.stop()
    APP["opt"] = load_optional(str(MODELS_DIR), file_stamp(MODELS_DIR))

    pages = {"home": st.Page(home_page, title="Home", url_path="home", default=True),
             "risk": st.Page(risk_page, title="Risk check", url_path="risk-check")}
    if any(APP["opt"][k] is not None for k in ("segments", "curve", "multiyear", "states")):
        pages["insights"] = st.Page(insights_page, title="Population insights", url_path="population-insights")
    pages["about"] = st.Page(about_page, title="How it works", url_path="how-it-works")
    APP["pages"] = pages
    page = st.navigation(list(pages.values()), position="top")
    page.run()
    if page.url_path != pages["risk"].url_path:
        cta_band()
    site_footer()


main()
