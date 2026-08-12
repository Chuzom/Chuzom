"""RED3 reproduction (mandate item 4 -- context propagation): a milestone whose
description was written BY THE PLANNER BEFORE any execution happened cannot
possibly encode a fact that only becomes known DURING execution of an earlier
milestone (e.g. the exact symbol/variable/path name an executor chose among
several valid options). TaskLedger.frozen_context() DOES carry each frozen
milestone's full `artifacts` dict forward (ledger.py L108-130) -- but
adapters.pack_prompt(), the ONLY function that turns frozen_context() into
the text actually sent to an executing model (used by BOTH CodexAdapter and
ReActAgent), renders just:

    f"  - [{c.get('id')}] {c.get('description') or c.get('id')}"

for every completed milestone (adapters.py L65-68) -- description only, never
`c.get('artifacts')`. So any execution-time decision made in an earlier
milestone (which file/symbol name was actually used, what a discovered value
was, etc.) is invisible to every later milestone's executor, even though the
ledger has it sitting right there.

Concrete scenario: milestone 1's task deliberately leaves a naming decision
open ("create a settings module"). The tier-1 agent picks the name `SETTINGS`
(it could equally have picked `CONFIG`, `APP_SETTINGS`, etc. -- this is a
genuine execution-time decision, not something the planner could have written
into milestone 1's description in advance). Milestone 3 needs to import that
EXACT name. We show milestone 3's actual rendered prompt (via the real,
unmodified pack_prompt()) does not contain "SETTINGS" anywhere, even though
`ledger.milestones[0].artifacts["diff"]` -- and frozen_context()'s own
`artifacts` field -- have it.

Run with: <WORKTREE>/.venv-audit/bin/python repro_context_propagation_artifacts_lost.py
"""
import sys

sys.path.insert(0, "src")

from chuzom.agentic.adapters import pack_prompt
from chuzom.agentic.ledger import TaskLedger, Milestone
from chuzom.agentic.acceptance import canary_check

# Milestone 1: planner cannot know in advance what name the executor will pick.
m1 = Milestone(
    id="create-settings-module",
    description="Create a settings module exposing the app's configuration as a dict.",
    acceptance=canary_check("noop"),
)
# Milestone 3 semantically DEPENDS on the exact symbol milestone 1's executor chose.
m3 = Milestone(
    id="wire-settings-into-main",
    description="In main.py, import the settings dict created in milestone "
                 "'create-settings-module' and print it at startup.",
    acceptance=canary_check("noop"),
)

ledger = TaskLedger(goal="build app with settings", milestones=[m1, m3])

# Simulate milestone 1 having ALREADY been executed and frozen -- exactly what
# MGEEEngine._work_milestone() -> ledger.freeze() does on a passing acceptance
# check. The executor's real, concrete decision lives in these artifacts:
ledger.freeze(
    m1,
    tier=1,
    artifacts={
        "provider": "codex",
        "output": "Created config.py exposing SETTINGS as the app configuration dict.",
        "diff": (
            "diff --git a/config.py b/config.py\n"
            "+++ b/config.py\n"
            "+SETTINGS = {\n"
            "+    'debug': False,\n"
            "+    'db_url': 'sqlite:///app.db',\n"
            "+}\n"
        ),
        "files": ["config.py"],
    },
)

# This is the EXACT data structure the engine hands to milestone 3's agent:
frozen = ledger.frozen_context()
print("=== frozen_context() entry for the completed milestone (ledger DOES retain artifacts) ===")
completed_entry = [c for c in frozen if c["id"] == "create-settings-module"][0]
print("id:", completed_entry["id"])
print("description:", completed_entry["description"])
print("artifacts keys present:", list(completed_entry["artifacts"].keys()))
print("artifacts['diff'] contains 'SETTINGS':", "SETTINGS" in completed_entry["artifacts"]["diff"])
print()

# This is the ACTUAL PROMPT TEXT milestone 3's agent receives -- the same
# pack_prompt() used verbatim by both CodexAdapter.run() (adapters.py L121)
# and ReActAgent.run() (react.py L183).
prompt_for_m3 = pack_prompt(m3, frozen)
print("=== actual prompt text sent to milestone 3's executor (real pack_prompt()) ===")
print(prompt_for_m3)
print("=== end prompt ===")
print()

assert "SETTINGS" in completed_entry["artifacts"]["diff"], "sanity: the ledger DOES have the fact"
assert "SETTINGS" not in prompt_for_m3, (
    "expected the concrete symbol name to be ABSENT from the rendered prompt"
)
print(
    ">>> PROVEN: the ledger retains milestone 1's full artifacts (including the "
    "diff that names the exact symbol 'SETTINGS'), but pack_prompt() -- the ONLY "
    "code path that turns frozen_context() into what a delegated executor "
    "actually reads -- renders JUST the planner-authored description for every "
    "completed milestone, never its artifacts/diff/output. Milestone 3's "
    "executor is asked to 'import the settings dict created in milestone "
    "create-settings-module' with NO WAY to know the dict is named SETTINGS "
    "(vs CONFIG, APP_SETTINGS, or anything else) short of independently "
    "re-reading the repo itself. Any multi-milestone plan where a later "
    "milestone depends on a concrete, execution-time-decided fact from an "
    "earlier one has NO guaranteed prompt-level path for that fact to survive -- "
    "the executor either has to rediscover it (only possible if it has "
    "filesystem tool access, e.g. tier-0 ReAct's read_file, and only if it "
    "thinks to look; CodexAdapter with cwd=None can't even do that reliably, "
    "see the separate cwd-wiring finding) or it silently guesses wrong."
)
