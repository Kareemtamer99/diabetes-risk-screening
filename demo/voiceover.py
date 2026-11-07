"""Narration for the demo video, from demo/VOICEOVER.md, with edge-tts (needs the internet).

  python demo/voiceover.py tts      render one clip per scene + voice samples, write demo/build/timings.json
  python demo/voiceover.py mix      mix the clips onto the last take: demo_1080p_vo.mp4, demo_square_vo.mp4
  python demo/voiceover.py all ...  tts, then record.py (extra args go to it), then mix

record.py reads timings.json and holds each scene until its line has been spoken, so the visuals wait for the voice.
The silent MP4s and the GIF stay as they are.
"""
import argparse
import json
import re
import subprocess
import wave
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from record import BUILD, CUT_SKIP, DEMO, TIMINGS_FILE, VO_LEAD, ff, probe_duration  # noqa: E402

SCRIPT = DEMO / "VOICEOVER.md"
CLIPS = BUILD / "vo"
SAMPLES = DEMO / "voice_samples"
VOICE = "en-US-AndrewNeural"
SAMPLE_VOICES = ["en-US-AndrewNeural", "en-US-AvaNeural", "en-US-BrianNeural"]


def parse(text: str) -> dict[str, dict]:
    """'## scene' blocks -> {scene: {"line": written text, "say": spoken text}}, in order."""
    out = {}
    for block in re.split(r"^## ", text, flags=re.M)[1:]:
        name = block.split("\n", 1)[0].strip()
        line = re.search(r"^> (.+)$", block, re.M)
        if not line:
            continue
        say = re.search(r"^say: (.+)$", block, re.M)
        out[name] = {"line": line[1].strip(), "say": (say or line)[1].strip()}
    return out


def mp3_seconds(path: Path) -> float:
    """edge-tts writes constant 48 kbps mono MP3, so size gives length without launching ffmpeg."""
    return path.stat().st_size * 8 / 48000


def tts(text: str, voice: str, dest: Path, rate: str):
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, "-m", "edge_tts", "--voice", voice, f"--rate={rate}", "--text", text,
                    "--write-media", str(dest)], check=True, capture_output=True)


def cmd_tts(args):
    lines = parse(SCRIPT.read_text(encoding="utf-8"))
    timings, words = {}, 0
    for name, v in lines.items():
        clip = CLIPS / f"{name}.mp3"
        tts(v["say"], args.voice, clip, args.rate)
        timings[name] = round(mp3_seconds(clip), 2)
        words += len(v["line"].split())
        print(f"  {name:11s} {timings[name]:5.2f}s  {v['line']}", flush=True)
    TIMINGS_FILE.write_text(json.dumps(timings, indent=2), encoding="utf-8")
    speech = sum(timings.values())
    print(f"{words} words, {speech:.1f}s of speech ({words / speech * 60:.0f} wpm)", flush=True)

    if not args.samples:  # the voice is chosen (Andrew); samples only on request
        return
    first_two = " ".join(v["say"] for v in list(lines.values())[:2])
    for voice in SAMPLE_VOICES:
        out = SAMPLES / f"{voice.split('-')[2].removesuffix('Neural').lower()}.mp3"
        tts(first_two, voice, out, args.rate)
        print(f"  sample {out.relative_to(DEMO.parent)} ({mp3_seconds(out):.1f}s)", flush=True)


def placements(scenes: list, cut: dict, clips: dict) -> list[tuple[str, float]]:
    """(scene, seconds into the cut) for each scene that was recorded and has a clip."""
    t = {s["name"]: s["t"] for s in scenes}
    return [(n, max(0.0, (t[n] - cut["start"]) / cut["k"]) + VO_LEAD) for n in clips if n in t]


def cmd_mix(_args):
    scenes = json.loads((BUILD / "scenes.json").read_text(encoding="utf-8"))
    cut = json.loads((BUILD / "cut.json").read_text(encoding="utf-8"))
    clips = {p.stem: p for p in sorted(CLIPS.glob("*.mp3"))}
    place = placements(scenes, cut, clips)
    if not place:
        sys.exit("no clips match the recorded scenes: run `voiceover.py tts` before record.py")
    vdur = probe_duration(DEMO / "demo_1080p.mp4")
    # A silent bed of the exact video length is input 0, so the mix always lasts the whole video.
    inputs, chains = ["-f", "lavfi", "-t", f"{vdur:.3f}", "-i", "anullsrc=r=48000:cl=mono"], []
    for i, (name, at) in enumerate(place, start=1):
        inputs += ["-i", clips[name]]
        ms = int(at * 1000)
        chains.append(f"[{i}:a]atempo={cut['k']:.4f},aresample=48000,adelay={ms}|{ms}[a{i}]")  # same speed-up as the video
    mix = "[0:a]" + "".join(f"[a{i}]" for i in range(1, len(place) + 1))
    graph = ";".join(chains) + (f";{mix}amix=inputs={len(place) + 1}:normalize=0:duration=first,"
                                "loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000,"
                                f"afade=t=in:d=0.05,afade=t=out:st={vdur - 0.6:.3f}:d=0.6[out]")
    wav = BUILD / "voiceover.wav"
    ff(*inputs, "-filter_complex", graph, "-map", "[out]", "-ac", "2", wav)
    with wave.open(str(wav)) as w:
        got = w.getnframes() / w.getframerate()
    assert abs(got - vdur) < 0.25, f"voiceover is {got:.2f}s but the video is {vdur:.2f}s"
    for src in ("demo_1080p.mp4", "demo_square.mp4"):
        dst = DEMO / src.replace(".mp4", "_vo.mp4")
        ff("-i", DEMO / src, "-i", wav, "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
           "-ar", "48000", "-shortest", "-movflags", "+faststart", dst)
        print(f"  {dst.relative_to(DEMO.parent)}: {dst.stat().st_size / 1e6:.2f} MB, {probe_duration(dst):.1f}s",
              flush=True)
    late = [n for n, at in place if at + json.loads(TIMINGS_FILE.read_text())[n] / cut['k'] > vdur]
    if late:
        print(f"  warning: narration runs past the end of the video in {late}", flush=True)


def self_check():
    md = "x\n## a\n> Hello there.\n\nsay: Hi there.\n\n## b\n> Bye.\n## c\nno line\n"
    assert parse(md) == {"a": {"line": "Hello there.", "say": "Hi there."}, "b": {"line": "Bye.", "say": "Bye."}}
    scenes = [{"name": "intro", "t": 1.0}, {"name": "home", "t": 7.0}]
    got = placements(scenes, {"start": 1.0 + CUT_SKIP, "k": 1.0}, {"intro": 0, "home": 0, "gone": 0})
    assert got == [("intro", VO_LEAD), ("home", 7.0 - 1.0 - CUT_SKIP + VO_LEAD)], got


def main():
    self_check()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=["tts", "mix", "all"])
    ap.add_argument("--voice", default=VOICE)
    ap.add_argument("--samples", action="store_true", help="also render the voice comparison samples")
    ap.add_argument("--rate", default="+5%", help="edge-tts speaking rate, e.g. +5%%")
    args, rest = ap.parse_known_args()
    if args.step in ("tts", "all"):
        cmd_tts(args)
    if args.step == "all":
        subprocess.run([sys.executable, str(DEMO / "record.py"), *rest], check=True)
    if args.step in ("mix", "all"):
        cmd_mix(args)


if __name__ == "__main__":
    main()
