"""e9test.py — E9 rig for compute_csv spec normalization +
corrective errors (compute_tools.py), and the filter/sort
variant spellings (filter_csv / verify_csv_subset).

Why E9 exists (parity test v3b, 2026-11-19): with pacing in
place the free route stopped killing the run — and the brain
then failed on its own. It called compute_csv 18 times, every
time with the spec in a NESTED-object shape the tool rejected:

  x13  {"filter": {...}, "count": {}}
  x1   {"filter": {...}, "sum": {"column": "amount_inr"}}
  x1   {"filter": {...}, "group_by": {"column": "product",
        "sum": {"column": "amount_inr"}}}
  x1   {"filter": {...}, "sum": {"column": "amount_inr"},
        "count": {}}
  x2   {"filter": {...}, "count": {}, "sum": {"column": ...},
        "count_where": {"column": "amount_inr", "gt": 1000},
        "group_by": "product", ...}   (the steps record caps
        args at 200 chars; the tail past "group_by": "p is the
        flat group_by + top_by_sum the goal required)

The errors were precise ("spec sum must name a column") but
carried no correction, and the model never converged — in v3
the same model had used the flat shapes correctly. This rig
proves the mechanical fix:

  (a) every exact failing arg shape from the v3b steps record
      now returns the exact correct facts (fixture = the real
      parity orders.csv; ground truth 10 completed orders,
      sum 12650, top Headphones 4800, 5 over 1000);
  (b) the flat shapes v3 used still work, with results
      IDENTICAL to their nested equivalents;
  (c) genuinely invalid specs (unknown key, missing column in
      either shape, unsupported count_where op, a spec that
      computes nothing) still FAIL — and every such error ends
      with the "Valid spec example:" correction;
  (d) a full loop run whose scripted brain opens with the v3b
      nested shape completes the parity-style task (compute ->
      filter -> write summary -> verify) and ends DONE by
      evidence auto-close.

SCRIPTED FAKE BRAIN, temp dirs only — no model, no network.

Run: python3 e9test.py   (exit 1 on any failure)
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
import compute_tools
import tools_registry

PASS = []
FAIL = []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("PASS " if cond else "FAIL ") + name +
          (f" — {detail}" if detail and not cond else ""))


class FakeBrain:
    """Scripted brain (e8test pattern): pops the next action
    per call and remembers every history it was shown."""

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
BASE = tempfile.mkdtemp(prefix="e9-rig-")
ROOT = os.path.join(BASE, "ws")
os.makedirs(ROOT)

# The real parity fixture (v1-v3b orders.csv, byte-identical).
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
SORT = {"column": "amount_inr", "order": "desc"}


def full_registry():
    reg = tools_registry.default_registry()
    tools_registry.register_workspace_tools(reg, ROOT)
    tools_registry.register_compute_tools(reg, ROOT)
    return reg


def tool_run(reg, name, args):
    for d in reg.as_tools():
        if d["name"] == name:
            return d["run"](args)
    raise AssertionError(f"tool {name} not registered")


reg = full_registry()


def compute(spec):
    ok, res = tool_run(reg, "compute_csv",
                       {"path": "orders.csv", "spec": spec})
    return ok, (json.loads(res) if ok else res)


# ------------------------------------- (a) the exact v3b failing shapes
ok, facts = compute({"filter": FILT, "count": {}})
check("(a) v3b x13 shape {count: {}} -> count of completed = 10",
      ok and facts.get("rows") == 10 and facts.get("count") == 10,
      str(facts))

ok, facts_a2 = compute({"filter": FILT,
                        "sum": {"column": "amount_inr"}})
check("(a) v3b shape {sum: {column}} -> sum 12650",
      ok and facts_a2.get("sum") == "12650", str(facts_a2))

ok, facts_a3 = compute({"filter": FILT,
                        "group_by": {"column": "product",
                                     "sum": {"column":
                                             "amount_inr"}}})
grp = facts_a3.get("groups", {}) if ok else {}
check("(a) v3b shape {group_by: {column, sum:{column}}} -> "
      "per-group sums (Headphones 4800 x2, Notebook 1800 x3)",
      ok and grp.get("Headphones") == {"count": 2, "sum": "4800"}
      and grp.get("Notebook") == {"count": 3, "sum": "1800"}
      and facts_a3.get("group_by") == "product",
      str(facts_a3))

ok, facts = compute({"filter": FILT,
                     "sum": {"column": "amount_inr"}, "count": {}})
check("(a) v3b shape {sum:{column}, count:{}} -> count 10 + sum",
      ok and facts.get("count") == 10
      and facts.get("sum") == "12650", str(facts))

# The x2 shape, reconstructed past the steps record's 200-char
# arg cap with the flat group_by + top_by_sum its goal required.
ok, facts = compute({"filter": FILT, "count": {},
                     "sum": {"column": "amount_inr"},
                     "count_where": {"column": "amount_inr",
                                     "gt": 1000},
                     "group_by": "product", "top_by_sum": True})
grp = facts.get("groups", {}) if ok else {}
check("(a) v3b x2 full shape -> groups + top_by_sum Headphones "
      "4800, per-group count_where exact",
      ok and facts.get("top_by_sum") == {"group": "Headphones",
                                         "sum": "4800"}
      and grp.get("Headphones", {}).get("count_where") == 2
      and grp.get("Keyboard", {}).get("count_where") == 1
      and facts.get("rows") == 10, str(facts))

ok, facts = compute({"filter": FILT, "sum": "amount_inr",
                     "count_where": {"column": "amount_inr",
                                     "op": ">", "value": 1000}})
check("(a) count_where {op: '>', value: N} spelling -> 5 over "
      "1000, sum 12650",
      ok and facts.get("count_where") == 5
      and facts.get("sum") == "12650", str(facts))

# ------------------------------------- (b) v3 flat shapes, identical facts
ok, facts_b1 = compute({"filter": FILT, "group_by": "product",
                        "sum": "amount_inr"})
check("(b) v3 flat {group_by, sum} == nested group_by facts",
      ok and facts_b1 == facts_a3, str(facts_b1))

ok, facts_b2 = compute({"filter": FILT, "sum": "amount_inr"})
check("(b) v3 flat {sum} == nested sum facts",
      ok and facts_b2 == facts_a2, str(facts_b2))

ok, facts = compute({"filter": FILT, "count": True,
                     "sum": "amount_inr",
                     "count_where": {"column": "amount_inr",
                                     "gt": 1000}})
check("(b) the worked-example spec itself (flat, no group_by) "
      "-> 10 / 12650 / 5",
      ok and facts.get("count") == 10
      and facts.get("sum") == "12650"
      and facts.get("count_where") == 5, str(facts))

# ------------------------------------- (c) invalid specs still FAIL,
# -------------------------------------     now with the correction inside
ok, res = compute({"filter": FILT, "median": "amount_inr"})
check("(c) unknown spec key still FAILS + carries the example",
      not ok and "unknown spec key" in res
      and "Valid spec example:" in res
      and compute_tools._SPEC_EXAMPLE in res, str(res))

ok, res = compute({"sum": "ghost"})
check("(c) missing column (flat) still FAILS + example",
      not ok and "ghost" in res
      and "Valid spec example:" in res, str(res))

ok, res = compute({"sum": {"column": "ghost"}})
check("(c) missing column (nested) still FAILS + example",
      not ok and "ghost" in res
      and "Valid spec example:" in res, str(res))

ok, res = compute({"count_where": {"column": "amount_inr",
                                   "op": "<", "value": 1000}})
check("(c) unsupported count_where op FAILS + example",
      not ok and "not supported" in res
      and "Valid spec example:" in res, str(res))

ok, res = compute({"filter": FILT})
check("(c) a spec that computes nothing still FAILS + example",
      not ok and "computes nothing" in res
      and "Valid spec example:" in res, str(res))

ok, res = tool_run(reg, "compute_csv",
                   {"path": "orders.csv", "spec": "amount_inr"})
check("(c) a non-object spec FAILS at the registry schema "
      "gate (handler never runs — E2 behaviour, unchanged)",
      not ok and "must be object" in res, str(res))

entry = reg.get("compute_csv")
check("(c) the tool description + spec schema carry the worked "
      "example for the brain",
      "Spec example:" in entry["desc"]
      and compute_tools._SPEC_EXAMPLE in entry["desc"]
      and compute_tools._SPEC_EXAMPLE
      in entry["schema"]["spec"]["desc"], entry["desc"][:120])

# --------------------------- (c2) filter/sort variant spellings (point 4)
ok, res = tool_run(reg, "filter_csv",
                   {"source": "orders.csv", "dest": "cleaned.csv",
                    "filter": {"column": "status",
                               "value": "completed"},
                    "sort": {"by": "amount_inr",
                             "direction": "descending"}})
facts = json.loads(res) if ok else {}
check("(c2) filter_csv accepts filter value-alias + sort "
      "by/direction/descending variants -> 10 rows",
      ok and facts.get("rows") == 10, str(res))
ok, res = tool_run(reg, "verify_csv_subset",
                   {"source": "orders.csv", "output": "cleaned.csv",
                    "filter": FILT, "sort": SORT})
check("(c2) verify_csv_subset passes that output",
      ok and res.startswith("OK"), str(res))

# ------------------------------------- (d) full loop, v3b-shaped opening
REQ9 = [
    {"tool": "compute_csv", "contains": "orders.csv"},
    {"tool": "file_write", "contains": "summary.md"},
    {"tool": "filter_csv", "contains": "cleaned.csv"},
    {"tool": "verify_csv_subset",
     "args": {"source": "orders.csv", "output": "cleaned.csv",
              "filter": FILT, "sort": SORT}},
]
tools_d = full_registry().as_tools()
entries_d = []
brain_d = FakeBrain([
    # The v3b opening: the nested shape that failed 18 times.
    {"action": "tool", "tool": "compute_csv",
     "args": {"path": "orders.csv",
              "spec": {"filter": FILT, "count": {},
                       "sum": {"column": "amount_inr"},
                       "count_where": {"column": "amount_inr",
                                       "gt": 1000},
                       "group_by": "product",
                       "top_by_sum": True}}},
    {"action": "tool", "tool": "filter_csv",
     "args": {"source": "orders.csv", "dest": "cleaned.csv",
              "filter": FILT, "sort": SORT}},
    {"action": "tool", "tool": "file_write",
     "args": {"path": "summary.md",
              "content": "Completed orders: 10\n"
                         "Total revenue: 12650\n"
                         "Top product: Headphones (4800)\n"
                         "Completed orders over 1000: 5\n"}},
    {"action": "tool", "tool": "verify_csv_subset",
     "args": {"source": "orders.csv", "output": "cleaned.csv",
              "filter": FILT, "sort": SORT}},
    # Must never run: the evidence completes at the verify.
    {"action": "tool", "tool": "file_list", "args": {}},
    {"action": "done", "answer": "late done"},
])
status, out = agent_loop.run_loop(
    "summarise orders.csv and write cleaned.csv, verifying "
    "both", tools_d, brain=brain_d, record=entries_d.append,
    stop=no_stop, allow=True, evidence=REQ9)
check("(d) the loop ends DONE (auto-closed) on the v3b-shaped "
      "run", status == "done" and "auto-closed" in out,
      f"{status} {out}")
check("(d) exactly 4 brain calls — no wander after the verify",
      len(brain_d.histories) == 4 and len(brain_d.script) == 2,
      f"brain calls={len(brain_d.histories)}")
comp = [e for e in entries_d if e.get("tool") == "compute_csv"]
check("(d) the nested-shape compute step is recorded OK with "
      "the exact facts",
      len(comp) == 1 and comp[0]["ok"] is True
      and '"rows": 10' in comp[0]["result"]
      and '"top_by_sum": {"group": "Headphones", '
          '"sum": "4800"}' in comp[0]["result"],
      f"{comp}")
with open(os.path.join(ROOT, "summary.md")) as f:
    summary = f.read()
check("(d) summary.md on disk carries the computed facts",
      "10" in summary and "12650" in summary
      and "Headphones" in summary, summary)
with open(os.path.join(ROOT, "cleaned.csv")) as f:
    cleaned = f.read().strip().splitlines()
check("(d) cleaned.csv on disk = header + the 10 completed "
      "rows, amount desc (2400 first, 250 last)",
      len(cleaned) == 11 and "2400" in cleaned[1]
      and cleaned[-1].endswith(",250,completed"), cleaned[:2])

print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("FAILED:", "; ".join(FAIL))
sys.exit(1 if FAIL else 0)
