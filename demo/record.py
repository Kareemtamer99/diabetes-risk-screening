"""Record the product demo video, screenshots and README assets.

Usage (from the repo root):
    .venv/Scripts/python demo/record.py                 # screenshots + recording + post-processing
    .venv/Scripts/python demo/record.py --dry-run       # fast pass only: checks every step, writes screenshots
    .venv/Scripts/python demo/record.py --post-only     # re-run ffmpeg on the last recording

Outputs go to demo/. Intermediate files (raw .webm, scene log, server log) go to demo/build/.
"""
import argparse
import json
import math
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import imageio_ffmpeg
from playwright.sync_api import Error as PWError, Locator, Page, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "demo"
BUILD = DEMO / "build"
SHOTS = DEMO / "screenshots"
STREAMLIT = ROOT / ".venv" / "Scripts" / "streamlit.exe"
LOGO = ROOT / "assets" / "logo.svg"
LOGO_MARK = ROOT / "assets" / "logo_mark.svg"  # the full logo has dark text, so the dark cards use the mark
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
W, H = 1920, 1080
BRAND, PRIMARY, ACCENT = "#0C3646", "#0E7490", "#67E8F9"

# Demo persona: answers that land in the high band, so the what-if has room to move.
PERSONA = {"age": "58", "height": "175", "weight": "104", "health": "Fair", "weight_after": 80}

CAPTIONS = {
    "home": "Diabetes risk screening, in about a minute.",
    "start": "Six questions. No sign-up.",
    "fill": "Six questions from the CDC's BRFSS health survey.",
    "result": "A clear risk level, and the answers behind it.",
    "whatif": "What if? Lower weight, get active, watch the risk drop.",
    "whatif_bp": "What if? Lower weight, treat blood pressure, watch the risk drop.",
    "segments": "{} population profiles found by clustering.",
    "cost": "Plan a screening program: cases caught versus cost.",
    "validation": "Checked on 4 later survey years: ROC-AUC held above 0.80.",
}

# Voiceover sync: demo/voiceover.py writes each scene's narration length here. Each scene then lasts at least
# VO_LEAD + clip + VO_TAIL seconds, and post-processing keeps real time so the audio lines up.
TIMINGS_FILE = ROOT / "demo" / "build" / "timings.json"
VO_LEAD, VO_TAIL = 0.3, 0.45
CUT_SKIP = 0.9  # the cut starts this long after the intro mark (loading page and card fade-in)


# ---------------------------------------------------------------- server

def free_port(start: int) -> int:
    for port in range(start, start + 50):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError("no free port")


def start_server(port: int) -> subprocess.Popen:
    BUILD.mkdir(parents=True, exist_ok=True)
    log = open(BUILD / "server.log", "w", encoding="utf-8")
    proc = subprocess.Popen(
        [str(STREAMLIT), "run", "app.py", "--server.port", str(port), "--server.headless", "true",
         "--browser.gatherUsageStats", "false", "--server.runOnSave", "false", "--server.fileWatcherType", "none"],
        cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    deadline = time.time() + 90
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"streamlit exited, see {BUILD / 'server.log'}")
        try:
            if urllib.request.urlopen(f"http://127.0.0.1:{port}/_stcore/health", timeout=2).read().strip() == b"ok":
                return proc
        except OSError:
            time.sleep(0.5)
    proc.kill()
    raise RuntimeError("streamlit did not become healthy in 90 s")


# ---------------------------------------------------------------- overlay

