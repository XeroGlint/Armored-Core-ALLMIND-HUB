"""Pressing SORTIE, end to end, with a fake emulator process: settings applied during the run and restored after,
backup, playtime, failed launches, Steam, manual add, hide, shortcuts and --play."""
import zipfile
from harness import *

app = new_app()
lib = lambda: app.cfg["library"]
key_for = lambda title: next(k for k, e in lib().items() if e["title"] == title)
ps3_dir = pathlib.Path(app.cfg["emulators"]["PS3"]).parent; ps3_cfg = ps3_dir / "config" / "config.yml"
ps2_ini = pathlib.Path(app.cfg["emulators"]["PS2"]).parent / "inis" / "PCSX2.ini"
original = "Video:\n  Renderer: Vulkan\n  Frame limit: 60\n  Resolution Scale: 200\n  Write Color Buffers: false\n"
orig_ini = "[EmuCore/GS]\nupscale_multiplier = 1\n\n[EmuCore]\nCdvdVerboseReads = false\n"
ps3_cfg.write_text(original); ps2_ini.parent.mkdir(exist_ok=True); ps2_ini.write_text(orig_ini)
save = ps3_dir / "dev_hdd0" / "home" / "00000001" / "savedata" / "GAME1"; save.mkdir(parents=True); (save / "SAVE.BIN").write_text("save")

PROCS, during, FAIL = [], {}, [False]
class FakeProc:
    def __init__(s, args): s.n = 0; s.args = args
    def poll(s):
        s.n += 1
        if s.n == 1:   # what the emulator would see while it runs
            during["ps3"] = ps3_cfg.read_text(); during["ps2"] = ps2_ini.read_text()
        return None if s.n < 3 else 0
def fake_spawn(args, **kw):
    if FAIL[0]: raise OSError("boom")
    p = FakeProc(args); PROCS.append(p); return p
a.spawn = fake_spawn

def run_game(k):
    """Let the app's own once-a-second timer watch the fake process until it 'exits' (about 3 seconds)."""
    t0 = time.time()
    while app.running and time.time() - t0 < 12: pump(app, 1, 0.1)

# ---- PS3: For Answer ----
fa = key_for("Armored Core: For Answer"); app.tree.selection_set(fa); pump(app, 2)
n0 = len(CALLS); app.play(); pump(app, 2); kinds = [c[0] for c in CALLS[n0:]]
check("missing firmware prompt appears", "askyesnocancel" in kinds, str(kinds))
check("first-PS3-launch notice appears", "showinfo" in kinds)
check("emulator is started with the game", bool(PROCS) and PROCS[0].args[-1] == fa and "--no-gui" in PROCS[0].args)
check("launcher is marked as running", app.running is True)
pt0 = lib()[fa]["playtime"]; run_game(fa)
d = during.get("ps3", "")
check("settings are applied while the game runs", all(x in d for x in ("Write Color Buffers: true", "Handle RSX memory tiling: true", "Frame limit: Auto", "Minimum Scalable Dimension: 320")), d.replace("\n", " | "))
check("auto resolution matches the display", f"Resolution Scale: {a.auto_scale('PS3', app.winfo_screenheight())}" in d, d.replace("\n", " | "))
now = ps3_cfg.read_text()
check("your own RPCS3 settings are restored afterwards", all(x in now for x in ("Frame limit: 60", "Resolution Scale: 200", "Write Color Buffers: false")) and "Handle RSX" not in now, now.replace("\n", " | "))
check("playtime is recorded", lib()[fa]["playtime"] > pt0)
zs = list((a.EMU_HOME.parent / "backups").glob("auto_PS3_*.zip"))
check("an automatic save backup was made", bool(zs) and any("SAVE.BIN" in n for n in zipfile.ZipFile(zs[0]).namelist()), str(zs))
check("launcher returns to idle", app.running is False and not app.cfg.get("pending_restore"))
time.sleep(0.8); pump(app, 4)
check("a very short session offers the crash diagnosis", any(c[0] == "askyesno" and "closed" in str(c[1]).lower() for c in CALLS))
close_all(app)
n1 = len(CALLS); app.play(); pump(app, 1); run_game(fa); close_all(app)
check("the firmware prompt is not repeated", "askyesnocancel" not in [c[0] for c in CALLS[n1:]])

# ---- failed launch ----
ps3_cfg.write_text(original); FAIL[0] = True; app.play(); pump(app, 1); FAIL[0] = False
check("a failed launch leaves your settings untouched", ps3_cfg.read_text() == original and not app.running and not app.cfg.get("pending_restore"))
check("a failed launch reports an error", any(c[0] == "showerror" for c in CALLS))

# ---- PS2 ini ----
ac3 = key_for("Armored Core 3"); app.tree.selection_set(ac3); pump(app, 1); app.play(); pump(app, 1); run_game(ac3)
check("PCSX2 settings are applied while running", "upscale_multiplier = " in during["ps2"] and "upscale_multiplier = 1\n" not in during["ps2"], during["ps2"].replace("\n", " | "))
check("PCSX2 settings are restored afterwards", ps2_ini.read_text().strip() == orig_ini.strip(), ps2_ini.read_text().replace("\n", " | "))
close_all(app)

# ---- Steam ----
ac6 = key_for(a.AC6_TITLE); app.tree.selection_set(ac6); pump(app, 1); n2 = len(PROCS); app.play(); pump(app, 1)
check("Armored Core VI is launched through Steam", len(PROCS) == n2 + 1 and PROCS[-1].args == ["xdg-open", "steam://rungameid/1888160"], str(PROCS[-1].args))
app.watch_steam(ac6, time.time() - 300, None); pump(app, 1)
check("the Steam watcher gives up if the game never starts", app.running is False)

# ---- manual add, hide, restore, shortcut, --play ----
extra = pathlib.Path(HOME) / "odd_name.iso"; extra.write_text("x")
app.ask_system = lambda: "PS2"; app.pick_title = lambda s: "Armored Core: Last Raven"; filedialog.askopenfilename = lambda *a, **k: str(extra)
n = len(lib()); app.add_game_manual(); pump(app, 1)
check("a manually added game appears", len(lib()) == n + 1 and any(e["title"] == "Armored Core: Last Raven" for e in lib().values()))
app.hide_game(key_for("Armored Core: Last Raven")); pump(app, 1)
check("hiding removes it from the library", not any(e["title"] == "Armored Core: Last Raven" for e in lib().values()))
app.unhide_all(); check("restore hidden games clears the hidden list", app.cfg["hidden"] == [])
app.make_shortcut(ac3); check("desktop shortcut explains it is Windows-only here", CALLS[-1][0] == "showinfo")
app.autoplay = "Armored Core 3"; n3 = len(PROCS); app.run_autoplay(); pump(app, 1); run_game(ac3)
check("a --play shortcut launches the right game", len(PROCS) == n3 + 1 and PROCS[-1].args[-1] == ac3, str(PROCS[-1].args))
finish(app)
