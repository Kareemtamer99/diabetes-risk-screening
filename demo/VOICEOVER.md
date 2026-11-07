# SugarScope demo: voiceover script

For a hiring manager: plain, confident, one idea per scene. About 120 words over the roughly 58 s cut.
Voice: `en-US-AndrewNeural`, chosen by the user (the comparison samples are in `voice_samples/`).

How this file is used: `demo/voiceover.py` reads every `## scene` heading and the `>` line under it.
- Only the `>` line is spoken.
- `say:` (optional) is how the line is spoken, when it should differ from how it is written.
- `caption:` is the burn-in caption that scene shows, kept close to the line. Captions live in `record.py`; this copy is for review.
- Each scene lasts at least as long as its clip plus a short gap, so the narration never gets cut off.

Every number comes from the result files: `models/meta.json` (229,474 cleaned survey responses; training used the 80% split, so the line says "built on", not "learned from"), `reports/results.csv` (the 6-question check catches 81.2% of people with diagnosed diabetes on held-out data), and `models/multiyear.json` `temporal_validation`: trained on 2015, tested on 4 later years (2017, 2019, 2021, 2025), test n summing to 956,642, lowest ROC-AUC 0.803.

## intro
> Millions of American adults have diabetes, and don't know it.

caption: (title card) Millions of adults have diabetes and don't know it.

## home
> SugarScope is a one-minute diabetes risk check.

caption: Diabetes risk screening, in about a minute.

## start
(no line: the caption says it)

caption: Six questions. No sign-up.

## fill
> Six questions from the CDC's health survey. Built on 229,474 real responses, the quick check catches 81 percent of people with diagnosed diabetes.

say: Six questions from the C D C's health survey. Built on two hundred twenty-nine thousand real responses, the quick check catches eighty-one percent of people with diagnosed diabetes.


caption: Six questions from the CDC's BRFSS health survey.

## result
> You get a clear risk level, and the answers that raised it.

caption: A clear risk level, and the answers behind it.

## whatif
> Then ask, what if? Change your weight or a health habit, and watch the estimate drop.

caption: What if? Lower weight, treat blood pressure (or get active, if that toggle shows), watch the risk drop.

## segments
> For public health teams, clustering finds four population profiles,

caption: 4 population profiles found by clustering.

## cost
> and a planner weighs cases caught against the cost of testing.

caption: Plan a screening program: cases caught versus cost.

## validation
> Checked against four later survey years, nearly a million new responses, its accuracy score held above 0.80.

say: Checked against four later survey years, nearly a million new responses, the A U C held above point eight.

caption: Checked on 4 later survey years: ROC-AUC held above 0.80.

## outro
> SugarScope. A screening aid, not a diagnosis. Try it live, or read the code on GitHub.

caption: (outro card) Live app and GitHub links. Screening aid, not a medical diagnosis.

## Planned timing (Andrew, +5%)
128 words, 46.1 s of speech. The estimated take is about 63 s against the 60 s limit; the real length is known only after the take.
If it runs over 60 s, the first trims are the home and segments holds, before any narration changes.
The what-if line says "drop" because both scripted changes lower risk: weight 104 to 80 kg, then blood pressure treated. The form now sets only age, weight and blood pressure Yes.

## Commands
- `.venv/Scripts/python demo/voiceover.py all --live-url URL`: tts, then record, then mix (about 4 min).
- `tts` alone renders the clips and `demo/build/timings.json` (internet, no ffmpeg). `--samples` re-renders the voice comparison.
- Delete `demo/build/timings.json` to record the silent version with its old pacing.
