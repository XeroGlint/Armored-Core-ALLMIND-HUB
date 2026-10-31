"""All 8 themes: colour contrast (WCAG) and a real render of each in its own process."""
import os, subprocess, sys
if len(sys.argv) > 2 and sys.argv[1] == "--one":
    from harness import *
    app = new_app(sys.argv[2]); app.tree.selection_set(next(iter(app.cfg["library"]))); pump(app, 3)
    shot("theme_" + sys.argv[2].replace(" ", "_")); check(f"theme {sys.argv[2]} renders", not ERR, "\n".join(ERR)[:300]); finish(app)

import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import ac_launcher as a
def lum(h):
    r, g, b = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)
def contrast(x, y):
    p, q = lum(x), lum(y); return (max(p, q) + 0.05) / (min(p, q) + 0.05)
PAIRS = [("TEXT", "PANEL", 4.5), ("TEXT", "BG", 4.5), ("TEXT", "PANEL2", 4.5), ("CYAN", "PANEL", 4.5), ("CYAN", "PANEL2", 4.5), ("DIM", "PANEL", 3.0), ("DIM", "PANEL2", 3.0),
         ("ORANGE", "PANEL", 3.0), ("ORANGE", "PANEL2", 3.0), ("ACC_FG", "ORANGE", 4.5), ("RED", "PANEL", 3.0), ("WARN", "PANEL2", 3.0), ("HOV_FG", "HOV", 4.5), ("ACC_FG", "ACC_HOV", 4.5)]
fails = 0
for name, pal in a.THEMES.items():
    bad = [f"{fg} on {bg} = {contrast(pal[fg], pal[bg]):.2f}" for fg, bg, need in PAIRS if contrast(pal[fg], pal[bg]) < need]
    print(("PASS " if not bad else "FAIL ") + f"{name}: text and accent colours are readable" + (f"  [{'; '.join(bad)}]" if bad else ""))
    fails += bool(bad)
    r = subprocess.run([sys.executable, __file__, "--one", name], capture_output=True, text=True, timeout=120)
    ok = r.returncode == 0
    print(("PASS " if ok else "FAIL ") + f"{name}: renders without errors" + ("" if ok else "  [" + (r.stdout + r.stderr)[-300:] + "]"))
    fails += not ok
sys.exit(1 if fails else 0)
