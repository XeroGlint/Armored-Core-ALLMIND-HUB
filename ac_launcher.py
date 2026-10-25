#!/usr/bin/env python3
"""
ARMORED CORE LAUNCHER - AC4 / For Answer styled multi-emulator frontend.
Covers PS1/PS2/PSP/PS3 Armored Core games before AC6 via DuckStation, PCSX2,
PPSSPP and RPCS3. You supply your own legally dumped games, BIOS and emulators.

Run:  python ac_launcher.py        (Python 3 + Tkinter only)
Data: ~/.ac_launcher/config.json
"""
import json, os, queue, re, shutil, subprocess, sys, threading, time, zipfile
import html as htmllib
import hashlib, math, random, ssl, struct
import urllib.error
import xml.etree.ElementTree as ET
import urllib.parse, urllib.request
import tkinter as tk, tkinter.font as tkfont
from pathlib import Path
import webbrowser
from tkinter import ttk, filedialog, messagebox, simpledialog
try:
    from PIL import Image, ImageTk
    HAVE_PIL = True
except ImportError:  # app still works, just without images
    HAVE_PIL = False

if os.name == "nt":  # must run before Tk starts, otherwise Windows bitmap-stretches the window (blurry)
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try: ctypes.windll.user32.SetProcessDPIAware()
        except Exception: pass
SC = 1.0


def px(n):
    return int(round(n * SC))

CFG_PATH = Path.home() / ".ac_launcher" / "config.json"

# ---- themes. WHITE GLINT = pale steel + ice-blue glow; NEXT = dark gunmetal + warning orange.
# (The primary accent colour variable is called ORANGE for historical reasons.)
THEMES = {
    "WHITE GLINT": dict(BG="#cdd6de", PANEL="#f4f7fa", PANEL2="#e2e9ef", LINE="#a9b9c6", CYAN="#14688f",
                        TEXT="#17222b", DIM="#66798a", ORANGE="#0a8fc8", RED="#d4372a", WARN="#ff7a1a",
                        ACC_FG="#03202e", HOV="#d0e6f2", HOV_FG="#08425f", ACC_HOV="#55c9f2",
                        SCAN="#e3eaf0", LED_DIM="#a8d6ec", GLINT="#6fd0f7"),
    "NEXT": dict(BG="#07090c", PANEL="#0e1317", PANEL2="#141b21", LINE="#2a3a45", CYAN="#8fd8ee",
                 TEXT="#c7d4db", DIM="#5b707d", ORANGE="#ff7a1a", RED="#e5412d", WARN="#ff7a1a",
                 ACC_FG="#000000", HOV="#1d2a33", HOV_FG="#ffffff", ACC_HOV="#ffa05a",
                 SCAN="#10171c", LED_DIM="#2e5360", GLINT="#8fd8ee"),
}
THEME_NAME = "WHITE GLINT"


def apply_theme(name):
    global THEME_NAME
    THEME_NAME = name if name in THEMES else "WHITE GLINT"
    globals().update(THEMES[THEME_NAME])


apply_theme("WHITE GLINT")

# VERIFY flags against each emulator's --help; they change between versions.
EMULATORS = {
    "PS1": {"name": "DuckStation", "gen": "PLAYSTATION",
            "args": lambda exe, rom, fs: [exe, "-batch"] + (["-fullscreen"] if fs else []) + ["--", rom],
            "exts": {".cue", ".chd", ".bin", ".iso", ".pbp", ".img"}},
    "PS2": {"name": "PCSX2", "gen": "PLAYSTATION 2",
            "args": lambda exe, rom, fs: [exe, "-batch"] + (["-fullscreen"] if fs else []) + ["--", rom],
            "exts": {".iso", ".chd", ".cso", ".bin", ".gz"}},
    "PSP": {"name": "PPSSPP", "gen": "PSP",
            "args": lambda exe, rom, fs: [exe] + (["--fullscreen"] if fs else []) + [rom],
            "exts": {".iso", ".cso", ".pbp", ".chd"}},
    "PS3": {"name": "RPCS3", "gen": "PLAYSTATION 3",
            # RPCS3 has no --fullscreen flag. Set "Start games in fullscreen mode" in RPCS3's
            # settings, or press Alt+Enter in-game.
            "args": lambda exe, rom, fs: [exe, "--no-gui", rom],
            "exts": {".iso"}},
}

GAMES = [  # (title, system, order, [keywords that must all appear]) specific -> generic
    ("Armored Core: Project Phantasma", "PS1", 2, ["phantasma"]),
    ("Armored Core: Master of Arena", "PS1", 3, ["master of arena"]),
    ("Armored Core", "PS1", 1, ["armored core"]),
    ("Armored Core 2: Another Age", "PS2", 5, ["armored core 2", "another age"]),
    ("Armored Core 2", "PS2", 4, ["armored core 2"]),
    ("Armored Core 3", "PS2", 6, ["armored core 3"]),
    ("Silent Line: Armored Core", "PS2", 7, ["silent line"]),
    ("Armored Core: Nexus", "PS2", 8, ["nexus"]),
    ("Armored Core: Nine Breaker", "PS2", 9, ["nine breaker"]),
    ("Armored Core: Formula Front", "PS2", 10, ["formula front"]),
    ("Armored Core: Last Raven", "PS2", 11, ["last raven"]),
    ("Armored Core 3 Portable", "PSP", 12, ["armored core 3"]),
    ("Armored Core: Last Raven Portable", "PSP", 13, ["last raven"]),
    ("Armored Core: Formula Front Extreme Battle", "PSP", 14, ["formula front"]),
    ("Armored Core 4", "PS3", 15, ["armored core 4"]),
    ("Armored Core: For Answer", "PS3", 16, ["for answer"]),
    ("Armored Core V", "PS3", 17, ["armored core v"]),
    ("Armored Core: Verdict Day", "PS3", 18, ["verdict day"]),
    ("Armored Core VI: Fires of Rubicon", "PC", 19, ["armored core vi"]),
]

BIOS_HINTS = {
    "PS1": "PS1 BIOS (e.g. scph*.bin) in DuckStation's bios folder",
    "PS2": "PS2 BIOS dump in PCSX2's bios folder",
    "PSP": "None required",
    "PS3": "PS3 firmware (PS3UPDAT.PUP): RPCS3 > File > Install Firmware",
}


# ---- built-in emulator manager ------------------------------------------------
# Downloads OFFICIAL builds into ~/.ac_launcher/emulators and sets them up in portable
# mode. Windows builds. Release asset names change over time - if a download fails,
# tweak the patterns below or use SET PATH MANUALLY.
EMU_HOME = Path.home() / ".ac_launcher" / "emulators"
UA = {"User-Agent": "ArmoredCoreLauncher/1.0 (fan-made launcher; personal use)"}
SOURCES = {
    "PS1": {"repo": "stenzek/duckstation", "pick": r"windows.*x64.*\.zip$", "skip": r"symbols|arm|debug"},
    "PS2": {"repo": "PCSX2/pcsx2", "pick": r"windows.*qt.*\.7z$", "skip": r"symbols|arm", "soft": r"avx"},
    "PS3": {"repo": "RPCS3/rpcs3-binaries-win", "pick": r"win64.*\.7z$", "skip": r"arm"},
    "PSP": {"page": "https://www.ppsspp.org/download", "pick": r"(/files/[0-9_]+/ppsspp_win\.zip)"},
}
EXE_GLOB = {"PS1": "duckstation-qt*.exe", "PS2": "pcsx2-qt.exe",
            "PSP": "PPSSPPWindows64.exe", "PS3": "rpcs3.exe"}


# ---- clean child environment (fixes RPCS3 "vcruntime140.dll was incorrectly installed") ------
def clean_env():
    """Environment for launching emulators. A packaged onefile exe unpacks its own DLLs into a
    temp _MEI folder; child programs must not inherit that folder on their search path."""
    env = dict(os.environ)
    mp = getattr(sys, "_MEIPASS", None)
    bad = os.path.normcase(os.path.abspath(mp)) if mp else None
    parts = [q for q in env.get("PATH", "").split(os.pathsep)
             if q and "_MEI" not in q and (not bad or os.path.normcase(os.path.abspath(q)) != bad)]
    env["PATH"] = os.pathsep.join(parts)
    for k in ("_MEIPASS2", "_PYI_APPLICATION_HOME_DIR", "_PYI_ARCHIVE_FILE", "_PYI_PARENT_PROCESS_LEVEL",
              "TCL_LIBRARY", "TK_LIBRARY", "PYTHONHOME", "PYTHONPATH"):
        env.pop(k, None)
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    return env


# ---- reset / uninstall helpers ----------------------------------------------------------------
EXT_RANK = {".cue": 0, ".chd": 1, ".pbp": 2, ".iso": 3, ".cso": 4, ".img": 5, ".gz": 6, ".bin": 7}


def dir_size(path):
    p = Path(path)
    if p.is_file(): return p.stat().st_size
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) if p.exists() else 0


def human(n):
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024 or u == "GB": return f"{n:.0f} {u}" if u == "B" else f"{n:.1f} {u}"
        n /= 1024


def safe_delete(target, home):
    """Delete a file/folder, but only ever inside the launcher's own data folder."""
    t, h = Path(target).resolve(), Path(home).resolve()
    if h.name != ".ac_launcher" or (t != h and h not in t.parents):
        raise RuntimeError(f"refusing to delete outside {h}")
    if not t.exists(): return True
    def onerr(func, path, exc):
        try:
            os.chmod(path, 0o700); func(path)
        except OSError:
            pass
    if t.is_dir():
        try: shutil.rmtree(t, onexc=onerr)
        except TypeError: shutil.rmtree(t, onerror=lambda f, q, e: onerr(f, q, e))
    else:
        try: t.unlink()
        except OSError: pass
    return not t.exists()


# ---- starting emulators from a packaged exe ---------------------------------------------------
LAUNCH_VIA_CMD = False   # "compatibility launch": start emulators through the Windows shell


def spawn(args, **kw):
    """Start an emulator. A onefile exe sets a private DLL directory (its temp _MEI folder) that child
    processes inherit, so RPCS3 finds the launcher's VCRUNTIME140.dll. Clear it while the child is
    created, then restore it for the launcher itself."""
    kw.setdefault("env", clean_env())
    if LAUNCH_VIA_CMD and os.name == "nt":
        cwd = kw.get("cwd") or os.getcwd()
        args = f'cmd /c start "" /wait /D "{cwd}" ' + subprocess.list2cmdline([str(a) for a in args])
        kw["creationflags"] = kw.get("creationflags", 0) | 0x08000000
    if os.name == "nt" and getattr(sys, "frozen", False):
        import ctypes
        k32 = ctypes.windll.kernel32
        k32.SetDllDirectoryW(None)
        try:
            return subprocess.Popen(args, **kw)
        finally:
            k32.SetDllDirectoryW(getattr(sys, "_MEIPASS", None))
    return subprocess.Popen(args, **kw)


# ---- live controller detection (XInput: Xbox pads, and DualShock/DualSense via Steam/DS4Windows) ----
XBTN = [(0x1, "UP"), (0x2, "DOWN"), (0x4, "LEFT"), (0x8, "RIGHT"), (0x10, "START"), (0x20, "BACK"), (0x40, "L3"),
        (0x80, "R3"), (0x100, "LB"), (0x200, "RB"), (0x1000, "A"), (0x2000, "B"), (0x4000, "X"), (0x8000, "Y")]
_XI = {}


def xinput_pads():
    """List of 4 entries: None (no pad) or a text describing what is pressed. Windows only."""
    if os.name != "nt": return []
    import ctypes
    from ctypes import wintypes
    if "lib" not in _XI:
        class PAD(ctypes.Structure):
            _fields_ = [("wButtons", wintypes.WORD), ("lt", ctypes.c_ubyte), ("rt", ctypes.c_ubyte),
                        ("lx", ctypes.c_short), ("ly", ctypes.c_short), ("rx", ctypes.c_short), ("ry", ctypes.c_short)]
        class STATE(ctypes.Structure):
            _fields_ = [("packet", wintypes.DWORD), ("pad", PAD)]
        _XI["STATE"], _XI["lib"] = STATE, None
        for dll in ("xinput1_4", "xinput1_3", "xinput9_1_0"):
            try: _XI["lib"] = ctypes.windll.LoadLibrary(dll); break
            except OSError: continue
    lib, STATE = _XI["lib"], _XI["STATE"]
    if not lib: return []
    out = []
    for i in range(4):
        st = STATE()
        if lib.XInputGetState(i, ctypes.byref(st)) != 0:
            out.append(None); continue
        g = st.pad
        parts = [n for m, n in XBTN if g.wButtons & m]
        if g.lt > 40: parts.append("LT")
        if g.rt > 40: parts.append("RT")
        for v, n in ((g.lx, "L-STICK X"), (g.ly, "L-STICK Y"), (g.rx, "R-STICK X"), (g.ry, "R-STICK Y")):
            if abs(v) > 12000: parts.append(f"{n} {v * 100 // 32768:+d}%")
        out.append(" + ".join(parts) or "connected - press a button")
    return out


def http_get(url, insecure=False):
    # insecure=True only for Sony's update servers, whose certificate chain Python doesn't trust by default
    ctx = ssl._create_unverified_context() if insecure and url.startswith("https") else None
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30, context=ctx)


def find_download(system):
    src = SOURCES[system]
    if "page" in src:
        html = http_get(src["page"]).read().decode("utf8", "ignore")
        m = re.search(src["pick"], html)
        if not m:
            raise RuntimeError("download link not found on ppsspp.org")
        url = urllib.parse.urljoin(src["page"], m.group(1))
        return url, "ppsspp_win.zip", url
    rels = json.load(http_get(f"https://api.github.com/repos/{src['repo']}/releases?per_page=15"))
    for rel in rels:
        assets = [a for a in rel.get("assets", []) if re.search(src["pick"], a["name"], re.I)
                  and not re.search(src["skip"], a["name"], re.I)]
        good = [a for a in assets if not re.search(src.get("soft", "$^"), a["name"], re.I)]
        if assets:
            a = (good or assets)[0]
            return a["browser_download_url"], a["name"], (a.get("updated_at") or a["name"])
    raise RuntimeError("no matching release asset found")


def download(url, dest, report, insecure=False):
    with http_get(url, insecure) as r, open(dest, "wb") as f:
        total, got = int(r.headers.get("Content-Length") or 0), 0
        while True:
            b = r.read(1 << 16)
            if not b:
                break
            f.write(b); got += len(b)
            if total:
                report(f"DOWNLOADING {int(got * 100 / total)}%")


def get_7z():
    """Use an installed 7-Zip, else fetch the official standalone 7zr.exe (small, extracts .7z)."""
    sz = shutil.which("7z") or shutil.which("7zz") or next(
        (c for c in (r"C:\Program Files\7-Zip\7z.exe", r"C:\Program Files (x86)\7-Zip\7z.exe") if os.path.exists(c)), None)
    if sz:
        return sz
    tool = EMU_HOME / "tools" / "7zr.exe"
    if not tool.exists():
        tool.parent.mkdir(parents=True, exist_ok=True)
        with http_get("https://www.7-zip.org/a/7zr.exe") as r, open(tool, "wb") as f:
            f.write(r.read())
    return str(tool)


def extract(archive, out):
    out.mkdir(parents=True, exist_ok=True)
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as z:
            z.extractall(out)
        return
    subprocess.run([get_7z(), "x", str(archive), f"-o{out}", "-y"], check=True,
                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   creationflags=0x08000000 if os.name == "nt" else 0, env=clean_env())  # no console flash


def installed_version(system):
    vf = EMU_HOME / EMULATORS[system]["name"] / ".ac_version"
    return vf.read_text(encoding="utf8").strip() if vf.exists() else None


def find_exe(system):
    base = EMU_HOME / EMULATORS[system]["name"]
    hits = sorted(base.rglob(EXE_GLOB[system])) if base.exists() else []
    return hits[0] if hits else None


def make_portable(system, exe):
    d = exe.parent  # keeps saves/configs/BIOS inside the launcher's own folder
    if system == "PS1": (d / "portable.txt").touch()
    if system == "PS2": (d / "portable.ini").touch()
    if system == "PSP": (d / "memstick").mkdir(exist_ok=True)
    if system in ("PS1", "PS2"): (d / "bios").mkdir(exist_ok=True)


def install_emulator(system, report):
    name = EMULATORS[system]["name"]
    report(f"{name}: LOCATING LATEST OFFICIAL BUILD")
    url, fname, ver = find_download(system)
    EMU_HOME.mkdir(parents=True, exist_ok=True)
    arc = EMU_HOME / fname
    download(url, arc, lambda m: report(f"{name}: {m}"))
    report(f"{name}: UNPACKING")
    extract(arc, EMU_HOME / name)  # extracts over old files; saves are kept
    arc.unlink(missing_ok=True)
    exe = find_exe(system)
    if not exe:
        raise RuntimeError("executable not found after unpacking")
    make_portable(system, exe)
    (EMU_HOME / name / ".ac_version").write_text(ver, encoding="utf8")
    return str(exe)


# ---- lore archive ---------------------------------------------------------------
# year, Wikipedia title (best guess; falls back to a search), short curated briefing.
# The live Wikipedia extract is the sourced reference; edit these freely.
LORE = {
 "Armored Core": ("1997", "Armored Core (video game)",
  "The one that started it. FromSoftware's first mech-combat game on PlayStation puts you in the cockpit of a customizable Armored Core, built part by part in the Garage before you take contracts from corporations. No chosen one: you are a mercenary, and the world is revealed through mission briefings and whoever is paying you."),
 "Armored Core: Project Phantasma": ("1997", "Armored Core: Project Phantasma",
  "A follow-up that builds directly on the original with more missions, parts and tougher contracts, deepening the same corporate-dominated, mercenary-for-hire world and growing the Arena side of the game."),
 "Armored Core: Master of Arena": ("1999", "Armored Core: Master of Arena",
  "Leans hard into the Arena: a ranked ladder of duels against rival pilots, alongside the contract work. A showcase for the series' pilot-versus-pilot appeal on the original PlayStation."),
 "Armored Core 2": ("2000", "Armored Core 2",
  "The PS2 era begins. Faster, sharper visuals and a new setting and storyline (reportedly on a colonised Mars), marking the first big reinvention of the series' world."),
 "Armored Core 2: Another Age": ("2001", "Armored Core 2: Another Age",
  "An expanded companion to AC2 revisiting the same world with new missions and a different story thread, for pilots who wanted more of that setting."),
 "Armored Core 3": ("2002", "Armored Core 3",
  "A fresh continuity on PS2 with refined combat and a new cast of clients and rivals; the start of a multi-game arc continued by Silent Line and Nexus."),
 "Silent Line: Armored Core": ("2003", "Silent Line: Armored Core",
  "A follow-up set in the AC3 universe with new missions and a tenser, more story-driven tone than its predecessor."),
 "Armored Core: Nexus": ("2004", "Armored Core: Nexus",
  "A large PS2 release delivered across two discs (Evolution and Revolution), carrying the AC3-era storyline forward with a big roster of parts and missions."),
 "Armored Core: Nine Breaker": ("2004", "Armored Core: Nine Breaker",
  "A PS2-era side entry that spotlights the series' competitive, duel-oriented side rather than a sprawling campaign."),
 "Armored Core: Formula Front": ("2005", "Armored Core: Formula Front",
  "The odd one out: instead of piloting directly, you build an AC and train its AI, then watch it fight in competitive matches. A mech-tactics experiment unique in the series."),
 "Armored Core: Last Raven": ("2005", "Armored Core: Last Raven",
  "A late-PS2 entry that carries the Nexus-era storyline toward its close, as the title suggests; the end of that generation of the series."),
 "Armored Core 3 Portable": ("2005", "Armored Core 3 Portable",
  "AC3's formula adapted for the PSP: the same garage-and-contract loop tuned for handheld play."),
 "Armored Core: Last Raven Portable": ("2006", "Armored Core: Last Raven Portable",
  "A handheld take on Last Raven, bringing the PS2 entry's missions and pilot-versus-pilot focus to PSP."),
 "Armored Core: Formula Front Extreme Battle": ("2006", "Armored Core: Formula Front Extreme Battle",
  "The AI-training tactics spin-off, expanded for PSP with more content for competitive matches."),
 "Armored Core 4": ("2006", "Armored Core 4",
  "A new generation on PS3 and Xbox 360 with a reinvented setting. ACs (called NEXTs here) are faster and more mobile, built around boost-based movement such as the Quick Boost, and the series' combat feel changes for good."),
 "Armored Core: For Answer": ("2008", "Armored Core: For Answer",
  "The direct sequel to AC4, set in the same world with a new campaign. Bigger set pieces, memorable rival pilots and multiple endings; widely regarded by fans as the high point of the AC4 era's fast, aggressive combat."),
 "Armored Core V": ("2012", "Armored Core V",
  "Another reboot with a new setting. Heavier and more deliberate than For Answer, with a strong emphasis on online team play and territory-style Conquest battles."),
 "Armored Core: Verdict Day": ("2013", "Armored Core: Verdict Day",
  "The follow-up to Armored Core V, continuing its world with a campaign and online features. The last mainline Armored Core before the ten-year gap to Armored Core VI."),
}

