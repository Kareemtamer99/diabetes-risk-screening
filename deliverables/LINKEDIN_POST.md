# LinkedIn post

Paste the text between the lines. Tag NextGen Institute's page where it is named, and attach `demo/demo_square.mp4` (or `demo/demo_1080p.mp4`) as the video.
Every number is listed with its source in `NUMBERS.md`.

## Main version

---

Many people with type 2 diabetes do not know it yet. A blood test can confirm it. The hard part is deciding who should get one.

As my final project for the AI & Machine Learning Internship at NextGen Institute, I built SugarScope: a one-minute diabetes risk check trained on 229,474 answers to the CDC's national health survey.

What it does:
- Asks 6 questions: blood pressure, cholesterol, BMI, general health, sex and age
- Shows a risk level and which answers raised it
- Lets screening planners weigh cases found against testing cost

What I used, simply:
- Data: the CDC health survey, cleaned (duplicate answers removed)
- Models: I compared logistic regression, random forest and gradient boosting, then kept gradient boosting
- Tuning: I set the cut-off so the model catches as many real cases as possible, since a missed case matters more than an extra blood test
- App: Python and Streamlit, so anyone can try it in the browser

Results on 45,895 people the model never saw:
- The 6-question check catches 81% of diagnosed diabetes cases, as many as the full 21-question version (80%)
- At an assumed $20 per test, that is about $66 per case found, against $131 when testing everyone
- It held up on 4 later survey years (2017 to 2025) without retraining

The biggest lesson: at the default setting my best model caught only 15% of cases. Choosing the cut-off mattered more than choosing the algorithm.

A big thank you to NextGen Institute and my mentors for the guidance, the feedback and the chance to build something real.

Demo in the video. SugarScope is a screening aid, not a diagnosis.

Live app: https://diabetesrisk-screening.streamlit.app/
Code: https://github.com/Kareemtamer99/diabetes-risk-screening

#MachineLearning #AI #DataScience #HealthTech #Internship

---

## Short version

---

Six questions, one minute: is it worth asking your doctor for a diabetes test?

That is SugarScope, my final project for the AI & Machine Learning Internship at NextGen Institute, trained on 229,474 CDC health survey responses.

On 45,895 held-out people, the 6-question model catches 81% of diagnosed diabetes cases, about the same as using all 21 questions, and it held up on 4 later survey years. The biggest gain came from tuning the decision threshold for recall: the default cut-off caught only 15%.

Screening aid, not a diagnosis. Demo in the video.

Live app: https://diabetesrisk-screening.streamlit.app/
Code: https://github.com/Kareemtamer99/diabetes-risk-screening

Thank you to NextGen Institute and my mentors.

#MachineLearning #DataScience #HealthTech

---
