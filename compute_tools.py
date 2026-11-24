"""Julie agent engine (E7): DETERMINISTIC COMPUTE + VERIFY TOOLS.

Why this module exists (parity test v1, 2026-11-19): a CSV facts
task was given to the same free model inside two engines, and BOTH
sides got the numbers wrong — not because the engines failed, but
because the model did the arithmetic in its head. The engine lesson:
facts must be COMPUTED BY CODE and outputs CHECKED BY CODE, never
trusted to the model's mental maths or memory. E7 gives the loop
three tools that do exactly that, all read-only, all confined to
the job workspace exactly like the E2.5 file tools (the confinement
helper is imported from workspace_tools, not re-implemented):

  compute_csv            read a workspace CSV and compute facts
                         from a small declarative spec (filter /
                         group_by / sum / count / count_where /
                         top_by_sum). Pure csv module; every sum
                         and comparison is Decimal — exact, no
                         float drift. The result is structured
                         JSON text the brain can quote verbatim.
  verify_file_contains   OK only when EVERY required substring is
                         present in a workspace text file; FAILED
                         listing exactly which are missing.
  verify_csv_rows        OK only when a workspace CSV matches the
                         declared expectations (row count,
                         must / must-not contain a column=value
                         row, numeric sort order); FAILED with the
                         specific mismatch.

Handlers follow the agent_loop tool contract: (ok, result) tuples;
a refusal or a failed check is (False, reason) — a FAILED step the
loop feeds back to the brain, never an exception and never a
silent pass. An invalid spec, an unknown spec key, or a column
the CSV does not have is a FAILED step naming the problem — the
tool never guesses what the brain "meant".

Numeric strictness (deliberate): a cell used by sum / count_where /
a sorted check must parse as a Decimal; an empty or non-numeric
cell is a FAILED step naming the row and value. Silently treating
bad data as 0 would manufacture facts — the exact failure E7
exists to prevent.

E8 (parity test v2) adds the two tools that close v2's remaining
failure modes mechanically:

  filter_csv             produce a filtered / sorted subset CSV
                         BY CODE: rows matching {column, equals}
                         are copied from the source VERBATIM (all
                         columns, original values, header
                         preserved) and optionally sorted
                         numeric-aware. The model never hand-copies
                         rows again — in v2 it copied a pending row
                         into cleaned.csv with its status rewritten
                         to "completed". Mutating: it writes the
                         dest file, so it needs Allow.
  verify_csv_subset      passes ONLY when the output's rows are
                         EXACTLY the source rows matching the
                         filter (verbatim row equality, all
                         columns), in the declared sort order. The
                         comparison is against the SOURCE, never
                         against expectations the brain chose — in
                         v2 the brain's own verify_csv_rows
                         expectations passed vacuously over its own
                         relabelled row. Read-only.

E9 (parity test v3b) hardens compute_csv against how free models
actually call it: in v3b the model sent the spec in nested-object
shapes — "count": {}, "sum": {"column": ...}, "group_by":
{"column": ..., "sum": {...}} — 18 times, was rejected 18 times
with errors that were precise but not corrective, and never
converged (in v3 the same model had used the flat shapes fine).
The tool now NORMALIZES the known spec keys: each accepts the
documented flat form AND the nested {"column": ...} form (plus
count_where's {"op": ">", "value": N} spelling), so shape
variance in a KNOWN key is no longer a failure. Strictness is
unchanged where it matters: unknown keys, missing columns and
non-numeric data still FAIL — but every spec-validation failure
now ends with a worked valid-spec example, so the feedback loop
itself carries the correction.
"""

import csv
import json
import os
from collections import Counter
from decimal import Decimal, InvalidOperation

from workspace_tools import _confined, _refused

ROW_CAP = 200_000            # max data rows compute/verify will read
VERIFY_READ_CAP = 8 * 1024 * 1024   # max bytes verify_file_contains reads

_SPEC_KEYS = ("filter", "group_by", "sum", "count", "count_where",
              "top_by_sum", "multiply_sum")
_EXPECT_KEYS = ("row_count", "must_contain", "must_not_contain",
                "sorted")