OVERLAY_JS = r"""
() => {
  if (window.__demo) return;
  const css = document.createElement('style');
  css.textContent = `
    #demo-cursor { position: fixed; left: 0; top: 0; width: 26px; height: 26px; margin: -13px 0 0 -13px;
      border-radius: 50%; background: rgba(14,116,144,0.92); border: 3px solid #fff; pointer-events: none;
      box-shadow: 0 2px 10px rgba(12,54,70,0.35); z-index: 2147483647; transition: transform 30ms linear, opacity 300ms ease,
      scale 120ms ease-out; opacity: 0; }
    #demo-cursor.on { opacity: 1; }
    #demo-cursor.down { scale: 0.78; }
    .demo-ripple { position: fixed; width: 26px; height: 26px; margin: -13px 0 0 -13px; border-radius: 50%;
      border: 3px solid #0E7490; pointer-events: none; z-index: 2147483646; animation: demo-rip 650ms ease-out forwards; }
    @keyframes demo-rip { from { transform: scale(1); opacity: .9 } to { transform: scale(3.4); opacity: 0 } }
    #demo-caption { position: fixed; left: 96px; bottom: 60px; z-index: 2147483645; pointer-events: none;
      display: flex; align-items: center; gap: 20px; padding: 22px 34px 22px 28px; border-radius: 16px;
      background: rgba(12,54,70,0.94); box-shadow: 0 12px 40px rgba(12,54,70,0.30);
      font-family: 'Figtree', 'Noto Sans', 'Segoe UI', sans-serif; font-weight: 600; font-size: 38px;
      letter-spacing: -0.01em; color: #fff; line-height: 1.2; max-width: 1500px;
      opacity: 0; transform: translateY(14px); transition: opacity 380ms ease, transform 380ms ease; }
    #demo-caption::before { content: ''; width: 6px; align-self: stretch; border-radius: 3px; background: #67E8F9; }
    #demo-caption.show { opacity: 1; transform: none; }
    #demo-card { position: fixed; inset: 0; z-index: 2147483644; display: flex; align-items: center; justify-content: center;
      background: radial-gradient(120% 90% at 30% 20%, #134A5E 0%, #0C3646 55%, #082733 100%);
      color: #fff; font-family: 'Figtree', 'Noto Sans', 'Segoe UI', sans-serif; transition: opacity 700ms ease; }
    #demo-card.hide { opacity: 0; }
    #demo-card .wrap { width: 1400px; }
    #demo-card .rise { opacity: 0; transform: translateY(18px); animation: demo-rise 700ms ease forwards; }
    @keyframes demo-rise { to { opacity: 1; transform: none; } }
    #demo-card .hook { font-size: 84px; font-weight: 700; line-height: 1.05; letter-spacing: -0.025em; }
    #demo-card .hook em { font-style: normal; color: #67E8F9; }
    #demo-card .sub { font-family: 'Noto Sans', 'Segoe UI', sans-serif; font-size: 34px; color: #C6DCE4; margin-top: 32px; }
    #demo-card .brand { display: flex; align-items: center; gap: 20px; font-size: 34px; font-weight: 600; margin-top: 72px; }
    #demo-card .logo svg, #demo-card .logo img { height: 64px; width: auto; display: block; border-radius: 22%;
      box-shadow: 0 0 0 2px rgba(103,232,249,0.35), 0 10px 30px rgba(0,0,0,0.25); }
    #demo-card .brand em { font-style: normal; color: #67E8F9; }
    #demo-card.outro .wrap { text-align: center; }
    #demo-card .logo.full { background: #fff; padding: 14px 22px; border-radius: 18px; }
    #demo-card .logo.full svg { box-shadow: none; border-radius: 0; height: 56px; }
    #demo-card.outro .logo.full svg { height: 104px; }
    #demo-card.outro .brand { justify-content: center; font-size: 64px; font-weight: 700; margin: 0; letter-spacing: -0.02em; }
    #demo-card.outro .logo svg, #demo-card.outro .logo img { height: 120px; }
    #demo-card .links { display: flex; justify-content: center; gap: 28px; margin-top: 56px; }
    #demo-card .link { font-size: 30px; padding: 18px 30px; border-radius: 14px; background: rgba(255,255,255,0.08);
      box-shadow: inset 0 0 0 1px rgba(255,255,255,0.25); }
    #demo-card .link b { color: #67E8F9; margin-right: 14px; font-weight: 600; }
    #demo-card .disc { font-family: 'Noto Sans', 'Segoe UI', sans-serif; font-size: 26px; color: #C6DCE4; margin-top: 56px; }
  `;
  document.head.appendChild(css);
  const font = document.createElement('link');
  font.rel = 'stylesheet';
  font.href = 'https://fonts.googleapis.com/css2?family=Figtree:wght@500;600;700&family=Noto+Sans:wght@400;500;600&display=block';
  document.head.appendChild(font);
  const cur = document.createElement('div'); cur.id = 'demo-cursor'; document.body.appendChild(cur);
  const cap = document.createElement('div'); cap.id = 'demo-caption'; document.body.appendChild(cap);
  const txt = document.createElement('span'); cap.appendChild(txt);
  let x = 960, y = 540, current = '';
  const place = () => { cur.style.transform = `translate(${x}px, ${y}px)`; };
  place();
  addEventListener('mousemove', e => { x = e.clientX; y = e.clientY; place(); }, true);
  addEventListener('mousedown', e => {
    cur.classList.add('down');
    const r = document.createElement('div'); r.className = 'demo-ripple';
    r.style.left = e.clientX + 'px'; r.style.top = e.clientY + 'px';
    document.body.appendChild(r); setTimeout(() => r.remove(), 700);
  }, true);
  addEventListener('mouseup', () => cur.classList.remove('down'), true);
  window.__demo = {
    cursor(on) { cur.classList.toggle('on', on); },
    caption(text) {
      if (text === current) return;
      current = text;
      cap.classList.remove('show');
      setTimeout(() => { if (current !== text) return; txt.textContent = text; if (text) cap.classList.add('show'); }, current ? 380 : 0);
    },
    card(html, cls) {
      let c = document.getElementById('demo-card');
      if (!c) { c = document.createElement('div'); c.id = 'demo-card'; document.body.appendChild(c); }
      c.className = (cls || '') + ' hide'; c.innerHTML = html;
      requestAnimationFrame(() => requestAnimationFrame(() => c.classList.remove('hide')));
    },
    uncard() {
      const c = document.getElementById('demo-card'); if (!c) return;
      c.classList.add('hide'); setTimeout(() => c.remove(), 750);
    },
  };
}
"""


