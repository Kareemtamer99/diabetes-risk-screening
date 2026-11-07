"""Post-production for the demo video, called by voiceover.py mix.

The plain cut (build/cut.mp4) becomes:
- a browser window mockup (rounded corners, shadow, traffic-light dots) at 88% of the frame,
  on a slowly drifting navy-to-teal brand gradient
- eased zoom-and-pan onto the focus areas that record.py logged (build/events.json)
- full-frame intro and outro cards that cross-fade into and out of the framed window
- lower-third captions of the narration, each word lighting up as it is spoken (ASS karaoke)
"""
import difflib
import re
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from record import BUILD, FFMPEG, H, W, probe_duration

FX = BUILD / "fx"
WIN_W = 1690                      # 88% of the frame width
CONTENT_H = round(WIN_W * H / W)  # 951: the browser keeps its 16:9 shape
BAR = 40                          # title bar
WIN_X = (W - WIN_W) // 2
WIN_Y = (H - CONTENT_H - BAR) // 2
CONTENT_Y = WIN_Y + BAR
RADIUS = 16
EASE_S = 0.7                      # zoom in/out duration
UP = 1.5                          # zoom works on a 1.5x upscale: sub-pixel pans, light enough for 8 GB of RAM
NAVY, TEAL, ACCENT = (12, 54, 70), (14, 116, 144), (103, 232, 249)


# ---------------------------------------------------------------- still assets

