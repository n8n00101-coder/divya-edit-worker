"""e8test.py — E8 rig for filter_csv + verify_csv_subset
(compute_tools.py), the evidence auto-close (agent_loop.py), and
the ENGINE_CORE filter rule (engine_instructions.py).

Why E8 exists (parity test v2, 2026-11-19): with E7's compute
tools Julie's facts went 1/4 -> 4/4, but three failure modes
remained, all one level up from arithmetic:

  (1) the brain HAND-COPIED rows into cleaned.csv and silently
      relabelled one pending row's status to "completed";
  (2) its self-chosen verify expectations passed vacuously over
      that relabelled row — the check never looked at the SOURCE;
  (3) after its verify passed, the brain never declared done —
      it wandered into the 40-step limit and a finished job was
      scored a failure.

This rig proves the mechanical fixes:

  (0) registry contract: filter_csv registered mutating + needs
      Allow; verify_csv_subset read-only; both real (not stubs).
  (a) filter_csv output = the exact expected rows VERBATIM (all
      columns, original values) + numeric-aware sort, on a
      mixed-status fixture; result carries row count + dest.
  (b) verify_csv_subset passes the filter_csv output and FAILS
      each tampered variant: relabelled status row (the v2
      shape), one row dropped, one extra row, wrong order.
  (c) auto-close: a scripted brain does the work (filter +
      verify evidence satisfied) and then KEEPS CALLING tools —
      the loop must end DONE the moment the evidence completes,
      with NO further brain calls; the terminal entry states
      "evidence complete — auto-closed". (c2) a chain treats the
      auto-closed DONE like a normal DONE and continues.
  (d) no-evidence runs are unchanged (E1 behaviour): the brain's
      own done + answer ends the run, no auto-close entry.
  (e) confinement for both new tools: ../ escapes, absolute
      paths outside the root, symlinks pointing out — refused,
      and nothing is written outside the root.
  (f) ENGINE_CORE carries the filter_csv / verify_csv_subset
      rule and it reaches the loaded instruction text.

SCRIPTED FAKE BRAIN, temp dirs only — no model, no network.

Run: python3 e8test.py   (exit 1 on any failure)
"""

import csv
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
import engine_instructions
import tools_registry

PASS = []
FAIL = []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("PASS " if cond else "FAIL ") + name +
          (f" — {detail}" if detail and not cond else ""))


class FakeBrain:
    """Scripted brain (e7test pattern): pops the next action per
    call and remembers every history it was shown — so the rig
    can count brain calls exactly."""

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
BASE = tempfile.mkdtemp(prefix="e8-rig-")
ROOT = os.path.join(BASE, "ws")            # the job workspace root
OUTSIDE = os.path.join(BASE, "outside")    # a dir OUTSIDE the root
os.makedirs(ROOT)
os.makedirs(OUTSIDE)

ORDERS = (
    "id,status,item,amount\n"
    "1,completed,Notebook,450\n"
    "2,pending,Pen Set,300\n"
    "3,completed,Headphones,4800\n"
    "4,cancelled,Speaker,2400\n"
    "5,completed,Mouse,1500\n"
    "6,pending,Cable,200\n"
    "7,completed,Keyboard,2100\n"
)
with open(os.path.join(ROOT, "orders.csv"), "w") as f:
    f.write(ORDERS)
with open(os.path.join(OUTSIDE, "outside.csv"), "w") as f:
    f.write("id,status,item,amount\n1,completed,X,1\n")
os.symlink(os.path.join(OUTSIDE, "outside.csv"),
           os.path.join(ROOT, "linked.csv"))

FILT = {"column": "status", "equals": "completed"}
SORT = {"column": "amount", "order": "desc"}
# Ground truth: the completed rows, verbatim, amount descending.
EXPECTED = [
    {"id": "3", "status": "completed", "item": "Headphones",
     "amount": "4800"},
    {"id": "7", "status": "completed", "item": "Keyboard",
     "amount": "2100"},
    {"id": "5", "status": "completed", "item": "Mouse",
     "amount": "1500"},
    {"id": "1", "status": "completed", "item": "Notebook",
     "amount": "450"},
]
HEADER = ["id", "status", "item", "amount"]