def logo_html() -> str:
    """Logo for the dark cards. The mark is preferred (the full logo has dark text), unless the full logo is
    newer, which means a rebrand updated only logo.svg; then the full logo sits on a light chip."""
    for _ in range(10):  # the app session may still be writing it
        if LOGO.exists() and LOGO.stat().st_size > 0:
            break
        time.sleep(1)
    ok = [f for f in (LOGO_MARK, LOGO) if f.exists() and f.stat().st_size > 0]
    if not ok:
        return ""
    f = ok[0] if len(ok) == 1 or LOGO_MARK.stat().st_mtime >= LOGO.stat().st_mtime else LOGO
    svg = f.read_text(encoding="utf-8")
    cls = "logo full" if f == LOGO else "logo"
    return f'<span class="{cls}">{svg[svg.find("<svg"):]}</span>'


def brand_html(name: str) -> str:
    logo = logo_html()
    # the full logo already spells the name, so the text is dropped beside it
    return logo if 'logo full' in logo else f"{logo}<span>{wordmark(name)}</span>"


def wordmark(name: str) -> str:
    """SugarScope -> Sugar<cyan>Scope</cyan>, echoing the logo; other names stay plain."""
    m = re.match(r"^([A-Z][a-z]+)([A-Z]\w+)$", name)
    return f"{m[1]}<em>{m[2]}</em>" if m else name


def intro_html(name: str, n_rows: str) -> str:
    sub = f"A one-minute risk check built on {n_rows} CDC survey responses." if n_rows else \
        "A one-minute risk check built on CDC survey data."
    return (f'<div class="wrap"><div class="hook rise" style="animation-delay:150ms">Millions of adults have diabetes<br>'
            f'<em>and don\'t know it.</em></div>'
            f'<div class="sub rise" style="animation-delay:1100ms">{sub}</div>'
            f'<div class="brand rise" style="animation-delay:1900ms">{brand_html(name)}</div></div>')


def outro_html(name: str, live: str, github: str) -> str:
    live, github = (re.sub(r"^https?://(www\.)?", "", u).rstrip("/") for u in (live, github))  # shorter on screen
    return (f'<div class="wrap"><div class="brand rise" style="animation-delay:100ms">{brand_html(name)}</div>'
            f'<div class="links rise" style="animation-delay:700ms"><span class="link"><b>Live app</b>{live}</span>'
            f'<span class="link"><b>GitHub</b>{github}</span></div>'
            f'<div class="disc rise" style="animation-delay:1300ms">Screening aid, not a medical diagnosis.</div></div>')


# ---------------------------------------------------------------- director

def ease(t: float) -> float:
    return 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