# The one worked example every compute_csv spec error carries
# (E9): a model that shaped the spec wrong gets the correction
# inside the FAILED result it is fed back, not just a refusal.
_SPEC_EXAMPLE = (
    '{"filter": {"column": "status", "equals": "completed"}, '
    '"count": true, "sum": "amount_inr", '
    '"count_where": {"column": "amount_inr", "gt": 1000}, '
    '"group_by": "product", "top_by_sum": true}')
_SPEC_HINT = "\nValid spec example: " + _SPEC_EXAMPLE


def _spec_column(value):
    """A spec column named in EITHER shape the models use: the
    flat string "amount_inr" or the nested object
    {"column": "amount_inr"}. Returns the column name, or None
    when the value names no column in either shape."""
    if isinstance(value, str) and value:
        return value
    if isinstance(value, dict):
        col = value.get("column")
        if isinstance(col, str) and col:
            return col
    return None


def _normalize_spec(spec):
    """E9 spec normalization: rewrite the KNOWN spec keys from
    whichever shape the brain used into the one internal shape
    the validator below has always accepted. Returns
    (normalized_spec, None) or (None, reason).

    Accepted variants, per key:
      filter      {"column", "equals"} — "value" is an alias
                  for "equals" (normalized before validation).
      sum         "amount_inr" | {"column": "amount_inr"}
      group_by    "product" | {"column": "product"} — a nested
                  group_by may also carry its own "sum" (flat or
                  nested); it is lifted to the top-level sum
                  when the spec has none of its own.
      count       true | {} | any object (an object value is
                  how v3b's model said "yes, count").
      count_where {"column", "gt"} | {"column", "op": ">",
                  "value"} | {"column", "value"} (value alone
                  implies gt). Any other op is a reason — only
                  "greater than" exists.
      top_by_sum  true | "amount_inr" | {"column": ...} — a
                  column value names the sum column (lifted
                  when the spec has no sum of its own) and
                  switches top_by_sum on.

    Unknown keys pass through untouched, so the strict
    unknown-key rejection still fires on them; values that name
    no column in either shape are a reason here, and column
    EXISTENCE is still checked by the validator against the
    CSV header, exactly as before."""
    out = {}
    for key, val in spec.items():
        if key == "filter":
            if isinstance(val, dict) and "equals" not in val \
                    and "value" in val:
                val = dict(val)
                val["equals"] = val.pop("value")
            out["filter"] = val
        elif key == "sum":
            col = _spec_column(val)
            if col is None:
                return None, ("spec sum must name a column — a "
                              "string or {\"column\": ...}")
            out["sum"] = col
        elif key == "group_by":
            col = _spec_column(val)
            if col is None:
                return None, ("spec group_by must name a column "
                              "— a string or {\"column\": ...}")
            out["group_by"] = col
            if isinstance(val, dict) and "sum" in val \
                    and "sum" not in spec and "sum" not in out:
                scol = _spec_column(val["sum"])
                if scol is None:
                    return None, ("spec group_by sum must name "
                                  "a column — a string or "
                                  "{\"column\": ...}")
                out["sum"] = scol
        elif key == "multiply_sum":
            # W6 (live-proven gap, 2026-11-24): line totals —
            # sum of a*b over two columns (qty x price) — were NOT
            # expressible, and two production agent jobs died on
            # exactly that ("required calculation not supported by
            # tools"). Accepted shapes: {"columns": [a, b]}, a bare
            # [a, b] list, or {"a": ..., "b": ...}.
            cols = None
            if isinstance(val, dict) and isinstance(val.get("columns"), list):
                cols = val["columns"]
            elif isinstance(val, list):
                cols = val
            elif isinstance(val, dict) and "a" in val and "b" in val:
                cols = [val["a"], val["b"]]
            if not cols or len(cols) != 2 \
                    or not all(isinstance(c, str) and c for c in cols):
                return None, ("spec multiply_sum must name exactly "
                              "two columns — {\"columns\": "
                              "[\"qty\", \"price\"]}")
            out["multiply_sum"] = {"columns": list(cols)}
        elif key == "count":
            if val is True or isinstance(val, dict) \
                    or val == "true":
                out["count"] = True
            elif val:
                out["count"] = val
            # a falsy count (false / null / 0) drops the key:
            # count simply was not requested
        elif key == "count_where":
            if isinstance(val, dict) and "gt" not in val \
                    and "value" in val:
                op = val.get("op", ">")
                if op != ">":
                    return None, (f"spec count_where op {op!r} "
                                  f"is not supported — the only "
                                  f"comparison is \"gt\" (>)")
                val = {"column": val.get("column"),
                       "gt": val["value"]}
            out["count_where"] = val
        elif key == "top_by_sum":
            if isinstance(val, bool):
                out["top_by_sum"] = val
            else:
                col = _spec_column(val)
                if col is None:
                    return None, ("spec top_by_sum must be true "
                                  "or name the sum column — a "
                                  "string or {\"column\": ...}")
                out["top_by_sum"] = True
                if "sum" not in spec and "sum" not in out:
                    out["sum"] = col
        else:
            out[key] = val
    return out, None