OVERVIEW = r"""Armored Core is FromSoftware's long-running mech-combat series. You play a mercenary pilot who builds a customizable mech (an AC) in the Garage and takes contracts from corporations, states and shadowy clients. Story arrives through mission briefings, rival pilots and your choice of contract rather than long cutscenes.

It is not one continuous story. Each generation resets or reinvents the setting:

  PS1 era      Armored Core, Project Phantasma, Master of Arena
  PS2 era      AC2 and Another Age, then AC3, Silent Line, Nexus, Nine Breaker, Formula Front, Last Raven
  PSP          Handheld versions and spin-offs
  4th gen      Armored Core 4 and For Answer (PS3 / Xbox 360)
  5th gen      Armored Core V and Verdict Day
  6th gen      Armored Core VI: Fires of Rubicon (PC / Steam, launched through Steam)

Briefings are short, spoiler-light summaries written by hand. The FIELD REPORT under each game is pulled live from Wikipedia and is the sourced reference. Select a game on the left."""

CACHE = Path.home() / ".ac_launcher" / "cache"


def log(msg):
    try:
        with open(CACHE.parent / "log.txt", "a", encoding="utf8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")
    except OSError:
        pass


def slug(t): return re.sub(r"\W+", "_", t.lower()).strip("_")


def wiki_query(params):
    q = urllib.parse.urlencode({"action": "query", "format": "json", "redirects": 1,
                                "prop": "extracts|pageimages|info", "exintro": 1, "explaintext": 1,
                                "piprop": "thumbnail", "pithumbsize": 600, "pilicense": "any", "inprop": "url", **params})
    return json.load(http_get("https://en.wikipedia.org/w/api.php?" + q))


def fetch_wiki(game, wiki_title):
    """Cover image + intro text from Wikipedia, cached on disk. Fetched at runtime, never bundled."""
    CACHE.mkdir(parents=True, exist_ok=True)
    cf = CACHE / f"{slug(game)}_v2.json"
    if cf.exists():
        info = json.loads(cf.read_text(encoding="utf8"))
        if info.get("img") and Path(info["img"]).exists():
            return info
    best = None
    for params in ({"titles": wiki_title},
                   {"generator": "search", "gsrsearch": wiki_title + " video game", "gsrlimit": 1}):
        for pg in wiki_query(params).get("query", {}).get("pages", {}).values():
            if "missing" in pg or not pg.get("extract"):
                continue
            info = {"extract": pg["extract"].strip(), "url": pg.get("fullurl", ""), "img": None}
            th = pg.get("thumbnail", {}).get("source")
            if th:
                ip = CACHE / (slug(game) + (Path(urllib.parse.urlparse(th).path).suffix or ".jpg"))
                with http_get(th) as r, open(ip, "wb") as f:
                    f.write(r.read())
                info["img"] = str(ip)
            if info["img"]:
                cf.write_text(json.dumps(info), encoding="utf8")
                return info
            best = best or info
    if best:
        return best
    raise RuntimeError("no Wikipedia article found")


# ---- game art from libretro-thumbnails (no account/API key needed) -------------------
# Public box art / title screens / in-game snaps for PS1, PS2, PSP, PS3 titles.
LIBRETRO = {"PS1": "Sony - PlayStation", "PS2": "Sony - PlayStation 2",
            "PSP": "Sony - PlayStation Portable", "PS3": "Sony - PlayStation 3"}
REGION_PREF = ("(USA", "(Europe", "(World", "(Japan", "(Asia")


def libretro_index(system):
    cf = CACHE / f"libretro_{system}.json"
    if cf.exists() and time.time() - cf.stat().st_mtime < 7 * 86400:
        return json.loads(cf.read_text(encoding="utf8"))
    CACHE.mkdir(parents=True, exist_ok=True)
    base = f"https://thumbnails.libretro.com/{urllib.parse.quote(LIBRETRO[system])}/Named_Boxarts/"
    page = http_get(base).read().decode("utf8", "ignore")
    names = [htmllib.unescape(urllib.parse.unquote(h)) for h in re.findall(r'href="([^"]+\.png)"', page)]
    names = [n for n in names if "armored core" in n.lower() or "silent line" in n.lower()]
    idx = {"base": base, "names": names}
    cf.write_text(json.dumps(idx), encoding="utf8")
    return idx


def fetch_libretro(game, system):
    idx = libretro_index(system)
    cands = []
    for n in idx["names"]:
        stem = n[:-4]
        if identify(stem, system)[0] == game and not re.search(r"\((demo|beta|proto|disc [23]|sample|bonus)", stem, re.I):
            cands.append((next((i for i, r in enumerate(REGION_PREF) if r in stem), 9), len(stem), n))
    if not cands:
        return None
    name = sorted(cands)[0][2]
    out = {"img": None, "extra": []}
    for kind in ("Named_Boxarts", "Named_Titles", "Named_Snaps"):
        dest = CACHE / f"{slug(game)}_{kind}.png"
        try:
            if not dest.exists():
                with http_get(idx["base"].replace("Named_Boxarts", kind) + urllib.parse.quote(name)) as r, open(dest, "wb") as f:
                    f.write(r.read())
            if kind == "Named_Boxarts": out["img"] = str(dest)
            else: out["extra"].append(str(dest))
        except Exception as ex:
            dest.unlink(missing_ok=True); log(f"libretro {kind} {name}: {ex!r}")
    return out if out["img"] or out["extra"] else None


def fetch_all(game, wiki_title, system):
    """Text from Wikipedia + pictures from libretro-thumbnails; either may fail on its own."""
    info = {"extract": "", "url": "", "img": None, "extra": []}
    errs = []
    try:
        info.update(fetch_wiki(game, wiki_title))
    except Exception as ex:
        errs.append(f"wiki: {ex}"); log(f"wiki {game}: {ex!r}")
    if system in LIBRETRO:
        try:
            art = fetch_libretro(game, system)
            if art:
                info["img"] = art["img"] or info["img"]; info["extra"] = art["extra"]
        except Exception as ex:
            errs.append(f"art: {ex}"); log(f"art {game}: {ex!r}")
    if game in STEAM_APPS:
        try:
            art = fetch_steam_art(game, STEAM_APPS[game])
            if art:
                info["img"] = art["img"] or info["img"]; info["extra"] = art["extra"]
        except Exception as ex:
            errs.append(f"steam art: {ex}"); log(f"steam art {game}: {ex!r}")
    if not info["extract"] and not info["img"] and not info["extra"]:
        raise RuntimeError("; ".join(errs) or "nothing found")
    return info


# ---- per-game settings + presets ----------------------------------------------------------
# Defaults are generic good-practice values. Title overrides below come from community
# documentation (RPCS3 wiki for For Answer, PCSX2 wiki notes for AC2/AC3), not guesses.
DEFAULT_OPTS = {
    "PS1": {"res": "auto", "ws": False},
    "PS2": {"res": "auto", "ws": True},
    "PSP": {"res": "auto"},
    "PS3": {"res": "auto", "fps": "Auto", "wcb": False, "min_dim": 16, "vsync": False, "af": 0, "tiling": False},   # RPCS3 stock values
}
PRESETS = {
    # RPCS3 wiki: Write Color Buffers ON (fixes missing AC graphics), frame limit Auto,
    # resolution scale threshold 320 (aligns effects when upscaling).
    "Armored Core: For Answer": {"wcb": True, "min_dim": 320, "tiling": True},
}
NOTES = {
    "Armored Core: For Answer": "RPCS3 wiki: Write Color Buffers ON fixes missing AC graphics, and Handle RSX memory tiling ON fixes most logo/AC texture corruption. Keep the frame limit on Auto or 60: above 60 FPS breaks game logic. RPCS3 issue #11984 reported crashes with Write Color Buffers at upscaled resolutions in older builds: if the game crashes, set the resolution to 1x. The first launch compiles the game for several minutes and may sit on a black screen. Settings are applied only while the game runs, then your own RPCS3 settings are put back.",
    "Armored Core 4": "RPCS3: leave Asynchronous Texture Streaming OFF in RPCS3's own settings; it makes the screen flicker in this game.",
    "Armored Core 2": "PCSX2 wiki: floating shadows and slightly off-centre FMVs when upscaling are known issues.",
    "Armored Core 2: Another Age": "PCSX2 wiki: floating shadows are a known issue (same as Armored Core 2).",
    "Armored Core 3": "PCSX2 wiki: in PCSX2's own Graphics settings, 'Bob (TFF)' deinterlacing works best for this game.",
}


def edit_keys(path, section, kv, yaml=False, create=False, old=None):
    """Set keys inside one section of an .ini or simple .yml file, keeping everything else intact.
    old (dict) receives each key's previous value (None if it was absent); a value of None deletes the key."""
    path = Path(path)
    if not path.exists():
        if not create: return False
        path.parent.mkdir(parents=True, exist_ok=True); text = ""
    else:
        text = path.read_text(encoding="utf8", errors="replace")
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines()
    is_hdr = (lambda l: l.rstrip() == f"{section}:") if yaml else (lambda l: l.strip() == f"[{section}]")
    idx = next((i for i, l in enumerate(lines) if is_hdr(l)), None)
    if idx is None:
        lines += ([""] if lines else []) + [f"{section}:" if yaml else f"[{section}]"]; idx = len(lines) - 1
    end = len(lines)
    for j in range(idx + 1, len(lines)):
        l = lines[j]
        if (yaml and l and not l[0].isspace() and not l.startswith("#")) or (not yaml and l.strip().startswith("[")):
            end = j; break
    for key, val in kv.items():
        pat = re.compile(rf"^(\s*){re.escape(key)}\s*{':' if yaml else '='}\s*.*$")
        for j in range(idx + 1, end):
            m = pat.match(lines[j])
            if m:
                if old is not None: old[key] = lines[j].split(":" if yaml else "=", 1)[1].strip()
                if val is None:
                    del lines[j]; end -= 1
                else:
                    lines[j] = f"{m.group(1)}{key}: {val}" if yaml else f"{key} = {val}"
                break
        else:
            if old is not None: old[key] = None
            if val is not None:
                lines.insert(idx + 1, f"  {key}: {val}" if yaml else f"{key} = {val}"); end += 1
    path.write_text(nl.join(lines) + nl, encoding="utf8")
    return True


def restore_settings(snaps):
    """Put the emulator settings back exactly as they were before a launch."""
    for path, section, yaml, old in snaps:
        try: edit_keys(path, section, old, yaml=yaml)
        except Exception as ex: log(f"restore {path}: {ex!r}")


def auto_scale(system, screen_h):
    """Internal-resolution scale that best matches the display height (PS3: percent, others: multiplier)."""
    if system == "PS3":
        return int(max(100, min(300, round(screen_h / 720 * 2) * 50)))   # nearest 50% step: 1080p -> 150
    native = {"PS1": 240, "PS2": 448, "PSP": 272}[system]
    cap = {"PS1": 8, "PS2": 6, "PSP": 8}[system]
    return max(1, min(cap, math.ceil(screen_h / native)))


def apply_settings(system, exe, o, snap=None):
    """Write the chosen options into the emulator's own (portable) config. Previous values are recorded in
    snap so they can be restored after the game. Keys other than RPCS3's were set from memory of each
    emulator's config format: verify if one is ignored."""
    snap = snap if snap is not None else []
    d = Path(exe).parent
    t = lambda v: "true" if v else "false"
    def E(path, section, kv, **kw):
        old = {}
        ok = edit_keys(path, section, kv, old=old, **kw)
        if ok: snap.append([str(path), section, bool(kw.get("yaml")), old])
        return ok
    if system == "PS3":
        return E(d / "config" / "config.yml", "Video", {
            "Frame limit": o["fps"], "Write Color Buffers": t(o["wcb"]),
            "Resolution Scale": o["res"], "Minimum Scalable Dimension": o["min_dim"],
            "VSync": t(o["vsync"]), "Anisotropic Filter Override": o["af"],
            "Handle RSX memory tiling": t(o["tiling"])}, yaml=True, create=True)
    if system == "PS2":
        f = d / "inis" / "PCSX2.ini"
        a_ = E(f, "EmuCore/GS", {"upscale_multiplier": float(o["res"]), "AspectRatio": "16:9" if o["ws"] else "Auto 4:3/3:2"})
        b_ = E(f, "EmuCore", {"EnableWideScreenPatches": t(o["ws"]), "EnableNoInterlacingPatches": "true"})
        return a_ and b_
    if system == "PS1":
        f = d / "settings.ini"
        a_ = E(f, "GPU", {"ResolutionScale": o["res"], "WidescreenHack": t(o["ws"])})
        b_ = E(f, "Display", {"AspectRatio": "16:9" if o["ws"] else "Auto (Game Native)"})
        return a_ and b_
    if system == "PSP":
        return E(d / "memstick" / "PSP" / "SYSTEM" / "ppsspp.ini", "Graphics", {"InternalResolution": o["res"]})
    return False


# ---- PS3 game updates / firmware (official Sony servers), save slots, controller help ----------
KNOWN_IDS = {"Armored Core: For Answer": ["BLUS30187", "BLES00370", "BLJM60066"],   # from the RPCS3 wiki
             "Armored Core V": ["BLUS30516", "BLES01440", "BLAS50448", "BLJM60378"]}
SAVE_DIRS = {"PS1": ["memcards", "savestates"], "PS2": ["memcards", "sstates"],
             "PSP": ["memstick/PSP/SAVEDATA", "memstick/PSP/PPSSPP_STATE"],
             "PS3": ["dev_hdd0/home/00000001/savedata"]}
SLOT_ROOT = Path.home() / ".ac_launcher" / "slots"
CONTROL_HELP = {
    "PS1": "DuckStation: Settings > Controllers > Automatic Mapping (pick your controller).",
    "PS2": "PCSX2: Settings > Controllers > Automatic Mapping (pick your controller).",
    "PSP": "PPSSPP: Settings > Controls > Control mapping.",
    "PS3": "RPCS3: Configuration > Pads. Choose the handler (XInput for Xbox pads, DualShock 4 / DualSense for PlayStation pads) and your device, or leave the default keyboard/XInput profile.",
}


def slot_dir(system, n): return SLOT_ROOT / system / f"slot{n}"


def copy_saves(system, exe, dest):
    """Copy an emulator's save folders into dest. Returns number of folders copied."""
    base, n = Path(exe).parent, 0
    shutil.rmtree(dest, ignore_errors=True)
    for rel in SAVE_DIRS[system]:
        if (base / rel).exists():
            shutil.copytree(base / rel, dest / rel); n += 1
    return n


def restore_saves(system, exe, src):
    base = Path(exe).parent
    for rel in SAVE_DIRS[system]:
        if (src / rel).exists():
            shutil.rmtree(base / rel, ignore_errors=True); shutil.copytree(src / rel, base / rel)


def sfo_title_id(path):
    b = Path(path).read_bytes()
    if b[:4] != b"\0PSF": return None
    kt, dt, n = struct.unpack_from("<III", b, 8)
    for i in range(n):
        ko, _fmt, ln, _mx, do = struct.unpack_from("<HHIII", b, 20 + 16 * i)
        key = b[kt + ko: b.index(b"\0", kt + ko)].decode("ascii", "ignore")
        if key == "TITLE_ID":
            return b[dt + do: dt + do + ln].split(b"\0")[0].decode("ascii", "ignore")
    return None


def ps3_title_id(path, exe):
    p = Path(path)
    for c in (p / "PS3_GAME" / "PARAM.SFO", p / "PARAM.SFO"):
        if c.is_file():
            try:
                t = sfo_title_id(c)
                if t: return t
            except Exception:
                pass
    gy = Path(exe).parent / "config" / "games.yml"
    if gy.is_file():
        mine = str(p).replace("\\", "/").rstrip("/").lower()
        for line in gy.read_text(encoding="utf8", errors="replace").splitlines():
            m = re.match(r"^\s*([A-Z]{4}\d{5}):\s*(.+?)\s*$", line)
            if m and m.group(2).strip(chr(34) + chr(39)).replace(chr(92), "/").rstrip("/").lower().startswith(mine):
                return m.group(1)
    m = re.search(r"[A-Z]{4}\d{5}", p.name)
    return m.group(0) if m else None


def pkg_ok(path, sha1):
    if not sha1: return True
    size = Path(path).stat().st_size
    def h(limit):
        x, left = hashlib.sha1(), limit
        with open(path, "rb") as f:
            while left > 0:
                b = f.read(min(1 << 20, left))
                if not b: break
                x.update(b); left -= len(b)
        return x.hexdigest()
    return sha1.lower() in (h(size), h(size - 32))  # PS3 packages are hashed without their last 32 bytes


def get_ps3_update(tid, report):
    """Latest official update package for a PS3 title from Sony's update server. None if there is none."""
    url = f"https://a0.ww.np.dl.playstation.net/tpl/np/{tid}/{tid}-ver.xml"
    try:
        data = http_get(url, insecure=True).read()
    except urllib.error.HTTPError as ex:
        if ex.code == 404: return None
        raise
    pk = [dict(x.attrib) for x in ET.fromstring(data).iter("package")]
    if not pk: return None
    ver = lambda x: float(re.sub(r"[^0-9.]", "", x.get("version", "0")) or 0)
    latest = max(pk, key=ver)
    dest = EMU_HOME.parent / "downloads" / tid / f"{tid}_{latest['version']}.pkg"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not (dest.exists() and pkg_ok(dest, latest.get("sha1sum"))):
        download(latest["url"], dest, lambda m: report(f"{tid} UPDATE: {m}"), insecure=True)
        if not pkg_ok(dest, latest.get("sha1sum")):
            dest.unlink(missing_ok=True); raise RuntimeError("downloaded update failed its checksum")
    return latest["version"], str(dest)


def get_ps3_firmware(report):
    """Official firmware: the link RPCS3's own quickstart page points to (Sony's server)."""
    page = http_get("https://rpcs3.net/quickstart").read().decode("utf8", "ignore")
    m = re.search(r"https?://[^\"'\s<>]+PS3UPDAT\.PUP", page)
    if not m: raise RuntimeError("firmware link not found on rpcs3.net/quickstart")
    dest = EMU_HOME.parent / "downloads" / "PS3UPDAT.PUP"; dest.parent.mkdir(parents=True, exist_ok=True)
    download(m.group(0), dest, lambda x: report(f"PS3 FIRMWARE: {x}"), insecure=True)
    return str(dest)


# ---- RPCS3 log diagnosis ------------------------------------------------------------------------
LOG_HINTS = [
    (r"Access violation", "A memory-access crash. For For Answer RPCS3 documents this when Write Color Buffers is combined with a resolution above 1x (issue #11984): set the resolution to 1x in GAME SETTINGS."),
    (r"VCRUNTIME|vcruntime", "A Visual C++ runtime DLL conflict: turn on COMPATIBILITY LAUNCH in SYSTEM CHECK, or install the Microsoft Visual C++ Redistributable."),
    (r"not enough (free )?(disk |hdd )?space|insufficient (disk|hdd)|ENOSPC", "Low disk space reported: free up space on the drive RPCS3 is installed on."),
    (r"firmware|libsysmodule|LLE module|sys_prx.*(not found|failed)", "Firmware modules may be missing: reinstall the PS3 firmware from SYSTEM CHECK."),
    (r"Vulkan|VK_ERROR|vkCreate|GPU device", "A graphics-driver problem: update your GPU driver, or switch RPCS3's renderer in its own settings."),
    (r"bad_alloc|out of memory|Out of memory", "Out of memory: close other programs, or lower the resolution scale."),
    (r"Failed to decrypt|Failed to load SELF|Invalid ELF|corrupt|EBOOT.*(not found|failed)|SELF.*failed", "The game files look damaged or incomplete: re-dump your disc or re-copy the game folder."),
    (r"Segfault|segmentation", "RPCS3 crashed hard. Update RPCS3 (UPDATE EMULATORS) and try again."),
]


