"""
Adjudication experiment for RED4-02: simulate a CHZ-SURF-01-class regression
by monkeypatching chuzom.tool_surface in-process (no files touched), then
verify whether tool_surface.unregistered() catches it (it should — that's
its job) and whether chuzom doctor's health verdict is affected (per RED-4's
claim, it should NOT be, because doctor never calls tool_surface at all for
verification purposes).
"""
import os, sys, io, contextlib

os.environ["HOME"] = "/tmp/adj-sandbox-3"
sys.path.insert(0, "src")

from chuzom import tool_surface as ts

# Simulate the exact bug class CHZ-SURF-01 was: an emitter learns to name a
# new logical tool, but nobody adds a DEPRECATED_TOOLS mapping or registers
# it in any tier -> resolution silently falls through to the tier floor
# (still "works" per resolve()'s total-function guarantee) OR, if we also
# remove it from KNOWN/EMITTABLE bookkeeping, resolve() would raise. Simplest
# faithful repro: add a brand-new emittable name that has NO deprecated-door
# mapping and isn't registered anywhere except we forget to add the mapping.

ts.EMITTABLE_TOOLS = ts.EMITTABLE_TOOLS | frozenset({"llm_totally_new_tool"})
# Deliberately do NOT add "llm_totally_new_tool" to DEPRECATED_TOOLS or any
# tier's registered set -- this is precisely "a future emitter invents an
# unroutable name" per unregistered()'s own docstring.

bad = ts.unregistered(slim="consolidated")
print("=== tool_surface.unregistered(slim='consolidated') after simulated regression ===")
print(bad)
assert "llm_totally_new_tool" in bad, "expected the guard function itself to catch this"
print("CONFIRMED: tool_surface.unregistered() DOES detect the simulated regression (as designed).")

print()
print("=== Now running chuzom doctor's _run_doctor() in the SAME broken process ===")
from chuzom.commands import doctor as doctor_mod

buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    exit_code, issues = doctor_mod._run_doctor(host=None)

out = buf.getvalue()
print(f"--- issues list returned by _run_doctor(): {issues} ---")
print(out[-4000:])
print(f"--- doctor exit_code captured: {exit_code} ---")
if "tool_surface" in out.lower() or "unroutable" in out.lower() or "llm_totally_new_tool" in out:
    print("DOCTOR SURFACED THE REGRESSION IN ITS OUTPUT.")
else:
    print("DOCTOR OUTPUT DOES NOT MENTION THE REGRESSION AT ALL.")
