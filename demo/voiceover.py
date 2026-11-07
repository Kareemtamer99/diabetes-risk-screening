"""Narration, sound and finishing for the demo video. Script: demo/VOICEOVER.md. Voice: edge-tts (needs the internet).

  python demo/voiceover.py tts                 render each scene's line with word timings, write build/timings.json
  python demo/voiceover.py mix --music PATH    build the final videos from the last take (record.py)
  python demo/voiceover.py all --live-url URL --music PATH   tts, then record.py, then mix

record.py reads timings.json and holds each scene until its line has been spoken. mix then:
- frames, zooms and captions the take (effects.py)
- mixes the voice, music ducked under it, and soft UI sounds (clicks, page-change whooshes)
- normalises to -14 LUFS, true peak -1.5 dB, and writes
  demo_1080p_vo.mp4, demo_square_vo.mp4 (narrated), demo_1080p.mp4, demo_square.mp4 (no audio),
  demo.gif and thumbnail.png
"""
import argparse
import asyncio
import json
import re
import subprocess
import sys
import time
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import effects  # noqa: E402
from record import BUILD, CUT_SKIP, DEMO, FFMPEG, ROOT, TIMINGS_FILE, VO_LEAD, ff, probe_duration  # noqa: E402

SCRIPT = DEMO / "VOICEOVER.md"
CLIPS = BUILD / "vo"
VOICE = "en-US-AndrewMultilingualNeural"
DEFAULT_PROSODY = {"rate": "+2%", "pitch": "+0Hz"}
NO_CAPTION = {"intro", "outro"}  # their cards carry the same words


def parse(text: str) -> dict[str, dict]:
    """'## scene' blocks -> {scene: {"line", "say", "rate", "pitch"}}, in order."""
    out = {}
    for block in re.split(r"^## ", text, flags=re.M)[1:]:
        name = block.split("\n", 1)[0].strip()
        line = re.search(r"^> (.+)$", block, re.M)
        if not line:
            continue
        say = re.search(r"^say: (.+)$", block, re.M)
        pros = dict(DEFAULT_PROSODY)
        if m := re.search(r"^prosody: (.+)$", block, re.M):
            pros.update(dict(kv.split("=", 1) for kv in m[1].split()))
        out[name] = {"line": line[1].strip(), "say": (say or line)[1].strip(), **pros}
    return out


def mp3_seconds(path: Path) -> float:
    """edge-tts writes constant 48 kbps mono MP3, so size gives length without launching ffmpeg."""
    return path.stat().st_size * 8 / 48000


async def _tts(text: str, voice: str, rate: str, pitch: str, dest: Path) -> list[dict]:
    import edge_tts
    words = []
    with open(dest, "wb") as f:
        async for c in edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, boundary="WordBoundary").stream():
            if c["type"] == "audio":
                f.write(c["data"])
            elif c["type"] == "WordBoundary":
                words.append({"text": c["text"], "t": c["offset"] / 1e7, "d": c["duration"] / 1e7})
    return words


def cmd_tts(args):
    lines = parse(SCRIPT.read_text(encoding="utf-8"))
    CLIPS.mkdir(parents=True, exist_ok=True)
    for old in CLIPS.glob("*.*"):
        old.unlink()
    timings, words = {}, 0
    for name, v in lines.items():
        clip = CLIPS / f"{name}.mp3"
        for attempt in range(4):  # the TTS service drops a request now and then
            try:
                bounds = asyncio.run(_tts(v["say"], args.voice, v["rate"], v["pitch"], clip))
                break
            except Exception as e:  # noqa: BLE001
                if attempt == 3:
                    raise
                print(f"    retrying {name}: {type(e).__name__}", flush=True)
                time.sleep(2 + 3 * attempt)
        (CLIPS / f"{name}.json").write_text(json.dumps(bounds, indent=1), encoding="utf-8")
        timings[name] = round(mp3_seconds(clip), 2)
        words += len(v["line"].split())
        print(f"  {name:11s} {timings[name]:5.2f}s  {v['rate']:>4} {v['pitch']:>5}  {v['line']}", flush=True)
    TIMINGS_FILE.write_text(json.dumps(timings, indent=2), encoding="utf-8")
    speech = sum(timings.values())
    print(f"{words} words, {speech:.1f}s of speech ({words / speech * 60:.0f} wpm), voice {args.voice}", flush=True)


