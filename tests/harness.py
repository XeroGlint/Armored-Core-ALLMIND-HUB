"""Shared helpers for the smoke tests. Runs the REAL launcher UI on a virtual display with fake emulators,
games and a throw-away HOME folder, so nothing on your machine is touched."""
import json, os, pathlib, sys, tempfile, time, traceback
HOME = os.environ.get("QA_HOME") or tempfile.mkdtemp()
os.environ["HOME"] = HOME
os.environ["USERPROFILE"] = HOME
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog

CALLS = []   # every pop-up the app tried to show: (kind, (title, text))
for _n in ("showinfo", "showwarning", "showerror"):
    setattr(messagebox, _n, (lambda n: lambda *a, **k: CALLS.append((n, a[:2])))(_n))
for _n in ("askyesno", "askokcancel", "askretrycancel"):
    setattr(messagebox, _n, (lambda n: lambda *a, **k: (CALLS.append((n, a[:2])), True)[1])(_n))
messagebox.askyesnocancel = lambda *a, **k: (CALLS.append(("askyesnocancel", a[:2])), False)[1]   # "launch anyway"
for _n in ("askopenfilename", "askdirectory"): setattr(filedialog, _n, lambda *a, **k: "")
filedialog.askopenfilenames = lambda *a, **k: ()
simpledialog.askstring = lambda *a, **k: None
tk.Menu.tk_popup = lambda self, *a, **k: None

import ac_launcher as a
ERR = []   # exceptions raised inside Tk callbacks
FAILS = []
OUT = pathlib.Path(os.environ.get("QA_OUT") or (pathlib.Path(tempfile.gettempdir()) / "ac_launcher_tests")); OUT.mkdir(exist_ok=True)


def make_world(theme="WHITE GLINT"):
    """Fake emulators, games, a fake Steam install, and a config pointing at them."""
    root = pathlib.Path(HOME) / "world"; root.mkdir(exist_ok=True)
    emus = {}
    for s, exe in (("PS1", "duckstation-qt.exe"), ("PS2", "pcsx2-qt.exe"), ("PSP", "PPSSPPWindows64.exe"), ("PS3", "rpcs3.exe")):
        d = root / "emus" / s; d.mkdir(parents=True, exist_ok=True); (d / exe).write_text("x"); emus[s] = str(d / exe)
    ps3 = pathlib.Path(emus["PS3"]).parent
    (ps3 / "config").mkdir(exist_ok=True); (ps3 / "config" / "config.yml").write_text("Video:\n  Frame limit: Auto\n")
    (ps3 / "RPCS3.log").write_text("\u00b7F 0:00:05.1 {PPU[0x1] Thread} VM: Access violation writing location 0x1\n\u00b7S 0:00:06 {x} done\n")
    games = {}
    def add(sys_, title, order, fn, **extra):
        p = root / "games" / sys_ / fn; p.parent.mkdir(parents=True, exist_ok=True); p.write_text("x")
        games[str(p)] = {"title": title, "system": sys_, "order": order, "playtime": 3700 * order, "last": time.time() - order * 100, "args": "", **extra}
    add("PS1", "Armored Core", 1, "Armored Core.cue"); add("PS1", "Armored Core: Project Phantasma", 2, "phantasma.cue", fav=True)
    add("PS2", "Armored Core 2", 4, "ac2.iso"); add("PS2", "Armored Core 3", 6, "ac3.iso"); add("PS2", "Armored Core: Nexus", 8, "nexus.iso")
    add("PSP", "Armored Core 3 Portable", 12, "ac3p.iso")
    add("PS3", "Armored Core 4", 15, "ac4.iso"); add("PS3", "Armored Core: For Answer", 16, "fa.iso")
    games["steam://rungameid/1888160"] = {"title": a.AC6_TITLE, "system": "PC", "order": 19, "playtime": 7200, "last": time.time(), "args": "", "dir": str(root)}
    st = root / "steam" / "steamapps"; st.mkdir(parents=True, exist_ok=True)
    (st / "appmanifest_1888160.acf").write_text('"AppState"\n{\n "appid" "1888160"\n "installdir" "ARMORED CORE VI FIRES OF RUBICON"\n}\n')
    cfg = {"steam_path": str(root / "steam"), "emulators": emus, "folders": [], "library": games, "fullscreen": True, "theme": theme, "skip_wizard": True}
    a.CFG_PATH.parent.mkdir(parents=True, exist_ok=True); a.CFG_PATH.write_text(json.dumps(cfg))
    return emus, games


def new_app(theme="WHITE GLINT", size="1280x820+0+0", fresh=True):
    if fresh: make_world(theme)
    a.apply_theme(theme)
    app = a.App()
    app.report_callback_exception = lambda et, ev, tb: ERR.append("".join(traceback.format_exception(et, ev, tb)))
    if size: app.geometry(size)
    pump(app, 8); time.sleep(1.0); pump(app, 8)   # let the launcher's own startup routine finish
    return app


def pump(app, n=6, d=0.05):
    for _ in range(n): app.update(); time.sleep(d)


def shot(name):
    try:
        from PIL import ImageGrab
        ImageGrab.grab(xdisplay=os.environ["DISPLAY"]).save(OUT / f"{name}.png")
    except Exception:
        pass


def check(label, ok, extra=""):
    print(("PASS " if ok else "FAIL ") + label + (f"  [{extra}]" if (extra and not ok) else ""))
    if not ok: FAILS.append(label)
    return ok


def toplevels(app): return [w for w in app.winfo_children() if isinstance(w, tk.Toplevel)]


def close_all(app):
    for w in toplevels(app): w.destroy()
    pump(app, 1)


def finish(app=None):
    check("no exceptions inside the app", not ERR, "\n".join(ERR)[:900])
    if app is not None:
        try: app.destroy()
        except Exception: pass
    sys.exit(1 if FAILS else 0)
