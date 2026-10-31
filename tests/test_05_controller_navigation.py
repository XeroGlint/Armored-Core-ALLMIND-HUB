"""Controller navigation, driven with scripted XInput states against the real widgets."""
from harness import *

app = new_app()
app.focus_displayof = lambda: app   # a virtual display has no window focus
real_os = a.os
class FakeWindows:   # makes pad_poll believe it is on Windows without breaking pathlib
    name = "nt"
    def __getattr__(s, k): return getattr(real_os, k)
def frame(state):
    a.os = FakeWindows(); a.xinput_raw = lambda: state
    try: app.pad_poll()
    finally: a.os = real_os
    pump(app, 1, 0.01)
A, B, X, Y, LB, RB, START, BACK, DUP, DDN, DL, DR = 0x1000, 0x2000, 0x4000, 0x8000, 0x100, 0x200, 0x10, 0x20, 0x1, 0x2, 0x4, 0x8
idle = (0, 0, 0, 0, 0)
def press(btn=0, lt=0, rt=0, lx=0, ly=0):
    frame((btn, lt, rt, lx, ly)); frame(idle); app.pad_dir_t = 0

check("many cursor stops in the library", len(app.pad_cands(app)) >= 15)
app.pad_idle = 19; frame(idle); check("a connected pad shows the hint", app.pad_present and app.pad_hint.winfo_ismapped())
press(DDN); check("first press selects the game list", app.pad_cur is app.tree)
s0 = app.tree.selection()[0]; press(DDN); pump(app, 2); check("D-pad down moves through the list", app.tree.selection()[0] != s0)
press(0, lx=-30000); check("left stick leaves the list toward the sidebar", app.pad_cur not in (None, app.tree))
app.set_filter("ALL"); press(0, lt=255); check("LT: previous platform (wraps)", app.filter == "PC", app.filter)
press(0, rt=255); check("RT: next platform", app.filter == "ALL")
press(RB); check("RB: next tab", app.cur_tab == "ARCHIVE"); press(RB); press(RB); check("RB again: Music", app.cur_tab == "MUSIC")
press(LB); check("LB: previous tab", app.cur_tab == "SOUNDTRACKS"); press(B); check("B: back to Library", app.cur_tab == "LIBRARY")
pump(app, 3); app.pad_clear(); app.pad_cur = None
PROCS = []
class FP:
    def __init__(s, a): s.args = a
    def poll(s): return None
a.spawn = lambda args, **kw: (PROCS.append(args), FP(args))[1]
app.bios_warned = {"PS1", "PS2", "PS3"}
fk = next(k for k, e in app.cfg["library"].items() if e["title"] == "Armored Core 3"); app.tree.selection_set(fk); pump(app, 2)
app.pad_set(app.tree); press(A); check("A on the list launches the game", len(PROCS) == 1 and PROCS[0][-1].endswith("ac3.iso"), str(PROCS))
app.running = False; app.deiconify(); pump(app, 1)
press(Y); check("Y toggles favorite", app.cfg["library"][fk].get("fav") is True)
press(X); pump(app, 3); tops = toplevels(app); check("X opens game settings", len(tops) == 1)
press(DDN); check("the dialog becomes the navigation root", app.pad_root() is tops[0])
check("dialog buttons are cursor stops", len(app.pad_cands(tops[0])) >= 8)
press(DDN); press(DR); press(A); check("A inside a dialog works", not ERR, "\n".join(ERR)[:400])
press(B); pump(app, 2); check("B closes the dialog", not toplevels(app))
press(BACK); pump(app, 3); check("BACK opens System Check", bool(toplevels(app))); press(B); pump(app, 2)
keys = []; app.pad_native = lambda pressed, fire, dx, dy: keys.append(pressed)
a.NATIVE_DEPTH[0] = 1; press(A); a.NATIVE_DEPTH[0] = 0; check("while a Windows pop-up is open, A is passed to it", any(k & A for k in keys))
messagebox.showinfo("x", "y"); check("pop-up counter returns to zero", a.NATIVE_DEPTH[0] == 0)
a.os = FakeWindows(); a.xinput_raw = lambda: None
try: app.pad_poll()
finally: a.os = real_os
check("unplugging the pad hides the hint", not app.pad_present)
finish(app)