def _font(size: int):
    for f in ("segoeui.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(f, size)
        except OSError:
            pass
    return ImageFont.load_default()


def make_assets(url_label: str):
    FX.mkdir(parents=True, exist_ok=True)
    # Gradient larger than the frame, so a moving crop makes it drift.
    gw, gh = int(W * 1.2), int(H * 1.2)
    yy, xx = np.mgrid[0:gh, 0:gw]
    ramp = (xx * 0.8 + yy * 0.6) / (gw * 0.8 + gh * 0.6)  # smooth diagonal, navy top-left to teal bottom-right
    bg = Image.fromarray((np.array(NAVY) + (np.array(TEAL) - np.array(NAVY)) * ramp[..., None]).astype(np.uint8))
    glow = Image.new("L", (gw, gh), 0)
    ImageDraw.Draw(glow).ellipse((gw * 0.55, -gh * 0.2, gw * 1.15, gh * 0.55), fill=70)
    ImageDraw.Draw(glow).ellipse((-gw * 0.2, gh * 0.6, gw * 0.35, gh * 1.25), fill=45)
    glow = glow.filter(ImageFilter.GaussianBlur(160))
    bg = Image.composite(Image.new("RGB", (gw, gh), ACCENT), bg, glow.point(lambda v: v * 0.5))
    bg.save(FX / "bg.png")

    box = (WIN_X, WIN_Y, WIN_X + WIN_W, CONTENT_Y + CONTENT_H)
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((box[0], box[1] + 26, box[2], box[3] + 26), RADIUS, fill=(3, 20, 28, 120))
    shadow.filter(ImageFilter.GaussianBlur(30)).save(FX / "shadow.png")

    chrome = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(chrome)
    d.rounded_rectangle(box, RADIUS, fill=(243, 245, 247, 255), outline=(255, 255, 255, 90), width=1)
    d.line((WIN_X, CONTENT_Y - 1, WIN_X + WIN_W, CONTENT_Y - 1), fill=(222, 228, 232, 255))
    cy = WIN_Y + BAR // 2
    for i, c in enumerate([(255, 95, 87), (254, 188, 46), (40, 200, 64)]):
        x = WIN_X + 24 + i * 22
        d.ellipse((x - 7, cy - 7, x + 7, cy + 7), fill=c + (255,))
    f = _font(16)
    tw = d.textlength(url_label, font=f)
    pw = max(420, tw + 60)
    d.rounded_rectangle((W / 2 - pw / 2, cy - 13, W / 2 + pw / 2, cy + 13), 13, fill=(229, 234, 238, 255))
    d.text((W / 2 - tw / 2, cy), url_label, font=f, fill=(74, 90, 99, 255), anchor="lm")
    chrome.save(FX / "chrome.png")

    # The page video gets rounded bottom corners; the title bar carries the top ones.
    mask = Image.new("L", (WIN_W, CONTENT_H), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle((0, 0, WIN_W - 1, CONTENT_H - 1), RADIUS, fill=255)
    md.rectangle((0, 0, WIN_W - 1, RADIUS), fill=255)
    mask.save(FX / "mask.png")


# ---------------------------------------------------------------- zoom

def to_frame(x: float, y: float) -> tuple[float, float]:
    """Viewport coordinates of the recorded page -> coordinates in the framed video."""
    return WIN_X + x * WIN_W / W, CONTENT_Y + y * CONTENT_H / H


def zoom_keys(events: list, rel) -> list[tuple[float, float, float, float]]:
    """(time, zoom, centre x, centre y) for each focus event, zoom capped so the focus area still fits."""
    keys = []
    for e in events:
        if e["type"] != "focus":
            continue
        cx, cy = to_frame(e["x"], e["y"])
        fw, fh = e["w"] * WIN_W / W, e["h"] * CONTENT_H / H
        z = max(1.0, min(e["z"], 0.92 * W / max(fw, 1), 0.85 * H / max(fh, 1)))
        if z == 1.0:
            cx, cy = W / 2, H / 2
        keys.append((rel(e["t"]), z, cx, cy))
    return keys


def eased(keys: list, i: int, base: float, T: str = "T") -> str:
    """ffmpeg expression: base plus each keyframe's change, eased in over EASE_S with smoothstep."""
    terms, prev = [], base
    for k in keys:
        delta = k[i] - prev
        prev = k[i]
        if abs(delta) > 1e-4:
            u = f"clip(({T}-{k[0]:.3f})/{EASE_S},0,1)"
            terms.append(f"{delta:+.4f}*{u}*{u}*(3-2*{u})")
    return f"{base}" + "".join(terms)


def zoompan_filter(keys: list) -> str:
    """Zoom on an upscale (UP), so the integer crop offsets of zoompan move in sub-pixel steps."""
    T = "(in/30)"
    z = eased(keys, 1, 1.0, T)
    cx = eased(keys, 2, W / 2, T)
    cy = eased(keys, 3, H / 2, T)
    return (f"scale={round(UP * W)}:{round(UP * H)}:flags=bicubic,"
            f"zoompan=z='{z}':x='clip({UP}*({cx})-iw/zoom/2,0,iw-iw/zoom)':y='clip({UP}*({cy})-ih/zoom/2,0,ih-ih/zoom)'"
            f":d=1:s={W}x{H}:fps=30")


# ---------------------------------------------------------------- captions

def norm(tok: str) -> str:
    return re.sub(r"[^a-z0-9']", "", tok.lower())


def align(display: str, spoken: list[dict]) -> list[tuple[str, float, float]]:
    """Give each written word the time of the spoken word(s) it stands for.
    spoken: [{"text", "t", "d"}] in seconds from clip start. Written-only tokens such as "229,474" take the
    span of the spoken words they replace ("two hundred twenty-nine thousand")."""
    toks = []
    for t in display.split():
        if toks and not norm(t):  # a lone dash or ellipsis sticks to the word before it
            toks[-1] += " " + t
        else:
            toks.append(t)
    a, b = [norm(t) for t in toks], [norm(w["text"]) for w in spoken]
    out: list = [None] * len(toks)
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                w = spoken[j1 + k]
                out[i1 + k] = (toks[i1 + k], w["t"], w["t"] + w["d"])
        elif i2 > i1:
            if j2 > j1:
                t0, t1 = spoken[j1]["t"], spoken[j2 - 1]["t"] + spoken[j2 - 1]["d"]
            else:  # nothing spoken for these: squeeze them in at the previous word's end
                t0 = t1 = out[i1 - 1][2] if i1 and out[i1 - 1] else (spoken[0]["t"] if spoken else 0.0)
            step = (t1 - t0) / (i2 - i1)
            for k in range(i2 - i1):
                out[i1 + k] = (toks[i1 + k], t0 + k * step, t0 + (k + 1) * step)
    return out


def chunks(words: list, max_chars: int = 38, max_lines: int = 2) -> list[list]:
    """Group timed words into caption cards of at most two lines, breaking after sentence ends."""
    cards, card, lines, line = [], [], 0, 0
    for w in words:
        n = len(w[0]) + (1 if line else 0)
        if line and line + n > max_chars:
            lines, line = lines + 1, 0
            if lines >= max_lines:
                cards.append(card)
                card, lines = [], 0
            n = len(w[0])
        card.append(w + (lines,))
        line += n
        if re.search(r"[.?!]$", w[0]) and len(card) > 2:
            cards.append(card)
            card, lines, line = [], 0, 0
    if card:
        cards.append(card)
    return cards


def ass_time(t: float) -> str:
    cs = max(0, round(t * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


ASS_HEAD = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,Segoe UI Semibold,46,&H00FFFFFF,&H70FFFFFF,&H1446360C,&H00000000,0,0,0,0,100,100,0,0,3,16,0,2,160,160,64,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def captions_ass(lines: list[tuple[float, float, list]], dest: Path):
    """lines: (clip start in the cut, speed factor k, aligned words). Spoken words turn from dim to white."""
    events = []
    for at, k, words in lines:
        cards = chunks([(w, at + t0 / k, at + t1 / k) for w, t0, t1 in words])
        for ci, card in enumerate(cards):
            start, end = card[0][1], card[-1][2] + 0.35
            if ci + 1 < len(cards):
                end = min(end, cards[ci + 1][0][1])
            text, row = "", 0
            for wi, (w, t0, t1, ln) in enumerate(card):
                nxt = card[wi + 1][1] if wi + 1 < len(card) else t1
                if ln != row:
                    text, row = text.rstrip() + r"\N", ln
                text += rf"{{\kf{max(1, round((nxt - t0) * 100))}}}{w} "
            events.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Cap,,0,0,0,,{text.rstrip()}")
    dest.write_text(ASS_HEAD + "\n".join(events) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- compose

def compose(cut: Path, keys: list, intro_end: float, outro_start: float, ass: Path | None, dest: Path):
    """Framed, zoomed video with the intro/outro cards full frame and captions on top (no audio)."""
    fx = lambda n: str(FX / n)  # noqa: E731
    graph = (
        "[0:v]split=3[c1][c2][c3];"
        f"[c1]scale={WIN_W}:{CONTENT_H}:flags=lanczos,format=rgba[s];[4:v]format=gray[m];[s][m]alphamerge[win];"
        f"[1:v]crop={W}:{H}:x='{W * 0.1:.0f}+{W * 0.09:.0f}*sin(2*PI*t/26)':y='{H * 0.1:.0f}+{H * 0.09:.0f}*sin(2*PI*t/33+1)',"
        "format=rgba[bg];"
        f"[bg][2:v]overlay=0:0[b1];[b1][3:v]overlay=0:0[b2];[b2][win]overlay={WIN_X}:{CONTENT_Y}:shortest=1,format=yuv420p[comp];"
        f"[comp]{zoompan_filter(keys)}[zm];"
        # Full-length card streams with alpha fades: a late-starting overlay input would make ffmpeg buffer every
        # frame until it arrives (out of memory on a 60 s take).
        f"[c2]format=yuva420p,fade=t=out:st={intro_end:.3f}:d=0.5:alpha=1[ci];"
        f"[c3]format=yuva420p,fade=t=in:st={outro_start:.3f}:d=0.45:alpha=1[co];"
        "[zm][ci]overlay=eof_action=pass[a];[a][co]overlay=eof_action=pass"
        + (",ass=captions.ass" if ass else "") + ",format=yuv420p[v]")
    # looped stills never end on their own: cap them at the cut's length, or ffmpeg keeps reading them forever
    loop = ["-loop", "1", "-framerate", "30", "-t", f"{probe_duration(cut):.3f}", "-i"]
    cmd = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", str(cut),
           *loop, fx("bg.png"), *loop, fx("shadow.png"), *loop, fx("chrome.png"), *loop, fx("mask.png"),
           "-filter_complex", graph, "-map", "[v]", "-threads", "2", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
           "-profile:v", "high", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an", str(dest)]
    # run in build/ so the ASS file is a plain relative path (no Windows drive-colon escaping)
    subprocess.run(cmd, check=True, cwd=str(ass.parent if ass else BUILD))


def self_check():
    spoken = [{"text": t, "t": i * 0.5, "d": 0.4} for i, t in enumerate(
        "built on two hundred twenty-nine thousand real answers".split())]
    got = align("built on 229,474 real answers.", spoken)
    assert [g[0] for g in got] == ["built", "on", "229,474", "real", "answers."], got
    assert got[2][1] == 1.0 and abs(got[2][2] - 2.9) < 1e-9, got[2]  # spans "two" .. "thousand"
    dash = align("six questions — age", [{"text": t, "t": i, "d": 0.5} for i, t in enumerate(["six", "questions", "age"])])
    assert dash[1][0] == "questions —" and len(dash) == 3, dash
    cards = chunks([(w, i, i + 1) for i, w in enumerate(("word " * 30).split())])
    assert all(max(c[3] for c in card) <= 1 for card in cards), "a caption card has more than two lines"
    keys = zoom_keys([{"type": "focus", "t": 2.0, "x": 960, "y": 540, "w": 100, "h": 50, "z": 1.3},
                      {"type": "focus", "t": 5.0, "x": 960, "y": 540, "w": W, "h": H, "z": 1.0}], lambda t: t)
    assert keys[0][1] == 1.3 and keys[1][1] == 1.0, keys
    assert eased(keys, 1, 1.0).count("clip(") == 6
