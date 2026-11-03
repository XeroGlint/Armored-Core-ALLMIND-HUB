"""The --selftest mode used by CI to smoke-test the packaged exe: opens the window, checks the icon, exits 0."""
import os, subprocess, sys, tempfile, pathlib
root = pathlib.Path(__file__).resolve().parent.parent
out = pathlib.Path(tempfile.mkdtemp()) / "selftest.txt"
env = dict(os.environ, HOME=tempfile.mkdtemp(), USERPROFILE=tempfile.mkdtemp())
r = subprocess.run([sys.executable, str(root / "ac_launcher.py"), "--selftest", str(out)], env=env, capture_output=True, text=True, timeout=120)
text = out.read_text() if out.exists() else ""
ok = r.returncode == 0 and "ok=True" in text and "icon=True" in text
print(("PASS " if ok else "FAIL ") + "--selftest opens the window, loads the icon and exits 0" + ("" if ok else f"  [{text.strip()} {r.stderr[-200:]}]"))
sys.exit(0 if ok else 1)
