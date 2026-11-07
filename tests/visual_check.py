"""Visual QA: real Chromium screenshots + layout asserts that AppTest cannot see (CSS, clipping, overlap, motion).

Per page and width: H1 below the nav and in view, no horizontal overflow, nav inset >= 12 px, no overlapping
text in the header band and cards, one-line slider bubbles, count-ups end on the same values as with
prefers-reduced-motion (and on any data-target), the home hero preview is labelled "Example", and no
scroll-reveal content is left at opacity 0 after scrolling to the bottom. A contact sheet per width is written too.

Run:  .venv/Scripts/python.exe tests/visual_check.py [--out G:/Temp/edge_final/visual]
Writes <out>/<page>_<WxH>.png and <out>/results.json; exit 1 if any layout assert fails.
"""
import argparse
import json
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "demo"))
from record import free_port, start_server  # noqa: E402  (same server start the demo recorder uses)

SIZES = [(1920, 1080), (1366, 768), (768, 1024), (375, 812)]
# The default page lives at "/"; "/home" shows Streamlit's "Page not found" dialog.
PAGES = [("home", "", None), ("risk_quick", "risk-check", "Quick check"), ("risk_full", "risk-check", "Full check"),
         ("insights", "population-insights", None), ("about", "how-it-works", None)]
assert len(PAGES) == 5

# One JS pass returns every layout fact the asserts need, measured at scroll 0 in the real viewport.
MEASURE = r"""() => {
  const vw = innerWidth, vh = innerHeight, out = {vw, vh};
  const vis = e => { const s = getComputedStyle(e), r = e.getBoundingClientRect();
    return s.visibility !== 'hidden' && s.display !== 'none' && +s.opacity > 0 && r.width > 0 && r.height > 0; };
  const box = e => { const r = e.getBoundingClientRect(); return {top: r.top, bottom: r.bottom, left: r.left, right: r.right}; };
  const header = document.querySelector('[data-testid="stHeader"]');
  out.nav = header ? box(header) : null;
  const navItems = header ? [...header.querySelectorAll('a, button')].filter(vis) : [];
  out.navFirst = navItems.length ? {text: navItems[0].innerText.trim().slice(0, 30), ...box(navItems[0])} : null;
  const h1 = [...document.querySelectorAll('h1')].find(vis);
  out.h1 = h1 ? {text: h1.innerText.trim().slice(0, 40), ...box(h1)} : null;
  // Overflow: visible elements past the viewport edge, unless an ancestor clips or scrolls them.
  const clipped = e => { for (let p = e.parentElement; p && p !== document.body; p = p.parentElement) {
      if (getComputedStyle(p).overflowX !== 'visible') return true; } return false; };
  out.overflow = [...document.querySelectorAll('body *')].filter(e => vis(e)).map(e => [e, e.getBoundingClientRect()])
    // only things a user could see poking out: starts on screen, ends past the right edge (plotly parks a measuring svg at left -1000)
    .filter(([e, r]) => r.right > vw + 1 && r.left < vw && r.left > -1 && !clipped(e))
    .slice(0, 8).map(([e, r]) => `${e.tagName.toLowerCase()}.${[...e.classList].slice(0, 2).join('.')} right=${Math.round(r.right)}`);
  out.scrollW = document.documentElement.scrollWidth;
  // Text overlap in the header band (nav + hero) and the cards: line boxes of different text nodes intersecting.
  const scopes = [header, ...document.querySelectorAll('.hero, [class*="st-key-card_"]')].filter(Boolean);
  const rects = [];
  for (const sc of scopes) {
    const w = document.createTreeWalker(sc, NodeFilter.SHOW_TEXT);
    for (let n = w.nextNode(); n; n = w.nextNode()) {
      const el = n.parentElement;
      if (!n.textContent.trim() || !el || el.closest('svg') || !vis(el)) continue;
      const rg = document.createRange(); rg.selectNodeContents(n);
      for (const r of rg.getClientRects()) if (r.width > 1 && r.height > 1) rects.push({n, t: n.textContent.trim().slice(0, 25), r});
    }
  }
  const seen = new Set(); out.overlaps = [];
  for (let i = 0; i < rects.length; i++) for (let j = i + 1; j < rects.length; j++) {
    const a = rects[i], b = rects[j]; if (a.n === b.n) continue;
    const ix = Math.min(a.r.right, b.r.right) - Math.max(a.r.left, b.r.left);
    const iy = Math.min(a.r.bottom, b.r.bottom) - Math.max(a.r.top, b.r.top);
    // 2 px slack: inline neighbours and line-height leading touch without overlapping visibly
    if (ix > 2 && iy > 2) { const k = a.t + '|' + b.t; if (!seen.has(k)) { seen.add(k); out.overlaps.push(`"${a.t}" x "${b.t}"`); } }
  }
  out.overlaps = out.overlaps.slice(0, 8);
  out.plots = [...document.querySelectorAll('.js-plotly-plot')].filter(vis).length;
  out.webgl = document.querySelectorAll('.js-plotly-plot canvas, canvas.gl-canvas').length
    + (/webgl is not supported/i.test(document.body.innerText) ? 1 : 0);
  out.notFound = [...document.querySelectorAll('[role="dialog"], [data-testid="stDialog"], [data-baseweb="modal"]')]
    .filter(vis).map(e => e.innerText.trim()).filter(t => /page not found/i.test(t)).map(t => t.slice(0, 80))
    .concat(/page not found/i.test(document.body.innerText) && !document.querySelector('[role="dialog"]') ? ['"Page not found" text on page'] : []);
  // Slider value bubbles: one line = all line boxes share one top.
  out.bubbles = [...document.querySelectorAll('[data-testid="stSliderThumbValue"]')].filter(vis).map(e => {
    // line boxes of the text nodes only (element rects nest and would double count); tops within 3 px = same line
    const tops = [], w = document.createTreeWalker(e, NodeFilter.SHOW_TEXT);
    for (let n = w.nextNode(); n; n = w.nextNode()) { if (!n.textContent.trim()) continue;
      const rg = document.createRange(); rg.selectNodeContents(n);
      for (const r of rg.getClientRects()) if (r.width > 0 && !tops.some(t => Math.abs(t - r.top) < 3)) tops.push(r.top); }
    return {text: e.innerText.trim(), lines: tops.length}; });
  return out;
}"""