def full_registry():
    reg = tools_registry.default_registry()
    tools_registry.register_workspace_tools(reg, ROOT)
    tools_registry.register_compute_tools(reg, ROOT)
    return reg


def tool_run(reg, name, args):
    """Run one tool through the registry's as_tools() contract."""
    for d in reg.as_tools():
        if d["name"] == name:
            return d["run"](args)
    raise AssertionError(f"tool {name} not registered")


def read_rows(rel):
    with open(os.path.join(ROOT, rel), newline="",
              encoding="utf-8") as f:
        r = csv.DictReader(f)
        return r.fieldnames, [dict(row) for row in r]


def write_rows(rel, rows):
    with open(os.path.join(ROOT, rel), "w", newline="",
              encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=HEADER,
                           lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


# ------------------------------------------------------- (0) contract
reg = full_registry()
check("(0) registry tail is the E7 tools + filter_csv + verify_csv_subset",
      reg.names()[-5:] == ["compute_csv", "verify_file_contains",
                           "verify_csv_rows", "filter_csv",
                           "verify_csv_subset"],
      str(reg.names()))
fc = reg.get("filter_csv")
vs = reg.get("verify_csv_subset")
check("(0) filter_csv is mutating + needs Allow, not a stub",
      (fc["mutating"], fc["needs_allow"], fc["stub"])
      == (True, True, False), str(fc))
check("(0) verify_csv_subset is read-only, no Allow, not a stub",
      (vs["mutating"], vs["needs_allow"], vs["stub"])
      == (False, False, False), str(vs))

# ------------------------------------------- (a) filter_csv exactness
ok, res = tool_run(reg, "filter_csv",
                   {"source": "orders.csv", "dest": "cleaned.csv",
                    "filter": FILT, "sort": SORT})
facts = json.loads(res) if ok else {}
check("(a) filter_csv reports the row count + dest",
      ok and facts.get("rows") == 4
      and facts.get("dest") == "cleaned.csv"
      and facts.get("source") == "orders.csv"
      and facts.get("sorted") == SORT, res)
fields, rows = read_rows("cleaned.csv")
check("(a) output header preserved, rows verbatim + sorted desc",
      fields == HEADER and rows == EXPECTED, f"{fields} {rows}")
ok, res = tool_run(reg, "filter_csv",
                   {"source": "orders.csv", "dest": "same.csv",
                    "filter": {"column": "status", "equals": "paid"}})
check("(a) a filter matching nothing writes a header-only file (0 rows)",
      ok and json.loads(res).get("rows") == 0
      and read_rows("same.csv")[1] == [], res)
ok, res = tool_run(reg, "filter_csv",
                   {"source": "orders.csv", "dest": "orders.csv",
                    "filter": FILT})
check("(a) dest == source is refused (the source is the verify reference)",
      not ok and "differ from its source" in res, res)
ok, res = tool_run(reg, "filter_csv",
                   {"source": "orders.csv", "dest": "x.csv",
                    "filter": {"column": "ghost", "equals": "y"}})
check("(a) a filter column the CSV does not have -> FAILED naming it",
      not ok and "ghost" in res, res)

# --------------------------------- (b) verify_csv_subset pass + tampers
ok, res = tool_run(reg, "verify_csv_subset",
                   {"source": "orders.csv", "output": "cleaned.csv",
                    "filter": FILT, "sort": SORT})
check("(b) verify_csv_subset passes the filter_csv output",
      ok and res.startswith("OK"), res)

# The v2 shape: id 1 dropped, pending id 2 included with its
# status REWRITTEN to "completed" (hand-copy relabelling).
write_rows("tampered_relabel.csv", EXPECTED[:3] + [
    {"id": "2", "status": "completed", "item": "Pen Set",
     "amount": "300"}])
ok, res = tool_run(reg, "verify_csv_subset",
                   {"source": "orders.csv",
                    "output": "tampered_relabel.csv",
                    "filter": FILT, "sort": SORT})
check("(b) a relabelled status row FAILS (missing + extra named)",
      not ok and "missing row" in res and "extra row" in res
      and "Pen Set" in res, res)

write_rows("tampered_dropped.csv", EXPECTED[:3])
ok, res = tool_run(reg, "verify_csv_subset",
                   {"source": "orders.csv",
                    "output": "tampered_dropped.csv",
                    "filter": FILT, "sort": SORT})
check("(b) one dropped row FAILS naming the missing row + count",
      not ok and "missing row" in res and "Notebook" in res
      and "row count" in res, res)

write_rows("tampered_extra.csv", EXPECTED + [
    {"id": "2", "status": "pending", "item": "Pen Set",
     "amount": "300"}])
ok, res = tool_run(reg, "verify_csv_subset",
                   {"source": "orders.csv",
                    "output": "tampered_extra.csv",
                    "filter": FILT, "sort": SORT})
check("(b) one extra row FAILS naming the extra row",
      not ok and "extra row" in res and "Pen Set" in res, res)

write_rows("tampered_order.csv",
           [EXPECTED[1], EXPECTED[0]] + EXPECTED[2:])
ok, res = tool_run(reg, "verify_csv_subset",
                   {"source": "orders.csv",
                    "output": "tampered_order.csv",
                    "filter": FILT, "sort": SORT})
check("(b) the right rows in the wrong order FAIL on order",
      not ok and "order differs at data row 1" in res, res)

# ------------------------------------------- (c) evidence auto-close
REQ8 = [
    {"tool": "filter_csv", "contains": "cleaned.csv"},
    {"tool": "verify_csv_subset",
     "args": {"source": "orders.csv", "output": "cleaned.csv",
              "filter": FILT, "sort": SORT}},
]
tools_c = full_registry().as_tools()
entries_c = []
brain_c = FakeBrain([
    {"action": "tool", "tool": "filter_csv",
     "args": {"source": "orders.csv", "dest": "cleaned.csv",
              "filter": FILT, "sort": SORT}},
    {"action": "tool", "tool": "verify_csv_subset",
     "args": {"source": "orders.csv", "output": "cleaned.csv",
              "filter": FILT, "sort": SORT}},
    # The brain now WANDERS (the v2 behaviour): more tool calls,
    # then a late done. None of these may ever run.
    {"action": "tool", "tool": "file_list", "args": {}},
    {"action": "tool", "tool": "file_read",
     "args": {"path": "orders.csv"}},
    {"action": "tool", "tool": "compute_csv",
     "args": {"path": "orders.csv", "spec": {"count": True}}},
    {"action": "done", "answer": "late done"},
])
status, out = agent_loop.run_loop(
    "write cleaned.csv (completed only, amount desc) and verify it",
    tools_c, brain=brain_c, record=entries_c.append, stop=no_stop,
    allow=True, evidence=REQ8)
check("(c) the run ends DONE by auto-close, not by the brain",
      status == "done" and "auto-closed" in out,
      f"{status} {out}")
check("(c) NO brain call happened after the evidence completed",
      len(brain_c.histories) == 2 and len(brain_c.script) == 4,
      f"brain calls={len(brain_c.histories)} "
      f"script left={len(brain_c.script)}")
term_c = [e for e in entries_c if e.get("tool") == "done"]
check("(c) the terminal entry states 'evidence complete — auto-closed'",
      len(term_c) == 1 and term_c[0]["ok"] is True
      and term_c[0]["result"].startswith(
          "evidence complete — auto-closed"),
      f"{entries_c}")
check("(c) cleaned.csv on disk is the exact expected subset",
      read_rows("cleaned.csv")[1] == EXPECTED)

# ------------------------------ (c2) a chain treats it as a normal DONE
entries_c2 = []
brain_c2 = FakeBrain([
    {"action": "tool", "tool": "filter_csv",
     "args": {"source": "orders.csv", "dest": "cleaned.csv",
              "filter": FILT, "sort": SORT}},
    {"action": "tool", "tool": "verify_csv_subset",
     "args": {"source": "orders.csv", "output": "cleaned.csv",
              "filter": FILT, "sort": SORT}},
    {"action": "done", "answer": "second goal done"},
])
job_c2 = {"task": "chain job",
          "chain": agent_loop.make_chain([
              {"goal": "make cleaned.csv", "evidence": REQ8},
              {"goal": "wrap up"}])}
status, out = agent_loop.run_chain(
    job_c2, tools_c, brain=brain_c2, record=entries_c2.append,
    stop=no_stop, allow=True)
state_c2 = agent_loop.chain_state({"steps": entries_c2})
check("(c2) the chain continues past the auto-closed goal and finishes",
      status == "done" and out == "second goal done"
      and len(brain_c2.histories) == 3
      and state_c2 is not None and state_c2["status"] == "done"
      and len(state_c2["handoffs"]) == 2
      and "auto-closed" in state_c2["handoffs"][0],
      f"{status} {out} {state_c2}")

# ------------------------------------- (d) no evidence = E1 behaviour
entries_d = []
brain_d = FakeBrain([
    {"action": "tool", "tool": "echo", "args": {"text": "hi"}},
    {"action": "done", "answer": "finished normally"},
])
status, out = agent_loop.run_loop(
    "say hi and finish", agent_loop.default_tools(), brain=brain_d,
    record=entries_d.append, stop=no_stop)
check("(d) a no-evidence run ends on the brain's own done + answer",
      status == "done" and out == "finished normally"
      and len(brain_d.histories) == 2, f"{status} {out}")
check("(d) no auto-close entry appears without declared evidence",
      all("auto-closed" not in str(e.get("result") or "")
          for e in entries_d)
      and [e for e in entries_d if e.get("tool") == "done"][0]
      ["result"] == "finished normally", f"{entries_d}")

# ------------------------------------------------------- (e) confinement
ok, res = tool_run(reg, "filter_csv",
                   {"source": "../outside.csv", "dest": "x.csv",
                    "filter": FILT})
check("(e) filter_csv refuses a ../ source escape",
      not ok and "REFUSED" in res, res)
ok, res = tool_run(reg, "filter_csv",
                   {"source": "orders.csv", "dest": "../evil.csv",
                    "filter": FILT})
check("(e) filter_csv refuses a ../ dest escape and writes nothing out",
      not ok and "REFUSED" in res
      and not os.path.exists(os.path.join(BASE, "evil.csv")), res)
ok, res = tool_run(reg, "filter_csv",
                   {"source": "orders.csv",
                    "dest": os.path.join(OUTSIDE, "evil2.csv"),
                    "filter": FILT})
check("(e) filter_csv refuses an absolute dest outside the root",
      not ok and "REFUSED" in res
      and not os.path.exists(os.path.join(OUTSIDE, "evil2.csv")),
      res)
ok, res = tool_run(reg, "verify_csv_subset",
                   {"source": "../outside.csv",
                    "output": "cleaned.csv",
                    "filter": FILT, "sort": SORT})
check("(e) verify_csv_subset refuses a ../ source escape",
      not ok and "REFUSED" in res, res)
ok, res = tool_run(reg, "verify_csv_subset",
                   {"source": "orders.csv",
                    "output": os.path.join(OUTSIDE, "outside.csv"),
                    "filter": FILT, "sort": SORT})
check("(e) verify_csv_subset refuses an absolute output outside the root",
      not ok and "REFUSED" in res, res)
ok, res = tool_run(reg, "verify_csv_subset",
                   {"source": "linked.csv", "output": "cleaned.csv",
                    "filter": FILT, "sort": SORT})
check("(e) verify_csv_subset refuses a symlink source pointing out",
      not ok and "REFUSED" in res, res)

# ------------------------------------------------- (f) instruction rule
check("(f) ENGINE_CORE carries the filter rule",
      "filter_csv" in engine_instructions.ENGINE_CORE
      and "verify_csv_subset" in engine_instructions.ENGINE_CORE
      and "Never write such a file by copying rows yourself"
      in engine_instructions.ENGINE_CORE)
text_f, _man_f = engine_instructions.load_instructions(job=None)
check("(f) the rule reaches the loaded instruction text",
      "filter_csv" in text_f and "verify_csv_subset" in text_f)

print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("FAILED:", "; ".join(FAIL))
sys.exit(1 if FAIL else 0)
