"""e10test.py — E10 rig for Claude Code working method + edit method.

E10 adds six mechanical features to the agent engine:

1. Read-before-edit enforcement: edit_file FAILS unless the same
   job record shows a file_read of that exact file earlier in the job.

2. Surgical edit_file tool: edit_file(path, old_text, new_text) —
   exact-match replacement; FAILS if old_text missing or non-unique
   (count reported); no whole-file rewrites for small changes.

3. search_text and list_files tools: search_text(pattern, glob?) +
   list_files(glob?) over the job workspace (grep/glob equivalents).

4. run_command tool: sandboxed to job workspace.

5. Verify-after-edit evidence gate: extending E6/E8 evidence
   verification so the auto-close gate checks that edits are verified.

6. Plan record: stored on job record with status reads from record only.

SCRIPTED FAKE BRAIN, temp dirs only — no model, no network.

Run: python3 e10test.py   (exit 1 on any failure)
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

for _v in ("http_proxy", "https_proxy", "all_proxy",
           "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
           "no_proxy", "NO_PROXY",
           "WORKER_URL", "RUNNER_KEY", "JOB"):
    os.environ.pop(_v, None)

import agent_loop
import tools_registry
import workspace_tools

PASS = []
FAIL = []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("PASS " if cond else "FAIL ") + name +
          (f" — {detail}" if detail and not cond else ""))


class FakeBrain:
    """Scripted brain: pops the next action per call and remembers
    every history it was shown."""

    def __init__(self, script):
        self.script = list(script)
        self.histories = []

    def __call__(self, goal, history, tools, observation=None):
        self.histories.append([dict(h) for h in history])
        if self.script:
            return self.script.pop(0)
        return {"action": "fail", "reason": "script exhausted"}


def no_stop():
    return False


# ------------------------------------------------------------ fixtures
BASE = tempfile.mkdtemp(prefix="e10-rig-")
ROOT = os.path.join(BASE, "ws")
os.makedirs(ROOT)

# A test file to work with
TEST_FILE = (
    "def hello():\n"
    "    print('hello world')\n"
    "\n"
    "def greet(name):\n"
    "    print(f'hello {name}')\n"
    "\n"
    "if __name__ == '__main__':\n"
    "    hello()\n"
)
with open(os.path.join(ROOT, "test.py"), "w") as f:
    f.write(TEST_FILE)

# Another file for multi-file tests
with open(os.path.join(ROOT, "data.txt"), "w") as f:
    f.write("line 1\nline 2\nline 3\n")

# A CSV for compute tools
ORDERS = (
    "id,product,amount_inr,status\n"
    "1,Notebook,450,completed\n"
    "2,Pen Set,250,pending\n"
    "3,Backpack,1800,completed\n"
    "4,Water Bottle,650,cancelled\n"
    "5,Notebook,450,completed\n"
    "6,Desk Lamp,1250,completed\n"
    "7,Pen Set,250,completed\n"
    "8,Backpack,1800,pending\n"
    "9,Headphones,2400,completed\n"
    "10,Water Bottle,650,completed\n"
    "11,Desk Lamp,1250,cancelled\n"
    "12,Headphones,2400,completed\n"
    "13,Notebook,900,completed\n"
    "14,Pen Set,300,pending\n"
    "15,Keyboard,2100,completed\n"
)
with open(os.path.join(ROOT, "orders.csv"), "w") as f:
    f.write(ORDERS)

FILT = {"column": "status", "equals": "completed"}


def full_registry(job_record=None):
    reg = tools_registry.default_registry()
    tools_registry.register_workspace_tools(reg, ROOT, job_record=job_record)
    tools_registry.register_compute_tools(reg, ROOT)
    tools_registry.register_plan_tool(reg, job_record)
    return reg


def tool_run(reg, name, args):
    for d in reg.as_tools():
        if d["name"] == name:
            return d["run"](args)
    raise AssertionError(f"tool {name} not registered")


# Create a job record for read-before-edit tracking
job_record = {}

reg = full_registry(job_record=job_record)

# ===================================================================
# 1. READ-BEFORE-EDIT ENFORCEMENT
# ===================================================================
print("\n=== 1. READ-BEFORE-EDIT ENFORCEMENT ===")

# First: edit without read should FAIL
ok, res = tool_run(reg, "edit_file", {
    "path": "test.py",
    "old_text": "print('hello world')",
    "new_text": "print('hello universe')"
})
check("1a) edit_file without prior file_read FAILS",
      not ok and "REFUSED" in res and "file_read" in res, str(res))

# Now read the file
ok, res = tool_run(reg, "file_read", {"path": "test.py"})
check("1b) file_read succeeds", ok, str(res))

# Now edit should work
ok, res = tool_run(reg, "edit_file", {
    "path": "test.py",
    "old_text": "print('hello world')",
    "new_text": "print('hello universe')"
})
check("1c) edit_file after file_read SUCCEEDS", ok, str(res))

# Verify the edit
ok, res = tool_run(reg, "file_read", {"path": "test.py"})
check("1d) file_read shows the edit", ok and "hello universe" in res, str(res))

# Edit without read on a different file should still fail
ok, res = tool_run(reg, "edit_file", {
    "path": "data.txt",
    "old_text": "line 1",
    "new_text": "LINE 1"
})
check("1e) edit_file on different file without read FAILS",
      not ok and "REFUSED" in res and "file_read" in res, str(res))

# Read data.txt then edit
ok, res = tool_run(reg, "file_read", {"path": "data.txt"})
ok, res = tool_run(reg, "edit_file", {
    "path": "data.txt",
    "old_text": "line 1",
    "new_text": "LINE 1"
})
check("1f) edit_file after reading data.txt SUCCEEDS", ok, str(res))

# ===================================================================
# 2. SURGICAL EDIT_FILE TOOL
# ===================================================================
print("\n=== 2. SURGICAL EDIT_FILE TOOL ===")

# Test exact match requirement (case sensitive)
ok, res = tool_run(reg, "file_read", {"path": "test.py"})
ok, res = tool_run(reg, "edit_file", {
    "path": "test.py",
    "old_text": "PRINT('hello universe')",  # wrong case
    "new_text": "print('hello')"
})
check("2a) edit_file case-sensitive exact match FAILS on wrong case",
      not ok and "not found" in res, str(res))

# Test unique match requirement (old_text must match exactly once)
# Add a duplicate line
ok, res = tool_run(reg, "file_read", {"path": "data.txt"})
ok, res = tool_run(reg, "edit_file", {
    "path": "data.txt",
    "old_text": "LINE 1\n",
    "new_text": "LINE ONE\n"
})
check("2b) edit_file unique match requirement - first edit succeeds", ok, str(res))

# Now there's still "line 2\nline 3\n" - let's add another duplicate
with open(os.path.join(ROOT, "dup.txt"), "w") as f:
    f.write("foo\nfoo\nbar\n")

reg2 = full_registry(job_record=job_record)

ok, res = tool_run(reg2, "file_read", {"path": "dup.txt"})
ok, res = tool_run(reg2, "edit_file", {
    "path": "dup.txt",
    "old_text": "foo\n",
    "new_text": "FOO\n"
})
check("2c) edit_file FAILS when old_text matches multiple times",
      not ok and "matches 2 times" in res, str(res))

# Test empty old_text
ok, res = tool_run(reg2, "file_read", {"path": "dup.txt"})
ok, res = tool_run(reg2, "edit_file", {
    "path": "dup.txt",
    "old_text": "",
    "new_text": "test"
})
check("2d) edit_file FAILS on empty old_text",
      not ok and "old_text must not be empty" in res, str(res))

# Test successful unique edit
with open(os.path.join(ROOT, "unique.txt"), "w") as f:
    f.write("unique content here\n")

reg3 = full_registry(job_record=job_record)
ok, res = tool_run(reg3, "file_read", {"path": "unique.txt"})
ok, res = tool_run(reg3, "edit_file", {
    "path": "unique.txt",
    "old_text": "unique content here\n",
    "new_text": "changed content\n"
})
check("2e) edit_file succeeds with unique exact match", ok, str(res))

# Verify the change
ok, res = tool_run(reg3, "file_read", {"path": "unique.txt"})
check("2f) edit_file change verified", ok and "changed content" in res, str(res))

# ===================================================================
# 3. SEARCH_TEXT TOOL
# ===================================================================
print("\n=== 3. SEARCH_TEXT TOOL ===")

reg4 = full_registry(job_record=job_record)

# Search for a pattern
ok, res = tool_run(reg4, "search_text", {"pattern": "hello"})
check("3a) search_text finds 'hello' in test.py",
      ok and "hello" in res.lower() and "test.py" in res, str(res))

# Search with glob
ok, res = tool_run(reg4, "search_text", {"pattern": "line", "glob": "*.txt"})
check("3b) search_text with glob finds 'line' in data.txt",
      ok and "line" in res.lower() and "data.txt" in res, str(res))

# Search for non-existent pattern
ok, res = tool_run(reg4, "search_text", {"pattern": "nonexistent_xyz"})
check("3c) search_text returns no-match message",
      ok and "no matches" in res.lower(), str(res))

# Invalid regex
ok, res = tool_run(reg4, "search_text", {"pattern": "[invalid"})
check("3d) search_text FAILS on invalid regex",
      not ok and "invalid regex" in res.lower(), str(res))

# Empty pattern
ok, res = tool_run(reg4, "search_text", {"pattern": ""})
check("3e) search_text FAILS on empty pattern",
      not ok and "pattern must not be empty" in res, str(res))

# ===================================================================
# 4. LIST_FILES TOOL
# ===================================================================
print("\n=== 4. LIST_FILES TOOL ===")

reg5 = full_registry(job_record=job_record)

# List all files
ok, res = tool_run(reg5, "list_files", {})
check("4a) list_files shows all files",
      ok and "test.py" in res and "data.txt" in res and "orders.csv" in res, str(res))

# List with glob
ok, res = tool_run(reg5, "list_files", {"glob": "*.py"})
check("4b) list_files with *.py glob shows only .py files",
      ok and "test.py" in res and "data.txt" not in res, str(res))

# List with glob for txt
ok, res = tool_run(reg5, "list_files", {"glob": "*.txt"})
check("4c) list_files with *.txt glob shows only .txt files",
      ok and "data.txt" in res and "test.py" not in res, str(res))

# ===================================================================
# 5. RUN_COMMAND TOOL
# ===================================================================
print("\n=== 5. RUN_COMMAND TOOL ===")

reg6 = full_registry(job_record=job_record)

# Run a simple command
ok, res = tool_run(reg6, "run_command", {"cmd": "echo hello world"})
check("5a) run_command executes echo",
      ok and "hello world" in res, str(res))

# Run command with list form
ok, res = tool_run(reg6, "run_command", {"cmd": ["echo", "from", "list"]})
check("5b) run_command executes list-form command",
      ok and "from list" in res, str(res))

# Run command that fails
ok, res = tool_run(reg6, "run_command", {"cmd": "false"})
check("5c) run_command reports non-zero exit",
      not ok and "exit 1" in res, str(res))

# Run command with timeout
ok, res = tool_run(reg6, "run_command", {"cmd": "sleep 10", "timeout": 1})
check("5d) run_command respects timeout",
      not ok and "timed out" in res.lower(), str(res))

# Run python to test
ok, res = tool_run(reg6, "run_command", {"cmd": "python3 -c \"print(2+2)\""})
check("5e) run_command can run python",
      ok and "4" in res, str(res))

# ===================================================================
# 6. VERIFY-AFTER-EDIT EVIDENCE GATE (extends E6/E8)
# ===================================================================
print("\n=== 6. VERIFY-AFTER-EDIT EVIDENCE GATE ===")

# Test that auto-close requires verify after edit
reg7 = full_registry(job_record=job_record)

# Create a fresh test file
with open(os.path.join(ROOT, "verify_test.py"), "w") as f:
    f.write("x = 1\n")

job7 = {"evidence": [
    {"tool": "edit_file", "contains": "verify_test.py"},
    {"tool": "verify_file_contains", "args": {"path": "verify_test.py", "contains": ["x = 2"]}}
]}

tools_d = reg7.as_tools()
entries_d = []
brain_d = FakeBrain([
    # Read the file
    {"action": "tool", "tool": "file_read",
     "args": {"path": "verify_test.py"}},
    # Edit it
    {"action": "tool", "tool": "edit_file",
     "args": {"path": "verify_test.py",
              "old_text": "x = 1\n",
              "new_text": "x = 2\n"}},
    # Verify it
    {"action": "tool", "tool": "verify_file_contains",
     "args": {"path": "verify_test.py", "contains": ["x = 2"]}},
])

status, out = agent_loop.run_loop(
    "edit verify_test.py to change x=1 to x=2 and verify",
    tools_d, brain=brain_d, record=entries_d.append,
    stop=no_stop, allow=True, evidence=job7["evidence"],
    job=job7)

check("6a) loop auto-closes after edit + verify",
      status == "done" and "auto-closed" in out, f"{status} {out}")

# Verify the evidence was satisfied
edit_steps = [e for e in entries_d if e.get("tool") == "edit_file"]
verify_steps = [e for e in entries_d if e.get("tool") == "verify_file_contains"]
check("6b) edit_file step recorded OK",
      len(edit_steps) == 1 and edit_steps[0]["ok"] is True, str(edit_steps))
check("6c) verify_file_contains step recorded OK",
      len(verify_steps) == 1 and verify_steps[0]["ok"] is True, str(verify_steps))

# ===================================================================
# 7. PLAN RECORD
# ===================================================================
print("\n=== 7. PLAN RECORD ===")

# Test that job_state reads plan from job record
job_with_plan = {
    "task": "test plan",
    "plan": ["step 1: read file", "step 2: edit file", "step 3: verify"]
}

# job_state calls fetch_job_state() which needs the Worker channel;
# monkeypatch it to return our test job record.
_orig_fetch = agent_loop.fetch_job_state
agent_loop.fetch_job_state = lambda: job_with_plan
try:
    reg8 = full_registry(job_record=job_record)
    ok, res = tool_run(reg8, "job_state", {})
    check("7a) job_state shows plan from job record",
          ok and "plan" in res.lower() and "step 1" in res, str(res))
finally:
    agent_loop.fetch_job_state = _orig_fetch

# ===================================================================
# 8. FULL INTEGRATION TEST
# ===================================================================
print("\n=== 8. FULL INTEGRATION TEST ===")

# A complete workflow: search -> list -> read -> edit -> verify -> run_command
with open(os.path.join(ROOT, "main.py"), "w") as f:
    f.write(
        "def calculate(a, b):\n"
        "    return a + b\n"
        "\n"
        "def main():\n"
        "    print(calculate(1, 2))\n"
        "\n"
        "if __name__ == '__main__':\n"
        "    main()\n"
    )

job8 = {"evidence": [
    {"tool": "search_text", "contains": "calculate"},
    {"tool": "edit_file", "contains": "main.py"},
    {"tool": "verify_file_contains", "args": {"path": "main.py", "contains": ["a * b"]}},
    {"tool": "run_command", "contains": "2"}
]}

reg9 = full_registry(job_record={})
tools_d = reg9.as_tools()
entries_d = []
brain_d = FakeBrain([
    # Search for calculate
    {"action": "tool", "tool": "search_text",
     "args": {"pattern": "calculate"}},
    # Read main.py
    {"action": "tool", "tool": "file_read",
     "args": {"path": "main.py"}},
    # Edit calculate to multiply
    {"action": "tool", "tool": "edit_file",
     "args": {"path": "main.py",
              "old_text": "    return a + b\n",
              "new_text": "    return a * b\n"}},
    # Verify the edit
    {"action": "tool", "tool": "verify_file_contains",
     "args": {"path": "main.py", "contains": ["a * b"]}},
    # Run the file
    {"action": "tool", "tool": "run_command",
     "args": {"cmd": "python3 main.py"}},
])

status, out = agent_loop.run_loop(
    "find calculate, change + to *, verify, run",
    tools_d, brain=brain_d, record=entries_d.append,
    stop=no_stop, allow=True, evidence=job8["evidence"],
    job=job8)

check("8a) full integration auto-closes",
      status == "done" and "auto-closed" in out, f"{status} {out}")

# Check all required tools ran
search_steps = [e for e in entries_d if e.get("tool") == "search_text"]
edit_steps = [e for e in entries_d if e.get("tool") == "edit_file"]
verify_steps = [e for e in entries_d if e.get("tool") == "verify_file_contains"]
run_steps = [e for e in entries_d if e.get("tool") == "run_command"]

check("8b) search_text ran", len(search_steps) == 1 and search_steps[0]["ok"], str(search_steps))
check("8c) edit_file ran", len(edit_steps) == 1 and edit_steps[0]["ok"], str(edit_steps))
check("8d) verify_file_contains ran", len(verify_steps) == 1 and verify_steps[0]["ok"], str(verify_steps))
check("8e) run_command ran", len(run_steps) == 1 and run_steps[0]["ok"], str(run_steps))

# Verify output shows 2 (1*2)
check("8f) run_command output shows correct result",
      any("2" in str(e.get("result", "")) for e in run_steps), str(run_steps))

# ===================================================================
# 9. GATE: DONE REJECTED WITHOUT POST-EDIT VERIFY (divya additions —
# the brief's rig bar: edit -> claim done -> gate rejects -> verify
# -> done accepted/auto-closed; and run_command counts as verify)
# ===================================================================
print("\n=== 9. GATE REJECTION + RUN_COMMAND VERIFY ===")

with open(os.path.join(ROOT, "gate_test.txt"), "w") as f:
    f.write("alpha\n")

reg10 = full_registry(job_record={})
job9 = {}
evidence9 = [{"tool": "edit_file", "contains": "gate_test.txt"}]
entries9 = []
brain9 = FakeBrain([
    {"action": "tool", "tool": "file_read",
     "args": {"path": "gate_test.txt"}},
    {"action": "tool", "tool": "edit_file",
     "args": {"path": "gate_test.txt",
              "old_text": "alpha\n", "new_text": "beta\n"}},
    {"action": "done", "answer": "edited gate_test.txt"},
    {"action": "tool", "tool": "run_command",
     "args": {"cmd": "grep -c beta gate_test.txt"}},
])
status, out = agent_loop.run_loop(
    "edit gate_test.txt, claim done unverified, then verify by command",
    reg10.as_tools(), brain=brain9, record=entries9.append,
    stop=no_stop, allow=True, evidence=evidence9, job=job9)

check("9a) run ends done (auto-closed) after the run_command verify",
      status == "done" and "auto-closed" in out, f"{status} {out}")
_rej = [e for e in entries9 if e.get("tool") == "verify" and not e.get("ok")]
check("9b) the unverified done claim was rejected by the E10 gate",
      len(_rej) == 1 and "verify-after-edit" in str(_rej[0].get("result")),
      str(_rej))
_run = [e for e in entries9 if e.get("tool") == "run_command"]
check("9c) rejection recorded before the run_command step",
      bool(_rej and _run) and entries9.index(_rej[0]) < entries9.index(_run[0]),
      str(entries9))
with open(os.path.join(ROOT, "gate_test.txt")) as f:
    check("9d) gate_test.txt on disk carries the edit",
          f.read() == "beta\n")

# ===================================================================
# 10. SET_PLAN TOOL + PLAN PERSISTENCE ACROSS KILL+RESUME
# (divya additions — item 6's write side and the brief's rig bar)
# ===================================================================
print("\n=== 10. SET_PLAN + KILL/RESUME PERSISTENCE ===")

PLAN1 = [{"title": "read the file", "status": "in_progress"},
         {"title": "edit it", "status": "pending"},
         {"title": "verify it", "status": "pending"}]
job10a = {}
reg11 = full_registry(job_record=job10a)
entries10a = []
brain10a = FakeBrain([
    {"action": "tool", "tool": "set_plan", "args": {"steps": PLAN1}},
    # script exhausts here -> FakeBrain fails the run: the runner
    # "dies" with only the record (entries + job dict) surviving.
])
status, out = agent_loop.run_loop(
    "plan then die", reg11.as_tools(), brain=brain10a,
    record=entries10a.append, stop=no_stop, allow=True, job=job10a)
check("10a) set_plan stored the normalized plan on the job record",
      job10a.get("plan") == PLAN1, str(job10a.get("plan")))
_sp = [e for e in entries10a if e.get("tool") == "set_plan"]
check("10b) set_plan step recorded OK (the record carries the plan)",
      len(_sp) == 1 and _sp[0]["ok"] is True, str(_sp))

# job_state read-back from a record holding ONLY steps (no plan key)
_orig_fetch = agent_loop.fetch_job_state
agent_loop.fetch_job_state = lambda: {
    "state": "running", "provider": "agent", "steps": entries10a}
try:
    ok, res = tool_run(reg11, "job_state", {})
    check("10c) job_state reconstructs the plan from recorded steps",
          ok and "[in_progress] read the file" in res, str(res))
finally:
    agent_loop.fetch_job_state = _orig_fetch

# Resume with a FRESH job dict: the loop restores the plan from seed
job10b = {}
reg11b = full_registry(job_record=job10b)
entries10b = []
brain10b = FakeBrain([
    {"action": "tool", "tool": "echo", "args": {"text": "resumed"}},
])
status, out = agent_loop.run_loop(
    "resumed run", reg11b.as_tools(), brain=brain10b,
    record=entries10b.append, stop=no_stop, allow=True, job=job10b,
    seed_history=agent_loop.build_resume_history(entries10a),
    step_offset=len(entries10a))
check("10d) resumed loop restored the plan onto the fresh job record",
      job10b.get("plan") == PLAN1, str(job10b.get("plan")))

# ...and the resumed brain can update it
PLAN2 = [{"title": "read the file", "status": "done"},
         {"title": "edit it", "status": "in_progress"},
         {"title": "verify it", "status": "pending"}]
job10c = {"plan": [dict(p) for p in PLAN1]}
reg11c = full_registry(job_record=job10c)
entries10c = []
brain10c = FakeBrain([
    {"action": "tool", "tool": "set_plan", "args": {"steps": PLAN2}},
    {"action": "done", "answer": "plan updated"},
])
status, out = agent_loop.run_loop(
    "update the plan", reg11c.as_tools(), brain=brain10c,
    record=entries10c.append, stop=no_stop, allow=True, job=job10c,
    seed_history=agent_loop.build_resume_history(entries10a),
    step_offset=len(entries10a))
check("10e) resumed brain updated the plan (statuses move)",
      status == "done" and job10c.get("plan") == PLAN2,
      f"{status} {job10c.get('plan')}")

# set_plan validation: a bad status is a FAILED step, plan untouched
job10d = {}
reg11d = full_registry(job_record=job10d)
entries10d = []
brain10d = FakeBrain([
    {"action": "tool", "tool": "set_plan",
     "args": {"steps": [{"title": "x", "status": "bogus"}]}},
    {"action": "tool", "tool": "set_plan",
     "args": {"steps": [{"title": "only step", "status": "pending"}]}},
    {"action": "done", "answer": "ok"},
])
status, out = agent_loop.run_loop(
    "plan validation", reg11d.as_tools(), brain=brain10d,
    record=entries10d.append, stop=no_stop, allow=True, job=job10d)
_spd = [e for e in entries10d if e.get("tool") == "set_plan"]
check("10f) bad-status set_plan FAILED, good one OK, plan holds the good one",
      len(_spd) == 2 and _spd[0]["ok"] is False and _spd[1]["ok"] is True
      and job10d.get("plan") == [{"title": "only step", "status": "pending"}],
      str(_spd))

print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("FAILED:", "; ".join(FAIL))
sys.exit(1 if FAIL else 0)