# Demo video storyboard

Final cut: 57.8 seconds, 1920x1080, 30 fps, no audio (LinkedIn autoplays muted, so the captions carry the story).
Audience: hiring managers scrolling LinkedIn. Captions are short, confident, and readable on a phone.

`record.py` drives every scene. Timings are approximate; the script logs the real ones to `demo/build/scenes.json`.

| # | Scene | Time | What happens on screen | Caption |
|---|-------|------|------------------------|---------|
| 1 | Hook | 0.0 to 5.2 s | Title card on the brand navy background. Hook line fades up, then the subline. | Millions of adults have diabetes and don't know it. / A one-minute risk check built on 229,474 CDC survey responses. |
| 2 | Home | 5.2 to 7.9 s | App home page. Cursor drifts across the hero. | Diabetes risk screening, in about a minute. |
| 3 | Start | 7.9 to 11.0 s | Cursor glides to "Start your risk check" and clicks (ripple). | Six questions. No sign-up. |
| 4 | Quick check | 11.0 to 26.7 s | Quick check form: Yes to high blood pressure and high cholesterol, weight typed, general health "Fair", age typed. Click "Check my risk". | Six questions from the CDC's BRFSS health survey. |
| 5 | Result | 26.7 to 32.3 s | Result panel: big percentage, risk pill, band meter, factor bars. Pause so it can be read. | A clear risk level, and the answers behind it. |
| 6 | What-if | 32.3 to 43.5 s | Drag the weight slider down, switch on "exercised regularly" (or "blood pressure under control" on the Quick check), watch "With changes" update. | What if? Lower weight, get active, watch the risk drop. (Quick check: "treat blood pressure" instead of "get active".) |
| 7a | Insights: segments | 43.5 to 48.6 s | Population insights page, the profile cards and PCA scatter. | Population profiles found by clustering (count read from the model, currently four). |
| 7b | Insights: cost | 48.6 to 54.2 s | Drag the cut-off slider in the screening cost planner; metrics and curve update. | Plan a screening program: cases caught versus cost. |
| 8 | Outro | 54.2 to 57.8 s | Logo, product name, "Live app" and "GitHub" links, disclaimer. | Screening aid, not a medical diagnosis. |

Captions never say the model predicts prediabetes: the target is diagnosed diabetes only.

## Outro card text
- Logo: `assets/logo_mark.svg` beside the SugarScope wordmark. If `assets/logo.svg` is newer than the mark (a rebrand that only updated the full logo), the full logo is shown on a white chip instead. Plain wordmark if both are missing. `--name` changes the name.
- Live app: `LIVE_APP_URL` placeholder
- GitHub: `GITHUB_URL` placeholder
- Screening aid, not a medical diagnosis.

Set the real links with `--live-url` and `--github-url` when recording.

## Outputs
- `demo_1080p.mp4`: full video, H.264, yuv420p, 30 fps, faststart, no audio
- `demo_square.mp4`: 1080x1080, letterboxed on brand navy so the whole screen stays visible on mobile feeds
- `demo.gif`: 14 s of result and what-if, sped up about 1.4x, 960 px wide, for the README
- `thumbnail.png`: result frame
- `screenshots/`: home, result, what-if, insights at 1920x1080, clean (no cursor or captions)

## Re-recording
`.venv/Scripts/python demo/record.py --live-url <url> --github-url <url>` re-records everything in about 3 minutes.
If a take runs past 59 s (slow reruns on a loaded machine), post-processing speeds the whole cut up uniformly, at most about 15%.
`--dry-run` checks every step quickly and refreshes the screenshots; `--post-only` re-encodes the last take.

## Voiceover
Narration lines are in `VOICEOVER.md`. `voiceover.py all` renders them and re-records with each scene held until its line ends.
It then writes `demo_1080p_vo.mp4` and `demo_square_vo.mp4` (AAC 160 kbps, 48 kHz, -16 LUFS). The silent MP4s and the GIF stay too.
A validation scene, after the cost planner, shows the multi-year summary with the caption "Checked on 4 later survey years: ROC-AUC held above 0.80."
