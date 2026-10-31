"""Run on a SMALL virtual screen (CI uses 1024x640): nothing important may be cut off. Also tests that the window
position is remembered between sessions (two separate runs sharing one HOME)."""
import os, subprocess, sys, tempfile
if len(sys.argv) > 1 and sys.argv[1] in ("--save", "--restore"):
    from harness import *
    if sys.argv[1] == "--save":
        app = new_app(size="1000x700+30+20"); app.on_close()
        check("window position is saved on close", json.loads(a.CFG_PATH.read_text()).get("geometry", "").startswith("1000x700"))
        sys.exit(1 if FAILS else 0)
    app = new_app(size=None, fresh=False); pump(app, 4)
    check("window position is restored next time", app.geometry().startswith("1000x700"), app.geometry()); finish(app)

from harness import *
app = new_app(size=None)
sw, sh = app.winfo_screenwidth(), app.winfo_screenheight()
def find(root, text):
    for w in root.winfo_children():
        if isinstance(w, tk.Label) and text in str(w.cget("text")) and w.winfo_viewable(): return w
        r = find(w, text)
        if r: return r
bottom = lambda w: w.winfo_rooty() + w.winfo_height()
check(f"window fits a {sw}x{sh} screen", app.winfo_width() <= sw and app.winfo_height() <= sh, f"{app.winfo_width()}x{app.winfo_height()}")
for text, label in (("\u25b6  SORTIE", "SORTIE button"), ("KO-FI", "Ko-fi button"), ("ACHIEVEMENTS", "last tab"), ("PLAYED", "status bar")):
    w = find(app, text); check(f"{label} is visible", w is not None and bottom(w) <= app.winfo_rooty() + app.winfo_height() + 2)
for name, fn in (("System Check", app.system_check), ("Controllers", app.controllers_dialog), ("Themes", app.theme_dialog), ("Reset / Uninstall", app.reset_dialog)):
    fn(); pump(app, 4); t = toplevels(app)[-1]; check(f"{name} dialog fits the screen", t.winfo_rooty() + t.winfo_height() <= sh + 2, f"{t.winfo_height()}"); shot("small_" + name.split()[0].lower()); t.destroy(); pump(app, 2)
app.tree.selection_set(next(k for k, e in app.cfg["library"].items() if e["title"] == "Armored Core: For Answer")); pump(app, 2)
app.game_settings(); pump(app, 4); t = toplevels(app)[-1]; btn = find(t, "SAVE")
check("game settings: the SAVE button stays reachable", btn is not None and bottom(btn) <= sh, f"{bottom(btn) if btn else None} vs {sh}"); shot("small_settings"); t.destroy()
shot("small_library")
home = tempfile.mkdtemp(); env = dict(os.environ, QA_HOME=home)
for mode in ("--save", "--restore"):
    r = subprocess.run([sys.executable, __file__, mode], env=env, capture_output=True, text=True, timeout=120)
    for line in r.stdout.splitlines():
        if line.startswith(("PASS", "FAIL")):
            print(line)
            if line.startswith("FAIL"): FAILS.append(line)
    if r.returncode != 0 and not any("FAIL" in l for l in r.stdout.splitlines()): check(f"geometry {mode} ran", False, (r.stdout + r.stderr)[-300:])
finish(app)