def analyze_rpcs3_log(text):
    """Returns (error_lines_with_counts, last_lines, hints)."""
    lines = text.splitlines()
    errs = {}
    for l in lines:
        if re.match(r"^\W?[FE] ", l):
            key = re.sub(r"^\W?[FE] \d+:\d+:\d+\.\d+ ", "", l)[:220]
            errs[key] = errs.get(key, 0) + 1
    blob = "\n".join(errs)
    hints = [h for pat, h in LOG_HINTS if re.search(pat, blob)]
    return sorted(errs.items(), key=lambda kv: -kv[1])[:20], lines[-12:], hints


# ---- Armored Core VI via Steam + game art from Steam's CDN --------------------------------------
AC6_APPID = 1888160
AC6_TITLE = "Armored Core VI: Fires of Rubicon"
STEAM_APPS = {AC6_TITLE: AC6_APPID}
SYSTEMS_ALL = {**EMULATORS, "PC": {"name": "Steam", "gen": "PC (STEAM)"}}
LORE[AC6_TITLE] = ("2023", "Armored Core VI: Fires of Rubicon",
    "FromSoftware's return to the series after a ten-year gap, on PC, PlayStation and Xbox. You are an independent mercenary, 621, sent to the planet Rubicon 3, where a volatile substance called Coral has pulled corporations and local factions into a struggle. A modern take on the garage-and-contract loop, with huge boss fights and a story that changes across repeat playthroughs. Launched here through Steam.")


def steam_roots():
    c = []
    if os.name == "nt":
        try:
            import winreg
            for hive, sub in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
                              (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam")):
                try:
                    with winreg.OpenKey(hive, sub) as k:
                        for name in ("SteamPath", "InstallPath"):
                            try: c.append(winreg.QueryValueEx(k, name)[0])
                            except OSError: pass
                except OSError: pass
        except ImportError: pass
        c += [r"C:\Program Files (x86)\Steam", r"C:\Program Files\Steam"]
    else:
        c += [str(Path.home() / ".steam" / "steam"), str(Path.home() / ".local" / "share" / "Steam")]
    return [Path(x) for x in c if x and Path(x).exists()]


def find_steam_game(appid, extra=None):
    roots = steam_roots() + ([Path(extra)] if extra and Path(extra).exists() else [])
    for root in roots:
        libs = [root]
        vdf = root / "steamapps" / "libraryfolders.vdf"
        if vdf.exists():
            libs += [Path(p.replace("\\\\", "\\")) for p in re.findall(r'"path"\s+"([^"]+)"', vdf.read_text(encoding="utf8", errors="replace"))]
        for lib in libs:
            for acf in (lib / "steamapps" / f"appmanifest_{appid}.acf", lib / f"appmanifest_{appid}.acf"):
                if acf.exists():
                    m = re.search(r'"installdir"\s+"([^"]+)"', acf.read_text(encoding="utf8", errors="replace"))
                    steamapps = acf.parent
                    return {"library": str(lib), "dir": str(steamapps / "common" / m.group(1)) if m else ""}
    return None


def proc_running(name):
    if os.name != "nt": return False
    try:
        out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {name}", "/NH"], capture_output=True, text=True,
                             creationflags=0x08000000, timeout=10).stdout
        return name.lower() in out.lower()
    except Exception:
        return False


def fetch_steam_art(game, appid):
    out = {"img": None, "extra": []}
    CACHE.mkdir(parents=True, exist_ok=True)
    for name in ("library_600x900.jpg", "header.jpg", "library_hero.jpg"):
        dest = CACHE / f"{slug(game)}_steam_{name}"
        try:
            if not dest.exists():
                with http_get(f"https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/{name}") as r, open(dest, "wb") as f:
                    f.write(r.read())
            if name.startswith("library_600"): out["img"] = str(dest)
            else: out["extra"].append(str(dest))
        except Exception as ex:
            dest.unlink(missing_ok=True); log(f"steam art {name}: {ex!r}")
    return out if out["img"] or out["extra"] else None


# ---- soundtrack guide ------------------------------------------------------------------------------
# Facts: composer credits (Wikipedia: Kota Hoshino), track details from fan wiki / reviews. "Best" = the tracks
# fans and reviewers most often single out; opinions vary.
OST_OVERVIEW = ("Most of the series' music is credited to Kota Hoshino, a FromSoftware composer who also plays bass and sings in the in-house band FreQuency "
                "(formed with fellow composer Tsukasa Saitoh). The band has released arrangement albums of the series' music, including Armored Core Reprises (2011) and Sunrise (2013).\n\n"
                "Rough picture of the eras (fan description, not a rule): the PS1 and PS2 games lean on electronic music such as techno and drum & bass; Armored Core 4 and For Answer add rock, industrial and "
                "heavily processed vocals; Armored Core VI mixes orchestral, rock and choir, with Hoshino working alongside Takashi Onodera and Shoi Miyazawa.\n\n"
                "Below are the tracks and albums fans and reviewers name most often. Taste varies a lot, especially on Armored Core VI. Use LISTEN to search for a track on YouTube.")
SOUNDTRACKS = [
    ("ps_era", "THE PS1 / PS2 ERA (ALBUM-LEVEL NOTE)", "1997 - 2005", "Hoshino credited with others, e.g. Master of Arena (with Tsukasa Saitoh, Keiichiro Segawa), Armored Core 2 (with Yuji Kanda, Ikuya Ichinohe, Keiichiro Segawa), Nexus (with Saitoh, Yukinori Takada, Kanda)",
     "Fans often describe these soundtracks as upbeat electronic music built for the garage and mission screens. I haven't singled out individual tracks here because I couldn't verify track names; listen to the full soundtracks of Armored Core 2, Nexus and Master of Arena if you like that sound.", "Armored Core Nexus soundtrack"),
    ("panther", "PANTHER", "Armored Core 4 (2006)", "Kota Hoshino, with Koichi Suenaga and Ayako Minami (soundtrack credit)",
     "Often called one of the best opening-stage tracks in the series. It returns in a later mission where you fight four of the game's top pilots, and its energy escalates the battle.", "Armored Core 4 Panther"),
    ("thinker", "THINKER", "Armored Core 4 (2006)", "Kota Hoshino, with Koichi Suenaga and Ayako Minami (soundtrack credit)",
     "A fan favourite from Armored Core 4. FreQuency later released a remix, \"Thinker -reprise-\".", "Armored Core 4 Thinker"),
    ("surface", "SOMEONE IS ALWAYS MOVING ON THE SURFACE", "Armored Core: For Answer (2008)", "Kota Hoshino, with Hideyuki Eto (soundtrack credit)",
     "The main theme of For Answer. A reviewer describes a minimalist-inspired build: a repeated piano motif that gradually gains choir and strings. FreQuency released an edit of it on the Sunrise album.", "Armored Core For Answer Someone Is Always Moving on the Surface"),
    ("remember", "REMEMBER", "Armored Core: For Answer (2008)", "Kota Hoshino, with Hideyuki Eto (soundtrack credit)",
     "A For Answer favourite that has been reworked twice: as \"Remember ~ on your memory\" and, in Verdict Day, as \"Mechanized Memories\" for the fight against White Glint.", "Armored Core For Answer Remember"),
    ("answer", "THE ANSWER", "Armored Core: For Answer (2008)", "Kota Hoshino, with Hideyuki Eto (soundtrack credit)",
     "Plays during certain versions of the final mission and is treated by fans as the game's near-title track.", "Armored Core For Answer The Answer"),
    ("scorcher", "SCORCHER", "Armored Core: For Answer (2008)", "Kota Hoshino, with Hideyuki Eto (soundtrack credit)",
     "A reviewer's example of For Answer pushing the abrasive style of Armored Core 4 further: heavily manipulated male vocals over grungy instrumentals.", "Armored Core For Answer Scorcher"),
    ("fa_album", "ARMORED CORE FOR ANSWER ORIGINAL SOUNDTRACK (ALBUM)", "Armored Core: For Answer (2008)", "Kota Hoshino, with Hideyuki Eto",
     "Reviewed by Square Enix Music Online as the series' most artistically accomplished soundtrack, keeping Armored Core 4's rock elements while improving the writing and variety. One reviewer's opinion, but a common one among fans.", "Armored Core For Answer Original Soundtrack"),
    ("mechanized", "MECHANIZED MEMORIES", "Armored Core: Verdict Day (2013)", "Kota Hoshino, with Yuka Kitamura (soundtrack credit)",
     "A remix of \"Remember\" used for the final boss: the White Glint fight, tying the game back to For Answer.", "Armored Core Verdict Day Mechanized Memories"),
    ("reprises", "ARMORED CORE REPRISES / SUNRISE (FREQUENCY)", "FreQuency albums (2011, 2013)", "FreQuency: Kota Hoshino and Tsukasa Saitoh",
     "Arrangement albums by the composers' own band, reworking the series' music as electric rock. Sunrise includes an edit of \"Someone Is Always Moving on the Surface\".", "FreQuency Armored Core Reprises"),
    ("steelhaze", "STEEL HAZE (WHERE TRUTHS MEET)", "Armored Core VI: Fires of Rubicon (2023)", "Arranged by Shoi Miyazawa and Kota Hoshino",
     "A standout vocal track from Armored Core VI. A fan wiki notes that its chorus was sung by the FromSoftware team that worked on the game. Fan opinion of Armored Core VI's soundtrack as a whole is split.", "Armored Core VI Steel Haze Where Truths Meet"),
]


# ---- RetroAchievements (read-only web API; you supply your own username + Web API key) -----------------
RA_CONSOLES = {12: "PS1", 21: "PS2", 41: "PSP"}   # RetroAchievements console IDs. PS3 and PC aren't supported by the service.


def ra_call(endpoint, key, user=None, **params):
    q = {"y": key, **params}
    if user: q["z"] = user
    try:
        raw = http_get("https://retroachievements.org/API/" + endpoint + "?" + urllib.parse.urlencode(q)).read()
    except urllib.error.HTTPError as ex:
        raise RuntimeError(f"RetroAchievements answered HTTP {ex.code}: check your username and Web API key")
    data = json.loads(raw.decode("utf8", "ignore"))
    if isinstance(data, dict) and ("Error" in data or ("message" in data and len(data) <= 3)):
        raise RuntimeError(str(data.get("Error") or data.get("message")))
    return data


def ra_ac_games(key, user):
    """Armored Core sets that exist on RetroAchievements (cached for a week: the service asks clients to cache)."""
    CACHE.mkdir(parents=True, exist_ok=True)
    out = []
    for cid, name in RA_CONSOLES.items():
        cf = CACHE / f"ra_games_{cid}.json"
        if cf.exists() and time.time() - cf.stat().st_mtime < 7 * 86400:
            games = json.loads(cf.read_text(encoding="utf8"))
        else:
            data = ra_call("API_GetGameList.php", key, user, i=cid, f=1)
            games = [g for g in data if re.search(r"armored core|silent line", g.get("Title", ""), re.I)
                     and not g.get("Title", "").startswith("~")]
            cf.write_text(json.dumps(games), encoding="utf8")
        for g in games:
            out.append({"id": g["ID"], "title": g["Title"], "console": name, "ach": g.get("NumAchievements", 0),
                        "lb": g.get("NumLeaderboards", 0), "pts": g.get("Points", 0)})
    return sorted(out, key=lambda g: (g["console"], g["title"]))


def ra_boot(key, user):
    return ra_call("API_GetUserProfile.php", key, user, u=user), ra_ac_games(key, user)


def ra_game(key, user, gid):
    info = ra_call("API_GetGameInfoAndUserProgress.php", key, user, g=gid, u=user)
    ach = info.get("Achievements") or {}
    ach = list(ach.values()) if isinstance(ach, dict) else list(ach)
    ach.sort(key=lambda a: a.get("DisplayOrder", 0))
    try:
        lbs = ra_call("API_GetGameLeaderboards.php", key, user, i=gid, c=200).get("Results", [])
    except Exception as ex:
        log(f"ra leaderboards {gid}: {ex!r}"); lbs = []
    got = [a for a in ach if a.get("DateEarned") or a.get("DateEarnedHardcore")]
    return {"id": gid, "title": info.get("Title", ""), "ach": ach, "lb": lbs,
            "earned": len(got), "total": len(ach), "pts_earned": sum(int(a.get("Points", 0)) for a in got),
            "pts_total": sum(int(a.get("Points", 0)) for a in ach)}


def ra_entries(key, user, lbid, title):
    return {"title": title, "rows": ra_call("API_GetLeaderboardEntries.php", key, user, i=lbid, c=25).get("Results", [])}


# ---- in-launcher audio player (Windows MCI: no extra packages) ------------------------------------------
AUDIO_EXTS = {".mp3", ".wav", ".wma", ".mid", ".midi", ".flac", ".m4a", ".aac", ".ogg"}
MUSIC_DIR = CFG_PATH.parent / "music"


class McPlayer:
    """Small audio engine on Windows' built-in MCI. Plays mp3, wav, wma and midi; flac, m4a, aac and ogg depend on
    the codecs installed in Windows."""
    A = "acplayer"

    def __init__(self): self.is_open = False

    def _cmd(self, c):
        import ctypes
        buf = ctypes.create_unicode_buffer(300)
        err = ctypes.windll.winmm.mciSendStringW(c, buf, 299, 0)
        if err:
            eb = ctypes.create_unicode_buffer(300)
            ctypes.windll.winmm.mciGetErrorStringW(err, eb, 299)
            raise RuntimeError(eb.value or f"MCI error {err}")
        return buf.value

    def load(self, path):
        self.close()
        self._cmd(f'open "{path}" alias {self.A}')
        self.is_open = True
        self._cmd(f"set {self.A} time format milliseconds")

    def play(self): self._cmd(f"play {self.A}")
    def pause(self): self._cmd(f"pause {self.A}")
    def resume(self): self._cmd(f"resume {self.A}")
    def stop(self): self._cmd(f"stop {self.A}")
    def seek(self, ms): self._cmd(f"seek {self.A} to {int(ms)}"); self._cmd(f"play {self.A}")
    def mode(self): return self._cmd(f"status {self.A} mode")
    def length(self): return int(self._cmd(f"status {self.A} length") or 0)
    def pos(self): return int(self._cmd(f"status {self.A} position") or 0)

    def volume(self, v):
        try: self._cmd(f"setaudio {self.A} volume to {int(v) * 10}")
        except RuntimeError: pass

    def close(self):
        if self.is_open:
            try: self._cmd(f"close {self.A}")
            except RuntimeError: pass
            self.is_open = False


def next_track(idx, n, loop, shuffle, auto, played):
    """Pick the next playlist index (None = stop). loop: 0 off, 1 all, 2 one."""
    if n == 0: return None
    if auto and loop == 2: return idx
    if shuffle and n > 1:
        if auto and loop == 0 and played >= n: return None
        return random.choice([x for x in range(n) if x != idx])
    i = idx + 1
    if i >= n:
        return 0 if (loop == 1 or not auto) else None
    return i