class Director:
    """Wraps page actions. record=True: overlay, eased cursor, human pacing. record=False: fast, no overlay."""

    def __init__(self, page: Page, record: bool, base_url: str):
        self.page, self.record, self.base = page, record, base_url
        self.t0 = time.monotonic()
        self.scenes: list[dict] = []
        self.timings = json.loads(TIMINGS_FILE.read_text(encoding="utf-8")) if record and TIMINGS_FILE.exists() else {}
        self.x, self.y = W / 2, H / 2

    # timing
    def now(self) -> float:
        return round(time.monotonic() - self.t0, 3)

    def pause(self, ms: int):
        if self.record:
            self.page.wait_for_timeout(ms)

    def mark(self, name: str, caption: str | None = None):
        if self.scenes and self.scenes[-1]["name"] in self.timings:  # let the previous scene's narration finish
            prev = self.scenes[-1]
            need = VO_LEAD + self.timings[prev["name"]] + VO_TAIL + (CUT_SKIP if prev["name"] == "intro" else 0)
            self.pause(max(0, int((prev["t"] + need - self.now()) * 1000)))
        self.scenes.append({"name": name, "t": self.now()})
        print(f"  {self.now():6.2f}s  {name}", flush=True)
        if self.record and caption is not None:
            self.page.evaluate("t => window.__demo.caption(t)", caption)

    def overlay(self):
        self.page.evaluate("""() => { if (document.getElementById('demo-margin')) return;
            const s = document.createElement('style'); s.id = 'demo-margin';
            s.textContent = '* { scroll-margin-top: 104px; }'; document.head.appendChild(s); }""")
        if self.record:
            self.page.evaluate(OVERLAY_JS)

    # streamlit sync
    def idle(self, settle: int = 250, timeout: int = 20000):
        """Wait for the Streamlit rerun to finish: script not running and no stale elements."""
        self.page.wait_for_timeout(settle)
        self.page.wait_for_function(
            """() => { const a = document.querySelector('[data-testid="stApp"]');
                       return a && a.getAttribute('data-test-script-state') !== 'running'
                              && !document.querySelector('[data-stale="true"]')
                              && !document.querySelector('[data-testid="stSkeleton"]'); }""", timeout=timeout)
        self.check_errors()

    def check_errors(self):
        bad = self.page.locator('[data-testid="stException"], [data-testid="stAlertContentError"]').filter(visible=True)
        if bad.count():
            raise RuntimeError(f"app shows an error: {bad.first.inner_text()[:300]}")

    # locating
    def widget(self, label: str) -> Locator:
        lab = self.page.locator('[data-testid="stWidgetLabel"]').filter(has_text=label)
        return self.page.locator('[data-testid="stElementContainer"]').filter(has=lab).filter(visible=True).first

    def first_visible(self, *locs: Locator, timeout: int = 8000) -> Locator | None:
        deadline = time.time() + timeout / 1000
        while time.time() < deadline:
            for loc in locs:
                v = loc.filter(visible=True)
                if v.count():
                    return v.first
            self.page.wait_for_timeout(200)
        return None

    # motion
    def move(self, x: float, y: float, speed: float = 1.0):
        if not self.record:
            self.page.mouse.move(x, y)
            self.x, self.y = x, y
            return
        dx, dy = x - self.x, y - self.y
        dist = math.hypot(dx, dy)
        if dist < 2:
            return
        steps = int(min(26, max(9, dist / 32)) / speed)  # brisk: about 0.15 to 0.4 s per move
        # slight arc: perpendicular offset, like a wrist movement
        nx, ny = (-dy / dist, dx / dist)
        bow = min(60.0, dist * 0.08)
        sx, sy = self.x, self.y
        for i in range(1, steps + 1):
            t = ease(i / steps)
            arc = math.sin(math.pi * t) * bow
            self.page.mouse.move(sx + dx * t + nx * arc, sy + dy * t + ny * arc)
            self.page.wait_for_timeout(14)
        self.x, self.y = x, y

    def scroll_to(self, loc: Locator, block: str = "center"):
        loc.wait_for(state="visible", timeout=15000)
        box = loc.bounding_box()
        if box and block == "center" and box["y"] > 110 and box["y"] + box["height"] < H - 190:
            return  # already comfortably in view, clear of the nav bar and the caption
        if self.record:
            loc.evaluate("(el, b) => el.scrollIntoView({behavior: 'smooth', block: b})", block)
            self.page.wait_for_timeout(900)
        else:
            loc.evaluate("(el, b) => el.scrollIntoView({block: b})", block)

    def hover(self, loc: Locator, dx: float = 0.5, dy: float = 0.5):
        box = loc.bounding_box()
        if not box:
            loc.scroll_into_view_if_needed()
            box = loc.bounding_box()
        self.move(box["x"] + box["width"] * dx, box["y"] + box["height"] * dy)

    def click(self, loc: Locator, tries: int = 3):
        for attempt in range(tries):
            try:
                loc.wait_for(state="visible", timeout=15000)
                self.hover(loc)
                self.pause(110)
                self.page.mouse.down()
                self.pause(90)
                self.page.mouse.up()
                return
            except (PWError, TypeError) as e:
                if attempt == tries - 1:
                    raise
                print(f"    retry click: {e}", flush=True)
                self.idle()

    def type_into(self, container: Locator, text: str):
        box = container.locator("input").first
        self.click(box)
        box.select_text()
        self.pause(150)
        box.press_sequentially(text, delay=40 if self.record else 0)
        self.pause(250)
        box.press("Enter")
        self.idle()

    def drag_slider(self, container: Locator, frac: float | None = None, value: float | None = None):
        """Drag a Streamlit slider thumb with the mouse; target as a fraction of the rail or as a value."""
        inp = container.locator('input[type="range"]').first
        thumb = inp.locator("xpath=../..")
        thumb.wait_for(state="visible", timeout=15000)
        before = inp.get_attribute("value")
        lo, hi = float(inp.get_attribute("min")), float(inp.get_attribute("max"))
        if value is not None:
            frac = (value - lo) / (hi - lo)
        tb, hb = track_box(thumb), thumb.bounding_box()
        cy = hb["y"] + hb["height"] / 2
        self.move(hb["x"] + hb["width"] / 2, cy)
        self.pause(200)
        self.page.mouse.down()
        self.move(tb["x"] + tb["width"] * frac, cy, speed=0.6)
        self.pause(150)
        self.page.mouse.up()
        self.idle(400)
        if inp.get_attribute("value") == before:  # drag missed: fall back to the keyboard
            print("    slider drag missed, using the keyboard", flush=True)
            target = value if value is not None else lo + frac * (hi - lo)
            key = "ArrowLeft" if target < float(before) else "ArrowRight"
            inp.focus()
            for _ in range(int(abs(target - float(before)) / float(inp.get_attribute("step") or 1))):
                inp.press(key)
            self.idle()

    def slider_frac(self, container: Locator) -> float:
        inp = container.locator('input[type="range"]').first
        lo, hi, v = (float(inp.get_attribute(k)) for k in ("min", "max", "value"))
        return (v - lo) / (hi - lo) if hi > lo else 0.0


