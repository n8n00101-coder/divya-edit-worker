"""e7test.py — E7 rig for compute_tools.py + the verify-style
done-evidence gate (agent_loop) + the ENGINE_CORE compute rule.

Why E7 exists (parity test v1): the model computed CSV facts in
its head and got them wrong inside BOTH engines, and the E6 gate
only proved artifacts exist, not that contents are right. This
rig proves facts are now computed and checked by CODE:

  (0) registry contract: compute/verify tools registered with
      proper schemas/descriptions, stub=False, all read-only.
  (a) compute_csv returns EXACT facts on a mixed-status fixture
      (filter+count+sum incl. a Decimal case floats get wrong,
      count_where, group_by + top_by_sum).
  (b) bad column / unknown spec key / malformed spec -> FAILED
      with the reason named.
  (c) verify_file_contains and verify_csv_rows pass and fail
      correctly per case, failures naming the specific mismatch.
  (d) full loop: a scripted brain writes a WRONG summary and
      claims done -> the verify-style gate rejects it; a FAILED
      verify does not satisfy the gate; the brain recomputes
      with compute_csv, rewrites, verifies OK -> done accepted.
  (d2) the ordering rule: a verify recorded BEFORE the artifact's
      last write is stale — the gate rejects the done claim
      until the file is verified again after the rewrite.
  (e) confinement: compute/verify refuse ../ escapes, absolute
      paths outside the root, and symlinks pointing out, exactly
      like the file tools.
  (f) ENGINE_CORE carries the compute/verify rule and it reaches
      the loaded instruction text.

SCRIPTED FAKE BRAIN, temp dirs only — no model, no network.

Run: python3 e7test.py   (exit 1 on any failure)
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
import engine_instructions
import tools_registry

PASS = []
FAIL = []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("PASS " if cond else "FAIL ") + name +
          (f" — {detail}" if detail and not cond else ""))


class FakeBrain:
    """Scripted brain (e25test pattern): pops the next action per
    call and remembers every history it was shown."""

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
BASE = tempfile.mkdtemp(prefix="e7-rig-")
ROOT = os.path.join(BASE, "ws")            # the job workspace root
OUTSIDE = os.path.join(BASE, "outside")    # a dir OUTSIDE the root
os.makedirs(ROOT)
os.makedirs(OUTSIDE)

ORDERS = (
    "id,status,item,amount\n"
    "1,paid,book,10.50\n"
    "2,pending,pen,5.25\n"
    "3,paid,desk,20.00\n"
    "4,paid,coin,0.10\n"
    "5,cancelled,lamp,99.99\n"
    "6,pending,mug,7.00\n"
    "7,paid,stamp,0.20\n"
)
with open(os.path.join(ROOT, "orders.csv"), "w") as f:
    f.write(ORDERS)
with open(os.path.join(ROOT, "ranked.csv"), "w") as f:
    f.write("name,amount\na,99.99\nb,20.00\nc,10.50\n")
with open(os.path.join(OUTSIDE, "outside.csv"), "w") as f:
    f.write("id,status,amount\n1,paid,1.00\n")
with open(os.path.join(OUTSIDE, "outside.txt"), "w") as f:
    f.write("outside secret")
os.symlink(os.path.join(OUTSIDE, "outside.csv"),
           os.path.join(ROOT, "linked.csv"))


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


# ------------------------------------------------------- (0) contract
reg = full_registry()
check("(0) compute tools registered after defaults + workspace tools",
      reg.names() == ["noop", "echo", "job_state", "get_history",
                      "file_list", "file_read", "file_write",
                      "file_append", "edit_file", "search_text",
                      "list_files", "run_command", "compute_csv",
                      "verify_file_contains", "verify_csv_rows",
                      "filter_csv", "verify_csv_subset"],
      str(reg.names()))
cls = {n: (reg.get(n)["mutating"], reg.get(n)["needs_allow"],
           reg.get(n)["stub"])
       for n in ("compute_csv", "verify_file_contains",
                 "verify_csv_rows")}
check("(0) compute/verify tools are read-only, no Allow, not stubs",
      all(v == (False, False, False) for v in cls.values()),
      str(cls))

# ------------------------------------------- (a) compute_csv exactness
ok, res = tool_run(reg, "compute_csv",
                   {"path": "orders.csv",
                    "spec": {"filter": {"column": "status",
                                        "equals": "paid"},
                             "count": True, "sum": "amount"}})
facts = json.loads(res) if ok else {}
check("(a) filter+count+sum: 4 paid rows, exact Decimal sum 30.80",
      ok and facts.get("rows") == 4 and facts.get("count") == 4
      and facts.get("sum") == "30.80"
      and facts.get("filter") == {"column": "status",
                                  "equals": "paid"},
      res)
ok, res = tool_run(reg, "compute_csv",
                   {"path": "orders.csv",
                    "spec": {"count_where": {"column": "amount",
                                             "gt": 15}}})
facts = json.loads(res) if ok else {}
check("(a) count_where amount>15 over all rows = 2",
      ok and facts.get("rows") == 7
      and facts.get("count_where") == 2, res)
ok, res = tool_run(reg, "compute_csv",
                   {"path": "orders.csv",
                    "spec": {"group_by": "status", "sum": "amount",
                             "top_by_sum": True}})
facts = json.loads(res) if ok else {}
check("(a) group_by status sums are exact per group",
      ok and facts.get("groups") == {
          "paid": {"count": 4, "sum": "30.80"},
          "pending": {"count": 2, "sum": "12.25"},
          "cancelled": {"count": 1, "sum": "99.99"}},
      res)
check("(a) top_by_sum names the cancelled group at 99.99",
      ok and facts.get("top_by_sum") == {"group": "cancelled",
                                         "sum": "99.99"}, res)

# ------------------------------------------------- (b) bad spec/column
ok, res = tool_run(reg, "compute_csv",
                   {"path": "orders.csv", "spec": {"sum": "nope"}})
check("(b) a sum column the CSV does not have -> FAILED naming it",
      not ok and "nope" in res and "header" in res, res)
ok, res = tool_run(reg, "compute_csv",
                   {"path": "orders.csv",
                    "spec": {"median": "amount"}})
check("(b) an unknown spec key -> FAILED naming it",
      not ok and "median" in res, res)
ok, res = tool_run(reg, "compute_csv",
                   {"path": "orders.csv",
                    "spec": {"count_where": {"column": "ghost",
                                             "gt": 1}}})
check("(b) a count_where column that does not exist -> FAILED",
      not ok and "ghost" in res, res)
ok, res = tool_run(reg, "compute_csv",
                   {"path": "orders.csv",
                    "spec": {"top_by_sum": True}})
check("(b) top_by_sum without group_by+sum -> FAILED with reason",
      not ok and "top_by_sum" in res, res)
ok, res = tool_run(reg, "compute_csv",
                   {"path": "orders.csv", "spec": {}})
check("(b) an empty spec -> FAILED, never a silent pass",
      not ok and "spec" in res, res)

# ---------------------------------------------------- (c) verify tools
with open(os.path.join(ROOT, "summary.txt"), "w") as f:
    f.write("paid=4 total=30.80\n")
ok, res = tool_run(reg, "verify_file_contains",
                   {"path": "summary.txt",
                    "contains": ["paid=4", "total=30.80"]})
check("(c) verify_file_contains passes when all strings present",
      ok and res.startswith("OK"), res)
ok, res = tool_run(reg, "verify_file_contains",
                   {"path": "summary.txt",
                    "contains": ["paid=4", "total=31.00"]})
check("(c) verify_file_contains fails listing ONLY the missing one",
      not ok and "total=31.00" in res and "paid=4" not in res, res)
ok, res = tool_run(reg, "verify_csv_rows",
                   {"path": "orders.csv", "expect": {"row_count": 7}})
check("(c) verify_csv_rows row_count exact -> OK",
      ok and res.startswith("OK"), res)
ok, res = tool_run(reg, "verify_csv_rows",
                   {"path": "orders.csv", "expect": {"row_count": 6}})
check("(c) verify_csv_rows row_count mismatch -> FAILED with both numbers",
      not ok and "expected 6" in res and "found 7" in res, res)
ok, res = tool_run(reg, "verify_csv_rows",
                   {"path": "orders.csv",
                    "expect": {"must_contain": {"column": "status",
                                                "equals": "cancelled"}}})
check("(c) must_contain a present row -> OK", ok, res)
ok, res = tool_run(reg, "verify_csv_rows",
                   {"path": "orders.csv",
                    "expect": {"must_contain": {"column": "status",
                                                "equals": "refunded"}}})
check("(c) must_contain an absent row -> FAILED naming it",
      not ok and "refunded" in res, res)
ok, res = tool_run(reg, "verify_csv_rows",
                   {"path": "orders.csv",
                    "expect": {"must_not_contain":
                               {"column": "status", "equals": "paid"}}})
check("(c) must_not_contain a present row -> FAILED naming it",
      not ok and "must_not_contain" in res and "paid" in res, res)
ok, res = tool_run(reg, "verify_csv_rows",
                   {"path": "ranked.csv",
                    "expect": {"sorted": {"column": "amount",
                                          "order": "desc"}}})
check("(c) sorted desc on a descending CSV -> OK", ok, res)
ok, res = tool_run(reg, "verify_csv_rows",
                   {"path": "ranked.csv",
                    "expect": {"sorted": {"column": "amount",
                                          "order": "asc"}}})
check("(c) sorted asc on a descending CSV -> FAILED naming the violation",
      not ok and "violated" in res, res)

# ------------------------------- (d) full loop: wrong -> gate -> fixed
REQ = [{"tool": "verify_file_contains",
        "args": {"path": "summary.txt",
                 "contains": ["paid=4", "total=30.80"]}}]
tools_d = full_registry().as_tools()
entries_d = []
brain_d = FakeBrain([
    {"action": "tool", "tool": "file_write",
     "args": {"path": "summary.txt", "content": "paid=9 total=999.00\n"}},
    {"action": "done", "answer": "summary written"},        # gate rejects
    {"action": "tool", "tool": "verify_file_contains",
     "args": {"path": "summary.txt",
              "contains": ["paid=4", "total=30.80"]}},      # FAILED verify
    {"action": "tool", "tool": "compute_csv",
     "args": {"path": "orders.csv",
              "spec": {"filter": {"column": "status",
                                  "equals": "paid"},
                       "count": True, "sum": "amount"}}},
    {"action": "tool", "tool": "file_write",
     "args": {"path": "summary.txt",
              "content": "paid=4 total=30.80\n"}},
    {"action": "tool", "tool": "verify_file_contains",
     "args": {"path": "summary.txt",
              "contains": ["paid=4", "total=30.80"]}},      # OK verify
    {"action": "done", "answer": "summary written and verified"},
])
status, out = agent_loop.run_loop(
    "summarise orders.csv into summary.txt", tools_d, brain=brain_d,
    record=entries_d.append, stop=no_stop, allow=True, evidence=REQ)
check("(d) the run ends done (E8 auto-close on the completed "
      "evidence) only after compute + rewrite + verify",
      status == "done" and "auto-closed" in out,
      f"{status} {out}")
rej_d = [e for e in entries_d if e.get("tool") == "verify"]
check("(d) the premature done claim was rejected exactly once, naming the verify tool",
      len(rej_d) == 1 and rej_d[0]["ok"] is False
      and "verify_file_contains" in rej_d[0]["result"],
      f"{entries_d}")
fv_d = [e for e in entries_d
        if e.get("tool") == "verify_file_contains" and e.get("ok") is False]
check("(d) the FAILED verify against wrong content is on record (and did not satisfy the gate)",
      len(fv_d) == 1 and "MISSING" in fv_d[0]["result"], f"{entries_d}")
with open(os.path.join(ROOT, "summary.txt")) as f:
    disk_d = f.read()
check("(d) the file on disk carries the computed facts, not the wrong ones",
      disk_d == "paid=4 total=30.80\n", repr(disk_d))

# ------------------------------- (d2) a stale verify does not pass
# E8 note: a second evidence requirement (the notes.txt write) is
# declared alongside REQ. Without it, the E8 auto-close would
# LEGITIMATELY end the run at the first OK verify — at that point
# the file was written and verified, i.e. done. The extra
# requirement keeps the run open so the rewrite can make the
# verify stale and the GATE's rejection is what is exercised.
REQ_D2 = REQ + [{"tool": "file_write", "contains": "notes.txt"}]
entries_d2 = []
brain_d2 = FakeBrain([
    {"action": "tool", "tool": "file_write",
     "args": {"path": "summary.txt",
              "content": "paid=4 total=30.80\n"}},
    {"action": "tool", "tool": "verify_file_contains",
     "args": {"path": "summary.txt",
              "contains": ["paid=4", "total=30.80"]}},      # OK...
    {"action": "tool", "tool": "file_write",
     "args": {"path": "summary.txt",
              "content": "paid=4 total=30.80\n"}},          # ...then rewritten
    {"action": "done", "answer": "done"},                   # gate rejects: stale verify
    {"action": "tool", "tool": "file_write",
     "args": {"path": "notes.txt",
              "content": "notes\n"}},                       # second requirement met
    {"action": "tool", "tool": "verify_file_contains",
     "args": {"path": "summary.txt",
              "contains": ["paid=4", "total=30.80"]}},      # fresh OK -> E8 auto-close
    {"action": "done", "answer": "verified after the last write"},
])
status, out = agent_loop.run_loop(
    "write and verify summary.txt", tools_d, brain=brain_d2,
    record=entries_d2.append, stop=no_stop, allow=True,
    evidence=REQ_D2)
check("(d2) done (E8 auto-close) only after a verify that follows the last write",
      status == "done" and "auto-closed" in out,
      f"{status} {out}")
rej_d2 = [e for e in entries_d2 if e.get("tool") == "verify"]
check("(d2) the stale-verify claim was rejected once, naming the last write",
      len(rej_d2) == 1 and rej_d2[0]["ok"] is False
      and "after the last write" in rej_d2[0]["result"],
      f"{entries_d2}")

# ------------------------------------------------------- (e) confinement
ok, res = tool_run(reg, "compute_csv",
                   {"path": "../outside.csv", "spec": {"count": True}})
check("(e) compute_csv refuses a ../ escape",
      not ok and "REFUSED" in res, res)
ok, res = tool_run(reg, "compute_csv",
                   {"path": os.path.join(OUTSIDE, "outside.csv"),
                    "spec": {"count": True}})
check("(e) compute_csv refuses an absolute path outside the root",
      not ok and "REFUSED" in res, res)
ok, res = tool_run(reg, "compute_csv",
                   {"path": "linked.csv", "spec": {"count": True}})
check("(e) compute_csv refuses a symlink pointing out of the root",
      not ok and "REFUSED" in res, res)
ok, res = tool_run(reg, "verify_file_contains",
                   {"path": "../outside.txt", "contains": ["secret"]})
check("(e) verify_file_contains refuses a ../ escape",
      not ok and "REFUSED" in res, res)
ok, res = tool_run(reg, "verify_csv_rows",
                   {"path": os.path.join(OUTSIDE, "outside.csv"),
                    "expect": {"row_count": 1}})
check("(e) verify_csv_rows refuses an absolute path outside the root",
      not ok and "REFUSED" in res, res)

# ------------------------------------------------- (f) instruction rule
check("(f) ENGINE_CORE carries the compute/verify rule",
      "compute_csv" in engine_instructions.ENGINE_CORE
      and "verify_file_contains" in engine_instructions.ENGINE_CORE
      and "in your head" in engine_instructions.ENGINE_CORE)
text_f, _man_f = engine_instructions.load_instructions(job=None)
check("(f) the rule reaches the loaded instruction text",
      "compute_csv" in text_f and "Facts and numbers" in text_f)

print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("FAILED:", "; ".join(FAIL))
sys.exit(1 if FAIL else 0)