def fmt_ms(ms):
    ms = max(0, int(ms) // 1000)
    return f"{ms // 60:02d}:{ms % 60:02d}"


def norm(s): return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def identify(name, system):
    n = norm(name)
    for title, sys_, order, kws in GAMES:
        if sys_ == system and all(norm(k) in n for k in kws):
            return title, order
    return None, None


def load_cfg():
    if CFG_PATH.exists():
        return json.loads(CFG_PATH.read_text())
    return {"emulators": {}, "folders": [], "library": {}, "fullscreen": True}


def save_cfg(cfg):
    CFG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CFG_PATH.write_text(json.dumps(cfg, indent=2))


def scan_folder(folder, system):
    exts = EMULATORS[system]["exts"]
    for root, dirs, files in os.walk(folder):
        if system == "PS3":
            for d in list(dirs):
                p = Path(root) / d
                if (p / "PS3_GAME").exists() or (p / "USRDIR" / "EBOOT.BIN").exists():
                    t, o = identify(d, system)
                    if t:
                        yield str(p), t, o
                    dirs.remove(d)
        for f in files:
            if Path(f).suffix.lower() in exts:
                t, o = identify(f, system)
                if t:
                    yield str(Path(root) / f), t, o


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        global SC
        SC = max(1.0, self.winfo_fpixels("1i") / 96)
        self.title("ARMORED CORE // LAUNCHER")
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{min(px(1180), sw - 60)}x{min(px(820), sh - 100)}")
        self.minsize(min(px(1040), sw - 60), min(px(780), sh - 100))
        self.configure(bg=BG)
        fams = set(tkfont.families())
        self.mono = next((f for f in ("Consolas", "Lucida Console", "DejaVu Sans Mono", "Courier New") if f in fams), "Courier")
        self.cfg = load_cfg()
        self.filter = "ALL"
        self.running = False
        self.installing = False
        self.msgs = queue.Queue()
        self.photos, self.wiki, self.wiki_fail, self.fetching, self.sel_lore = {}, {}, {}, set(), None
        self.glint_x, self.glint_wait = None, 40
        self.updates, self.checking, self.check_win, self.check_body = set(), False, None, None
        self.cur_tab = "LIBRARY"
        self.mus = McPlayer() if os.name == "nt" else None
        self.music = [p for p in self.cfg.get("playlist", []) if os.path.exists(p)]
        self.mus_idx, self.mus_state, self.mus_started, self.mus_len, self.mus_count = -1, "stopped", 0.0, 0, 0
        self.mus_hist, self.mus_was_playing, self.viz_h = [], False, [0.05] * 32
        self.mus_loop, self.mus_shuffle = self.cfg.get("music_loop", 0), self.cfg.get("music_shuffle", False)
        self.ra_ok, self.ra_loading, self.ra_games, self.ra_cur, self.ra_view = False, False, [], None, "ach"
        globals()["LAUNCH_VIA_CMD"] = bool(self.cfg.get("cmd_launch"))
        self.autodetect()
        self.style_setup()
        self.build_ui()
        self.refresh()
        self.tick()
        self.poll()
        self.typewrite("AC SYSTEM BOOT ... ALL SYSTEMS NOMINAL", 0)
        self.anim()
        self.music_tick()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(700, self.startup)

    def F(self, size=10, bold=False):
        return (self.mono, size, "bold" if bold else "normal")

    # ---- theme -------------------------------------------------------------
    def style_setup(self):
        s = ttk.Style(self); s.theme_use("clam")
        s.configure("AC.Treeview", background=PANEL, fieldbackground=PANEL, foreground=TEXT,
                    rowheight=px(30), borderwidth=0, font=self.F(10))
        s.map("AC.Treeview", background=[("selected", ORANGE)], foreground=[("selected", ACC_FG)])
        s.configure("AC.Treeview.Heading", background=PANEL2, foreground=CYAN, relief="flat",
                    font=self.F(9, True), borderwidth=0)
        s.map("AC.Treeview.Heading", background=[("active", PANEL2)])
        s.configure("AC.Vertical.TScrollbar", background=PANEL2, troughcolor=BG, bordercolor=BG,
                    arrowcolor=CYAN, lightcolor=PANEL2, darkcolor=PANEL2)

    def button(self, parent, text, cmd, accent=False, big=False):
        fg, bg = (ACC_FG, ORANGE) if accent else (CYAN, PANEL2)
        b = tk.Label(parent, text=text, bg=bg, fg=fg, font=self.F(13 if big else 9, True),
                     padx=12, pady=12 if big else 6, cursor="hand2", anchor="w" if not big else "center",
                     highlightthickness=1, highlightbackground=ORANGE if accent else LINE)
        hov = (ACC_HOV, ACC_FG) if accent else (HOV, HOV_FG)
        b.bind("<Enter>", lambda e: b.config(bg=hov[0], fg=hov[1]))
        b.bind("<Leave>", lambda e: b.config(bg=bg, fg=fg))
        b.bind("<Button-1>", lambda e: cmd())
        return b

    def panel(self, parent, title):
        f = tk.Frame(parent, bg=PANEL, highlightthickness=1, highlightbackground=LINE)
        tk.Label(f, text="\u25a0 " + title, bg=PANEL, fg=ORANGE, font=self.F(9, True), anchor="w").pack(fill="x", padx=10, pady=(8, 2))
        tk.Frame(f, bg=LINE, height=1).pack(fill="x", padx=10, pady=(0, 6))
        return f

    # ---- layout ------------------------------------------------------------
    def build_ui(self):
        self.header = tk.Canvas(self, height=px(78), bg=BG, highlightthickness=0)
        self.header.pack(fill="x")
        self.header.bind("<Configure>", self.draw_header)

        body = tk.Frame(self, bg=BG); body.pack(fill="both", expand=True, padx=10, pady=(0, 6))
        body.columnconfigure(1, weight=1); body.rowconfigure(0, weight=1)

        # left: system select + utilities
        left = self.panel(body, "SELECT PLATFORM"); left.grid(row=0, column=0, sticky="ns", padx=(0, 8))
        left.config(width=190)
        self.sys_btns = {}
        for key, sub in [("ALL", "ALL FRAMES"), ("FAV", "FAVORITES")] + [(k, v["name"]) for k, v in EMULATORS.items()] + [("PC", "STEAM")]:
            fr = tk.Frame(left, bg=PANEL, cursor="hand2"); fr.pack(fill="x", padx=8, pady=2)
            bar = tk.Frame(fr, bg=PANEL, width=4); bar.pack(side="left", fill="y")
            t = tk.Label(fr, text={"FAV": "\u2605 FAVS"}.get(key, key), bg=PANEL, fg=TEXT, font=self.F(12, True), anchor="w", padx=8)
            t.pack(fill="x")
            u = tk.Label(fr, text=sub.upper(), bg=PANEL, fg=DIM, font=self.F(8), anchor="w", padx=8)
            u.pack(fill="x")
            for w in (fr, t, u, bar):
                w.bind("<Button-1>", lambda e, k=key: self.set_filter(k))
            self.sys_btns[key] = (bar, t)
        tk.Frame(left, bg=LINE, height=1).pack(fill="x", padx=10, pady=10)
        for txt, cmd in [("+ ADD FOLDER", self.add_folder), ("\u21bb RESCAN", self.rescan),
                         ("\u2713 SYSTEM CHECK", self.system_check), ("\u2193 UPDATE EMULATORS", self.update_now),
                         ("\u25ce CONTROLLERS", self.controllers_dialog), ("\u2716 RESET / UNINSTALL", self.reset_dialog)]:
            self.button(left, txt, cmd).pack(fill="x", padx=10, pady=3)

        # center: list
        center = tk.Frame(body, bg=BG); center.grid(row=0, column=1, sticky="nsew")
        self.build_tabs(center)
        mid = self.panel(center, "AVAILABLE ARMORED CORES"); self.tab_frames["LIBRARY"] = mid
        self.build_archive(center)
        self.build_soundtracks(center)
        self.build_music(center)
        self.build_achievements(center)
        sr = tk.Frame(mid, bg=PANEL); sr.pack(fill="x", padx=10, pady=(0, 6))
        tk.Label(sr, text="SEARCH >", bg=PANEL, fg=DIM, font=self.F(9)).pack(side="left")
        self.q = tk.StringVar(); self.q.trace_add("write", lambda *_: self.refresh())
        self.search_entry = tk.Entry(sr, textvariable=self.q, bg=BG, fg=CYAN, insertbackground=CYAN, relief="flat",
                 font=self.F(10), highlightthickness=1, highlightbackground=LINE,
                 highlightcolor=ORANGE)
        self.search_entry.pack(side="left", fill="x", expand=True, padx=6, ipady=3)
        wrap = tk.Frame(mid, bg=PANEL); wrap.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        cols = ("no", "title", "sys", "time")
        self.tree = ttk.Treeview(wrap, columns=cols, show="headings", style="AC.Treeview", selectmode="browse")
        for c, t, w, a in (("no", "NO.", 50, "center"), ("title", "DESIGNATION", 400, "w"),
                           ("sys", "PLATFORM", 80, "center"), ("time", "FLIGHT TIME", 100, "center")):
            self.tree.heading(c, text=t); self.tree.column(c, width=px(w), anchor=a)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview, style="AC.Vertical.TScrollbar")
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True); sb.pack(side="right", fill="y")
        self.tree.tag_configure("odd", background=PANEL2)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.show_detail())
        self.tree.bind("<Double-1>", lambda e: self.play())

        # right: sortie data
        right = self.right = self.panel(body, "SORTIE DATA"); right.grid(row=0, column=2, sticky="ns", padx=(8, 0))
        right.config(width=300)
        self.button(right, "\u25b6  SORTIE", self.play, accent=True, big=True).pack(side="bottom", fill="x", padx=10, pady=12)
        self.cover_lbl = tk.Label(right, bg=PANEL2, fg=DIM, font=self.F(8), text="NO COVER", width=18, height=6)
        self.cover_lbl.pack(padx=12, pady=(0, 4))
        self.fields = {}
        for key in ("DESIGNATION", "PLATFORM", "EMULATOR", "STATUS", "TOTAL FLIGHT TIME", "LAST SORTIE"):
            tk.Label(right, text=key, bg=PANEL, fg=DIM, font=self.F(8), anchor="w").pack(fill="x", padx=12, pady=(6, 0))
            l = tk.Label(right, text="---", bg=PANEL, fg=CYAN, font=self.F(10, True), anchor="w",
                         justify="left", wraplength=px(265))
            l.pack(fill="x", padx=12); self.fields[key] = l
        tk.Frame(right, bg=LINE, height=1).pack(fill="x", padx=10, pady=10)
        self.fs = tk.BooleanVar(value=self.cfg.get("fullscreen", True))
        tk.Checkbutton(right, text=" FULLSCREEN", variable=self.fs, bg=PANEL, fg=TEXT, selectcolor=BG,
                       activebackground=PANEL, activeforeground=CYAN, font=self.F(9, True),
                       highlightthickness=0, bd=0, anchor="w").pack(fill="x", padx=10)
        r1 = tk.Frame(right, bg=PANEL); r1.pack(fill="x", padx=10, pady=(8, 3))
        self.button(r1, "VIEW LORE", self.view_lore).pack(side="left", fill="x", expand=True, padx=(0, 3))
        self.button(r1, "\u2605 FAVORITE", self.toggle_fav).pack(side="left", fill="x", expand=True, padx=(3, 0))
        r2 = tk.Frame(right, bg=PANEL); r2.pack(fill="x", padx=10, pady=3)
        self.button(r2, "SETTINGS", self.game_settings).pack(side="left", fill="x", expand=True, padx=(0, 3))
        self.button(r2, "EMU FOLDER", self.open_emu_dir).pack(side="left", fill="x", expand=True, padx=(3, 0))

        # status bar
        sbar = tk.Frame(self, bg=PANEL2, height=px(26)); sbar.pack(fill="x", side="bottom")
        self.led = tk.Label(sbar, text="\u25cf", bg=PANEL2, fg=CYAN, font=self.F(10)); self.led.pack(side="left", padx=(10, 4))
        self.status = tk.Label(sbar, text="", bg=PANEL2, fg=TEXT, font=self.F(9)); self.status.pack(side="left")
        self.clock = tk.Label(sbar, text="", bg=PANEL2, fg=DIM, font=self.F(9)); self.clock.pack(side="right", padx=10)
        self.set_filter("ALL")
        self.show_tab("LIBRARY")
        self.tree.bind("<Return>", lambda e: self.play())
        self.bind("<Control-f>", lambda e: self.search_entry.focus_set())
        self.bind("<Escape>", lambda e: self.focus_set())

    def draw_header(self, _=None):
        c = self.header; c.delete("all"); w = c.winfo_width(); k = SC
        c.create_polygon(0, 0, w, 0, w, 50*k, w - 40*k, 78*k, 300*k, 78*k, 270*k, 50*k, 0, 50*k, fill=PANEL, outline=LINE)
        c.create_polygon(310*k, 78*k, 340*k, 54*k, w - 70*k, 54*k, w - 42*k, 78*k, fill=PANEL2, outline="")
        for i in range(14):  # hazard stripes
            x = (12 + i * 22) * k
            c.create_polygon(x, 8*k, x + 12*k, 8*k, x + 4*k, 42*k, x - 8*k, 42*k, fill=WARN if i < 4 else LINE, outline="")
        c.create_text(335*k, 22*k, text="ARMORED CORE", anchor="w", fill=TEXT, font=self.F(24, True))
        c.create_text(335*k, 66*k, text="MULTI-FRAME LAUNCHER  //  PS1 \u00b7 PS2 \u00b7 PSP \u00b7 PS3 \u00b7 PC",
                      anchor="w", fill=CYAN, font=self.F(9, True))
        c.create_line(0, 50*k, 270*k, 50*k, fill=ORANGE, width=2)
        c.create_text(w - 14*k, 22*k, text=f"FRAME // {THEME_NAME}", anchor="e", fill=ORANGE, font=self.F(10, True))
        c.create_text(w - 14*k, 38*k, text="ALL PILOTS: SORTIE READY", anchor="e", fill=DIM, font=self.F(8))

    def anim(self):  # light sweep across the header every few seconds
        c, k = self.header, SC
        if self.glint_x is not None:
            c.delete("glint"); x = self.glint_x
            c.create_polygon(x, 0, x + 46*k, 0, x + 12*k, 78*k, x - 34*k, 78*k, fill=GLINT, stipple="gray50", outline="", tags="glint")
            self.glint_x += 26 * k
            if self.glint_x > c.winfo_width() + 60 * k:
                c.delete("glint"); self.glint_x, self.glint_wait = None, 160
        else:
            self.glint_wait -= 1
            if self.glint_wait <= 0: self.glint_x = -60 * k
        self.after(40, self.anim)

    # ---- small behaviours ----------------------------------------------------
    def tick(self):
        self.clock.config(text=time.strftime("%Y.%m.%d  %H:%M:%S"))
        if not self.running and not self.installing:
            self.led.config(fg=CYAN if int(time.time()) % 2 else LED_DIM)
        self.after(1000, self.tick)

    def typewrite(self, msg, i):
        self.status.config(text=msg[:i] + ("_" if i < len(msg) else ""))
        if i < len(msg):
            self.after(18, lambda: self.typewrite(msg, i + 1))

    def set_filter(self, key):
        self.filter = key
        for k, (bar, t) in self.sys_btns.items():
            on = k == key
            bar.config(bg=ORANGE if on else PANEL); t.config(fg=CYAN if on else TEXT)
        self.refresh()

    # ---- library -------------------------------------------------------------
    def ask_system(self):
        d = tk.Toplevel(self, bg=PANEL, highlightthickness=1, highlightbackground=ORANGE)
        d.title("PLATFORM"); d.transient(self); d.resizable(False, False); d.grab_set()
        d.geometry(f"+{self.winfo_x() + 400}+{self.winfo_y() + 250}")
        tk.Label(d, text="\u25a0 WHICH PLATFORM IS THIS FOLDER?", bg=PANEL, fg=ORANGE, font=self.F(10, True)).pack(padx=20, pady=(16, 8))
        res = {"v": None}
        def pick(k): res["v"] = k; d.destroy()
        for k, v in EMULATORS.items():
            self.button(d, f"{k}  \u2014  {v['name']}", lambda k=k: pick(k)).pack(fill="x", padx=20, pady=3)
        tk.Frame(d, height=12, bg=PANEL).pack()
        self.wait_window(d); return res["v"]

    def add_folder(self):
        d = filedialog.askdirectory(title="Choose a folder containing your games")
        if not d: return
        s = self.ask_system()
        if not s: return
        self.cfg["folders"].append({"path": d, "system": s}); self.rescan()

    def rescan(self):
        old, best = self.cfg["library"], {}
        for fo in self.cfg["folders"]:
            for path, title, order in scan_folder(fo["path"], fo["system"]):
                rank = EXT_RANK.get(Path(path).suffix.lower(), 5)   # e.g. prefer .cue over its .bin
                key = (fo["system"], title)
                if key not in best or rank < best[key][0]: best[key] = (rank, path, order)
        lib = {}
        for (sys_, title), (_, path, order) in best.items():
            prev = old.get(path) or next((v for v in old.values() if v.get("title") == title and v.get("system") == sys_), {})
            e = {"playtime": prev.get("playtime", 0), "last": prev.get("last", 0), "args": prev.get("args", ""),
                 "title": title, "system": sys_, "order": order}
            for k in ("opts", "fav", "tid"):
                if k in prev: e[k] = prev[k]
            lib[path] = e
        info = find_steam_game(AC6_APPID, self.cfg.get("steam_path"))
        if info:
            key = f"steam://rungameid/{AC6_APPID}"; prev = old.get(key, {})
            lib[key] = {"playtime": prev.get("playtime", 0), "last": prev.get("last", 0), "args": "", "title": AC6_TITLE,
                        "system": "PC", "order": 19, "dir": info["dir"], **({"fav": True} if prev.get("fav") else {})}
        for pth, v in old.items():   # keep entries from folders not scanned right now (e.g. unplugged drive)
            if (v.get("system"), v.get("title")) not in best and os.path.exists(pth): lib.setdefault(pth, v)
        self.cfg["library"] = lib
        save_cfg(self.cfg); self.refresh()
        self.typewrite(f"SCAN COMPLETE ... {len(lib)} FRAME(S) REGISTERED", 0)

    def refresh(self):
        if not hasattr(self, "tree"): return
        keep = self.selected()
        self.tree.delete(*self.tree.get_children())
        q = norm(self.q.get())
        n = 0
        for path, e in sorted(self.cfg["library"].items(), key=lambda kv: kv[1].get("order", 99)):
            if (self.filter == "FAV" and not e.get("fav")) or (self.filter not in ("ALL", "FAV") and e["system"] != self.filter) or (q and q not in norm(e["title"])):
                continue
            n += 1
            h, m = divmod(int(e["playtime"] // 60), 60)
            self.tree.insert("", "end", iid=path, tags=("odd",) if n % 2 == 0 else (),
                             values=(f"{e['order']:02d}", ("\u2605 " if e.get("fav") else "") + e["title"].upper(), e["system"], f"{h:02d}:{m:02d}"))
        if keep and self.tree.exists(keep): self.tree.selection_set(keep)
        elif self.tree.get_children(): self.tree.selection_set(self.tree.get_children()[0])
        self.show_detail()

    def selected(self):
        if not hasattr(self, "tree"): return None
        sel = self.tree.selection()
        return sel[0] if sel and sel[0] in self.cfg["library"] else None

    def show_detail(self):
        k = self.selected()
        if not k:
            for l in self.fields.values(): l.config(text="---", fg=CYAN)
            self.fields["DESIGNATION"].config(text="NO FRAME SELECTED" if self.cfg["library"] else "NO DATA - ADD A GAME FOLDER")
            self.update_cover(None)
            return
        e = self.cfg["library"][k]; emu = SYSTEMS_ALL[e["system"]]
        exe = self.cfg["emulators"].get(e["system"]); ok = True if e["system"] == "PC" else bool(exe and Path(exe).exists())
        h, m = divmod(int(e["playtime"] // 60), 60)
        last = time.strftime("%Y-%m-%d %H:%M", time.localtime(e["last"])) if e["last"] else "NO RECORD"
        vals = {"DESIGNATION": e["title"].upper(), "PLATFORM": emu["gen"], "EMULATOR": emu["name"].upper(),
                "STATUS": "READY" if ok else "EMULATOR PATH NOT SET",
                "TOTAL FLIGHT TIME": f"{h}h {m:02d}m", "LAST SORTIE": last}
        for key, v in vals.items(): self.fields[key].config(text=v, fg=CYAN)
        self.fields["STATUS"].config(fg=CYAN if ok else RED)
        self.update_cover(e["title"])

    # ---- emulators / tools ---------------------------------------------------
    # ---- tabs / archive ---------------------------------------------------------
    def build_tabs(self, center):
        self.tab_frames, self.tab_btns = {}, {}
        bar = tk.Frame(center, bg=BG); bar.pack(fill="x", pady=(0, 6))
        for name in ("LIBRARY", "ARCHIVE", "SOUNDTRACKS", "MUSIC", "ACHIEVEMENTS"):
            b = tk.Label(bar, text=name, bg=PANEL2, fg=TEXT, font=self.F(10, True), padx=22, pady=6,
                         cursor="hand2", highlightthickness=1, highlightbackground=LINE)
            b.pack(side="left", padx=(0, 4)); b.bind("<Button-1>", lambda e, n=name: self.show_tab(n))
            self.tab_btns[name] = b

    def show_tab(self, name):
        for f in self.tab_frames.values(): f.pack_forget()
        self.tab_frames[name].pack(fill="both", expand=True)
        for n, b in self.tab_btns.items():
            on = n == name; b.config(bg=ORANGE if on else PANEL2, fg=ACC_FG if on else TEXT)
        self.right.grid_remove() if name in ("ARCHIVE", "SOUNDTRACKS", "MUSIC", "ACHIEVEMENTS") else self.right.grid()
        self.cur_tab = name
        if name == "ACHIEVEMENTS": self.ra_open()

    def build_archive(self, center):
        a = self.panel(center, "ARCHIVE // LORE & HISTORY"); self.tab_frames["ARCHIVE"] = a
        row = tk.Frame(a, bg=PANEL); row.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.lore_tree = ttk.Treeview(row, show="tree", style="AC.Treeview", selectmode="browse")
        self.lore_tree.column("#0", width=px(270))
        self.lore_tree.insert("", "end", iid="__overview", text="00  SERIES OVERVIEW")
        for title, sys_, order, _ in sorted(GAMES, key=lambda g: g[2]):
            self.lore_tree.insert("", "end", iid=title, text=f"{order:02d}  {title.upper()}  [{sys_}]")
        self.lore_tree.pack(side="left", fill="y")
        view = tk.Frame(row, bg=PANEL); view.pack(side="left", fill="both", expand=True, padx=(12, 0))
        top = tk.Frame(view, bg=PANEL); top.pack(fill="x", pady=(0, 8))
        self.lore_img = tk.Label(top, bg=PANEL2, fg=DIM, font=self.F(8), text="NO IMAGE", width=18, height=8)
        self.lore_img.pack(side="left")
        meta = tk.Frame(top, bg=PANEL); meta.pack(side="left", fill="x", expand=True, padx=14)
        self.lore_title = tk.Label(meta, bg=PANEL, fg=TEXT, font=self.F(15, True), anchor="w", justify="left", wraplength=px(430))
        self.lore_title.pack(fill="x")
        self.lore_meta = tk.Label(meta, bg=PANEL, fg=ORANGE, font=self.F(9, True), anchor="w")
        self.lore_meta.pack(fill="x", pady=(2, 10))
        self.button(meta, "OPEN WIKIPEDIA ARTICLE", lambda: self.open_url("wiki")).pack(anchor="w", pady=2)
        self.button(meta, "SEARCH ARMORED CORE FANDOM WIKI", lambda: self.open_url("fandom")).pack(anchor="w", pady=2)
        self.gal = tk.Frame(view, bg=PANEL); self.gal.pack(fill="x", pady=(0, 8))
        tw = tk.Frame(view, bg=PANEL); tw.pack(fill="both", expand=True)
        self.lore_text = tk.Text(tw, bg=BG, fg=TEXT, font=self.F(10), wrap="word", relief="flat", padx=12, pady=10,
                                 highlightthickness=1, highlightbackground=LINE, state="disabled", cursor="arrow")
        sb = ttk.Scrollbar(tw, orient="vertical", command=self.lore_text.yview, style="AC.Vertical.TScrollbar")
        self.lore_text.configure(yscrollcommand=sb.set)
        self.lore_text.tag_configure("h", foreground=ORANGE, font=self.F(10, True))
        self.lore_text.tag_configure("dim", foreground=DIM)
        self.lore_text.pack(side="left", fill="both", expand=True); sb.pack(side="right", fill="y")
        self.lore_tree.bind("<<TreeviewSelect>>", self.render_lore)
        self.lore_tree.selection_set("__overview")

    def render_lore(self, *_):
        sel = self.lore_tree.selection(); k = sel[0] if sel else "__overview"
        self.sel_lore = k
        t = self.lore_text; t.config(state="normal"); t.delete("1.0", "end")
        self.fill_gallery(None)
        if k == "__overview":
            self.lore_title.config(text="ARMORED CORE"); self.lore_meta.config(text="FROMSOFTWARE  //  1997 - PRESENT")
            t.insert("end", OVERVIEW)
            w = self.wiki.get("__overview")
            self.set_img(self.lore_img, self.photo(w.get("img"), (px(130), px(180))) if w else None)
            if not w: self.fetch_art("__overview")
        else:
            _, sys_, _, _ = next(g for g in GAMES if g[0] == k)
            year, _, blurb = LORE[k]
            self.lore_title.config(text=k.upper())
            self.lore_meta.config(text=f"{year}  //  {SYSTEMS_ALL[sys_]['gen']}  //  FROMSOFTWARE")
            t.insert("end", "BRIEFING\n", "h"); t.insert("end", blurb + "\n\n")
            t.insert("end", "FIELD REPORT  (live from Wikipedia)\n", "h")
            w = self.wiki.get(k)
            if w:
                t.insert("end", (w["extract"][:2800] or "No article text available.") + "\n")
                self.set_img(self.lore_img, self.photo(w.get("img"), (px(130), px(180))))
                self.fill_gallery(w)
            else:
                self.set_img(self.lore_img, None)
                if k in self.wiki_fail:
                    t.insert("end", f"Could not load ({self.wiki_fail.pop(k)}). Needs internet; select again to retry.", "dim")
                else:
                    t.insert("end", "Retrieving data ...", "dim"); self.fetch_art(k)
        t.config(state="disabled")

    def fill_gallery(self, w):
        for c in self.gal.winfo_children(): c.destroy()
        for pth in ((w or {}).get("extra") or [])[:3]:
            ph = self.photo(pth, (px(190), px(110)))
            if ph: tk.Label(self.gal, image=ph, bg=PANEL2, bd=0).pack(side="left", padx=(0, 6))

    def open_url(self, kind):
        k = self.sel_lore
        if not k or k == "__overview":
            return webbrowser.open("https://en.wikipedia.org/wiki/Armored_Core" if kind == "wiki" else "https://armoredcore.fandom.com/")
        if kind == "wiki":
            w = self.wiki.get(k)
            webbrowser.open((w or {}).get("url") or "https://en.wikipedia.org/w/index.php?search=" + urllib.parse.quote(k))
        else:
            webbrowser.open("https://armoredcore.fandom.com/wiki/Special:Search?query=" + urllib.parse.quote(k))

    def view_lore(self):
        k = self.selected()
        if not k: return
        t = self.cfg["library"][k]["title"]
        self.show_tab("ARCHIVE")
        if self.lore_tree.exists(t):
            self.lore_tree.selection_set(t); self.lore_tree.see(t)

    # ---- online art / wiki data --------------------------------------------------
    def fetch_art(self, title):
        if title in self.wiki or title in self.fetching or (title not in LORE and title != "__overview"): return
        self.fetching.add(title)
        def work():
            try: self.msgs.put(("wiki", title, fetch_all(title, LORE[title][1] if title in LORE else "Armored Core", next((g[1] for g in GAMES if g[0] == title), None)), None))
            except Exception as ex:
                log(f"wiki fetch {title}: {ex!r}"); self.msgs.put(("wiki", title, None, str(ex)))
        threading.Thread(target=work, daemon=True).start()

    def on_wiki(self, title, info, err):
        self.fetching.discard(title)
        if info: self.wiki[title] = info
        else: self.wiki_fail[title] = err or "unknown error"
        if self.sel_lore == title: self.render_lore()
        k = self.selected()
        if k and self.cfg["library"][k]["title"] == title: self.update_cover(title)

    def photo(self, path, box):
        if not HAVE_PIL or not path or not Path(path).exists(): return None
        key = (path, box)
        if key not in self.photos:
            try:
                im = Image.open(path).convert("RGB"); im.thumbnail(box)
                self.photos[key] = ImageTk.PhotoImage(im)
            except Exception:
                return None
        return self.photos[key]

    def set_img(self, label, ph, empty="NO IMAGE"):
        if ph: label.config(image=ph, text="", width=ph.width(), height=ph.height())
        else: label.config(image="", text=empty, width=18, height=8 if label is self.lore_img else 6)

    def update_cover(self, title):
        info = self.wiki.get(title) if title else None
        if title and not info: self.fetch_art(title)
        self.set_img(self.cover_lbl, self.photo(info.get("img"), (px(130), px(165))) if info else None, "NO COVER")

    # ---- built-in emulator installer ----------------------------------------
    def autodetect(self):
        for s in EMULATORS:
            if not Path(self.cfg["emulators"].get(s) or "?").is_file():
                exe = find_exe(s)
                if exe: self.cfg["emulators"][s] = str(exe)
        save_cfg(self.cfg)

    def install_all(self):
        if messagebox.askyesno("Install emulators", "Download the latest official DuckStation, PCSX2, PPSSPP and RPCS3 builds into the launcher's own folder?\n(Re-running updates them; saves are kept.)"):
            self.install(list(EMULATORS))

    def install(self, systems, then=None):
        if self.installing: return
        self.installing = True; self.led.config(fg=ORANGE)
        def work():
            for s in systems:
                try:
                    self.msgs.put(("ok", s, install_emulator(s, lambda m: self.msgs.put(("msg", m)))))
                except Exception as ex:
                    self.msgs.put(("err", s, str(ex)))
            self.msgs.put(("done", then))
        threading.Thread(target=work, daemon=True).start()

    def poll(self):
        try:
            while True:
                m = self.msgs.get_nowait()
                if m[0] == "msg":
                    self.status.config(text=m[1].upper(), fg=ORANGE)
                elif m[0] == "ok":
                    self.cfg["emulators"][m[1]] = m[2]; save_cfg(self.cfg); self.updates.discard(m[1])
                    self.status.config(text=f"{EMULATORS[m[1]]['name'].upper()} INSTALLED", fg=CYAN)
                elif m[0] == "err":
                    self.status.config(text=f"{EMULATORS[m[1]]['name'].upper()} INSTALL FAILED", fg=RED)
                    messagebox.showerror("Install failed", f"{EMULATORS[m[1]]['name']}: {m[2]}\n\nCheck your connection, or use SET PATH MANUALLY.")
                elif m[0] == "ra":
                    self.on_ra(m[1], m[2], m[3])
                elif m[0] == "pkg":
                    self.on_pkg(m[1], m[2], m[3])
                elif m[0] == "cli":
                    self.on_cli(m[1], m[2], m[3])
                elif m[0] == "fw":
                    self.on_fw(m[1], m[2])
                elif m[0] == "upd":
                    self.on_updates(m[1], m[2])
                elif m[0] == "wiki":
                    self.on_wiki(m[1], m[2], m[3])
                elif m[0] == "done":
                    self.installing = False; self.show_detail(); self.refresh_check()
                    if m[1]: m[1]()
        except queue.Empty:
            pass
        self.after(100, self.poll)

    def import_bios(self, s=None):
        s = s or self.ask_system()
        if not s: return
        exe = self.cfg["emulators"].get(s)
        if s == "PSP":
            return messagebox.showinfo("BIOS", "PSP needs no BIOS.")
        if not exe or not Path(exe).exists():
            return messagebox.showerror("Not installed", "Install the emulator first.")
        files = filedialog.askopenfilenames(title=f"Select your own {s} BIOS/firmware file(s)")
        if not files: return
        if s == "PS3":  # RPCS3 firmware install; verify flag with rpcs3 --help
            messagebox.showinfo("PS3 firmware", "Only RPCS3 itself can install PS3 firmware, so its window will open. If it shows a welcome or download prompt, close that prompt: it will install the file you picked. Wait for the progress bar to finish, then close RPCS3.")
            spawn([exe, "--installfw", files[0]], cwd=str(Path(exe).parent), env=clean_env())
        else:
            dest = Path(exe).parent / "bios"; dest.mkdir(exist_ok=True)
            for f in files: shutil.copy2(f, dest)
        self.typewrite(f"{s} BIOS IMPORTED", 0)
        self.refresh_check()

    # ---- startup check, updates, saves, theme, favorites --------------------------
    def startup(self):
        self.restore_pending()
        self.rescan()
        if self.setup_needed() and not self.cfg.get("skip_wizard"):
            self.system_check()
        self.check_updates(True)

    def bios_ok(self, s):
        exe = self.cfg["emulators"].get(s)
        if s == "PSP": return True
        if not exe or not Path(exe).exists(): return False
        d = Path(exe).parent
        if s == "PS3": return (d / "dev_flash" / "sys").is_dir()
        b = d / "bios"
        return b.is_dir() and any(f.is_file() for f in b.iterdir())

    def setup_needed(self):
        return any(not (self.cfg["emulators"].get(s) and Path(self.cfg["emulators"][s]).exists()) or not self.bios_ok(s)
                   for s in EMULATORS)

    def set_opt(self, key, val):
        self.cfg[key] = val; save_cfg(self.cfg)
        if key == "cmd_launch": globals()["LAUNCH_VIA_CMD"] = bool(val)

    def system_check(self):
        if self.check_win and self.check_win.winfo_exists():
            self.check_win.lift(); return self.refresh_check()
        w = self.check_win = tk.Toplevel(self, bg=PANEL, highlightthickness=1, highlightbackground=ORANGE)
        w.title("PRE-SORTIE SYSTEM CHECK"); w.transient(self)
        w.geometry(f"{px(760)}x{px(640)}+{self.winfo_x() + px(100)}+{self.winfo_y() + px(40)}")
        tk.Label(w, text="\u25a0 PRE-SORTIE SYSTEM CHECK", bg=PANEL, fg=ORANGE, font=self.F(13, True)).pack(anchor="w", padx=16, pady=(14, 0))
        tk.Label(w, text="PS1/PS2 BIOS must be your own dump. PS3 firmware can be fetched from Sony's official link via RPCS3's own page.",
                 bg=PANEL, fg=DIM, font=self.F(9)).pack(anchor="w", padx=16, pady=(0, 8))
        foot = tk.Frame(w, bg=PANEL); foot.pack(side="bottom", fill="x", padx=16, pady=12)
        self.check_body = tk.Frame(w, bg=PANEL); self.check_body.pack(fill="both", expand=True, padx=16)
        for text, key, dflt in ((" AUTO-UPDATE EMULATORS AT STARTUP", "auto_update", True),
                                (" DON'T SHOW THIS WINDOW AT STARTUP", "skip_wizard", False),
                                (" COMPATIBILITY LAUNCH (turn on if an emulator reports a DLL error)", "cmd_launch", False)):
            v = tk.BooleanVar(value=self.cfg.get(key, dflt))
            tk.Checkbutton(foot, text=text, variable=v, command=lambda v=v, k=key: self.set_opt(k, v.get()),
                           bg=PANEL, fg=TEXT, selectcolor=BG, activebackground=PANEL, activeforeground=CYAN,
                           font=self.F(9, True), highlightthickness=0, bd=0, anchor="w").pack(anchor="w")
        btns = tk.Frame(foot, bg=PANEL); btns.pack(fill="x", pady=(8, 0))
        self.button(btns, "CHECK FOR UPDATES", lambda: self.check_updates(True)).pack(side="left")
        self.button(btns, "BACKUP SAVES", self.backup_saves).pack(side="left", padx=6)
        self.button(btns, "THEME", self.switch_theme).pack(side="left")
        self.button(btns, "SET PATHS", self.set_emulators).pack(side="left", padx=6)
        self.button(btns, "CLOSE", w.destroy, accent=True).pack(side="right")
        self.refresh_check()

    def refresh_check(self):
        if not (self.check_win and self.check_win.winfo_exists()): return
        for c in self.check_body.winfo_children(): c.destroy()
        for s, em in EMULATORS.items():
            exe = self.cfg["emulators"].get(s); ok = bool(exe and Path(exe).exists()); upd = ok and s in self.updates
            card = tk.Frame(self.check_body, bg=PANEL2, highlightthickness=1, highlightbackground=LINE)
            card.pack(fill="x", pady=4)
            r1 = tk.Frame(card, bg=PANEL2); r1.pack(fill="x", padx=10, pady=(8, 2))
            tk.Label(r1, text=f"{s}  {em['name'].upper()}", bg=PANEL2, fg=TEXT, font=self.F(11, True)).pack(side="left")
            st, col = ("UPDATE AVAILABLE", WARN) if upd else (("INSTALLED", CYAN) if ok else ("NOT INSTALLED", RED))
            tk.Label(r1, text=st, bg=PANEL2, fg=col, font=self.F(9, True)).pack(side="left", padx=12)
            if not ok or upd:
                self.button(r1, "UPDATE" if upd else "INSTALL", lambda s=s: self.install([s]), accent=True).pack(side="right")
            r2 = tk.Frame(card, bg=PANEL2); r2.pack(fill="x", padx=10, pady=(2, 2))
            if s == "PSP":
                tk.Label(r2, text="BIOS / FIRMWARE: NOT REQUIRED", bg=PANEL2, fg=DIM, font=self.F(9)).pack(side="left", pady=(0, 6))
                continue
            bok = self.bios_ok(s)
            tk.Label(r2, text="FIRMWARE:" if s == "PS3" else "BIOS:", bg=PANEL2, fg=DIM, font=self.F(9)).pack(side="left")
            tk.Label(r2, text="FOUND" if bok else "MISSING", bg=PANEL2, fg=CYAN if bok else RED, font=self.F(9, True)).pack(side="left", padx=8)
            self.button(r2, "REPLACE" if bok else "IMPORT FILE", lambda s=s: self.import_bios(s)).pack(side="right")
            if s == "PS3": self.button(r2, "DOWNLOAD OFFICIAL", self.get_firmware).pack(side="right", padx=6)
            tk.Label(card, text=BIOS_HINTS[s], bg=PANEL2, fg=DIM, font=self.F(8)).pack(anchor="w", padx=10, pady=(0, 8))
        self.steam_card()

    def update_now(self):
        self.typewrite("CHECKING FOR EMULATOR UPDATES ...", 0); self.check_updates(True, force=True)

    def check_updates(self, prompt, force=False):
        if self.checking or self.installing: return
        self.checking = True
        def work():
            ups = []
            for s in EMULATORS:
                if not find_exe(s): continue  # only launcher-managed installs can be updated
                try:
                    if installed_version(s) != find_download(s)[2]: ups.append(s)
                except Exception as ex:
                    log(f"update check {s}: {ex!r}")
            self.msgs.put(("upd", ups, prompt))
        threading.Thread(target=work, daemon=True).start()

    def on_updates(self, ups, prompt):
        self.checking = False; self.updates = set(ups); self.refresh_check()
        if not prompt: return
        if not ups:
            return self.typewrite("ALL EMULATORS UP TO DATE", 0)
        names = ", ".join(EMULATORS[s]["name"] for s in ups)
        if self.cfg.get("auto_update", True):
            self.typewrite(f"AUTO-UPDATING: {names.upper()}", 0); self.install(ups)
        elif messagebox.askyesno("Emulator updates", f"Updates available: {names}\nDownload and install now? (Saves are kept.)"):
            self.install(ups)

    def backup_saves(self):
        dirs = SAVE_DIRS
        out = EMU_HOME.parent / "backups"; out.mkdir(parents=True, exist_ok=True)
        zp = out / f"saves_{time.strftime('%Y%m%d_%H%M%S')}.zip"; n = 0
        with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
            for s, rels in dirs.items():
                exe = self.cfg["emulators"].get(s)
                if not exe: continue
                for rel in rels:
                    d = Path(exe).parent / rel
                    for f in (d.rglob("*") if d.exists() else []):
                        if f.is_file(): z.write(f, f"{s}/{rel}/{f.relative_to(d)}"); n += 1
        if n:
            messagebox.showinfo("Backup complete", f"{n} files saved to:\n{zp}")
        else:
            zp.unlink(missing_ok=True); messagebox.showinfo("Backup", "No save files found yet.")

    def toggle_fav(self):
        k = self.selected()
        if k:
            e = self.cfg["library"][k]; e["fav"] = not e.get("fav"); save_cfg(self.cfg); self.refresh()

    def switch_theme(self):
        names = list(THEMES); nxt = names[(names.index(THEME_NAME) + 1) % len(names)]
        if not messagebox.askyesno("Theme", f"Switch to the {nxt} theme? The launcher will restart."): return
        self.cfg["theme"] = nxt; save_cfg(self.cfg)
        args = [sys.executable] + ([] if getattr(sys, "frozen", False) else [os.path.abspath(sys.argv[0])])
        spawn(args, env=dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT="1"))
        self.destroy()

    # ---- per-game settings dialog -------------------------------------------------------
    def opts_for(self, k):
        e = self.cfg["library"][k]
        saved = dict(e.get("opts", {}))
        if "res_pct" in saved: saved.setdefault("res", saved.pop("res_pct"))   # older saved settings
        return {**DEFAULT_OPTS[e["system"]], **PRESETS.get(e["title"], {}), **saved}

    def choice_row(self, parent, text, options, cur, key, note=None):
        row = tk.Frame(parent, bg=PANEL); row.pack(fill="x", padx=16, pady=3)
        tk.Label(row, text=text, bg=PANEL, fg=DIM, font=self.F(8, True)).pack(anchor="w")
        bar = tk.Frame(row, bg=PANEL); bar.pack(anchor="w", pady=3)
        items = []
        def paint():
            for lb, val in items:
                on = cur.get(key) == val
                lb.config(bg=ORANGE if on else PANEL2, fg=ACC_FG if on else TEXT)
        def pick(val):
            cur[key] = val; paint()
        for label, val in options:
            lb = tk.Label(bar, text=label, padx=12, pady=6, cursor="hand2", font=self.F(9, True),
                          highlightthickness=1, highlightbackground=LINE)
            lb.pack(side="left", padx=(0, 4)); lb.bind("<Button-1>", lambda e, v=val: pick(v)); items.append((lb, val))
        paint()
        if note:
            tk.Label(row, text=note, bg=PANEL, fg=DIM, font=self.F(8), wraplength=px(560), justify="left").pack(anchor="w")

    def game_settings(self):
        k = self.selected()
        if not k: return
        e = self.cfg["library"][k]; s = e["system"]
        if s == "PC":
            return messagebox.showinfo("Graphics", "Armored Core VI is a Steam game. Change its graphics in the game's own options menu, or in Steam > Properties.")
        cur = self.opts_for(k)
        d = tk.Toplevel(self, bg=PANEL, highlightthickness=1, highlightbackground=ORANGE)
        d.title("GAME SETTINGS"); d.transient(self); d.grab_set()
        sh = self.winfo_screenheight()
        d.geometry(f"{px(700)}x{min(px(780), sh - 80)}+{self.winfo_x() + px(100)}+{self.winfo_y() + px(20)}")
        foot = tk.Frame(d, bg=PANEL); foot.pack(side="bottom", fill="x", padx=16, pady=12)
        tk.Label(d, text="\u25a0 " + e["title"].upper(), bg=PANEL, fg=ORANGE, font=self.F(12, True)).pack(anchor="w", padx=16, pady=(14, 0))
        tk.Label(d, text=f"{EMULATORS[s]['name']}  //  applied automatically every time you press SORTIE",
                 bg=PANEL, fg=DIM, font=self.F(9)).pack(anchor="w", padx=16, pady=(0, 6))
        if e["title"] in NOTES:
            tk.Label(d, text=NOTES[e["title"]], bg=PANEL2, fg=TEXT, font=self.F(9), wraplength=px(620), justify="left",
                     padx=10, pady=8).pack(fill="x", padx=16, pady=(0, 6))
        if s == "PS3" and e["title"] == "Armored Core: For Answer" and cur.get("wcb") and (auto_scale("PS3", self.winfo_screenheight()) if cur.get("res") == "auto" else cur.get("res", 100)) > 100:
            tk.Label(d, text="WARNING: Write Color Buffers with a resolution above 1x is known to crash For Answer (RPCS3 issue #11984). Use 1x or press RECOMMENDED PRESET.",
                     bg=PANEL2, fg=RED, font=self.F(9, True), wraplength=px(620), justify="left", padx=10, pady=6).pack(fill="x", padx=16, pady=(0, 6))
        res = {"PS3": [("1x  720p", 100), ("1.5x  1080p", 150), ("2x  1440p", 200), ("3x  4K", 300)],
               "PS1": [(f"{n}x", n) for n in (1, 2, 4, 6, 8)], "PS2": [(f"{n}x", n) for n in (1, 2, 3, 4, 6)],
               "PSP": [(f"{n}x", n) for n in (1, 2, 3, 4, 5)]}[s]
        auto_val = auto_scale(s, self.winfo_screenheight())
        unit = "%" if s == "PS3" else "x"
        self.choice_row(d, "RESOLUTION (INTERNAL SCALE)", [("AUTO", "auto")] + res, cur, "res",
                        f"AUTO matches your {self.winfo_screenwidth()}x{self.winfo_screenheight()} display: currently {auto_val}{unit}. "
                        + ("PS3 values are a percent of the game's native 720p (150% = 1080p)." if s == "PS3" else "Higher looks sharper but needs a stronger GPU."))
        if s == "PS3":
            self.choice_row(d, "FRAME LIMIT", [("AUTO", "Auto"), ("60", "60"), ("30", "30"), ("UNLIMITED", "Off")], cur, "fps")
            self.choice_row(d, "WRITE COLOR BUFFERS", [("ON", True), ("OFF", False)], cur, "wcb",
                            "Leave ON for For Answer. Some other games prefer it off.")
            self.choice_row(d, "VSYNC", [("OFF", False), ("ON", True)], cur, "vsync", "Default OFF. Turn on only if you see screen tearing.")
            self.choice_row(d, "ANISOTROPIC FILTERING", [("AUTO", 0), ("2x", 2), ("4x", 4), ("8x", 8), ("16x", 16)], cur, "af")
            self.choice_row(d, "HANDLE RSX MEMORY TILING", [("OFF", False), ("ON", True)], cur, "tiling",
                            "RPCS3 wiki: ON fixes most For Answer logo and AC texture corruption.")
        if s in ("PS1", "PS2"):
            self.choice_row(d, "WIDESCREEN", [("ON", True), ("OFF", False)], cur, "ws",
                            "PS2: uses PCSX2's built-in widescreen patches where one exists for the game." if s == "PS2"
                            else "PS1: stretches the 3D view; the image can look odd at the edges.")
        row = tk.Frame(d, bg=PANEL); row.pack(fill="x", padx=16, pady=5)
        tk.Label(row, text="EXTRA COMMAND-LINE ARGS (ADVANCED)", bg=PANEL, fg=DIM, font=self.F(8, True)).pack(anchor="w")
        av = tk.StringVar(value=e.get("args", ""))
        tk.Entry(row, textvariable=av, bg=BG, fg=CYAN, insertbackground=CYAN, relief="flat", font=self.F(10),
                 highlightthickness=1, highlightbackground=LINE, highlightcolor=ORANGE).pack(fill="x", ipady=3, pady=3)
        def save():
            e["opts"] = dict(cur); e["args"] = av.get(); save_cfg(self.cfg); d.destroy()
            self.typewrite("SETTINGS SAVED - APPLIED ON NEXT SORTIE", 0)
        def reset():
            e.pop("opts", None); d.destroy(); self.game_settings()
        foot2 = tk.Frame(d, bg=PANEL); foot2.pack(side="bottom", fill="x", padx=16)
        self.button(foot, "SAVE", save, accent=True).pack(side="right")
        self.button(foot, "CANCEL", d.destroy).pack(side="right", padx=6)
        self.button(foot, "RECOMMENDED PRESET", reset).pack(side="left")
        if s == "PS3":
            foot3 = tk.Frame(d, bg=PANEL); foot3.pack(side="bottom", fill="x", padx=16, pady=(0, 4))
            self.button(foot3, "DIAGNOSE LAST RUN", self.diagnose_ps3, accent=True).pack(side="left", padx=(0, 6))
            self.button(foot3, "OPEN RPCS3 LOG", lambda: self.open_log(s)).pack(side="left")
        self.button(foot2, "CONTROLLER SETUP", lambda: self.controller_setup(s)).pack(side="left", padx=(0, 6))
        self.button(foot2, "SAVE SLOTS", self.save_slots).pack(side="left", padx=(0, 6))
        if s == "PS3": self.button(foot2, "GET GAME UPDATE", lambda: self.ps3_update(k)).pack(side="left")

    def open_log(self, s):
        exe = self.cfg["emulators"].get(s)
        if not exe: return
        base = Path(exe).parent
        target = next((c for c in (base / "RPCS3.log", base / "log" / "RPCS3.log") if c.exists()), base)
        os.startfile(str(target)) if os.name == "nt" else subprocess.Popen(["xdg-open", str(target)])

    # ---- PS3 updates / firmware, controllers, save slots ---------------------------------
    def ps3_tid(self, k, ask=True):
        e = self.cfg["library"][k]
        if e.get("tid"): return e["tid"]
        exe = self.cfg["emulators"].get("PS3")
        tid = ps3_title_id(k, exe) if exe else None
        if not tid and ask:
            hint = ", ".join(KNOWN_IDS.get(e["title"], [])) or "for example BLUS30187"
            tid = (simpledialog.askstring("Title ID", f"Couldn't detect this game's ID.\nEnter it (known IDs: {hint}):", parent=self) or "").strip().upper()
            if not re.fullmatch(r"[A-Z]{4}\d{5}", tid): return None
        if tid: e["tid"] = tid; save_cfg(self.cfg)
        return tid

    def ps3_update(self, k):
        tid = self.ps3_tid(k)
        if not tid: return
        self.typewrite(f"CHECKING SONY SERVERS FOR {tid} UPDATES ...", 0)
        def work():
            try:
                self.msgs.put(("pkg", tid, get_ps3_update(tid, lambda m: self.msgs.put(("msg", m))), None))
            except Exception as ex:
                log(f"ps3 update {tid}: {ex!r}"); self.msgs.put(("pkg", tid, None, str(ex)))
        threading.Thread(target=work, daemon=True).start()

    def on_pkg(self, tid, res, err):
        if err:
            self.typewrite("UPDATE CHECK FAILED", 0)
            return messagebox.showerror("Game update", f"{tid}: {err}")
        if res is None:
            return self.typewrite(f"NO OFFICIAL UPDATE LISTED FOR {tid}", 0)
        ver, path = res
        self.cfg.setdefault("ps3_updates", {})[tid] = ver; save_cfg(self.cfg)
        self.rpcs3_cli("--installpkg", path, f"update v{ver}")

    def get_firmware(self):
        self.typewrite("FETCHING OFFICIAL PS3 FIRMWARE ...", 0)
        def work():
            try: self.msgs.put(("fw", get_ps3_firmware(lambda m: self.msgs.put(("msg", m))), None))
            except Exception as ex:
                log(f"ps3 firmware: {ex!r}"); self.msgs.put(("fw", None, str(ex)))
        threading.Thread(target=work, daemon=True).start()

    def on_fw(self, path, err):
        if err:
            if messagebox.askyesno("Firmware", f"{err}\n\nOpen RPCS3's quickstart page to download it manually?"):
                webbrowser.open("https://rpcs3.net/quickstart")
            return
        self.rpcs3_cli("--installfw", path, "firmware")

    def rpcs3_cli(self, flag, path, what):
        exe = self.cfg["emulators"].get("PS3")
        if not exe or not Path(exe).exists():
            return messagebox.showerror("RPCS3 missing", "Install RPCS3 first.")
        def work():
            try:
                pr = spawn([exe, flag, path], cwd=str(Path(exe).parent), env=clean_env())
                try: rc = pr.wait(timeout=8)
                except subprocess.TimeoutExpired: rc = None   # still running = installing
            except OSError:
                rc = -1
            self.msgs.put(("cli", rc, path, what))
        threading.Thread(target=work, daemon=True).start()

    def on_cli(self, rc, path, what):
        if rc in (None, 0):
            messagebox.showinfo("RPCS3", f"RPCS3 is installing the {what}. Wait for its progress bar to finish, then close RPCS3.")
        else:
            menu = "Install Firmware" if "firmware" in what else "Install Packages/Raps/Edats"
            messagebox.showinfo("Install manually", f"RPCS3 didn't accept the automatic install.\nIn RPCS3 use File > {menu} and choose:\n{path}")
            d = str(Path(path).parent)
            os.startfile(d) if os.name == "nt" else subprocess.Popen(["xdg-open", d])

    def controller_setup(self, s):
        exe = self.cfg["emulators"].get(s)
        if not exe or not Path(exe).exists():
            return messagebox.showerror("Not installed", "Install the emulator first.")
        messagebox.showinfo("Controller setup", f"The emulator's own window will open.\n\n{CONTROL_HELP[s]}\n\nControls are saved by the emulator and used for every game on that console.")
        spawn([exe], cwd=str(Path(exe).parent), env=clean_env())

    def save_slots(self):
        k = self.selected()
        if not k: return
        if self.cfg["library"][k]["system"] == "PC":
            return messagebox.showinfo("Save slots", "Armored Core VI saves are handled by Steam Cloud. Save slots are for emulated games.")
        s = self.cfg["library"][k]["system"]; exe = self.cfg["emulators"].get(s)
        if not exe or not Path(exe).exists():
            return messagebox.showerror("Not installed", "Install the emulator first.")
        d = tk.Toplevel(self, bg=PANEL, highlightthickness=1, highlightbackground=ORANGE)
        d.title("SAVE SLOTS"); d.transient(self); d.grab_set()
        d.geometry(f"{px(620)}x{px(460)}+{self.winfo_x() + px(160)}+{self.winfo_y() + px(80)}")
        tk.Label(d, text=f"\u25a0 SAVE SLOTS // {EMULATORS[s]['name'].upper()}", bg=PANEL, fg=ORANGE, font=self.F(12, True)).pack(anchor="w", padx=16, pady=(14, 0))
        tk.Label(d, text="A slot holds all of this console's saves (the emulator keeps every game's saves together). Loading backs up your current saves first.",
                 bg=PANEL, fg=DIM, font=self.F(8), wraplength=px(580), justify="left").pack(anchor="w", padx=16, pady=(0, 8))
        body = tk.Frame(d, bg=PANEL); body.pack(fill="both", expand=True, padx=16)
        def info(n):
            sd = slot_dir(s, n)
            if not sd.exists(): return "EMPTY"
            files = sum(1 for f in sd.rglob("*") if f.is_file())
            return f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(sd.stat().st_mtime))}   {files} files"
        def busy():
            if self.running: messagebox.showinfo("Busy", "Close the game first.")
            return self.running
        def do_save(n):
            if busy(): return
            if slot_dir(s, n).exists() and not messagebox.askyesno("Overwrite", f"Overwrite slot {n}?"): return
            if not copy_saves(s, exe, slot_dir(s, n)): messagebox.showinfo("Save slot", "No save files found yet.")
            else: self.typewrite(f"SAVED TO SLOT {n}", 0)
            render()
        def do_load(n):
            if busy() or not slot_dir(s, n).exists(): return
            if not messagebox.askyesno("Load slot", f"Replace the current saves with slot {n}?\nYour current saves are backed up first."): return
            copy_saves(s, exe, SLOT_ROOT / s / "before_last_load"); restore_saves(s, exe, slot_dir(s, n))
            self.typewrite(f"LOADED SLOT {n}", 0)
        def render():
            for c in body.winfo_children(): c.destroy()
            for n in range(1, 6):
                r = tk.Frame(body, bg=PANEL2, highlightthickness=1, highlightbackground=LINE); r.pack(fill="x", pady=3)
                tk.Label(r, text=f"SLOT {n}", bg=PANEL2, fg=TEXT, font=self.F(10, True), width=8, anchor="w").pack(side="left", padx=10, pady=8)
                tk.Label(r, text=info(n), bg=PANEL2, fg=DIM, font=self.F(9)).pack(side="left")
                self.button(r, "LOAD", lambda n=n: do_load(n)).pack(side="right", padx=(0, 8))
                self.button(r, "SAVE HERE", lambda n=n: do_save(n), accent=True).pack(side="right", padx=4)
        render()
        self.button(d, "CLOSE", d.destroy).pack(side="bottom", anchor="e", padx=16, pady=12)

    # ---- reset / uninstall ----------------------------------------------------------------
    def restart_app(self):
        args = [sys.executable] + ([] if getattr(sys, "frozen", False) else [os.path.abspath(sys.argv[0])])
        spawn(args, env=clean_env())
        self.destroy()

    def reset_dialog(self):
        if self.running or self.installing:
            return messagebox.showinfo("Busy", "Wait for the running game or install to finish first.")
        home = CFG_PATH.parent; dl = EMU_HOME.parent / "downloads"; bk = EMU_HOME.parent / "backups"
        items = [  # key, title, description, paths, ticked by default
            ("settings", "LAUNCHER SETTINGS & LIBRARY", "Game list, favorites, playtime, per-game settings, theme. Your game files are never touched.", [CFG_PATH], True),
            ("cache", "CACHED ART & LORE", "Downloaded cover art, screenshots and articles. Re-downloaded when needed.", [CACHE], True),
            ("downloads", "DOWNLOADED UPDATES & FIRMWARE", "Game update packages and firmware installers fetched by the launcher.", [dl], True),
            ("log", "LOG FILE", "Error log.", [home / "log.txt"], True),
            ("music", "MUSIC LIBRARY", "Songs you imported into the launcher's music player.", [MUSIC_DIR], False),
            ("slots", "SAVE SLOTS & BACKUPS", "Your launcher save slots and backup zips. These are copies of your save data.", [SLOT_ROOT, bk], False),
            ("emus", "EMULATORS (AND THEIR SAVES, BIOS, FIRMWARE, CONFIGS)", "Everything in the emulator folders the launcher installed, including saves, BIOS, PS3 firmware and installed PS3 updates.", [EMU_HOME], False),
        ]
        d = tk.Toplevel(self, bg=PANEL, highlightthickness=1, highlightbackground=RED)
        d.title("RESET / UNINSTALL"); d.transient(self); d.grab_set()
        sh = self.winfo_screenheight()
        d.geometry(f"{px(720)}x{min(px(700), sh - 80)}+{self.winfo_x() + px(120)}+{self.winfo_y() + px(30)}")
        tk.Label(d, text="\u25a0 RESET / UNINSTALL", bg=PANEL, fg=RED, font=self.F(13, True)).pack(anchor="w", padx=16, pady=(14, 0))
        tk.Label(d, text="Your game files (ISOs, disc images, game folders) are never deleted. Tick what to remove.",
                 bg=PANEL, fg=DIM, font=self.F(9)).pack(anchor="w", padx=16, pady=(0, 6))
        foot = tk.Frame(d, bg=PANEL); foot.pack(side="bottom", fill="x", padx=16, pady=12)
        vars_ = {}
        for key, title, desc, paths, dflt in items:
            size = sum(dir_size(q) for q in paths)
            v = tk.BooleanVar(value=dflt); vars_[key] = v
            r = tk.Frame(d, bg=PANEL2, highlightthickness=1, highlightbackground=LINE); r.pack(fill="x", padx=16, pady=3)
            tk.Checkbutton(r, text=f" {title}   ({human(size)})", variable=v, bg=PANEL2, fg=TEXT, selectcolor=BG,
                           activebackground=PANEL2, activeforeground=CYAN, font=self.F(9, True), highlightthickness=0,
                           bd=0, anchor="w").pack(fill="x", padx=8, pady=(6, 0))
            tk.Label(r, text=desc, bg=PANEL2, fg=DIM, font=self.F(8), wraplength=px(640), justify="left").pack(anchor="w", padx=30, pady=(0, 6))
        frozen = getattr(sys, "frozen", False)
        exe_var = tk.BooleanVar(value=True)
        if frozen:
            tk.Checkbutton(d, text=" ALSO DELETE THIS PROGRAM (the launcher .exe) on FULL UNINSTALL", variable=exe_var, bg=PANEL, fg=TEXT,
                           selectcolor=BG, activebackground=PANEL, activeforeground=CYAN, font=self.F(8, True), highlightthickness=0,
                           bd=0, anchor="w").pack(fill="x", padx=16, pady=(6, 0))
        def run(keys, full):
            if full:
                t = simpledialog.askstring("Full uninstall", "This permanently deletes EVERYTHING the launcher created:\nsettings, library, emulators and their saves/BIOS/firmware, slots and backups.\n(Your game files are not touched.)\n\nType UNINSTALL to confirm:", parent=d)
                if (t or "").strip().upper() != "UNINSTALL": return
                targets = [home]
            else:
                if not keys: return messagebox.showinfo("Nothing selected", "Tick at least one item.", parent=d)
                names = ", ".join(t for k, t, *_ in items if k in keys)
                if not messagebox.askyesno("Delete", f"Permanently delete:\n{names}\n\nThis cannot be undone.", parent=d): return
                targets = [q for k, _, _, paths, _ in items if k in keys for q in paths]
            left = [str(q) for q in targets if not safe_delete(q, home)]
            if not full and "emus" in keys and "settings" not in keys:
                self.cfg["emulators"] = {k: v for k, v in self.cfg["emulators"].items() if not str(v).startswith(str(EMU_HOME))}
                save_cfg(self.cfg)
            if left:
                messagebox.showwarning("Some items are in use", "Couldn't delete (close any emulator that is open, then try again):\n" + "\n".join(left), parent=d)
            if full:
                if frozen and exe_var.get():
                    subprocess.Popen(f'cmd /c ping -n 4 127.0.0.1 >nul & del /f /q "{sys.executable}"', shell=True,
                                     creationflags=0x08000000 if os.name == "nt" else 0)
                messagebox.showinfo("Uninstalled", "The launcher's data has been removed. The launcher will now close.", parent=d)
                self.destroy()
            else:
                self.restart_app()
        self.button(foot, "FULL UNINSTALL (EVERYTHING)", lambda: run(set(), True)).pack(side="left")
        self.button(foot, "CANCEL", d.destroy).pack(side="right", padx=(6, 0))
        self.button(foot, "DELETE SELECTED", lambda: run({k for k, v in vars_.items() if v.get()}, False), accent=True).pack(side="right")

    # ---- controllers window -----------------------------------------------------------------
    def controllers_dialog(self):
        d = tk.Toplevel(self, bg=PANEL, highlightthickness=1, highlightbackground=ORANGE)
        d.title("CONTROLLERS"); d.transient(self)
        sh = self.winfo_screenheight()
        d.geometry(f"{px(760)}x{min(px(720), sh - 80)}+{self.winfo_x() + px(100)}+{self.winfo_y() + px(20)}")
        tk.Label(d, text="\u25a0 CONTROLLERS", bg=PANEL, fg=ORANGE, font=self.F(13, True)).pack(anchor="w", padx=16, pady=(14, 0))
        tk.Label(d, text="Live check of your pads, plus one-click access to each emulator's own controller settings.",
                 bg=PANEL, fg=DIM, font=self.F(9)).pack(anchor="w", padx=16, pady=(0, 8))
        box = tk.Frame(d, bg=PANEL2, highlightthickness=1, highlightbackground=LINE); box.pack(fill="x", padx=16, pady=4)
        tk.Label(box, text="DETECTED PADS (XINPUT)", bg=PANEL2, fg=DIM, font=self.F(8, True)).pack(anchor="w", padx=10, pady=(8, 2))
        pad_lbls = []
        for i in range(4):
            l = tk.Label(box, text="", bg=PANEL2, fg=TEXT, font=self.F(10, True), anchor="w"); l.pack(fill="x", padx=10, pady=1)
            pad_lbls.append(l)
        tk.Label(box, text="Xbox pads show here. DualShock 4 / DualSense appear when run through Steam Input or DS4Windows; "
                           "RPCS3 and DuckStation can also read them directly, so 'none' here doesn't always mean broken.",
                 bg=PANEL2, fg=DIM, font=self.F(8), wraplength=px(700), justify="left").pack(anchor="w", padx=10, pady=(4, 8))
        def poll():
            if not d.winfo_exists(): return
            pads = xinput_pads()
            if not pads:
                pad_lbls[0].config(text="Live detection is only available on Windows.", fg=DIM)
            for i, l in enumerate(pad_lbls):
                if pads:
                    st = pads[i]
                    l.config(text=f"PAD {i + 1}:  " + ("not detected" if st is None else st), fg=DIM if st is None else CYAN)
            d.after(150, poll)
        poll()
        for s_, em in EMULATORS.items():
            r = tk.Frame(d, bg=PANEL2, highlightthickness=1, highlightbackground=LINE); r.pack(fill="x", padx=16, pady=4)
            top = tk.Frame(r, bg=PANEL2); top.pack(fill="x", padx=10, pady=(8, 2))
            tk.Label(top, text=f"{s_}  {em['name'].upper()}", bg=PANEL2, fg=TEXT, font=self.F(10, True)).pack(side="left")
            self.button(top, "OPEN CONTROLLER SETTINGS", lambda s_=s_: self.controller_setup(s_)).pack(side="right")
            tk.Label(r, text=CONTROL_HELP[s_], bg=PANEL2, fg=DIM, font=self.F(8), wraplength=px(700), justify="left").pack(anchor="w", padx=10, pady=(0, 8))
        tk.Label(d, text="Note: RPCS3's Player 1 defaults to the keyboard, so for a controller switch the Handler in Configuration > Pads. "
                         "Controls are saved by each emulator and used for every game on that console.",
                 bg=PANEL, fg=TEXT, font=self.F(8), wraplength=px(720), justify="left").pack(anchor="w", padx=16, pady=6)
        self.button(d, "CLOSE", d.destroy).pack(side="bottom", anchor="e", padx=16, pady=12)

    # ---- RPCS3 log diagnosis window ----------------------------------------------------------
    def rpcs3_log_path(self):
        exe = self.cfg["emulators"].get("PS3")
        if not exe: return None
        base = Path(exe).parent
        return next((c for c in (base / "log" / "RPCS3.log", base / "RPCS3.log") if c.exists()), None)

    def diagnose_ps3(self, ask=False):
        if ask and not messagebox.askyesno("Game closed quickly", "The PS3 game closed or crashed soon after starting.\nLook at RPCS3's log to find out why?"):
            return
        lp = self.rpcs3_log_path()
        if not lp:
            return messagebox.showinfo("No log yet", "RPCS3 hasn't written a log yet. Launch a PS3 game first.")
        errs, tail, hints = analyze_rpcs3_log(lp.read_text(encoding="utf8", errors="replace"))
        exe = self.cfg["emulators"].get("PS3")
        free = shutil.disk_usage(Path(exe).parent).free / 1024**3 if exe else 0
        d = tk.Toplevel(self, bg=PANEL, highlightthickness=1, highlightbackground=ORANGE)
        d.title("DIAGNOSE LAST RUN"); d.transient(self)
        sh = self.winfo_screenheight()
        d.geometry(f"{px(820)}x{min(px(640), sh - 80)}+{self.winfo_x() + px(80)}+{self.winfo_y() + px(30)}")
        tk.Label(d, text="\u25a0 DIAGNOSE LAST RUN // RPCS3", bg=PANEL, fg=ORANGE, font=self.F(13, True)).pack(anchor="w", padx=16, pady=(14, 0))
        tk.Label(d, text=f"Log: {lp}   //   free disk space on RPCS3's drive: {free:.1f} GB", bg=PANEL, fg=DIM, font=self.F(8)).pack(anchor="w", padx=16, pady=(0, 6))
        foot = tk.Frame(d, bg=PANEL); foot.pack(side="bottom", fill="x", padx=16, pady=12)
        tw = tk.Frame(d, bg=PANEL); tw.pack(fill="both", expand=True, padx=16)
        t = tk.Text(tw, bg=BG, fg=TEXT, font=self.F(9), wrap="word", relief="flat", padx=10, pady=8, highlightthickness=1, highlightbackground=LINE)
        sb = ttk.Scrollbar(tw, orient="vertical", command=t.yview, style="AC.Vertical.TScrollbar"); t.configure(yscrollcommand=sb.set)
        t.tag_configure("h", foreground=ORANGE, font=self.F(9, True)); t.tag_configure("bad", foreground=RED); t.tag_configure("dim", foreground=DIM)
        t.pack(side="left", fill="both", expand=True); sb.pack(side="right", fill="y")
        report = []
        def add(txt, tag=None): t.insert("end", txt + "\n", tag); report.append(txt)
        add("LIKELY CAUSES", "h")
        for h in hints: add("\u2022 " + h)
        if not hints: add("No known problem pattern found. Send the lines below (COPY REPORT) to get it looked at.", "dim")
        add("\nERRORS IN THE LOG (most frequent first)", "h")
        for line, n in errs: add(f"[{n}x] {line}", "bad")
        if not errs: add("None. If the screen is black with no errors, the game may still be compiling (first launch takes several minutes) or waiting at a prompt.", "dim")
        add("\nLAST LINES OF THE LOG", "h")
        for line in tail: add(line[:220], "dim")
        t.config(state="disabled")
        def copy():
            self.clipboard_clear(); self.clipboard_append("\n".join(report)); self.typewrite("REPORT COPIED TO CLIPBOARD", 0)
        self.button(foot, "COPY REPORT", copy, accent=True).pack(side="left")
        self.button(foot, "OPEN FULL LOG", lambda: self.open_log("PS3")).pack(side="left", padx=6)
        self.button(foot, "CLOSE", d.destroy).pack(side="right")

    # ---- Armored Core VI (Steam) ---------------------------------------------------------------
    def play_steam(self, k):
        e = self.cfg["library"][k]
        try:
            os.startfile(k) if os.name == "nt" else spawn(["xdg-open", k])
        except OSError as ex:
            return messagebox.showerror("Steam", f"Couldn't start Steam: {ex}")
        self.running = True; self.led.config(fg=WARN)
        self.music_suspend()
        self.status.config(text=f"\u25b6 STARTING VIA STEAM: {e['title'].upper()}", fg=WARN)
        self.iconify()
        self.after(3000, lambda: self.watch_steam(k, time.time(), None))

    def watch_steam(self, k, launched, seen_at):
        up = proc_running("ArmoredCore6.exe")
        if up and seen_at is None: seen_at = time.time()
        if up or (seen_at is None and time.time() - launched < 180):
            return self.after(3000, lambda: self.watch_steam(k, launched, seen_at))
        e = self.cfg["library"][k]
        if seen_at: e["playtime"] += time.time() - seen_at; e["last"] = time.time()
        save_cfg(self.cfg); self.running = False
        self.deiconify(); self.status.config(fg=TEXT); self.refresh(); self.music_resume()
        self.typewrite("SORTIE COMPLETE ... WELCOME BACK, 621", 0)

    def steam_card(self):
        info = find_steam_game(AC6_APPID, self.cfg.get("steam_path"))
        card = tk.Frame(self.check_body, bg=PANEL2, highlightthickness=1, highlightbackground=LINE); card.pack(fill="x", pady=4)
        r = tk.Frame(card, bg=PANEL2); r.pack(fill="x", padx=10, pady=8)
        tk.Label(r, text="PC  STEAM: ARMORED CORE VI", bg=PANEL2, fg=TEXT, font=self.F(11, True)).pack(side="left")
        tk.Label(r, text="FOUND" if info else "NOT FOUND", bg=PANEL2, fg=CYAN if info else RED, font=self.F(9, True)).pack(side="left", padx=12)
        self.button(r, "LOCATE STEAM FOLDER", self.locate_steam).pack(side="right")

    def locate_steam(self):
        d = filedialog.askdirectory(title="Select your Steam folder (or the Steam library folder Armored Core VI is installed in)")
        if not d: return
        self.cfg["steam_path"] = d; save_cfg(self.cfg)
        if find_steam_game(AC6_APPID, d):
            self.rescan(); messagebox.showinfo("Steam", "Armored Core VI found and added to your library.")
        else:
            messagebox.showwarning("Not found", "Couldn't find Armored Core VI there. Install it in Steam, or choose the Steam library folder it's installed in.")
        self.refresh_check()

    def restore_pending(self):
        snap = self.cfg.pop("pending_restore", None)
        if snap:
            restore_settings(snap); save_cfg(self.cfg)

    # ---- soundtracks tab -----------------------------------------------------------------------
    def build_soundtracks(self, center):
        a = self.panel(center, "SOUNDTRACKS // THE SOUND OF ARMORED CORE"); self.tab_frames["SOUNDTRACKS"] = a
        row = tk.Frame(a, bg=PANEL); row.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.ost_tree = ttk.Treeview(row, show="tree", style="AC.Treeview", selectmode="browse")
        self.ost_tree.column("#0", width=px(300))
        self.ost_tree.insert("", "end", iid="__overview", text="00  SERIES SOUND OVERVIEW")
        for i, t in enumerate(SOUNDTRACKS, 1):
            self.ost_tree.insert("", "end", iid=t[0], text=f"{i:02d}  {t[1]}")
        self.ost_tree.pack(side="left", fill="y")
        view = tk.Frame(row, bg=PANEL); view.pack(side="left", fill="both", expand=True, padx=(12, 0))
        self.ost_title = tk.Label(view, bg=PANEL, fg=TEXT, font=self.F(14, True), anchor="w", justify="left", wraplength=px(560)); self.ost_title.pack(fill="x")
        self.ost_meta = tk.Label(view, bg=PANEL, fg=ORANGE, font=self.F(9, True), anchor="w", justify="left", wraplength=px(560)); self.ost_meta.pack(fill="x", pady=(2, 8))
        bt = tk.Frame(view, bg=PANEL); bt.pack(fill="x", pady=(0, 8))
        self.button(bt, "\u25b6 LISTEN (YOUTUBE SEARCH)", self.open_track, accent=True).pack(side="left")
        self.button(bt, "ABOUT KOTA HOSHINO", lambda: webbrowser.open("https://en.wikipedia.org/wiki/Kota_Hoshino")).pack(side="left", padx=6)
        tw = tk.Frame(view, bg=PANEL); tw.pack(fill="both", expand=True)
        self.ost_text = tk.Text(tw, bg=BG, fg=TEXT, font=self.F(10), wrap="word", relief="flat", padx=12, pady=10,
                                highlightthickness=1, highlightbackground=LINE, state="disabled", cursor="arrow")
        self.ost_text.tag_configure("h", foreground=ORANGE, font=self.F(10, True))
        self.ost_text.pack(fill="both", expand=True)
        self.ost_tree.bind("<<TreeviewSelect>>", self.render_track)
        self.ost_tree.selection_set("__overview")

    def render_track(self, *_):
        sel = self.ost_tree.selection(); k = sel[0] if sel else "__overview"
        self.ost_sel = k
        t = self.ost_text; t.config(state="normal"); t.delete("1.0", "end")
        if k == "__overview":
            self.ost_title.config(text="THE SOUND OF ARMORED CORE"); self.ost_meta.config(text="COMPOSERS // FREQUENCY // ERAS")
            t.insert("end", OST_OVERVIEW)
        else:
            _, title, game, credit, desc, _q = next(x for x in SOUNDTRACKS if x[0] == k)
            self.ost_title.config(text=title); self.ost_meta.config(text=f"{game}\nCREDIT: {credit}")
            t.insert("end", "WHY IT'S LOVED\n", "h"); t.insert("end", desc + "\n\n")
            t.insert("end", "Opinions on 'best' differ; these are tracks fans and reviewers name often.", "h")
        t.config(state="disabled")

    def open_track(self):
        k = getattr(self, "ost_sel", "__overview")
        q = "Armored Core soundtrack" if k == "__overview" else next(x[5] for x in SOUNDTRACKS if x[0] == k)
        webbrowser.open("https://www.youtube.com/results?search_query=" + urllib.parse.quote(q))

    # ---- shared widget helper ---------------------------------------------------------------------
    def entry(self, parent, var, width, **kw):
        return tk.Entry(parent, textvariable=var, width=width, bg=BG, fg=CYAN, insertbackground=CYAN, relief="flat",
                        font=self.F(10), highlightthickness=1, highlightbackground=LINE, highlightcolor=ORANGE, **kw)

    def on_close(self):
        try:
            if self.mus: self.mus.close()
            save_cfg(self.cfg)
        finally:
            self.destroy()

    # ---- RetroAchievements tab ---------------------------------------------------------------------
    def ra_creds(self):
        r = self.cfg.get("ra") or {}
        return r.get("user", "").strip(), r.get("key", "").strip()

    def ra_thread(self, kind, fn, *args):
        def work():
            try: self.msgs.put(("ra", kind, fn(*args), None))
            except Exception as ex:
                log(f"ra {kind}: {ex!r}"); self.msgs.put(("ra", kind, None, str(ex)))
        threading.Thread(target=work, daemon=True).start()

    def build_achievements(self, center):
        a = self.panel(center, "RETROACHIEVEMENTS // ACHIEVEMENTS & LEADERBOARDS"); self.tab_frames["ACHIEVEMENTS"] = a
        u, k = self.ra_creds()
        top = tk.Frame(a, bg=PANEL); top.pack(fill="x", padx=10, pady=(0, 4))
        tk.Label(top, text="USER", bg=PANEL, fg=DIM, font=self.F(8, True)).pack(side="left")
        self.ra_user = tk.StringVar(value=u); self.entry(top, self.ra_user, 14).pack(side="left", padx=(4, 10), ipady=3)
        tk.Label(top, text="WEB API KEY", bg=PANEL, fg=DIM, font=self.F(8, True)).pack(side="left")
        self.ra_key = tk.StringVar(value=k); self.entry(top, self.ra_key, 22, show="\u2022").pack(side="left", padx=(4, 10), ipady=3)
        self.button(top, "CONNECT", self.ra_connect, accent=True).pack(side="left")
        self.button(top, "DISCONNECT", self.ra_disconnect).pack(side="left", padx=6)
        self.button(top, "GET KEY", lambda: webbrowser.open("https://retroachievements.org/controlpanel.php")).pack(side="left")
        self.ra_status = tk.Label(a, text="", bg=PANEL, fg=DIM, font=self.F(9), anchor="w", justify="left", wraplength=px(820))
        self.ra_status.pack(fill="x", padx=12, pady=(0, 2))
        tk.Label(a, text="RetroAchievements covers PS1, PS2 and PSP games (not PS3 or PC). To EARN achievements, turn on RetroAchievements inside DuckStation, "
                         "PCSX2 or PPSSPP (Settings > Achievements) and log in there; this tab shows your progress and the leaderboards.",
                 bg=PANEL, fg=DIM, font=self.F(8), anchor="w", justify="left", wraplength=px(820)).pack(fill="x", padx=12, pady=(0, 6))
        body = tk.Frame(a, bg=PANEL); body.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.ra_games_tree = ttk.Treeview(body, columns=("con", "ach"), show="tree headings", style="AC.Treeview", selectmode="browse")
        self.ra_games_tree.heading("#0", text="ARMORED CORE SETS"); self.ra_games_tree.heading("con", text="SYS"); self.ra_games_tree.heading("ach", text="ACH")
        self.ra_games_tree.column("#0", width=px(240)); self.ra_games_tree.column("con", width=px(50), anchor="center"); self.ra_games_tree.column("ach", width=px(50), anchor="center")
        self.ra_games_tree.pack(side="left", fill="y")
        self.ra_games_tree.bind("<<TreeviewSelect>>", self.ra_pick)
        right = tk.Frame(body, bg=PANEL); right.pack(side="left", fill="both", expand=True, padx=(10, 0))
        bar = tk.Frame(right, bg=PANEL); bar.pack(fill="x")
        self.ra_tab_btns = {}
        for key, label in (("ach", "ACHIEVEMENTS"), ("lb", "LEADERBOARDS")):
            b = tk.Label(bar, text=label, padx=14, pady=5, cursor="hand2", font=self.F(9, True), highlightthickness=1, highlightbackground=LINE)
            b.pack(side="left", padx=(0, 4)); b.bind("<Button-1>", lambda e, k=key: self.ra_set_view(k)); self.ra_tab_btns[key] = b
        self.ra_summary = tk.Label(bar, text="", bg=PANEL, fg=CYAN, font=self.F(9, True)); self.ra_summary.pack(side="right")
        box = tk.Frame(right, bg=PANEL); box.pack(fill="both", expand=True, pady=(6, 0))
        self.ra_ach = ttk.Treeview(box, columns=("desc", "pts", "earned"), show="tree headings", style="AC.Treeview", selectmode="browse")
        for c, t, w in (("#0", "ACHIEVEMENT", 230), ("desc", "HOW TO UNLOCK", 320), ("pts", "PTS", 50), ("earned", "EARNED", 110)):
            self.ra_ach.heading(c, text=t); self.ra_ach.column(c, width=px(w), anchor="w" if c in ("#0", "desc") else "center")
        self.ra_ach.tag_configure("earned", foreground=CYAN); self.ra_ach.tag_configure("locked", foreground=DIM)
        self.ra_lb = ttk.Treeview(box, columns=("desc", "top", "score"), show="tree headings", style="AC.Treeview", selectmode="browse")
        for c, t, w in (("#0", "LEADERBOARD", 230), ("desc", "WHAT IT TRACKS", 280), ("top", "TOP PLAYER", 100), ("score", "TOP SCORE", 100)):
            self.ra_lb.heading(c, text=t); self.ra_lb.column(c, width=px(w), anchor="w" if c in ("#0", "desc") else "center")
        self.ra_lb.bind("<Double-1>", self.ra_open_board)
        self.ra_set_view("ach")

    def ra_set_view(self, v):
        self.ra_view = v
        for k, b in self.ra_tab_btns.items():
            on = k == v; b.config(bg=ORANGE if on else PANEL2, fg=ACC_FG if on else TEXT)
        self.ra_ach.pack_forget(); self.ra_lb.pack_forget()
        (self.ra_ach if v == "ach" else self.ra_lb).pack(fill="both", expand=True)

    def ra_open(self):
        u, k = self.ra_creds()
        if not (u and k):
            self.ra_status.config(text="Enter your RetroAchievements username and Web API key (RetroAchievements > Settings > Keys), then press CONNECT.", fg=DIM)
        elif not self.ra_ok and not self.ra_loading:
            self.ra_connect(silent=True)

    def ra_connect(self, silent=False):
        u, k = self.ra_user.get().strip(), self.ra_key.get().strip()
        if not (u and k):
            return None if silent else messagebox.showinfo("RetroAchievements", "Enter your username and Web API key first.")
        self.cfg["ra"] = {"user": u, "key": k}; save_cfg(self.cfg)
        self.ra_loading = True; self.ra_status.config(text="Connecting to RetroAchievements ...", fg=ORANGE)
        self.ra_thread("boot", ra_boot, k, u)

    def ra_disconnect(self):
        self.cfg.pop("ra", None); save_cfg(self.cfg)
        self.ra_ok = False; self.ra_games = []; self.ra_user.set(""); self.ra_key.set("")
        for t in (self.ra_games_tree, self.ra_ach, self.ra_lb): t.delete(*t.get_children())
        self.ra_summary.config(text=""); self.ra_status.config(text="Disconnected. Your key was removed from the launcher's settings.", fg=DIM)

    def ra_pick(self, *_):
        sel = self.ra_games_tree.selection()
        if not sel: return
        u, k = self.ra_creds(); self.ra_cur = int(sel[0])
        self.ra_summary.config(text="LOADING ...")
        self.ra_thread("game", ra_game, k, u, int(sel[0]))

    def ra_open_board(self, *_):
        sel = self.ra_lb.selection()
        if not sel: return
        u, k = self.ra_creds(); title = self.ra_lb.item(sel[0], "text")
        self.ra_thread("entries", ra_entries, k, u, int(sel[0]), title)

    def on_ra(self, kind, data, err):
        if kind == "boot":
            self.ra_loading = False
            if err:
                self.ra_ok = False
                return self.ra_status.config(text=f"Could not connect: {err}", fg=RED)
            prof, games = data; self.ra_ok = True; self.ra_games = games
            self.ra_status.config(text=f"Connected as {prof.get('User', '')}  //  {prof.get('TotalPoints', 0)} points  //  "
                                       f"{prof.get('TotalTruePoints', 0)} true points  //  member since {str(prof.get('MemberSince', ''))[:10]}", fg=CYAN)
            self.ra_games_tree.delete(*self.ra_games_tree.get_children())
            for g in games:
                self.ra_games_tree.insert("", "end", iid=str(g["id"]), text=g["title"], values=(g["console"], g["ach"]))
            if not games:
                self.ra_status.config(text=self.ra_status.cget("text") + "  //  No Armored Core sets found for PS1, PS2 or PSP on RetroAchievements right now.")
            elif self.ra_games_tree.get_children():
                self.ra_games_tree.selection_set(self.ra_games_tree.get_children()[0])
        elif kind == "game":
            if err: return self.ra_summary.config(text=f"ERROR: {err}"[:90])
            if data["id"] != self.ra_cur: return
            self.ra_ach.delete(*self.ra_ach.get_children()); self.ra_lb.delete(*self.ra_lb.get_children())
            todo = []
            for a in data["ach"]:
                d = a.get("DateEarnedHardcore") or a.get("DateEarned")
                iid = str(a.get("ID"))
                self.ra_ach.insert("", "end", iid=iid, text=a.get("Title", ""), tags=("earned" if d else "locked",),
                                   values=(a.get("Description", ""), a.get("Points", 0), ("\u2714 " + str(d)[:10]) if d else "-"))
                if a.get("BadgeName"): todo.append((iid, a["BadgeName"], bool(d)))
            for lb in data["lb"]:
                top = lb.get("TopEntry") or {}
                self.ra_lb.insert("", "end", iid=str(lb.get("ID")), text=lb.get("Title", ""),
                                  values=(lb.get("Description", ""), top.get("User", "-"), top.get("FormattedScore", top.get("Score", "-"))))
            self.ra_summary.config(text=f"{data['earned']}/{data['total']} earned  //  {data['pts_earned']}/{data['pts_total']} pts  //  {len(data['lb'])} leaderboards  (double-click a leaderboard)")
            if todo: self.ra_badges(todo, data["id"])
        elif kind == "badge":
            iid, path = data
            ph = self.photo(path, (px(26), px(26)))
            if ph and self.ra_ach.exists(iid): self.ra_ach.item(iid, image=ph)
        elif kind == "entries":
            if err: return messagebox.showerror("Leaderboard", err)
            d = tk.Toplevel(self, bg=PANEL, highlightthickness=1, highlightbackground=ORANGE)
            d.title("LEADERBOARD"); d.transient(self)
            d.geometry(f"{px(560)}x{px(560)}+{self.winfo_x() + px(180)}+{self.winfo_y() + px(60)}")
            tk.Label(d, text="\u25a0 " + data["title"].upper(), bg=PANEL, fg=ORANGE, font=self.F(12, True), wraplength=px(520), justify="left").pack(anchor="w", padx=16, pady=(14, 6))
            t = ttk.Treeview(d, columns=("rank", "user", "score", "date"), show="headings", style="AC.Treeview")
            for c, tx, w in (("rank", "#", 50), ("user", "PLAYER", 190), ("score", "SCORE", 120), ("date", "DATE", 110)):
                t.heading(c, text=tx); t.column(c, width=px(w), anchor="center" if c != "user" else "w")
            for r in data["rows"]:
                t.insert("", "end", values=(r.get("Rank"), r.get("User"), r.get("FormattedScore", r.get("Score")), str(r.get("DateSubmitted", ""))[:10]))
            t.pack(fill="both", expand=True, padx=16)
            self.button(d, "CLOSE", d.destroy).pack(anchor="e", padx=16, pady=12)

    def ra_badges(self, items, gid):
        def work():
            d = CACHE / "ra_badges"; d.mkdir(parents=True, exist_ok=True)
            for iid, badge, earned in items:
                name = badge + ("" if earned else "_lock"); f = d / f"{name}.png"
                try:
                    if not f.exists():
                        with http_get(f"https://media.retroachievements.org/Badge/{name}.png") as r, open(f, "wb") as fh:
                            fh.write(r.read())
                    if self.ra_cur == gid: self.msgs.put(("ra", "badge", (iid, str(f)), None))
                except Exception as ex:
                    f.unlink(missing_ok=True); log(f"ra badge {name}: {ex!r}")
        threading.Thread(target=work, daemon=True).start()

    # ---- music tab ----------------------------------------------------------------------------------
    def build_music(self, center):
        a = self.panel(center, "MUSIC // LAUNCHER AUDIO PLAYER"); self.tab_frames["MUSIC"] = a
        if not self.mus:
            tk.Label(a, text="The audio player uses Windows' built-in audio engine and isn't available on this system.", bg=PANEL, fg=DIM, font=self.F(10)).pack(padx=16, pady=20)
            return
        lcd = tk.Frame(a, bg=BG, highlightthickness=1, highlightbackground=LINE); lcd.pack(fill="x", padx=10, pady=(0, 6))
        self.lcd_title = tk.Label(lcd, text="NO TRACK LOADED", bg=BG, fg=ORANGE, font=self.F(14, True), anchor="w"); self.lcd_title.pack(fill="x", padx=12, pady=(8, 0))
        self.lcd_time = tk.Label(lcd, text="00:00 / 00:00", bg=BG, fg=CYAN, font=self.F(11, True), anchor="w"); self.lcd_time.pack(fill="x", padx=12)
        self.viz = tk.Canvas(lcd, height=px(56), bg=BG, highlightthickness=0); self.viz.pack(fill="x", padx=12, pady=6)
        self.seekbar = tk.Canvas(lcd, height=px(12), bg=PANEL2, highlightthickness=0, cursor="hand2"); self.seekbar.pack(fill="x", padx=12, pady=(0, 10))
        self.seekbar.bind("<Button-1>", self.music_seek)
        ctl = tk.Frame(a, bg=PANEL); ctl.pack(fill="x", padx=10, pady=4)
        self.button(ctl, "\u25c0\u25c0 PREV", self.music_prev).pack(side="left", padx=(0, 4))
        self.btn_play = self.button(ctl, "\u25b6 PLAY", self.music_toggle, accent=True); self.btn_play.pack(side="left", padx=4)
        self.button(ctl, "\u25a0 STOP", self.music_stop).pack(side="left", padx=4)
        self.button(ctl, "NEXT \u25b6\u25b6", lambda: self.music_next(False)).pack(side="left", padx=4)
        self.btn_loop = self.button(ctl, "", self.music_cycle_loop); self.btn_loop.pack(side="left", padx=(14, 4))
        self.btn_shuf = self.button(ctl, "", self.music_toggle_shuffle); self.btn_shuf.pack(side="left", padx=4)
        tk.Label(ctl, text="VOL", bg=PANEL, fg=DIM, font=self.F(8, True)).pack(side="left", padx=(14, 2))
        self.vol = tk.IntVar(value=self.cfg.get("music_vol", 70))
        tk.Scale(ctl, from_=0, to=100, orient="horizontal", variable=self.vol, showvalue=0, length=px(120), bg=PANEL, fg=TEXT,
                 troughcolor=PANEL2, highlightthickness=0, bd=0, activebackground=ORANGE, command=self.music_volume).pack(side="left")
        self.music_paint_toggles()
        lst = tk.Frame(a, bg=PANEL); lst.pack(fill="both", expand=True, padx=10, pady=(6, 4))
        self.music_tree = ttk.Treeview(lst, columns=("type",), show="tree headings", style="AC.Treeview", selectmode="extended")
        self.music_tree.heading("#0", text="PLAYLIST"); self.music_tree.heading("type", text="TYPE")
        self.music_tree.column("#0", width=px(560)); self.music_tree.column("type", width=px(70), anchor="center")
        sb = ttk.Scrollbar(lst, orient="vertical", command=self.music_tree.yview, style="AC.Vertical.TScrollbar")
        self.music_tree.configure(yscrollcommand=sb.set)
        self.music_tree.pack(side="left", fill="both", expand=True); sb.pack(side="right", fill="y")
        self.music_tree.bind("<Double-1>", lambda e: self.music_play_selected())
        foot = tk.Frame(a, bg=PANEL); foot.pack(fill="x", padx=10, pady=(0, 10))
        self.button(foot, "+ ADD FILES", self.music_add_files).pack(side="left", padx=(0, 4))
        self.button(foot, "+ ADD FOLDER", self.music_add_folder).pack(side="left", padx=4)
        self.button(foot, "REMOVE", self.music_remove).pack(side="left", padx=4)
        self.button(foot, "CLEAR", self.music_clear).pack(side="left", padx=4)
        self.copy_var = tk.BooleanVar(value=self.cfg.get("music_copy", True))
        tk.Checkbutton(foot, text=" COPY INTO LAUNCHER", variable=self.copy_var, command=lambda: self.set_opt("music_copy", self.copy_var.get()),
                       bg=PANEL, fg=TEXT, selectcolor=BG, activebackground=PANEL, activeforeground=CYAN, font=self.F(8, True),
                       highlightthickness=0, bd=0).pack(side="right")
        self.music_refresh_list()

    def music_paint_toggles(self):
        self.btn_loop.config(text="LOOP: " + ("OFF", "ALL", "ONE")[self.mus_loop])
        self.btn_shuf.config(text="SHUFFLE: " + ("ON" if self.mus_shuffle else "OFF"))

    def music_refresh_list(self):
        self.music_tree.delete(*self.music_tree.get_children())
        for i, p in enumerate(self.music):
            mark = "\u25b6 " if i == self.mus_idx and self.mus_state != "stopped" else ""
            self.music_tree.insert("", "end", iid=str(i), text=f"{mark}{i + 1:02d}  {Path(p).stem}", values=(Path(p).suffix[1:].upper(),))

    def music_add(self, paths):
        added = 0
        for p in paths:
            src = Path(p)
            if src.suffix.lower() not in AUDIO_EXTS or not src.is_file(): continue
            if self.copy_var.get() and src.resolve().parent != MUSIC_DIR.resolve():
                MUSIC_DIR.mkdir(parents=True, exist_ok=True)
                dest = MUSIC_DIR / src.name
                if not dest.exists() or dest.stat().st_size != src.stat().st_size:
                    i = 1
                    while dest.exists(): dest = MUSIC_DIR / f"{src.stem} ({i}){src.suffix}"; i += 1
                    shutil.copy2(src, dest)
                src = dest
            if str(src) not in self.music: self.music.append(str(src)); added += 1
        self.cfg["playlist"] = self.music; save_cfg(self.cfg); self.music_refresh_list()
        self.typewrite(f"{added} TRACK(S) ADDED", 0)

    def music_add_files(self):
        exts = " ".join("*" + e for e in sorted(AUDIO_EXTS))
        self.music_add(filedialog.askopenfilenames(title="Choose music files", filetypes=[("Audio", exts), ("All files", "*.*")]))

    def music_add_folder(self):
        d = filedialog.askdirectory(title="Choose a folder of music")
        if d: self.music_add(sorted(str(f) for f in Path(d).rglob("*") if f.suffix.lower() in AUDIO_EXTS))

    def music_remove(self):
        gone = {int(i) for i in self.music_tree.selection()}
        if not gone: return
        cur = self.music[self.mus_idx] if 0 <= self.mus_idx < len(self.music) else None
        self.music = [p for i, p in enumerate(self.music) if i not in gone]
        self.mus_idx = self.music.index(cur) if cur in self.music else -1
        if cur is None or self.mus_idx < 0: self.music_stop()
        self.cfg["playlist"] = self.music; save_cfg(self.cfg); self.music_refresh_list()

    def music_clear(self):
        self.music_stop(); self.music = []; self.mus_idx = -1; self.cfg["playlist"] = []; save_cfg(self.cfg); self.music_refresh_list()

    def music_play_selected(self):
        sel = self.music_tree.selection()
        if sel: self.music_play_index(int(sel[0]))

    def music_play_index(self, i):
        if not (0 <= i < len(self.music)): return
        try:
            self.mus.load(self.music[i]); self.mus.volume(self.vol.get()); self.mus.play()
        except Exception as ex:
            self.mus_state = "stopped"; self.btn_play.config(text="\u25b6 PLAY")
            return self.typewrite(f"CAN'T PLAY {Path(self.music[i]).name}: {ex}"[:100], 0)
        self.mus_idx, self.mus_state, self.mus_started = i, "playing", time.time()
        try: self.mus_len = self.mus.length()
        except Exception: self.mus_len = 0
        self.mus_hist.append(i)
        self.lcd_title.config(text=Path(self.music[i]).stem.upper()[:60])
        self.btn_play.config(text="\u275a\u275a PAUSE"); self.music_refresh_list()

    def music_toggle(self):
        if self.mus_state == "playing":
            self.mus.pause(); self.mus_state = "paused"; self.btn_play.config(text="\u25b6 PLAY")
        elif self.mus_state == "paused":
            self.mus.resume(); self.mus_state = "playing"; self.btn_play.config(text="\u275a\u275a PAUSE")
        else:
            sel = self.music_tree.selection()
            self.music_play_index(int(sel[0]) if sel else (self.mus_idx if self.mus_idx >= 0 else 0))

    def music_stop(self):
        if not self.mus: return
        try:
            if self.mus.is_open: self.mus.stop()
        except Exception: pass
        self.mus_state = "stopped"; self.mus_count = 0
        if hasattr(self, "btn_play"): self.btn_play.config(text="\u25b6 PLAY"); self.music_refresh_list()

    def music_next(self, auto=False):
        if auto: self.mus_count += 1
        else: self.mus_count = 0
        i = next_track(self.mus_idx, len(self.music), self.mus_loop, self.mus_shuffle, auto, self.mus_count)
        if i is None: return self.music_stop()
        self.music_play_index(i)

    def music_prev(self):
        try:
            if self.mus_state != "stopped" and self.mus.pos() > 3000: return self.music_play_index(self.mus_idx)
        except Exception: pass
        if len(self.mus_hist) > 1:
            self.mus_hist.pop(); self.music_play_index(self.mus_hist.pop())
        elif self.music:
            self.music_play_index((self.mus_idx - 1) % len(self.music))

    def music_cycle_loop(self):
        self.mus_loop = (self.mus_loop + 1) % 3; self.cfg["music_loop"] = self.mus_loop; save_cfg(self.cfg); self.music_paint_toggles()

    def music_toggle_shuffle(self):
        self.mus_shuffle = not self.mus_shuffle; self.cfg["music_shuffle"] = self.mus_shuffle; save_cfg(self.cfg); self.music_paint_toggles()

    def music_volume(self, v):
        self.cfg["music_vol"] = int(float(v))
        if self.mus and self.mus.is_open: self.mus.volume(int(float(v)))

    def music_seek(self, e):
        if self.mus_state not in ("playing", "paused") or self.mus_len <= 0: return
        try:
            self.mus.seek(e.x / max(1, self.seekbar.winfo_width()) * self.mus_len)
            self.mus_state = "playing"; self.btn_play.config(text="\u275a\u275a PAUSE")
        except Exception: pass

    def music_suspend(self):   # quiet the player while a game runs
        if self.mus and self.mus_state == "playing":
            try: self.mus.pause(); self.mus_state = "paused"; self.mus_was_playing = True
            except Exception: pass

    def music_resume(self):
        if self.mus and self.mus_was_playing and self.mus_state == "paused":
            try: self.mus.resume(); self.mus_state = "playing"
            except Exception: pass
        self.mus_was_playing = False

    def music_tick(self):
        if self.mus and hasattr(self, "viz"):
            try:
                if self.mus_state == "playing":
                    if time.time() - self.mus_started > 1.0 and self.mus.mode() == "stopped":
                        self.music_next(auto=True)
                    else:
                        pos = self.mus.pos(); self.mus_len = self.mus_len or self.mus.length()
                        self.lcd_time.config(text=f"{fmt_ms(pos)} / {fmt_ms(self.mus_len)}")
                        if self.cur_tab == "MUSIC":
                            w, h = self.seekbar.winfo_width(), self.seekbar.winfo_height()
                            self.seekbar.delete("all")
                            self.seekbar.create_rectangle(0, 0, w * pos / max(1, self.mus_len), h, fill=ORANGE, outline="")
            except Exception:
                pass
            if self.cur_tab == "MUSIC": self.draw_viz()
        self.after(150, self.music_tick)

    def draw_viz(self):   # decorative equaliser bars (not a real spectrum analyser)
        c = self.viz; c.delete("all"); w, h = c.winfo_width(), c.winfo_height()
        n = len(self.viz_h); bw = max(3, w // n)
        for i in range(n):
            target = random.random() ** 0.7 if self.mus_state == "playing" else 0.04
            self.viz_h[i] = self.viz_h[i] * 0.55 + target * 0.45
            bh = max(2, int(self.viz_h[i] * (h - 4))); x = i * bw
            c.create_rectangle(x + 1, h - bh, x + bw - 2, h, fill=ORANGE, outline="")
            c.create_rectangle(x + 1, h - bh, x + bw - 2, h - bh + max(2, int(2 * SC)), fill=CYAN, outline="")

    def set_emulators(self):
        for sys_, em in EMULATORS.items():
            cur = self.cfg["emulators"].get(sys_, "unset")
            p = filedialog.askopenfilename(title=f"{em['name']} executable for {sys_}  (Cancel keeps: {cur})")
            if p: self.cfg["emulators"][sys_] = p
        save_cfg(self.cfg); self.show_detail()
        self.typewrite("EMULATOR PATHS UPDATED", 0)

    def open_emu_dir(self):
        k = self.selected()
        if k and self.cfg["library"][k]["system"] == "PC":
            d = self.cfg["library"][k].get("dir")
            if d: os.startfile(d) if os.name == "nt" else spawn(["xdg-open", d])
            return
        exe = k and self.cfg["emulators"].get(self.cfg["library"][k]["system"])
        if exe:
            d = str(Path(exe).parent)
            os.startfile(d) if os.name == "nt" else subprocess.Popen(["xdg-open", d])

    def extra_args(self):
        k = self.selected()
        if not k: return
        d = tk.Toplevel(self, bg=PANEL, highlightthickness=1, highlightbackground=ORANGE)
        d.title("EXTRA ARGS"); d.transient(self); d.grab_set()
        d.geometry(f"+{self.winfo_x() + 350}+{self.winfo_y() + 260}")
        tk.Label(d, text="\u25a0 EXTRA COMMAND-LINE ARGS FOR THIS FRAME", bg=PANEL, fg=ORANGE, font=self.F(10, True)).pack(padx=20, pady=(16, 8))
        v = tk.StringVar(value=self.cfg["library"][k]["args"])
        tk.Entry(d, textvariable=v, width=48, bg=BG, fg=CYAN, insertbackground=CYAN, relief="flat", font=self.F(10),
                 highlightthickness=1, highlightbackground=LINE, highlightcolor=ORANGE).pack(padx=20, ipady=4)
        def ok():
            self.cfg["library"][k]["args"] = v.get(); save_cfg(self.cfg); d.destroy()
        self.button(d, "CONFIRM", ok, accent=True).pack(padx=20, pady=14, fill="x")

    def bios_help(self):
        messagebox.showinfo("BIOS / FIRMWARE - SUPPLY YOUR OWN",
                            "\n".join(f"{s}: {t}" for s, t in BIOS_HINTS.items()))

    # ---- launch --------------------------------------------------------------
    def play(self):
        k = self.selected()
        if not k or self.running: return
        e = self.cfg["library"][k]
        if e["system"] == "PC": return self.play_steam(k)
        exe = self.cfg["emulators"].get(e["system"])
        if not exe or not Path(exe).exists():
            nm = EMULATORS[e["system"]]["name"]
            if messagebox.askyesno("Emulator not installed", f"{nm} isn't installed yet.\nDownload the official build now?"):
                self.install([e["system"]], then=self.play)
            return
        o = self.opts_for(k)
        if o.get("res") == "auto": o["res"] = auto_scale(e["system"], self.winfo_screenheight())   # match the display
        snap = []
        try:
            if not apply_settings(e["system"], exe, o, snap):
                self.typewrite("RUN THE EMULATOR ONCE SO IT CREATES ITS CONFIG - SETTINGS NOT APPLIED YET", 0)
        except Exception as ex:
            log(f"apply settings {e['title']}: {ex!r}")
        self.cfg["pending_restore"] = snap; save_cfg(self.cfg)
        if e["system"] == "PS3" and not self.cfg.get("ps3_notice"):
            messagebox.showinfo("First PS3 launch", "RPCS3 compiles the game's code the first time you play it. This can take several minutes, and the screen may stay black or show a progress bar. Don't close it; later launches are much faster.")
            self.cfg["ps3_notice"] = True; save_cfg(self.cfg)
        if e["system"] == "PS3":
            tid = self.ps3_tid(k, ask=False); seen = self.cfg.setdefault("ps3_updates", {})
            if tid and tid not in seen:
                seen[tid] = "asked"; save_cfg(self.cfg)
                if messagebox.askyesno("Game update", f"Check Sony's servers for the official {e['title']} update and install it now?\n(Recommended: some games need it to run properly.)"):
                    self.restore_pending()
                    return self.ps3_update(k)
        cmd = EMULATORS[e["system"]]["args"](exe, k, self.fs.get())
        if e["args"]: cmd[1:1] = e["args"].split()
        self.cfg["fullscreen"] = self.fs.get()
        try:
            proc = spawn(cmd, cwd=str(Path(exe).parent), env=clean_env())
        except OSError as ex:
            self.restore_pending()
            return messagebox.showerror("Launch failed", str(ex))
        self.running = True; self.led.config(fg=ORANGE)
        self.music_suspend()
        self.status.config(text=f"\u25b6 IN SORTIE: {e['title'].upper()}", fg=ORANGE)
        self.iconify()
        start = time.time()
        self.after(1000, lambda: self.wait(proc, k, start))

    def wait(self, proc, k, start):
        if proc.poll() is None:
            return self.after(1000, lambda: self.wait(proc, k, start))
        e = self.cfg["library"][k]
        e["playtime"] += time.time() - start; e["last"] = time.time()
        self.restore_pending(); save_cfg(self.cfg); self.running = False
        self.deiconify(); self.status.config(fg=TEXT); self.refresh(); self.music_resume()
        self.typewrite("SORTIE COMPLETE ... WELCOME BACK, RAVEN", 0)
        if e["system"] == "PS3" and time.time() - start < 150:   # closed quickly: probably a problem
            self.after(500, lambda: self.diagnose_ps3(ask=True))


if __name__ == "__main__":
    apply_theme(load_cfg().get("theme", "WHITE GLINT"))
    App().mainloop()