def track_box(thumb: Locator) -> dict:
    """The slider rail: the nearest ancestor of the thumb that is much wider than the thumb."""
    return thumb.evaluate("""t => { let e = t.parentElement;
        while (e && e.getBoundingClientRect().width < t.getBoundingClientRect().width * 6) e = e.parentElement;
        const r = e.getBoundingClientRect(); return {x: r.x, y: r.y, width: r.width, height: r.height}; }""")


# ---------------------------------------------------------------- the story

def segments_caption() -> str:
    """The profile count comes from the model output, so the caption never disagrees with the screen."""
    words = {2: "Two", 3: "Three", 4: "Four", 5: "Five", 6: "Six", 7: "Seven", 8: "Eight"}
    try:
        seg = json.loads((ROOT / "models" / "segments.json").read_text(encoding="utf-8"))
        k = int(seg.get("k") or len(seg["segments"]))
        return CAPTIONS["segments"].format(words.get(k, str(k)))
    except (OSError, ValueError, KeyError):
        return "Population profiles found by clustering."


def go_to_page(d: Director, name: str) -> bool:
    """Open a page or tab by its visible name: nav link, tab, or a hidden nav link's href."""
    pat = re.compile(rf"^\s*{re.escape(name)}\s*$", re.I)
    target = d.first_visible(d.page.get_by_role("tab", name=pat), d.page.get_by_role("link", name=pat),
                             d.page.get_by_role("button", name=pat), timeout=3000)
    if target:
        d.click(target)
        d.idle(500)
        return True
    hidden = d.page.locator("a", has_text=pat)
    if hidden.count() and hidden.first.get_attribute("href"):
        d.page.goto(hidden.first.get_attribute("href"))
        d.idle(800)
        d.overlay()
        return True
    return False


def story(d: Director, *a):
    try:
        _story(d, *a)
    except Exception:
        BUILD.mkdir(parents=True, exist_ok=True)
        d.page.screenshot(path=str(BUILD / "failure.png"))
        (BUILD / "failure.html").write_text(d.page.content(), encoding="utf-8")
        print(f"  failed at {d.now():.1f}s; see demo/build/failure.png and failure.html", flush=True)
        raise