def placements(scenes: list, cut: dict, clips: dict) -> list[tuple[str, float]]:
    """(scene, seconds into the cut) for each scene that was recorded and has a clip."""
    t = {s["name"]: s["t"] for s in scenes}
    return [(n, max(0.0, (t[n] - cut["start"]) / cut["k"]) + VO_LEAD) for n in clips if n in t]


# ---------------------------------------------------------------- audio

def sfx_assets():
    """Soft UI sounds, synthesised (no downloads): a short filtered tick and a pink-noise whoosh."""
    ff("-f", "lavfi", "-i", "anoisesrc=d=0.03:c=white:a=0.5", "-af",
       "highpass=f=2200,lowpass=f=7000,afade=t=out:st=0:d=0.03", "-ar", "48000", "-ac", "2", effects.FX / "click.wav")
    ff("-f", "lavfi", "-i", "anoisesrc=d=0.5:c=pink:a=0.6", "-af",
       "highpass=f=250,lowpass=f=2200,afade=t=in:d=0.2:curve=qsin,afade=t=out:st=0.2:d=0.3:curve=qsin",
       "-ar", "48000", "-ac", "2", effects.FX / "whoosh.wav")


def loudness(path: Path, extra: str = "") -> dict:
    """loudnorm analysis (input_i, input_tp, input_lra, input_thresh, target_offset) of a file."""
    af = "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json" + extra
    err = subprocess.run([FFMPEG, "-hide_banner", "-i", str(path), "-af", af, "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    return json.loads(err[err.rindex("{"):err.rindex("}") + 1])


def segment_lufs(path: Path, t0: float, dur: float) -> float:
    """Integrated loudness of one stretch of a file."""
    err = subprocess.run([FFMPEG, "-hide_banner", "-ss", f"{t0:.3f}", "-t", f"{dur:.3f}", "-i", str(path),
                          "-af", "ebur128", "-f", "null", "-"], capture_output=True, text=True).stderr
    return float(re.findall(r"I:\s+(-?[\d.]+) LUFS", err)[-1])


def speech_and_gap(place, clips, k, sounds=()) -> tuple[tuple[float, float], tuple[float, float]]:
    """The longest narrated stretch and the longest music-only gap (no line, no UI sound), as (start, length)."""
    spans = sorted((at, at + mp3_seconds(clips[n]) / k) for n, at in place)
    speech = max(spans, key=lambda s: s[1] - s[0])
    gaps = [(a[1] + 0.4, b[0] - 0.2) for a, b in zip(spans, spans[1:])]  # skip the duck's release tail
    pieces = []  # split each gap at UI sounds, keeping clear of each by 0.3 s
    for g0, g1 in gaps:
        cuts = sorted(t for t in sounds if g0 < t < g1)
        edges = [g0] + [x for t in cuts for x in (t - 0.3, t + 0.6)] + [g1]
        pieces += [(edges[i], edges[i + 1]) for i in range(0, len(edges), 2)]
    gap = max(pieces, key=lambda g: g[1] - g[0])
    return (speech[0] + 0.3, speech[1] - speech[0] - 0.6), (gap[0], gap[1] - gap[0])


def norm2(src: Path, dest: Path, i: float, tp: float):
    """Static gain to i LUFS, then a peak limiter at tp dB. (loudnorm falls back to its dynamic mode when peaks are
    high, and that acts like an automatic gain control: it lifted the quiet music gaps by about 7 dB.)"""
    gain = i - float(loudness(src)["input_i"])
    ff("-i", src, "-af", f"volume={gain:.2f}dB,alimiter=limit={10 ** (tp / 20):.4f}:attack=5:release=60:level=false,"
                         "aresample=48000", "-ar", "48000", "-ac", "2", dest)


def mix_audio(place, clips, cut, vdur, events, rel, music: Path | None, music_start: float = 0.0) -> Path:
    k = cut["k"]
    inputs = ["-f", "lavfi", "-t", f"{vdur:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]  # 0: bed of exact length
    chains, vox, n = [], [], 0  # n: index of the last input added
    for name, at in place:
        inputs += ["-i", clips[name]]
        n += 1
        i, ms = n, int(at * 1000)
        chains.append(f"[{i}:a]atempo={k:.4f},aresample=48000,aformat=channel_layouts=stereo,adelay={ms}|{ms}[v{i}]")
        vox.append(f"[v{i}]")
    clicks = [rel(e["t"]) for e in events if e["type"] == "click"]
    whooshes = [max(0, rel(e["t"]) - 0.12) for e in events if e["type"] == "whoosh"]
    ci, wi = n + 1, n + 2
    inputs += ["-i", effects.FX / "click.wav", "-i", effects.FX / "whoosh.wav"]
    fxs = []
    if clicks:
        chains.append(f"[{ci}:a]volume=0.06,asplit={len(clicks)}" + "".join(f"[c{j}]" for j in range(len(clicks))))
        for j, t in enumerate(clicks):
            chains.append(f"[c{j}]adelay={int(t * 1000)}|{int(t * 1000)}[cd{j}]")
            fxs.append(f"[cd{j}]")
    if whooshes:
        chains.append(f"[{wi}:a]volume=0.1,asplit={len(whooshes)}" + "".join(f"[w{j}]" for j in range(len(whooshes))))
        for j, t in enumerate(whooshes):
            chains.append(f"[w{j}]adelay={int(t * 1000)}|{int(t * 1000)}[wd{j}]")
            fxs.append(f"[wd{j}]")
    # Stage 1: voice + UI sounds, normalised on their own to -14 LUFS, so the voice sets the loudness.
    chains.append(f"[0:a]{''.join(vox)}{''.join(fxs)}amix=inputs={len(vox) + len(fxs) + 1}:normalize=0:duration=first[out]")
    fore_raw, fore = BUILD / "fore_raw.wav", BUILD / "fore.wav"
    ff(*inputs, "-filter_complex", ";".join(chains), "-map", "[out]", "-ar", "48000", "-ac", "2", fore_raw)
    norm2(fore_raw, fore, -14, -2.0)
    out = BUILD / "mix.wav"
    if not music:
        norm2(fore, out, -14, -1.5)
    else:
        # Stage 2: a barely-there bed at -32 LUFS under the normalised voice, ducked about 12 dB more while it speaks.
        graph = (f"[0:a]asplit=2[fa][key];[1:a]atrim={music_start:.3f}:{music_start + vdur:.3f},asetpts=N/SR/TB,"
                 "aresample=48000,aformat=channel_layouts=stereo,loudnorm=I=-32:TP=-9:LRA=11,aresample=48000,"
                 f"afade=t=in:d=1.5,afade=t=out:st={vdur - 2:.3f}:d=2[mus];"
                 "[mus][key]sidechaincompress=threshold=0.01:ratio=12:attack=15:release=350:makeup=1[duck];"
                 "[fa][duck]amix=inputs=2:normalize=0:duration=first[out]")
        pre = BUILD / "mix_pre.wav"
        ff("-i", fore, "-stream_loop", "-1", "-i", music, "-filter_complex", graph, "-map", "[out]",
           "-ar", "48000", "-ac", "2", pre)
        norm2(pre, out, -14, -2.0)  # a small final trim; -2 dB target keeps the AAC encode under -1.5 dBTP
    with wave.open(str(out)) as w:
        got = w.getnframes() / w.getframerate()
    assert abs(got - vdur) < 0.25, f"audio is {got:.2f}s but the video is {vdur:.2f}s"
    return out


# ---------------------------------------------------------------- finishing

X264 = ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-profile:v", "high", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart"]


def cmd_mix(args):
    scenes = json.loads((BUILD / "scenes.json").read_text(encoding="utf-8"))
    events = json.loads((BUILD / "events.json").read_text(encoding="utf-8"))
    cut = json.loads((BUILD / "cut.json").read_text(encoding="utf-8"))
    rel = lambda t: max(0.0, (t - cut["start"]) / cut["k"])  # noqa: E731
    t = {s["name"]: rel(s["t"]) for s in scenes}
    clips = {p.stem: p for p in sorted(CLIPS.glob("*.mp3"))}
    place = placements(scenes, cut, clips)
    if not place:
        sys.exit("no clips match the recorded scenes: run `voiceover.py tts` before record.py")
    cutfile = BUILD / "cut.mp4"
    vdur = probe_duration(cutfile)
    lines = parse(SCRIPT.read_text(encoding="utf-8"))

    if args.audio_only:
        return remix(args, place, clips, cut, events, rel)

    print("building effects: window, zoom, captions", flush=True)
    effects.make_assets(re.sub(r"^https?://", "", args.live_url).rstrip("/"))
    cap = [(at, cut["k"], effects.align(lines[n]["line"], json.loads((CLIPS / f"{n}.json").read_text(encoding="utf-8"))))
           for n, at in place if n not in NO_CAPTION]
    ass = BUILD / "captions.ass"
    effects.captions_ass(cap, ass)
    keys = effects.zoom_keys(events, rel)
    framed = BUILD / "framed.mp4"
    if args.reuse_video and framed.exists():
        print("  reusing build/framed.mp4", flush=True)
    else:
        effects.compose(cutfile, keys, intro_end=t["home"] - 0.6, outro_start=t["outro"], ass=ass, dest=framed)

    print("mixing audio", flush=True)
    effects.FX.mkdir(parents=True, exist_ok=True)
    sfx_assets()
    music = Path(args.music) if args.music else None
    if music and not music.exists():
        sys.exit(f"music file not found: {music}")
    if not music:
        print("  no --music given: voice and UI sounds only", flush=True)
    audio = mix_audio(place, clips, cut, vdur, events, rel, music, args.music_start)
    aac = ["-c:a", "aac", "-b:a", "160k", "-ar", "48000"]

    print("writing outputs", flush=True)
    ff("-i", framed, "-c:v", "copy", "-an", "-movflags", "+faststart", DEMO / "demo_1080p.mp4")
    ff("-i", framed, "-i", audio, "-map", "0:v", "-map", "1:a", "-c:v", "copy", *aac, "-shortest",
       "-movflags", "+faststart", DEMO / "demo_1080p_vo.mp4")
    ff("-i", framed, "-vf", "scale=1080:-2:flags=lanczos,pad=1080:1080:0:(oh-ih)/2:color=0x0C3646,format=yuv420p",
       "-r", "30", *X264, "-an", DEMO / "demo_square.mp4")
    ff("-i", DEMO / "demo_square.mp4", "-i", audio, "-map", "0:v", "-map", "1:a", "-c:v", "copy", *aac, "-shortest",
       "-movflags", "+faststart", DEMO / "demo_square_vo.mp4")

    g0, g1 = t["result"] - 2.5, t.get("segments") or t["outro"]  # GIF: fill -> result -> what-if, about 14 s
    speed = max(1.0, (g1 - g0) / 14.0)
    vf = f"setpts=PTS/{speed:.3f},fps=12,scale=960:-1:flags=lanczos"
    pal = BUILD / "palette.png"
    ff("-ss", f"{g0:.3f}", "-t", f"{g1 - g0:.3f}", "-i", framed, "-vf", f"{vf},palettegen=max_colors=128:stats_mode=diff", pal)
    ff("-ss", f"{g0:.3f}", "-t", f"{g1 - g0:.3f}", "-i", framed, "-i", pal, "-lavfi",
       f"{vf}[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle", DEMO / "demo.gif")
    zoomed = [k for k in keys if k[1] > 1.0 and t["whatif"] <= k[0] < t.get("segments", 1e9)]
    thumb_t = (zoomed[-1][0] + 1.2) if zoomed else t["whatif"] + 2.0  # the what-if, zoomed in, after the drop
    ff("-ss", f"{thumb_t:.3f}", "-i", framed, "-frames:v", "1", DEMO / "thumbnail.png")

    report_audio(audio, place, clips, cut, [rel(e['t']) for e in events if e['type'] in ('click', 'whoosh')])
    for f in ("demo_1080p_vo.mp4", "demo_square_vo.mp4", "demo_1080p.mp4", "demo_square.mp4", "demo.gif", "thumbnail.png"):
        p = DEMO / f
        extra = f", {probe_duration(p):.1f}s" if p.suffix in (".mp4", ".gif") else ""
        print(f"  {p.relative_to(ROOT)}: {p.stat().st_size / 1e6:.2f} MB{extra}", flush=True)
    late = [n for n, at in place if at + json.loads(TIMINGS_FILE.read_text())[n] / cut["k"] > vdur]
    if late:
        print(f"  warning: narration runs past the end of the video in {late}", flush=True)


def report_audio(audio: Path, place, clips, cut, sounds=()):
    (s0, sd), (g0, gd) = speech_and_gap(place, clips, cut["k"], sounds)
    sp, gp = segment_lufs(audio, s0, sd), segment_lufs(audio, g0, gd)
    final = loudness(DEMO / "demo_1080p_vo.mp4")
    print(f"  speech {s0:.1f}-{s0 + sd:.1f}s: {sp:.1f} LUFS | music-only gap {g0:.1f}-{g0 + gd:.1f}s: {gp:.1f} LUFS"
          f" | difference {sp - gp:.1f} dB", flush=True)
    print(f"  final {final['input_i']} LUFS integrated, true peak {final['input_tp']} dBTP", flush=True)


def remix(args, place, clips, cut, events, rel):
    """Audio only: new mix muxed onto the existing framed video and square cut (no recording, no compose)."""
    framed = BUILD / "framed.mp4"
    vdur = probe_duration(framed)
    sfx_assets()
    audio = mix_audio(place, clips, cut, vdur, events, rel, Path(args.music) if args.music else None, args.music_start)
    aac = ["-c:a", "aac", "-b:a", "160k", "-ar", "48000"]
    for video, dst in ((framed, "demo_1080p_vo.mp4"), (DEMO / "demo_square.mp4", "demo_square_vo.mp4")):
        ff("-i", video, "-i", audio, "-map", "0:v", "-map", "1:a", "-c:v", "copy", *aac, "-shortest",
           "-movflags", "+faststart", DEMO / dst)
        print(f"  demo/{dst}: {(DEMO / dst).stat().st_size / 1e6:.2f} MB, {probe_duration(DEMO / dst):.1f}s", flush=True)
    report_audio(audio, place, clips, cut, [rel(e['t']) for e in events if e['type'] in ('click', 'whoosh')])


def self_check():
    md = "x\n## a\n> Hello there.\n\nsay: Hi there.\n\nprosody: rate=+0% pitch=-2Hz\n\n## b\n> Bye.\n## c\nno line\n"
    got = parse(md)
    assert got["a"] == {"line": "Hello there.", "say": "Hi there.", "rate": "+0%", "pitch": "-2Hz"}, got
    assert got["b"] == {"line": "Bye.", "say": "Bye.", **DEFAULT_PROSODY} and "c" not in got, got
    scenes = [{"name": "intro", "t": 1.0}, {"name": "home", "t": 7.0}]
    got = placements(scenes, {"start": 1.0 + CUT_SKIP, "k": 1.0}, {"intro": 0, "home": 0, "gone": 0})
    assert got == [("intro", VO_LEAD), ("home", 7.0 - 1.0 - CUT_SKIP + VO_LEAD)], got
    effects.self_check()


def main():
    self_check()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=["tts", "mix", "all"])
    ap.add_argument("--voice", default=VOICE)
    ap.add_argument("--music", help="background music file (looped or trimmed to the video)")
    ap.add_argument("--music-start", type=float, default=2.0,
                    help="seconds into the track to start: 2.0 skips the swell-in and lands on the first downbeat of the "
                         "default track (120 bpm, 2 s bars)")
    ap.add_argument("--reuse-video", action="store_true", help="mix: skip the compose and use build/framed.mp4")
    ap.add_argument("--audio-only", action="store_true", help="mix: re-do the audio and mux it onto the existing video")
    ap.add_argument("--live-url", default="your-app.streamlit.app")
    args, rest = ap.parse_known_args()
    if args.step in ("tts", "all"):
        cmd_tts(args)
    if args.step == "all":
        subprocess.run([sys.executable, str(DEMO / "record.py"), "--live-url", args.live_url, *rest], check=True)
    if args.step in ("mix", "all"):
        cmd_mix(args)


if __name__ == "__main__":
    main()