# Run in every frame (st.components.html content lives in iframes). Numbers that look animated: elements marked
# as count-ups, plus their declared target if the markup gives one.
NUMBERS = r"""() => [...document.querySelectorAll('[data-count]')]
  .map(e => ({text: e.textContent.trim(), target: e.dataset.final ?? e.dataset.count}))"""  # app.py MOTION_JS ends on data-final

# Scroll the page's scroll container to the bottom in steps (fires IntersectionObserver reveals), then list
# on-screen-sized elements still at opacity ~0.
SCROLL_ALL = """async () => { let s = document.scrollingElement, h = s.scrollHeight;
  for (const e of document.querySelectorAll('*')) { const o = getComputedStyle(e).overflowY;
    if ((o === 'auto' || o === 'scroll') && e.scrollHeight > h) { s = e; h = e.scrollHeight; } }
  for (let y = 0; y <= h; y += Math.max(200, innerHeight / 2)) { s.scrollTop = y; scrollTo(0, y); await new Promise(r => setTimeout(r, 120)); }
  s.scrollTop = h; await new Promise(r => setTimeout(r, 1200)); }"""
# Streamlit's slider min/max tick labels sit at opacity 0 until hover by design, so they are excluded.
STUCK = r"""() => [...document.querySelectorAll('.rv:not(.rv-in)')].map(e => `.rv never revealed: "${e.textContent.trim().slice(0, 30)}"`)
  .concat([...document.querySelectorAll('body *')].filter(e => {
    const r = e.getBoundingClientRect(); if (r.width < 8 || r.height < 8 || !e.textContent.trim()) return false;
    if (e.closest('svg, [aria-hidden="true"], .js-plotly-plot .hoverlayer, [role="tooltip"], [data-testid^="stSlider"]')) return false;
    const s = getComputedStyle(e); return s.display !== 'none' && s.visibility !== 'hidden' && +s.opacity < 0.05;
  }).filter(e => !(e.parentElement && +getComputedStyle(e.parentElement).opacity < 0.05))  // report the outermost only
  .slice(0, 8).map(e => `${e.tagName.toLowerCase()}.${[...e.classList].slice(0, 2).join('.')} "${e.textContent.trim().slice(0, 30)}"`))"""

EXAMPLE = r"""() => [...document.querySelectorAll('.pv *, [class*="hero"] *, [class*="preview"] *')]
  .some(e => e.children.length === 0 && /^\s*example\b/i.test(e.textContent) && e.getBoundingClientRect().width > 0)"""


