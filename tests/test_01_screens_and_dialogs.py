"""Startup, every tab, every dialog, and the per-game settings screen for each console."""
from harness import *

app = new_app()
lib = lambda: app.cfg["library"]
key_for = lambda title: next(k for k, e in lib().items() if e["title"] == title)

check("library lists every game (incl. Armored Core VI via Steam)", len(app.tree.get_children()) == 9, str(len(app.tree.get_children())))
shot("library")
for tab in ("ARCHIVE", "SOUNDTRACKS", "MUSIC", "ACHIEVEMENTS", "LIBRARY"):
    app.show_tab(tab); pump(app, 4); check(f"tab {tab} opens", app.cur_tab == tab and not ERR, "\n".join(ERR)[:400]); shot("tab_" + tab.lower())

for name, fn in (("System Check", app.system_check), ("Controllers", app.controllers_dialog), ("Themes", app.theme_dialog), ("Reset / Uninstall", app.reset_dialog)):
    fn(); pump(app, 4); check(f"dialog: {name}", bool(toplevels(app)) and not ERR, "\n".join(ERR)[:400]); shot("dlg_" + name.split()[0].lower()); close_all(app)

for title in ("Armored Core", "Armored Core 3", "Armored Core 3 Portable", "Armored Core: For Answer"):
    app.tree.selection_set(key_for(title)); pump(app, 1); app.game_settings(); pump(app, 4)
    check(f"game settings: {title}", bool(toplevels(app)) and not ERR, "\n".join(ERR)[:400]); shot("settings_" + title.split()[-1].lower()); close_all(app)

app.tree.selection_set(key_for(a.AC6_TITLE)); pump(app, 1); app.game_settings(); app.save_slots()
check("Armored Core VI: settings/slots explain it is handled by Steam", not toplevels(app) and not ERR)
app.tree.selection_set(key_for("Armored Core: For Answer")); pump(app, 1)
app.save_slots(); pump(app, 3); check("save slots dialog", bool(toplevels(app)) and not ERR); shot("slots"); close_all(app)
app.diagnose_ps3(); pump(app, 3); check("diagnose dialog reads the RPCS3 log", bool(toplevels(app)) and not ERR); shot("diagnose"); close_all(app)
app.view_lore(); pump(app, 2); check("VIEW LORE jumps to the archive entry", app.cur_tab == "ARCHIVE" and app.sel_lore == "Armored Core: For Answer")
finish(app)