def _story(d: Director, name: str, n_rows: str, live: str, github: str):
    page = d.page
    page.goto(d.base, wait_until="domcontentloaded")
    if d.record:
        page.wait_for_selector("body", state="attached")
        d.overlay()
        page.evaluate("() => document.fonts.load('700 92px Figtree')")
        page.evaluate("([h, c]) => window.__demo.card(h, c)", [intro_html(name, n_rows), "intro"])
        page.wait_for_timeout(100)
    d.mark("intro")
    page.wait_for_selector('[data-testid="stApp"]', timeout=60000)
    d.idle(800, timeout=60000)
    d.overlay()
    d.pause(max(0, 5000 - int((d.now() - d.scenes[-1]["t"]) * 1000)))

    # Home
    if d.record:
        page.evaluate("() => window.__demo.uncard()")
        d.pause(500)
        page.evaluate("() => window.__demo.cursor(true)")
    d.mark("home", CAPTIONS["home"])
    h1 = d.first_visible(page.locator("h1"), timeout=3000)
    if h1:
        d.hover(h1, 0.3, 0.5)
        d.pause(300)
        d.hover(h1, 0.75, 0.6)
    d.pause(300)
    d.shot("home")
    bento = d.first_visible(page.locator(".bento"), timeout=2000)
    if bento:  # the stat tiles count up (1.1 s) once they scroll into view; hold until they settle
        d.scroll_to(bento)
        d.pause(1300)

    # Start
    # the CTA band sits below the stats, so no scroll back up to the hero button
    start = d.first_visible(page.locator('.st-key-cta_band_start button'), page.get_by_role("link", name=re.compile("start your risk check", re.I)),
                            page.get_by_role("button", name=re.compile("start your risk check", re.I)), timeout=3000)
    if start:
        d.mark("start", CAPTIONS["start"])
        d.scroll_to(start)
        d.click(start)
        d.idle(600)
        d.overlay()  # no-op unless the page reloaded
        d.pause(300)
    else:
        print("    no 'Start your risk check' control: skipping the start scene", flush=True)
    quick = d.first_visible(page.get_by_role("tab", name=re.compile(r"^\s*quick check", re.I)), timeout=3000)
    if quick:
        d.click(quick)
        d.idle()

    # Quick check
    d.mark("fill", CAPTIONS["fill"])
    # Real use on screen: type, click toggles, open a dropdown. Blood pressure Yes also unlocks the what-if toggle.
    d.type_into(d.widget("Age (years)"), PERSONA["age"])
    sex = d.widget("Sex")
    d.click(sex.locator("button").filter(has_text=re.compile(r"^\s*Male\s*$")))
    d.idle()
    d.type_into(d.widget("Height (cm)"), PERSONA["height"])
    d.type_into(d.widget("Weight (kg)"), PERSONA["weight"])
    for label in ("high blood pressure", "high cholesterol"):
        w = d.widget(label)
        d.scroll_to(w)
        d.click(w.locator("button").filter(has_text=re.compile(r"^\s*Yes\s*$")))
        d.idle()
    health = d.widget("rate your health")
    d.scroll_to(health)
    d.click(health.locator('[role="combobox"], [data-baseweb="select"]').first)
    d.pause(250)
    d.click(page.get_by_role("option", name=PERSONA["health"], exact=True))
    d.idle()
    submit = d.first_visible(page.get_by_role("button", name=re.compile("check my risk", re.I)))
    d.scroll_to(submit)
    d.click(submit)
    d.idle(500)

    # Result
    risk = d.first_visible(page.get_by_text("Estimated risk", exact=True), timeout=20000)
    if not risk:
        raise RuntimeError("result did not appear")
    d.mark("result", CAPTIONS["result"])
    d.scroll_to(risk, "center")
    d.hover(risk, 0.6, 3)
    d.pause(900)
    bars = d.first_visible(page.get_by_text("What raised your score", exact=True), timeout=3000)
    if bars:
        d.hover(bars, 0.3, 4)
        d.pause(600)
    d.pause(300)
    d.shot("result")

    # What-if
    weight = d.widget("If your weight were")
    active = page.get_by_text("If you exercised regularly", exact=True).filter(visible=True).count() > 0
    d.mark("whatif", CAPTIONS["whatif" if active else "whatif_bp"])
    d.scroll_to(weight)
    d.drag_slider(weight, value=PERSONA["weight_after"])
    d.pause(300)
    habit = d.first_visible(page.get_by_text("If you exercised regularly", exact=True),
                            page.get_by_text(re.compile("blood pressure were treated", re.I)), timeout=3000)
    if habit:
        d.click(habit)
        d.idle()
    after = d.first_visible(page.get_by_text(re.compile("^With changes")), timeout=8000)
    if after:
        d.scroll_to(after)
        d.hover(after, 0.5, 1.5)
    d.pause(700)
    d.shot("whatif")

    # Population insights
    if d.record:
        page.evaluate("() => window.__demo.caption('')")
    if go_to_page(d, "Population insights"):
        seg = d.first_visible(page.get_by_text("Population profiles", exact=True), timeout=10000)
        if seg:
            d.mark("segments", segments_caption())
            d.scroll_to(seg, "start")
            scatter = d.first_visible(page.locator('[class*="st-key-ins_pca"], .stPlotlyChart'), timeout=3000)
            d.pause(500)
            if scatter:
                d.hover(scatter, 0.35, 0.4)
                d.pause(400)
                d.hover(scatter, 0.6, 0.55)
            d.pause(400)
            d.shot("insights")
        cut = d.widget("Flag people whose estimate is at least")
        if cut.count():
            d.mark("cost", CAPTIONS["cost"])
            d.scroll_to(cut)
            d.drag_slider(cut, frac=min(0.92, d.slider_frac(cut) + 0.3))
            d.pause(900)
        else:
            print("    no cost planner: skipping the cost scene", flush=True)
        valid = d.first_visible(page.get_by_text(re.compile("hold up in later years")), timeout=2000)
        if valid:  # heading at the top, so the ROC-AUC table below it is on screen
            d.mark("validation", CAPTIONS["validation"])
            d.scroll_to(valid, "start")
            d.pause(600)
            year = d.widget("Survey year")  # the map sits beside the table: switch its year, then hover a state
            if year.count():
                d.drag_slider(year, frac=0.0)
                chart = d.first_visible(page.locator('[class*="st-key-ins_choropleth"]'), timeout=3000)
                if chart:
                    d.hover(chart, 0.55, 0.5)
                    d.pause(700)
            else:
                d.pause(900)
        else:
            print("    no multi-year summary: skipping the validation scene", flush=True)
        state_map = d.first_visible(page.locator(".st-key-card_ins_map"), page.get_by_text("By state", exact=True), timeout=2000)
        if state_map and not d.record:  # README screenshot only; the video stays under 60 s
            d.scroll_to(state_map, "start")
            page.wait_for_selector(".choroplethlayer path", state="attached", timeout=15000)
            page.wait_for_timeout(800)
            d.shot("state_map")
    else:
        print("    no Population insights page: skipping the insights scenes", flush=True)

    # Outro
    if d.record:
        page.evaluate("() => { window.__demo.caption(''); window.__demo.cursor(false); }")
        page.evaluate("([h, c]) => window.__demo.card(h, c)", [outro_html(name, live, github), "outro"])
    d.mark("outro")
    d.pause(4500)
    d.mark("end")


