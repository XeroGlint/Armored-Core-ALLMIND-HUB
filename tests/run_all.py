"""Runs every smoke test (each in its own process). Needs a display: on Linux use  xvfb-run -a python3 tests/run_all.py
The small-screen test is separate:  xvfb-run -a -s "-screen 0 1024x640x24" python3 tests/test_08_small_screen.py"""
import pathlib, subprocess, sys
here = pathlib.Path(__file__).resolve().parent
failed = 0
for t in sorted(p for p in here.glob("test_*.py") if "small_screen" not in p.name):
    r = subprocess.run([sys.executable, str(t)], capture_output=True, text=True, timeout=300)
    lines = [l for l in r.stdout.splitlines() if l.startswith(("PASS", "FAIL"))]
    bad = [l for l in lines if l.startswith("FAIL")]
    print(f"{'OK  ' if r.returncode == 0 and not bad else 'FAIL'} {t.name}: {len(lines) - len(bad)} passed, {len(bad)} failed")
    for l in bad: print("     " + l)
    if r.returncode != 0 and not bad: print("     " + (r.stdout + r.stderr)[-600:])
    failed += (r.returncode != 0) or bool(bad)
print("ALL TESTS PASSED" if not failed else f"{failed} test file(s) failed")
sys.exit(1 if failed else 0)