def _read_csv(root_real, rel):
    """Read one confined CSV. Returns (rows, fieldnames, error):
    on success error is None; on any problem rows/fieldnames are
    None and error is the (False, reason) handler result. Rows are
    DictReader dicts with None cells normalised to ""."""
    target = _confined(root_real, rel)
    if target is None:
        return None, None, _refused(rel)
    if not os.path.isfile(target):
        return None, None, (False, f"not a file: {rel!r}")
    try:
        with open(target, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            fields = reader.fieldnames
            if not fields:
                return None, None, (False,
                                    f"{rel!r} has no header row")
            rows = []
            for row in reader:
                rows.append({k: ("" if v is None else v)
                             for k, v in row.items()
                             if k is not None})
                if len(rows) > ROW_CAP:
                    return None, None, (False,
                                        f"{rel!r} has more than the "
                                        f"{ROW_CAP}-row read cap")
    except UnicodeDecodeError as e:
        return None, None, (False,
                            f"{rel!r} is not valid UTF-8 text: {e}")
    except (OSError, csv.Error) as e:
        return None, None, (False, f"could not read CSV {rel!r}: {e}")
    return rows, fields, None


def _num(raw, col, rowno):
    """Parse one cell as an exact Decimal. Returns (Decimal, None)
    or (None, reason) — empty and non-numeric cells are reasons,
    never silently zero."""
    s = str(raw if raw is not None else "").strip()
    if not s:
        return None, (f"data row {rowno}: empty value in numeric "
                      f"column {col!r}")
    try:
        return Decimal(s), None
    except InvalidOperation:
        return None, (f"data row {rowno}: value {s!r} in column "
                      f"{col!r} is not numeric")


def _num_literal(v, what):
    """Parse a spec-side number (count_where gt) as Decimal."""
    if isinstance(v, bool) or v is None:
        return None, f"{what} must be a number, got {v!r}"
    try:
        return Decimal(str(v)), None
    except InvalidOperation:
        return None, f"{what} must be a number, got {v!r}"


def _parse_filter(filt, fields, what="filter"):
    """Validate a {"column", "equals"} filter object against a CSV
    header. Returns (column, equals_str, None) or
    (None, None, reason) — a malformed filter or a column the CSV
    does not have is a reason, never a guess. E9: "value" is
    accepted as an alias for "equals" — the other spelling
    models reach for."""
    if isinstance(filt, dict) and "equals" not in filt \
            and "value" in filt:
        filt = dict(filt)
        filt["equals"] = filt.pop("value")
    if not isinstance(filt, dict) \
            or "column" not in filt or "equals" not in filt:
        return None, None, (f"{what} must be an object "
                            "{\"column\": ..., \"equals\": ...}")
    col = filt["column"]
    if not isinstance(col, str) or not col:
        return None, None, f"{what} must name a column"
    if col not in fields:
        return None, None, (f"{what} names column {col!r}, which "
                            f"is not in the CSV header {fields}")
    return col, str(filt["equals"]), None


def _parse_sort(srt, fields, what="sort"):
    """Validate a {"column", "order": "asc"|"desc"} sort object
    against a CSV header. Returns (column, order, None) or
    (None, None, reason). E9: the variant spellings models use
    are normalized first — "by" for "column", "direction" for
    "order", "ascending"/"descending" for "asc"/"desc"."""
    if isinstance(srt, dict):
        srt = dict(srt)
        if "column" not in srt and "by" in srt:
            srt["column"] = srt.pop("by")
        if "order" not in srt and "direction" in srt:
            srt["order"] = srt.pop("direction")
        if srt.get("order") == "ascending":
            srt["order"] = "asc"
        elif srt.get("order") == "descending":
            srt["order"] = "desc"
    if not isinstance(srt, dict) or "column" not in srt \
            or srt.get("order") not in ("asc", "desc"):
        return None, None, (f"{what} must be an object "
                            "{\"column\": ..., \"order\": "
                            "\"asc\"|\"desc\"}")
    col = srt["column"]
    if not isinstance(col, str) or not col:
        return None, None, f"{what} must name a column"
    if col not in fields:
        return None, None, (f"{what} names column {col!r}, which "
                            f"is not in the CSV header {fields}")
    return col, srt["order"], None


def _sorted_rows(picked, col, order):
    """Numeric-aware sort of (rowno, row) pairs by `col`: every
    cell must parse as a Decimal (the E7 strictness rule — a
    non-numeric cell is a FAILED step naming the row, never a
    silent lexical ordering). Stable: rows with equal keys keep
    their source order. Returns (rows, None) or (None, reason)."""
    keyed = []
    for rowno, r in picked:
        d, bad = _num(r.get(col, ""), col, rowno)
        if bad:
            return None, bad
        keyed.append((d, r))
    keyed.sort(key=lambda kr: kr[0], reverse=(order == "desc"))
    return [r for _d, r in keyed], None


def register_compute_tools(reg, root):
    """Register the compute/verify tools on `reg`, confined to
    `root` (the per-job workspace directory; created here if
    missing, mirroring register_workspace_tools). The E7 three
    (compute_csv / verify_file_contains / verify_csv_rows) and
    E8's verify_csv_subset are read-only: they never write, so
    they never need Allow, and a verify step is always safe for
    the loop's resume verify-first guard. E8's filter_csv WRITES
    its dest file, so it is mutating and needs Allow."""
    root_real = os.path.realpath(str(root))
    os.makedirs(root_real, exist_ok=True)

    # ------------------------------------------------ compute_csv
    def _compute_csv(args):
        def spec_fail(msg):
            """A SPEC-validation failure (E9): the reason plus
            the worked example, so the feedback the loop gives
            the brain carries the correction. Data failures
            (unreadable file, non-numeric cells) do NOT get the
            example — the spec was not their problem."""
            return False, msg + _SPEC_HINT

        rel = str(args.get("path") or "")
        spec = args.get("spec")
        if not isinstance(spec, dict) or not spec:
            return spec_fail("compute_csv needs a spec object — "
                             "one of: " + ", ".join(_SPEC_KEYS))
        spec, norm_bad = _normalize_spec(spec)
        if norm_bad:
            return spec_fail(norm_bad)
        unknown = sorted(set(spec) - set(_SPEC_KEYS))
        if unknown:
            return spec_fail(f"unknown spec key(s): "
                             f"{', '.join(unknown)} — supported: "
                             f"{', '.join(_SPEC_KEYS)}")
        rows, fields, err = _read_csv(root_real, rel)
        if err:
            return err

        def need_col(col, where):
            if not isinstance(col, str) or not col:
                return f"spec {where} must name a column"
            if col not in fields:
                return (f"spec {where} names column {col!r}, which "
                        f"is not in the CSV header {fields}")
            return None

        filt = spec.get("filter")
        fcol = feq = None
        if filt is not None:
            if not isinstance(filt, dict) \
                    or "column" not in filt or "equals" not in filt:
                return spec_fail(
                    "spec filter must be an object "
                    "{\"column\": ..., \"equals\": ...}")
            bad = need_col(filt["column"], "filter")
            if bad:
                return spec_fail(bad)
            fcol, feq = filt["column"], str(filt["equals"])
        gcol = spec.get("group_by")
        if gcol is not None:
            bad = need_col(gcol, "group_by")
            if bad:
                return spec_fail(bad)
        scol = spec.get("sum")
        if scol is not None:
            bad = need_col(scol, "sum")
            if bad:
                return spec_fail(bad)
        mspec = spec.get("multiply_sum")
        mcols = None
        if mspec is not None:
            if not isinstance(mspec, dict) \
                    or not isinstance(mspec.get("columns"), list) \
                    or len(mspec["columns"]) != 2:
                return spec_fail("spec multiply_sum must be an "
                                 "object {\"columns\": [a, b]}")
            mcols = mspec["columns"]
            for mc in mcols:
                bad = need_col(mc, "multiply_sum")
                if bad:
                    return spec_fail(bad)
        cw = spec.get("count_where")
        cw_col = cw_gt = None
        if cw is not None:
            if not isinstance(cw, dict) \
                    or "column" not in cw or "gt" not in cw:
                return spec_fail(
                    "spec count_where must be an object "
                    "{\"column\": ..., \"gt\": number}")
            bad = need_col(cw["column"], "count_where")
            if bad:
                return spec_fail(bad)
            cw_gt, bad = _num_literal(cw["gt"], "count_where gt")
            if bad:
                return spec_fail(bad)
            cw_col = cw["column"]
        want_count = bool(spec.get("count"))
        want_top = bool(spec.get("top_by_sum"))
        if want_top and (gcol is None or scol is None):
            return spec_fail("spec top_by_sum needs both "
                             "group_by and sum in the same spec")
        if not (want_count or scol is not None or cw is not None
                or gcol is not None or mspec is not None):
            return spec_fail("spec computes nothing — give at "
                             "least one of count, sum, "
                             "count_where, group_by, multiply_sum")

        picked = [(i + 1, r) for i, r in enumerate(rows)
                  if fcol is None or str(r.get(fcol, "")) == feq]

        def metrics(members):
            """The requested metrics over one set of (rowno, row).
            Returns (dict, None) or (None, reason)."""
            out = {}
            if gcol is not None or want_count:
                out["count"] = len(members)
            if scol is not None:
                total = Decimal(0)
                for rowno, r in members:
                    d, bad = _num(r.get(scol, ""), scol, rowno)
                    if bad:
                        return None, bad
                    total += d
                out["sum"] = str(total)
            if cw is not None:
                n = 0
                for rowno, r in members:
                    d, bad = _num(r.get(cw_col, ""), cw_col, rowno)
                    if bad:
                        return None, bad
                    if d > cw_gt:
                        n += 1
                out["count_where"] = n
            if mcols is not None:
                total = Decimal(0)
                for rowno, r in members:
                    da, bad = _num(r.get(mcols[0], ""), mcols[0], rowno)
                    if bad:
                        return None, bad
                    db, bad = _num(r.get(mcols[1], ""), mcols[1], rowno)
                    if bad:
                        return None, bad
                    total += da * db
                out["multiply_sum"] = str(total)
            return out, None

        facts = {"path": rel, "rows": len(picked)}
        if filt is not None:
            facts["filter"] = {"column": fcol, "equals": feq}
        if gcol is None:
            m, bad = metrics(picked)
            if bad:
                return False, bad
            facts.update(m)
        else:
            groups = {}
            for rowno, r in picked:
                groups.setdefault(str(r.get(gcol, "")),
                                  []).append((rowno, r))
            facts["group_by"] = gcol
            g_out = {}
            for g in sorted(groups):
                m, bad = metrics(groups[g])
                if bad:
                    return False, bad
                g_out[g] = m
            facts["groups"] = g_out
            if want_top:
                best = None
                for g in sorted(g_out):
                    s = Decimal(g_out[g]["sum"])
                    if best is None or s > best[1]:
                        best = (g, s)
                facts["top_by_sum"] = {"group": best[0],
                                       "sum": str(best[1])}
        return True, json.dumps(facts, ensure_ascii=False,
                                sort_keys=True)

    # --------------------------------------- verify_file_contains
    def _verify_contains(args):
        rel = str(args.get("path") or "")
        subs = args.get("contains")
        if not isinstance(subs, list) or not subs \
                or not all(isinstance(s, str) and s for s in subs):
            return False, ("verify_file_contains needs "
                           "'contains': a non-empty list of "
                           "strings that must ALL be present")
        target = _confined(root_real, rel)
        if target is None:
            return _refused(rel)
        if not os.path.isfile(target):
            return False, f"not a file: {rel!r}"
        try:
            with open(target, "rb") as f:
                raw = f.read(VERIFY_READ_CAP + 1)
        except OSError as e:
            return False, f"read failed for {rel!r}: {e}"
        if len(raw) > VERIFY_READ_CAP:
            return False, (f"{rel!r} is larger than the "
                           f"{VERIFY_READ_CAP}-byte verify cap — "
                           f"refusing to verify a partial read")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            return False, (f"refused: {rel!r} is not valid UTF-8 "
                           f"text — cannot verify its contents")
        missing = [s for s in subs if s not in text]
        if missing:
            return False, (f"MISSING from {rel!r}: "
                           + "; ".join(repr(s) for s in missing))
        return True, (f"OK: {rel!r} contains all {len(subs)} "
                      f"required string(s)")

    # -------------------------------------------- verify_csv_rows
    def _verify_csv_rows(args):
        rel = str(args.get("path") or "")
        expect = args.get("expect")
        if not isinstance(expect, dict) or not expect:
            return False, ("verify_csv_rows needs an expect "
                           "object — one of: "
                           + ", ".join(_EXPECT_KEYS))
        unknown = sorted(set(expect) - set(_EXPECT_KEYS))
        if unknown:
            return False, (f"unknown expect key(s): "
                           f"{', '.join(unknown)} — supported: "
                           f"{', '.join(_EXPECT_KEYS)}")
        rows, fields, err = _read_csv(root_real, rel)
        if err:
            return err
        problems = []
        if "row_count" in expect:
            rc = expect["row_count"]
            if isinstance(rc, bool) or not isinstance(rc, int):
                return False, ("expect row_count must be an "
                               f"integer, got {rc!r}")
            if len(rows) != rc:
                problems.append(f"row_count: expected {rc}, "
                                f"found {len(rows)}")
        for key in ("must_contain", "must_not_contain"):
            if key not in expect:
                continue
            conds = expect[key]
            if isinstance(conds, dict):
                conds = [conds]
            if not isinstance(conds, list) or not conds \
                    or not all(isinstance(c, dict)
                               and "column" in c and "equals" in c
                               for c in conds):
                return False, (f"expect {key} must be a "
                               "{\"column\": ..., \"equals\": ...} "
                               "object or a list of them")
            for c in conds:
                col = c["column"]
                if col not in fields:
                    return False, (f"expect {key} names column "
                                   f"{col!r}, which is not in the "
                                   f"CSV header {fields}")
                found = any(str(r.get(col, "")) == str(c["equals"])
                            for r in rows)
                if key == "must_contain" and not found:
                    problems.append(
                        f"must_contain: no row with "
                        f"{col}={c['equals']!r}")
                if key == "must_not_contain" and found:
                    problems.append(
                        f"must_not_contain: found a row with "
                        f"{col}={c['equals']!r}")
        if "sorted" in expect:
            srt = expect["sorted"]
            if not isinstance(srt, dict) \
                    or "column" not in srt \
                    or srt.get("order") not in ("asc", "desc"):
                return False, ("expect sorted must be an object "
                               "{\"column\": ..., \"order\": "
                               "\"asc\"|\"desc\"}")
            col, order = srt["column"], srt["order"]
            if col not in fields:
                return False, (f"expect sorted names column "
                               f"{col!r}, which is not in the "
                               f"CSV header {fields}")
            prev = None
            for i, r in enumerate(rows):
                d, bad = _num(r.get(col, ""), col, i + 1)
                if bad:
                    problems.append(f"sorted: {bad}")
                    break
                if prev is not None and \
                        ((order == "desc" and d > prev)
                         or (order == "asc" and d < prev)):
                    problems.append(
                        f"sorted {order} by {col!r} violated at "
                        f"data row {i + 1}: {prev} then {d}")
                    break
                prev = d
        if problems:
            return False, (f"{rel!r} FAILED verification: "
                           + "; ".join(problems))
        return True, (f"OK: {rel!r} matches all expectations "
                      f"({len(rows)} data rows)")

    # ------------------------------------------------ filter_csv
    def _filter_csv(args):
        src_rel = str(args.get("source") or "")
        dst_rel = str(args.get("dest") or "")
        rows, fields, err = _read_csv(root_real, src_rel)
        if err:
            return err
        filt = args.get("filter")
        if filt is None:
            return False, ("filter_csv needs a filter object "
                           "{\"column\": ..., \"equals\": ...}")
        fcol, feq, bad = _parse_filter(filt, fields)
        if bad:
            return False, bad
        srt = args.get("sort")
        scol = sorder = None
        if srt is not None:
            scol, sorder, bad = _parse_sort(srt, fields)
            if bad:
                return False, bad
        picked = [(i + 1, r) for i, r in enumerate(rows)
                  if str(r.get(fcol, "")) == feq]
        out_rows = [r for _n, r in picked]
        if scol is not None:
            out_rows, bad = _sorted_rows(picked, scol, sorder)
            if bad:
                return False, bad
        target = _confined(root_real, dst_rel)
        if target is None or target == root_real:
            return _refused(dst_rel)
        if target == _confined(root_real, src_rel):
            return False, ("filter_csv dest must differ from its "
                           "source — overwriting the source would "
                           "destroy the file verify_csv_subset "
                           "checks the output against")
        if os.path.isdir(target):
            return False, f"is a directory: {dst_rel!r}"
        try:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "w", newline="",
                      encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=fields,
                                   lineterminator="\n")
                w.writeheader()
                for r in out_rows:
                    w.writerow({k: r.get(k, "") for k in fields})
        except (OSError, csv.Error) as e:
            return False, f"write failed for {dst_rel!r}: {e}"
        facts = {"source": src_rel, "dest": dst_rel,
                 "rows": len(out_rows),
                 "filter": {"column": fcol, "equals": feq}}
        if scol is not None:
            facts["sorted"] = {"column": scol, "order": sorder}
        return True, json.dumps(facts, ensure_ascii=False,
                                sort_keys=True)

    # --------------------------------------- verify_csv_subset
    def _verify_subset(args):
        src_rel = str(args.get("source") or "")
        out_rel = str(args.get("output") or "")
        srows, sfields, err = _read_csv(root_real, src_rel)
        if err:
            return err
        orows, ofields, err = _read_csv(root_real, out_rel)
        if err:
            return err
        filt = args.get("filter")
        if filt is None:
            return False, ("verify_csv_subset needs a filter "
                           "object {\"column\": ..., "
                           "\"equals\": ...}")
        fcol, feq, bad = _parse_filter(filt, sfields)
        if bad:
            return False, bad
        srt = args.get("sort")
        scol = sorder = None
        if srt is not None:
            scol, sorder, bad = _parse_sort(srt, sfields)
            if bad:
                return False, bad
        picked = [(i + 1, r) for i, r in enumerate(srows)
                  if str(r.get(fcol, "")) == feq]
        expected = [r for _n, r in picked]
        if scol is not None:
            expected, bad = _sorted_rows(picked, scol, sorder)
            if bad:
                return False, bad
        problems = []
        if ofields != sfields:
            problems.append(f"header differs: source header "
                            f"{sfields}, output header {ofields}")

        def _key(r):
            return tuple(str(r.get(c, "")) for c in sfields)

        exp_keys = [_key(r) for r in expected]
        out_keys = [_key(r) for r in orows]
        missing = list((Counter(exp_keys)
                        - Counter(out_keys)).elements())
        extra = list((Counter(out_keys)
                      - Counter(exp_keys)).elements())
        for k in missing[:3]:
            problems.append("missing row (in the source subset, "
                            f"not in the output): {list(k)}")
        if len(missing) > 3:
            problems.append(f"… and {len(missing) - 3} more "
                            f"missing row(s)")
        for k in extra[:3]:
            problems.append("extra row (in the output, not in "
                            f"the source subset): {list(k)}")
        if len(extra) > 3:
            problems.append(f"… and {len(extra) - 3} more "
                            f"extra row(s)")
        if not missing and not extra:
            for i, (a, b) in enumerate(zip(exp_keys, out_keys)):
                if a != b:
                    problems.append(
                        f"order differs at data row {i + 1}: "
                        f"expected {list(a)}, found {list(b)}")
                    break
        elif len(orows) != len(expected):
            problems.append(
                f"row count: expected {len(expected)} (source "
                f"rows with {fcol}={feq!r}), found {len(orows)}")
        if problems:
            return False, (f"{out_rel!r} FAILED subset "
                           f"verification against source "
                           f"{src_rel!r}: " + "; ".join(problems))
        order_txt = (f", sorted {sorder} by {scol!r}"
                     if scol is not None else "")
        return True, (f"OK: {out_rel!r} is exactly the subset of "
                      f"{src_rel!r} with {fcol}={feq!r} — "
                      f"{len(expected)} row(s), verbatim"
                      f"{order_txt}")

    reg.register(
        "compute_csv",
        "Compute exact facts from a workspace CSV with CODE (never in your head). Args: {path, spec}. Spec example: "
        + _SPEC_EXAMPLE +
        " — flat string forms (\"sum\": \"amount_inr\") and nested forms (\"sum\": {\"column\": \"amount_inr\"}, \"count\": {}) are both accepted. For LINE TOTALS — the sum of one column times another, like qty x price — use \"multiply_sum\": {\"columns\": [\"qty\", \"price\"]}; combined with \"group_by\" it returns that product-sum per group. Returns JSON facts. Read-only.",
        {"path": {"type": "string", "required": True,
                  "desc": "CSV path inside the workspace"},
         "spec": {"type": "object", "required": True,
                  "desc": "declarative spec — example: "
                          + _SPEC_EXAMPLE}},
        _compute_csv, timeout=30)
    reg.register(
        "verify_file_contains",
        "Verify a workspace text file contains ALL of the required strings. Args: {path, contains:[...]}. OK only if every string is present; FAILED lists the missing ones. Read-only.",
        {"path": {"type": "string", "required": True,
                  "desc": "file path inside the workspace"},
         "contains": {"type": "array", "required": True,
                      "desc": "strings that must ALL be present"}},
        _verify_contains, timeout=15)
    reg.register(
        "verify_csv_rows",
        "Verify a workspace CSV against expectations: row_count, must_contain / must_not_contain {column,equals}, sorted {column, order asc|desc}. Args: {path, expect}. OK only if all match; FAILED names the mismatch. Read-only.",
        {"path": {"type": "string", "required": True,
                  "desc": "CSV path inside the workspace"},
         "expect": {"type": "object", "required": True,
                    "desc": "expectations: row_count/must_contain/must_not_contain/sorted"}},
        _verify_csv_rows, timeout=30)
    reg.register(
        "filter_csv",
        "Produce a filtered (and optionally sorted) copy of a workspace CSV BY CODE: the rows matching filter {column,equals} are copied from source to dest VERBATIM (all columns, original values), header preserved, sort {column, order asc|desc} numeric-aware. Args: {source, dest, filter, sort?}. Example: {\"source\": \"orders.csv\", \"dest\": \"cleaned.csv\", \"filter\": {\"column\": \"status\", \"equals\": \"completed\"}, \"sort\": {\"column\": \"amount_inr\", \"order\": \"desc\"}}. Returns JSON with the row count and dest. Use this — never copy rows into an output file yourself. Mutating (writes dest) — needs Allow.",
        {"source": {"type": "string", "required": True,
                    "desc": "source CSV path inside the workspace"},
         "dest": {"type": "string", "required": True,
                  "desc": "output CSV path inside the workspace"},
         "filter": {"type": "object", "required": True,
                    "desc": "{\"column\": ..., \"equals\": ...} — rows whose column equals the value are copied"},
         "sort": {"type": "object", "required": False,
                  "desc": "{\"column\": ..., \"order\": \"asc\"|\"desc\"} — numeric-aware ordering of the copied rows"}},
        _filter_csv, mutating=True, timeout=30)
    reg.register(
        "verify_csv_subset",
        "Verify a workspace CSV is EXACTLY a filtered/sorted subset of a SOURCE CSV: the output's rows must equal the source rows matching filter {column,equals} verbatim in every column, count included, in the sort order when sort {column, order asc|desc} is given. Args: {source, output, filter, sort?}. Example: {\"source\": \"orders.csv\", \"output\": \"cleaned.csv\", \"filter\": {\"column\": \"status\", \"equals\": \"completed\"}, \"sort\": {\"column\": \"amount_inr\", \"order\": \"desc\"}}. Compared against the source itself — relabelled, dropped, extra or misordered rows FAIL with the specific mismatch. Read-only.",
        {"source": {"type": "string", "required": True,
                    "desc": "source CSV path inside the workspace"},
         "output": {"type": "string", "required": True,
                    "desc": "output CSV path inside the workspace"},
         "filter": {"type": "object", "required": True,
                    "desc": "{\"column\": ..., \"equals\": ...} — the subset the output must equal"},
         "sort": {"type": "object", "required": False,
                  "desc": "{\"column\": ..., \"order\": \"asc\"|\"desc\"} — the order the output rows must be in"}},
        _verify_subset, timeout=30)
    return reg