def shot(self: Director, name: str):
    if not self.record:
        SHOTS.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=str(SHOTS / f"{name}.png"))
        print(f"    screenshot {name}.png", flush=True)


Director.shot = shot


def product_name(page: Page) -> str:
    title = page.title().strip()
    parts = [p.strip() for p in re.split(r"\s+[·|\-]\s+", title) if p.strip()]
    return parts[-1] if parts else "Diabetes Risk Screening"


def run(args) -> tuple[Path | None, list]:
    port = free_port(args.port)
    base = f"http://127.0.0.1:{port}/"
    meta = json.loads((ROOT / "models" / "meta.json").read_text(encoding="utf-8"))
    n_rows = f"{meta['n_rows']:,}" if "n_rows" in meta else ""
    print(f"starting streamlit on {port}", flush=True)
    server = start_server(port)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--disable-gpu", "--disable-dev-shm-usage", "--renderer-process-limit=1"])  # the GPU process crashes when RAM is low
            try:
                # Pass 1: fast, no video. Validates every step and writes clean screenshots.
                ctx = browser.new_context(viewport={"width": W, "height": H}, device_scale_factor=1)
                page = ctx.new_page()
                print("pass 1: checks and screenshots", flush=True)
                d = Director(page, record=False, base_url=base)
                d.page.goto(base)
                d.page.wait_for_selector('[data-testid="stApp"]', timeout=60000)
                d.idle(800, timeout=60000)
                name = args.name or product_name(page)
                print(f"  product name: {name}", flush=True)
                story(d, name, n_rows, args.live_url, args.github_url)
                ctx.close()
                if args.dry_run:
                    return None, d.scenes

                # Pass 2: the recording.
                shutil.rmtree(BUILD / "video", ignore_errors=True)
                ctx = browser.new_context(viewport={"width": W, "height": H}, device_scale_factor=1,
                                          record_video_dir=str(BUILD / "video"), record_video_size={"width": W, "height": H})
                page = ctx.new_page()
                print("pass 2: recording", flush=True)
                d = Director(page, record=True, base_url=base)
                story(d, name, n_rows, args.live_url, args.github_url)
                video = Path(page.video.path())
                ctx.close()
                raw = BUILD / "raw.webm"
                shutil.move(video, raw)
                (BUILD / "scenes.json").write_text(json.dumps(d.scenes, indent=2), encoding="utf-8")
                return raw, d.scenes
            finally:
                browser.close()
    finally:
        server.terminate()
        try:
            server.wait(10)
        except subprocess.TimeoutExpired:
            server.kill()


