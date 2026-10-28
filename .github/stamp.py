"""Writes the commit hash into ac_launcher.py so the app can tell whether a newer build exists."""
import os, pathlib

p = pathlib.Path("ac_launcher.py")
s = p.read_text(encoding="utf8")
t = s.replace('BUILD_ID = "dev"', f'BUILD_ID = "{os.environ["GITHUB_SHA"]}"', 1)
assert s != t, "BUILD_ID marker not found"
p.write_text(t, encoding="utf8")
print("stamped", os.environ["GITHUB_SHA"])
