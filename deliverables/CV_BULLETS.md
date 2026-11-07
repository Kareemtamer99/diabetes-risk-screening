# CV bullets

Pick one. Every number is listed with its source in `NUMBERS.md`.

1. **Course format.** Built a diabetes risk-screening tool from ~250K CDC survey responses (BRFSS), reducing the questionnaire from 21 to 6 key questions while keeping recall at 81% (ROC-AUC 0.812) on a 45,895-person held-out test set, using Python, scikit-learn and Streamlit.

2. **Modelling focus.** Trained and calibrated a gradient-boosting classifier on 229,474 de-duplicated BRFSS records, tuning the decision threshold to raise recall from 15% to 80% and cutting the estimated cost per case found from $131 to $64 compared with testing everyone (assumed $20 per test), using scikit-learn and pandas.

3. **Product focus.** Designed and deployed SugarScope, a Streamlit diabetes screening app with a 6-question quick check, what-if analysis and k-means population segments (highest-risk segment: 32% prevalence vs 15% overall), backed by a leak-free scikit-learn pipeline trained on 229,474 survey records.

## Portfolio one-liner

SugarScope: a one-minute, six-question diabetes risk check trained on 229,474 CDC survey responses that catches 81% of diagnosed diabetes cases in held-out testing.