# ---------------------------------------------------------------- post-processing

def ff(*a):
    cmd = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error", *map(str, a)]
    subprocess.run(cmd, check=True)


def probe_duration(path: Path) -> float:
    out = subprocess.run([FFMPEG, "-hide_banner", "-i", str(path)], capture_output=True, text=True).stderr
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", out)
    return int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3]) if m else 0.0


def post(raw: Path, scenes: list):
    t = {s["name"]: s["t"] for s in scenes}
    start = t["intro"] + CUT_SKIP
    dur = t["end"] - start
    # Rerun speed varies with machine load; a uniform speed-up of up to ~15% keeps the cut under 60 s unnoticed.
    # Uniform speed-up, at most 10%, keeps the cut under 60 s; voiceover.py speeds the narration by the same k.
    k = max(1.0, min(1.10, dur / 59.5))
    (BUILD / "cut.json").write_text(json.dumps({"start": start, "k": k, "dur": dur / k}), encoding="utf-8")
    rel = {n: (v - start) / k for n, v in t.items()}
    x264 = ["-c:v", "libx264", "-preset", "slow", "-crf", "18", "-profile:v", "high", "-level", "4.1",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an"]
    main = DEMO / "demo_1080p.mp4"
    print(f"encoding demo_1080p.mp4 ({dur:.1f}s take at {k:.2f}x)", flush=True)
    ff("-ss", f"{start:.3f}", "-i", raw, "-t", f"{dur:.3f}",
       "-vf", f"setpts=PTS/{k:.4f},fps=30,scale=1920:1080:flags=lanczos,format=yuv420p", "-r", "30", *x264, main)

    print("encoding demo_square.mp4", flush=True)
    ff("-i", main, "-vf", "scale=1080:-2:flags=lanczos,pad=1080:1080:0:(oh-ih)/2:color=0x0C3646,format=yuv420p",
       "-r", "30", *x264, DEMO / "demo_square.mp4")

    # GIF: fill -> result -> what-if, sped up to fit about 14 s.
    g0, g1 = rel["result"] - 2.5, rel.get("segments") or rel["outro"]
    speed = max(1.0, (g1 - g0) / 14.0)
    print(f"encoding demo.gif ({g1 - g0:.1f}s at {speed:.2f}x)", flush=True)
    vf = f"setpts=PTS/{speed:.3f},fps=12,scale=960:-1:flags=lanczos"
    pal = BUILD / "palette.png"
    ff("-ss", f"{g0:.3f}", "-t", f"{g1 - g0:.3f}", "-i", main, "-vf", f"{vf},palettegen=max_colors=128:stats_mode=diff", pal)
    ff("-ss", f"{g0:.3f}", "-t", f"{g1 - g0:.3f}", "-i", main, "-i", pal, "-lavfi",
       f"{vf}[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle", DEMO / "demo.gif")

    print("writing thumbnail.png", flush=True)
    ff("-ss", f"{rel['whatif'] - 0.6:.3f}", "-i", main, "-frames:v", "1", DEMO / "thumbnail.png")

    for f in ("demo_1080p.mp4", "demo_square.mp4", "demo.gif", "thumbnail.png"):
        p = DEMO / f
        extra = f", {probe_duration(p):.1f}s" if p.suffix in (".mp4", ".gif") else ""
        print(f"  {p.relative_to(ROOT)}: {p.stat().st_size / 1e6:.2f} MB{extra}", flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8610)
    ap.add_argument("--name", default="SugarScope", help="product name on the title cards")
    ap.add_argument("--live-url", default="your-app.streamlit.app")
    ap.add_argument("--github-url", default="https://github.com/Kareemtamer99/diabetes-risk-screening")
    ap.add_argument("--dry-run", action="store_true", help="fast pass only: checks every step and writes screenshots")
    ap.add_argument("--post-only", action="store_true", help="re-run post-processing on demo/build/raw.webm")
    args = ap.parse_args()
    if args.post_only:
        post(BUILD / "raw.webm", json.loads((BUILD / "scenes.json").read_text(encoding="utf-8")))
        return
    raw, scenes = run(args)
    if raw:
        post(raw, scenes)
    print("done", flush=True)


if __name__ == "__main__":
    sys.exit(main())
