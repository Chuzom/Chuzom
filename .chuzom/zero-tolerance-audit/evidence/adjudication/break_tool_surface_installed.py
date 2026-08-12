"""
Same experiment as break_tool_surface.py but against a FULLY INSTALLED
sandbox, so doctor's baseline verdict is "healthy" before we inject the
live tool_surface regression -- isolating whether the regression itself
moves the needle on doctor's verdict.
"""
import os, sys, io, contextlib

os.environ["HOME"] = "/tmp/adj-sandbox-4"
sys.path.insert(0, "src")

sys.argv = ["chuzom", "install"]
from chuzom.cli import main as cli_main
try:
    cli_main()
except SystemExit:
    pass

print("\n=== BASELINE doctor (nothing broken yet) ===")
from chuzom.commands import doctor as doctor_mod
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    exit_code_before, issues_before = doctor_mod._run_doctor(host=None)
print(f"baseline exit_code={exit_code_before} issues={issues_before}")

print("\n=== Injecting CHZ-SURF-01-class regression via tool_surface monkeypatch ===")
from chuzom import tool_surface as ts
ts.EMITTABLE_TOOLS = ts.EMITTABLE_TOOLS | frozenset({"llm_totally_new_tool"})
bad = ts.unregistered(slim="consolidated")
print(f"tool_surface.unregistered() now reports: {bad}")
assert bad, "regression injection failed"

print("\n=== doctor AGAIN, same process, regression LIVE ===")
buf2 = io.StringIO()
with contextlib.redirect_stdout(buf2):
    exit_code_after, issues_after = doctor_mod._run_doctor(host=None)
print(f"after-regression exit_code={exit_code_after} issues={issues_after}")

print("\n=== VERDICT ===")
if exit_code_before == exit_code_after and issues_before == issues_after:
    print("CONFIRMED: doctor's verdict is BYTE-FOR-BYTE IDENTICAL before and after "
          "injecting a live, real tool_surface.unregistered()-detectable regression. "
          "Doctor cannot see this class of bug.")
else:
    print("doctor's verdict CHANGED after the regression -- RED4-02 would be weakened.")
    print(f"before: {issues_before}")
    print(f"after:  {issues_after}")
