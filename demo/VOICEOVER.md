# SugarScope demo: voiceover script (v2)

Told as a short story for a hiring manager: problem, idea, you using it, the aha, the bigger picture, proof, call to action.
Voice: `en-US-AndrewMultilingualNeural`, chosen by the user. About 120 words over roughly 60 to 65 s.

How this file is used: `demo/voiceover.py` reads every `## scene` heading.
- `>` is the line as written. It is also the on-screen caption, highlighted word by word as it is spoken.
- `say:` (optional) is how the line is spoken, when that differs from how it is written.
- `prosody:` (optional) sets edge-tts `rate` and `pitch` for that line. The default is `rate=+2% pitch=+0Hz`.
- Punctuation shapes the pauses: commas for short breaths, em dashes for a beat.
- Each scene lasts at least as long as its line plus a short gap (about 0.3 s), so lines never get cut off. Music fills the longer visual scenes.
- The intro and outro lines are not captioned, because their cards carry the same words.

## Claim sources
Every spoken claim, and where it comes from:
- "More than one in four adults with diabetes don't know they have it": CDC National Diabetes Statistics Report, "At a glance" (updated Sept. 16, 2026). 27.6% of adults aged 18 and older with diabetes are undiagnosed (11.0 million of 40.1 million). https://www.cdc.gov/diabetes/php/data-research/index.html
- "Six quick questions": the Quick check in `app.py` (6 inputs).
- "229,474 real survey answers": `models/meta.json` `n_rows` (cleaned BRFSS 2015 responses; training used the 80% split, so the line says "built on").
- "Catches 81 percent of diagnosed cases": `reports/results.csv`, SHORT (6 questions) on held-out test data, recall 0.8115.
- "Held up on four later survey years": `models/multiyear.json` `temporal_validation`. Trained on 2015, tested on 2017, 2019, 2021 and 2025 (956,642 responses), lowest ROC-AUC 0.803.
- "Watch it fall": the scripted what-if (weight 104 to 80 kg, then blood pressure treated). The last take went from 45% to 18%.
- Spoken numbers, apart from the CDC fraction: three (229,474, 81 percent, four later years).

## intro
> More than one in four adults with diabetes don't know they have it.

prosody: rate=+0% pitch=-2Hz

## home
> So what if one minute could tell you whether it's worth getting tested?

prosody: rate=+2% pitch=+1Hz

## start
(no line: the click and the page change speak for themselves)

## fill
> You answer six quick questions — age, weight, a little health history. No sign-up, nothing stored.

prosody: rate=+4% pitch=+0Hz

## result
> And there it is — your risk level, and exactly which answers pushed it up.

prosody: rate=+2% pitch=+0Hz

## whatif
> Now the fun part. Drop the weight, treat that blood pressure... and watch it fall.

prosody: rate=+0% pitch=+3Hz

## segments
> Zoom out, and public-health teams can see who to reach first,

prosody: rate=+3% pitch=+0Hz

## cost
> and what screening them would actually cost.

prosody: rate=+3% pitch=-1Hz

## validation
> It's built on 229,474 real survey answers, catches 81 percent of diagnosed cases, and held up on four later survey years.

say: It's built on two hundred twenty-nine thousand real survey answers, catches eighty-one percent of diagnosed cases, and held up on four later survey years.

prosody: rate=+4% pitch=+0Hz

## outro
> Try it yourself — the link's below. Just remember: it's a screening aid, not a diagnosis.

prosody: rate=+0% pitch=+1Hz

## Commands
- `.venv/Scripts/python demo/voiceover.py tts` renders the lines with word timings into `demo/build/vo/` and writes `timings.json` (needs the internet, no ffmpeg).
- `.venv/Scripts/python demo/voiceover.py all --live-url URL --music PATH` renders the lines, records the take, builds the framed and zoomed video, mixes voice, music and UI sounds, and writes every output.
