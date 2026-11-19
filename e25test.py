"""e25test.py — E2.5 rig for workspace_tools.py (workspace file tools).

Drives agent_loop.run_loop with tools taken from a Registry that has
the workspace tools registered against a TEMP workspace root, plus
direct registry-level calls for the confinement proofs. SCRIPTED
FAKE BRAIN (no model), local temp dirs only — no live external
calls, nothing outside the temp tree is ever a valid target.

Cases (the E2.5 acceptance gate):
  (0) registry contract: file_* entries registered with proper
      schemas/descriptions, stub=False; reads read-only, writes
      mutating + needs_allow.
  (a) round trip through the registry + agent loop with a scripted
      brain: write -> read -> append -> list all succeed in order
      and the on-disk content is exactly what the tools reported.
  (b) confinement: ../ escapes, absolute paths outside the root,
      and symlinks (file and dir) pointing out are ALL refused as
      FAILED steps; nothing is created or read outside the root.
      An absolute path INSIDE the root still works (positive
      control — the check is confinement, not a ban on absolutes).
  (c) the E2 Allow gate applies to the writes: file_write without
      Allow is REFUSED (handler never runs, no file on disk); with
      Allow it executes.
  (d) caps and binary handling: a binary file read is refused with
      the reason; an oversize text file reads back capped with a
      truncation note; an oversize write is refused and creates
      nothing.

Run: python3 e25test.py   (exit 1 on any failure)
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Hermetic rig (e2test pattern): clear egress-proxy env vars so
# nothing imported transitively can mangle local behaviour.
for _v in ("http_proxy", "https_proxy", "all_proxy",
           "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
           "no_proxy", "NO_PROXY"):
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
    """Scripted brain (e2test pattern): pops the next action per
    call and remembers every (history, tools) it was shown."""

    def __init__(self, script):
        self.script = list(script)
        self.histories = []
        self.offered = []

    def __call__(self, goal, history, tools, observation=None):
        self.histories.append([dict(h) for h in history])
        self.offered.append([(t["name"], t.get("desc", "")) for t in tools])
        if self.script:
            return self.script.pop(0)
        return {"action": "fail", "reason": "script exhausted"}


def recorder():
    entries = []
    return entries, entries.append


def no_stop():
    return False


# ------------------------------------------------------------ fixtures
BASE = tempfile.mkdtemp(prefix="e25-rig-")
ROOT = os.path.join(BASE, "ws")            # the job workspace root
OUTSIDE = os.path.join(BASE, "outside")    # a dir OUTSIDE the root
os.makedirs(ROOT)
os.makedirs(OUTSIDE)
SECRET = os.path.join(OUTSIDE, "secret.txt")
with open(SECRET, "w") as f:
    f.write("outside secret — must never be read via the tools")
BASE_SECRET = os.path.join(BASE, "base-secret.txt")   # ../ from root
with open(BASE_SECRET, "w") as f:
    f.write("base secret")


def ws_registry():
    reg = tools_registry.default_registry()
    tools_registry.register_workspace_tools(reg, ROOT)
    return reg


def tool_run(reg, name, args):
    """Run one tool through the registry's as_tools() contract."""
    for d in reg.as_tools():
        if d["name"] == name:
            return d["run"](args)
    raise AssertionError(f"tool {name} not registered")


# ------------------------------------------------------- (0) contract
reg = ws_registry()
check("(0) file tools registered after the default set",
      reg.names() == ["noop", "echo", "job_state", "file_list",
                      "file_read", "file_write", "file_append",
                      "edit_file", "search_text", "list_files",
                      "run_command"],
      str(reg.names()))
cls = {n: (reg.get(n)["mutating"], reg.get(n)["needs_allow"],
           reg.get(n)["stub"]) for n in reg.names()
       if n.startswith("file_")}
check("(0) reads read-only, writes mutating+Allow, none stubbed",
      cls == {"file_list": (False, False, False),
              "file_read": (False, False, False),
              "file_write": (True, True, False),
              "file_append": (True, True, False)}, str(cls))