def in_frames(page, js):
    """Evaluate js in the page and every child frame; concatenate list results, OR boolean ones."""
    vals = []
    for fr in page.frames:
        try:
            vals.append(fr.evaluate(js))
        except Exception:  # cross-origin or detached frame: nothing of ours in it
            pass
    if vals and isinstance(vals[0], bool):
        return any(vals)
    return [x for v in vals if v for x in v]


def motion_checks(page, reduced_page, name):
    """Count-ups end on the same values as with reduced motion (and on any declared target); reveals all fire."""
    fails = []
    if name == "home" and not in_frames(page, EXAMPLE):
        fails.append('hero preview card is not labelled "Example"')
    for fr in page.frames:  # count-ups start only when scrolled into view, so scroll everything first
        try:
            fr.evaluate(SCROLL_ALL)
        except Exception:
            pass
    page.wait_for_timeout(2000)  # 1.1 s count-up + 1.5 s failsafe window
    animated = in_frames(page, NUMBERS)
    still = in_frames(reduced_page, NUMBERS)
    for a in animated:
        if a["target"] is not None and a["text"] != str(a["target"]):
            fails.append(f"count-up shows {a['text']!r}, target {a['target']!r}")
    if [a["text"] for a in animated] != [s["text"] for s in still]:
        fails.append(f"count-up end values differ from reduced-motion values: {[a['text'] for a in animated]} vs {[s['text'] for s in still]}")
    stuck = in_frames(page, STUCK)
    if stuck:
        fails.append(f"scroll-reveal stuck at opacity 0 after scrolling: {stuck}")
    return fails, len(animated)


SCROLLER = """() => { let best = document.scrollingElement, h = best.scrollHeight;
  for (const e of document.querySelectorAll('*')) { const s = getComputedStyle(e).overflowY;
    if ((s === 'auto' || s === 'scroll') && e.scrollHeight > h) { best = e; h = e.scrollHeight; } }
  return h; }"""


def settle(page, ms=800):
    page.wait_for_selector('[data-testid="stApp"]', timeout=60000)
    page.wait_for_function("() => !document.querySelector('[data-testid=\"stStatusWidget\"]')", timeout=60000)
    page.wait_for_timeout(ms)


def prepare(page, base, path, tab):
    page.goto(f"{base}/{path}", wait_until="domcontentloaded")
    settle(page, 1200)
    page.locator("h1").first.wait_for(state="visible", timeout=20000)  # first load of a fresh context renders late
    if tab:
        page.get_by_role("tab", name=re.compile(rf"^\s*{tab}", re.I)).first.click()
        settle(page)
        page.get_by_role("button", name=re.compile("check my risk", re.I)).filter(visible=True).first.click()
        settle(page, 1500)
        # what-if open: move the weight slider 15 kg down so the before/after state is on screen
        # Streamlit 1.67 sliders are a hidden input[type=range] (no role=slider); keyboard on it, as demo/record.py does
        slider = page.locator('[class*="whatif"] input[type="range"]')
        if slider.count():
            slider.first.focus()
            for _ in range(15):
                slider.first.press("ArrowLeft")
            settle(page, 1500)
    if path == "population-insights":
        page.locator(".js-plotly-plot").last.wait_for(state="visible", timeout=30000)
        page.wait_for_timeout(1500)
    page.evaluate("() => { document.querySelectorAll('*').forEach(e => { if (e.scrollTop) e.scrollTop = 0; }); }")


def check(m, name=""):
    fails = []
    # insights swallows chart errors, so a chart can vanish without any app error: count them
    if name == "insights":
        if m["plots"] < 4:
            fails.append(f"insights shows {m['plots']} Plotly charts, want >= 4 (scatter, cost, trend, map)")
        if m["webgl"]:
            fails.append(f"WebGL canvas / 'WebGL is not supported' present ({m['webgl']})")
    if m["notFound"]:
        fails.append(f"'Page not found' dialog present: {m['notFound']}")
    nav, h1, nf = m["nav"], m["h1"], m["navFirst"]
    if not h1:
        fails.append("no visible H1")
    else:
        if nav and h1["top"] < nav["bottom"] - 0.5:
            fails.append(f"H1 '{h1['text']}' top {h1['top']:.0f} < nav bottom {nav['bottom']:.0f} (clipped under nav)")
        if h1["top"] < 0 or h1["bottom"] > m["vh"] or h1["left"] < 0 or h1["right"] > m["vw"]:
            fails.append(f"H1 '{h1['text']}' not fully inside viewport {h1}")
    if m["scrollW"] > m["vw"] + 1 or m["overflow"]:
        fails.append(f"horizontal overflow: scrollWidth {m['scrollW']} > {m['vw']}; {m['overflow']}")
    if nf and nf["left"] < 12:
        fails.append(f"nav first item '{nf['text']}' left {nf['left']:.0f}px < 12px")
    if m["overlaps"]:
        fails.append(f"text overlap: {m['overlaps']}")
    multi = [b for b in m["bubbles"] if b["lines"] > 1]
    if multi:
        fails.append(f"slider bubble wraps: {multi}")
    return fails