check("(0) every file tool carries a desc + arg schema",
      all(reg.get(n)["desc"] and isinstance(reg.get(n)["schema"], dict)
          for n in cls))
check("(0) file_read/write schemas require path (write also content)",
      reg.get("file_read")["schema"]["path"]["required"] is True
      and reg.get("file_write")["schema"]["path"]["required"] is True
      and reg.get("file_write")["schema"]["content"]["required"] is True)
check("(0) brain_list offers the file tools to the brain",
      [d["name"] for d in reg.brain_list()][-8:] ==
      ["file_list", "file_read", "file_write", "file_append",
       "edit_file", "search_text", "list_files", "run_command"])

# ------------------------------------------- (a) round trip via the loop
entries, record = recorder()
brain = FakeBrain([
    {"action": "tool", "tool": "file_write",
     "args": {"path": "notes/a.txt", "content": "hello"}},
    {"action": "tool", "tool": "file_read",
     "args": {"path": "notes/a.txt"}},
    {"action": "tool", "tool": "file_append",
     "args": {"path": "notes/a.txt", "content": " world"}},
    {"action": "tool", "tool": "file_read",
     "args": {"path": "notes/a.txt"}},
    {"action": "tool", "tool": "file_list", "args": {}},
    {"action": "done", "answer": "round trip complete"},
])
status, out = agent_loop.run_loop("write, read, append, list",
                                  reg.as_tools(), brain=brain,
                                  record=record, stop=no_stop,
                                  allow=True)
seq = [(e["tool"], e["ok"]) for e in entries]
check("(a) round-trip task completes at done", status == "done", status)
check("(a) steps recorded in order, all ok",
      seq[:5] == [("file_write", True), ("file_read", True),
                  ("file_append", True), ("file_read", True),
                  ("file_list", True)], str(seq))
check("(a) first read returns exactly what was written",
      entries[1]["result"] == "hello", repr(entries[1]["result"]))
check("(a) second read returns the appended content",
      entries[3]["result"] == "hello world", repr(entries[3]["result"]))
check("(a) list shows the notes dir at the root",
      "notes/" in entries[4]["result"], entries[4]["result"])
with open(os.path.join(ROOT, "notes", "a.txt")) as f:
    on_disk = f.read()
check("(a) on-disk content matches the tool reports",
      on_disk == "hello world", repr(on_disk))

# ------------------------------------------------------- (b) confinement
ok, res = tool_run(reg, "file_read", {"path": "../base-secret.txt"})
check("(b) ../ read refused as a FAILED step",
      ok is False and "REFUSED" in res and "escapes" in res, res)
ok, res = tool_run(reg, "file_write",
                   {"path": "../evil.txt", "content": "x"})
check("(b) ../ write refused", ok is False and "REFUSED" in res, res)
check("(b) nothing created outside via ../",
      not os.path.exists(os.path.join(BASE, "evil.txt")))
ok, res = tool_run(reg, "file_append",
                   {"path": "../../evil2.txt", "content": "x"})
check("(b) ../../ append refused", ok is False and "REFUSED" in res, res)
ok, res = tool_run(reg, "file_read", {"path": SECRET})
check("(b) absolute path outside the root refused (read)",
      ok is False and "REFUSED" in res, res)
evil_abs = os.path.join(OUTSIDE, "evil-abs.txt")
ok, res = tool_run(reg, "file_write",
                   {"path": evil_abs, "content": "x"})
check("(b) absolute path outside the root refused (write)",
      ok is False and "REFUSED" in res, res)
check("(b) nothing created at the absolute outside path",
      not os.path.exists(evil_abs))

os.symlink(SECRET, os.path.join(ROOT, "link.txt"))
ok, res = tool_run(reg, "file_read", {"path": "link.txt"})
check("(b) symlink file pointing out refused (read)",
      ok is False and "REFUSED" in res, res)
os.symlink(OUTSIDE, os.path.join(ROOT, "linkdir"))
ok, res = tool_run(reg, "file_write",
                   {"path": "linkdir/evil.txt", "content": "x"})
check("(b) write through a symlinked dir pointing out refused",
      ok is False and "REFUSED" in res, res)