def contact_sheets(out, col_w=480):
    """One PNG per width: every page side by side, scaled to col_w, labelled, for a quick human review."""
    from PIL import Image, ImageDraw
    for w, h in SIZES:
        shots = [(name, out / f"{name}_{w}x{h}.png") for name, _, _ in PAGES]
        imgs = [(n, Image.open(p).convert("RGB")) for n, p in shots if p.exists()]
        if not imgs:
            continue
        cw = min(col_w, w)
        scaled = [(n, im.resize((cw, int(im.height * cw / im.width)))) for n, im in imgs]
        sheet = Image.new("RGB", (len(scaled) * (cw + 16) + 16, max(im.height for _, im in scaled) + 48), "white")
        draw = ImageDraw.Draw(sheet)
        for i, (n, im) in enumerate(scaled):
            x = 16 + i * (cw + 16)
            draw.text((x, 14), f"{n}  {w}x{h}", fill="black")
            sheet.paste(im, (x, 36))
        sheet.save(out / f"contact_{w}x{h}.png")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="G:/Temp/edge_final/visual")
    ap.add_argument("--sizes", default="", help="comma-separated widths to run, e.g. 768,375,1366 (default: all)")
    args = ap.parse_args()
    out = Path(args.out)
    if args.sizes:
        SIZES[:] = [s for s in SIZES if str(s[0]) in args.sizes.split(",")]  # contact_sheets reads SIZES too
        assert SIZES, f"no known width in --sizes {args.sizes}"
    out.mkdir(parents=True, exist_ok=True)
    port = free_port(8650)
    server = start_server(port)
    base, results = f"http://127.0.0.1:{port}", []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            for w, h in SIZES:
                ctx = browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=1)
                rctx = browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=1, reduced_motion="reduce")
                page, rpage = ctx.new_page(), rctx.new_page()
                for name, path, tab in PAGES:
                    shot = out / f"{name}_{w}x{h}.png"
                    try:
                        prepare(page, base, path, tab)
                        prepare(rpage, base, path, tab)
                        # Layout + screenshot on the reduced-motion page: deterministic end states, nothing mid-animation.
                        m = rpage.evaluate(MEASURE)
                        fails = check(m, name)
                        # Motion page: count-ups end right, nothing left at opacity 0 after scrolling.
                        mfails, n_counts = motion_checks(page, rpage, name)
                        fails += mfails
                        m["countups"] = n_counts
                        # Streamlit scrolls an inner container, so grow the viewport to its height for a full-page shot.
                        full = min(int(rpage.evaluate(SCROLLER)) + 40, 16000)
                        rpage.set_viewport_size({"width": w, "height": max(h, full)})
                        rpage.wait_for_timeout(900)
                        rpage.screenshot(path=str(shot), full_page=True)
                        rpage.set_viewport_size({"width": w, "height": h})
                    except Exception as e:  # one broken page must not hide the others
                        m, fails = {}, [f"could not render: {type(e).__name__}: {str(e)[:200]}"]
                    results.append({"page": name, "size": f"{w}x{h}", "shot": str(shot), "fails": fails, "countups": m.get("countups"),
                                    "plots": m.get("plots"), "webgl": m.get("webgl"),
                                    "h1": m.get("h1"), "nav": m.get("nav"), "navFirst": m.get("navFirst")})
                    print(f"[{'FAIL' if fails else 'PASS'}] {name:11} {w}x{h}" + "".join(f"\n    - {f}" for f in fails))
                ctx.close()
                rctx.close()
            browser.close()
    finally:
        server.kill()
    (out / "results.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    contact_sheets(out)
    n_fail = sum(bool(r["fails"]) for r in results)
    print(f"\n{len(results) - n_fail}/{len(results)} page x size combos pass; shots in {out}")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