check("(b) nothing created in the outside dir via the symlink",
      not os.path.exists(os.path.join(OUTSIDE, "evil.txt")))
ok, res = tool_run(reg, "file_list", {"path": "linkdir"})
check("(b) list through a symlinked dir pointing out refused",
      ok is False and "REFUSED" in res, res)

inside_abs = os.path.join(ROOT, "notes", "a.txt")
ok, res = tool_run(reg, "file_read", {"path": inside_abs})
check("(b) positive control: absolute path INSIDE the root works",
      ok is True and res == "hello world", repr(res))
with open(SECRET) as f:
    check("(b) outside secret untouched on disk",
          f.read().startswith("outside secret"))

# --------------------------------------------------------- (c) Allow gate
entries, record = recorder()
brain = FakeBrain([
    {"action": "tool", "tool": "file_write",
     "args": {"path": "gated.txt", "content": "must not land"}},
    {"action": "done", "answer": "write was refused, stopping"},
])
status, out = agent_loop.run_loop("write without allow", reg.as_tools(),
                                  brain=brain, record=record,
                                  stop=no_stop)
ref = [e for e in entries if e["tool"] == "file_write"]
check("(c) un-Allowed file_write recorded as FAILED step",
      len(ref) == 1 and ref[0]["ok"] is False
      and "REFUSED" in ref[0]["result"], str(entries))
check("(c) refusal fed back to the brain as FAILED history",
      any("FAILED" in h.get("result", "") and "REFUSED" in h["result"]
          for h in brain.histories[1]), str(brain.histories))
check("(c) handler never ran — no file on disk",
      not os.path.exists(os.path.join(ROOT, "gated.txt")))

entries, record = recorder()
brain = FakeBrain([
    {"action": "tool", "tool": "file_write",
     "args": {"path": "gated.txt", "content": "landed with allow"}},
    {"action": "done", "answer": "written"},
])
status, out = agent_loop.run_loop("write with allow", reg.as_tools(),
                                  brain=brain, record=record,
                                  stop=no_stop, allow={"file_write"})
check("(c) with Allow (name set) file_write executes for real",
      status == "done" and entries[0]["ok"] is True, str(entries))
with open(os.path.join(ROOT, "gated.txt")) as f:
    check("(c) allowed write is really on disk",
          f.read() == "landed with allow")

# --------------------------------------------- (d) caps + binary handling
with open(os.path.join(ROOT, "bin.dat"), "wb") as f:
    f.write(b"\x89PNG\x00\x01\x02binary")
ok, res = tool_run(reg, "file_read", {"path": "bin.dat"})
check("(d) binary file read refused with the reason",
      ok is False and "binary" in res, res)
with open(os.path.join(ROOT, "latin.txt"), "wb") as f:
    f.write(b"\xff\xfe not utf-8")
ok, res = tool_run(reg, "file_read", {"path": "latin.txt"})
check("(d) non-UTF-8 file read refused with the reason",
      ok is False and "UTF-8" in res, res)

big = os.path.join(ROOT, "big.txt")
with open(big, "w") as f:
    f.write("a" * (workspace_tools.READ_CAP + 5000))
ok, res = tool_run(reg, "file_read", {"path": "big.txt"})
check("(d) oversize text read succeeds but is capped + noted",
      ok is True and "truncated" in res
      and len(res) <= workspace_tools.READ_CAP + 200,
      f"len={len(res)}")
ok, res = tool_run(reg, "file_write",
                   {"path": "toobig.txt",
                    "content": "x" * (workspace_tools.WRITE_CAP + 1)})
check("(d) oversize write refused with the cap reason",
      ok is False and "write cap" in res, res)
check("(d) oversize write created nothing",
      not os.path.exists(os.path.join(ROOT, "toobig.txt")))
ok, res = tool_run(reg, "file_read", {"path": "no-such.txt"})
check("(d) missing file is a clean FAILED step, not a crash",
      ok is False and "not a file" in res, res)

print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("FAILED:", "; ".join(FAIL))
sys.exit(1 if FAIL else 0)
