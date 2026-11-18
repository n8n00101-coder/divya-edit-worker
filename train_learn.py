"""Train mode (Nod Phase 1.75): Julie auto-learns from conversations.

Ajju's order (2026-11-18): NO manual porting. Julie learns automatically
from (1) divya's chats with Ajju — the digest divya appends at
``~/workspace/julie-train/DIGEST.md`` — and (2) Ajju's Nod chats, via a
Nod export file. Nobody hand-carries rules any more; this module is the
whole loop:

    sources -> STAGING ledger -> safety gate + wrong-reply battery
            -> LIVE learnings (only if the battery is green)

A failing gate or battery leaves the entry HELD in staging with the
reason written down — one bad conversation can never corrupt Julie
(the Phase 1.75 safety law). Every run writes an after-report
(LAST_RUN.md) saying what was learned, what was held, and why.

Live learnings land in two places, both of which Julie already reads:
  * ``skills/learned/train_live.json`` — the ledger of record. The
    Worker mirrors it into KV (ulearn:) via ulearnSync and injects the
    rules into every brain call through memContext (WA + app).
  * ``skills/learned/prompt_notes.md`` — appended in self_learn's
    format; brain.py's prompt_notes() already feeds it to the runner
    brain. (self_learn.py itself is NOT imported: in this repo its
    ``state``/``skill_hub`` imports don't exist and its daily() is a
    web-research loop, not conversation learning. Its prompt-notes
    CHANNEL is the genuine fit, so promotion writes through it.
    learn.py is not wired either: it distils video-editing tutorials
    into fx_ helpers for the codegen few-shot pool — a different store
    for a different consumer, nothing to do with reply rules.)

Digest entry shape (one line):
    N. USER: "..." -> REPLY: ... -> RULE: ...
(the digest uses the unicode arrow; see DIGEST.md)

Nod export shape (JSON) — what the importer accepts:
    {
      "exported_at": "2026-11-18T00:00:00Z",
      "learnings": [{"user": "...", "reply": "...", "rule": "..."}],
      "conversations": [
        {"id": "...", "rule": "optional rule distilled by Nod",
         "messages": [{"role": "user", "text": "..."},
                      {"role": "assistant", "text": "..."}]}
      ]
    }
A conversation WITHOUT a "rule" is counted and skipped — this module
never invents a rule Nod didn't state.

Usage:
    python3 train_learn.py run [--digest PATH] [--nod-export PATH]
        [--ledger-dir DIR] [--report PATH]
        [--battery-cmd CMD ...] [--skip-battery]
Exit 0 = run completed (holds are normal outcomes, printed in the
summary JSON on the last line). Non-zero = the run itself crashed.
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent
DEFAULT_DIGEST = Path.home() / "workspace" / "julie-train" / "DIGEST.md"
DEFAULT_LEDGER_DIR = REPO / "skills" / "learned"
DEFAULT_REPORT = Path.home() / "workspace" / "julie-train" / "LAST_RUN.md"
MAX_RULE = 300

# ------------------------------------------------------------ gate rules
_SECRET_RX = re.compile(
    r"(sk-[A-Za-z0-9_-]{10,}|ghp_[A-Za-z0-9]{10,}|gho_[A-Za-z0-9]{10,}|"
    r"AKIA[A-Z0-9]{10,}|xox[bap]-[A-Za-z0-9-]{10,}|api[_ ]?key\s*[:=]\s*\S{8,})")
_EMAIL_RX = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RX = re.compile(r"(?<!\d)(?:\+?91[\s-]?)?[6-9]\d{9}(?!\d)")
_INJECT_RX = re.compile(
    r"(ignore (all |the )?(previous|above)|disregard|system prompt|"
    r"you are now|new instructions?:|override (the )?(rules|system))", re.I)
# A candidate rule must never teach Julie to break the REPLY SYSTEM:
# no unasked menu dumps, no invented state, no multi-replies, no
# ignoring Stop. Focused phrase scan (EN + romanized Telugu).
_CONTRA_RX = re.compile(
    r"(menu|options list|style list).{0,30}(dump|ivvu|cheppu|pampu|send|show)|"
    r"(invent|guess).{0,20}(status|count|percent|progress)|"
    r"(okka message ki|per message).{0,20}(rendu|two|multiple|anni) repl|"
    r"stop.{0,20}(ignore|vaddu|cheyaku)", re.I)


def gate_rule(rule, known_norm):
    """Deterministic safety lint for one candidate rule.
    Returns (ok, reason). known_norm = set of normalized live+staged
    rule texts (duplicate check)."""
    r = (rule or "").strip()
    if len(r) < 10:
        return False, "rule too short to mean anything"
    if len(r) > MAX_RULE:
        return False, f"rule too long ({len(r)} > {MAX_RULE} chars)"
    if _SECRET_RX.search(r):
        return False, "looks like it contains a secret/API key"
    if _EMAIL_RX.search(r) or _PHONE_RX.search(r):
        return False, "contains a personal identifier (email/phone)"
    if _INJECT_RX.search(r):
        return False, "prompt-injection / override marker"
    if _CONTRA_RX.search(r):
        return False, "contradicts the REPLY SYSTEM (menu dump / invented state / multi-reply / ignore-stop)"
    if _norm(r) in known_norm:
        return False, "duplicate of an existing learning"
    return True, ""


def _norm(text):
    return re.sub(r"[^a-z0-9 ]", "", (text or "").lower()).strip()


def _eid(source, user, rule):
    return hashlib.sha1(f"{source}|{user}|{rule}".encode("utf-8")).hexdigest()[:12]


# ------------------------------------------------------------ sources
_DIGEST_RX = re.compile(
    r"^\d+\.\s+USER:\s*(.+?)\s*→\s*REPLY:\s*(.+?)\s*→\s*RULE:\s*(.+?)\s*$")
_DATE_RX = re.compile(r"^##\s+(\d{4}-\d{2}-\d{2})")


def parse_digest(path):
    """DIGEST.md -> [{id, source, date, user, reply, rule}]."""
    out, date = [], ""
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        m = _DATE_RX.match(line)
        if m:
            date = m.group(1)
            continue
        m = _DIGEST_RX.match(line.strip())
        if not m:
            continue
        user = m.group(1).strip().strip('"')
        reply, rule = m.group(2).strip(), m.group(3).strip()
        out.append({"id": _eid("divya-digest", user, rule),
                    "source": "divya-digest", "date": date,
                    "user": user, "reply": reply, "rule": rule})
    return out


def parse_nod_export(path):
    """Nod export JSON -> (entries, skipped_no_rule). See module docstring
    for the accepted shape. Raw conversations without a stated rule are
    counted, never converted — no invented rules."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    out, skipped = [], 0
    for e in data.get("learnings", []) or []:
        user = str(e.get("user", "")).strip()
        reply = str(e.get("reply", "")).strip()
        rule = str(e.get("rule", "")).strip()
        if not rule:
            skipped += 1
            continue
        out.append({"id": _eid("nod", user, rule), "source": "nod",
                    "date": str(e.get("date", ""))[:10],
                    "user": user, "reply": reply, "rule": rule})
    for c in data.get("conversations", []) or []:
        rule = str(c.get("rule", "")).strip()
        msgs = c.get("messages", []) or []
        users = [str(m.get("text", "")) for m in msgs if m.get("role") == "user"]
        assts = [str(m.get("text", "")) for m in msgs if m.get("role") == "assistant"]
        if not rule or not users:
            skipped += 1
            continue
        user = users[0].strip()
        out.append({"id": _eid("nod", user, rule), "source": "nod",
                    "date": str(c.get("date", ""))[:10], "user": user,
                    "reply": assts[-1].strip() if assts else "", "rule": rule})
    return out, skipped


# ------------------------------------------------------------ ledgers
def _load(path, key):
    try:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        v = d.get(key, [])
        return v if isinstance(v, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save(path, key, rows):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps({key: rows}, indent=2, ensure_ascii=False),
                          encoding="utf-8")


def _append_prompt_notes(ledger_dir, rows, today):
    Path(ledger_dir).mkdir(parents=True, exist_ok=True)
    p = Path(ledger_dir) / "prompt_notes.md"
    old = p.read_text(encoding="utf-8") if p.exists() else ""
    lines = [ln for ln in (f"- ({today}) {r['rule']}" for r in rows)
             if ln not in old]
    if lines:
        p.write_text(old + ("\n" if old and not old.endswith("\n") else "")
                     + "\n".join(lines) + "\n", encoding="utf-8")
    return len(lines)


# ------------------------------------------------------------ battery
def run_battery(cmds):
    """Run the wrong-reply battery commands; (ok, detail) — ok only if
    EVERY command exits 0."""
    detail = []
    for cmd in cmds:
        try:
            r = subprocess.run(cmd, shell=True, cwd=REPO,
                               capture_output=True, text=True, timeout=600)
        except subprocess.TimeoutExpired:
            return False, f"battery timed out: {cmd}"
        tail = (r.stdout or "").strip().splitlines()
        detail.append(f"{cmd} -> exit {r.returncode}"
                      + (f" ({tail[-1][:80]})" if tail else ""))
        if r.returncode != 0:
            return False, "; ".join(detail)
    return True, "; ".join(detail)


DEFAULT_BATTERY = ["node cfworker/replytest.mjs", "node cfworker/wa107test.mjs"]


# ------------------------------------------------------------ the run
def run(digest=None, nod_export=None, ledger_dir=DEFAULT_LEDGER_DIR,
        report=DEFAULT_REPORT, battery_cmds=None, skip_battery=False):
    ledger_dir = Path(ledger_dir)
    staging_path = ledger_dir / "train_staging.json"
    live_path = ledger_dir / "train_live.json"
    staging = _load(staging_path, "staging")
    live = _load(live_path, "live")
    known_ids = {e["id"] for e in staging} | {e["id"] for e in live}
    known_norm = {_norm(e.get("rule", "")) for e in staging + live}

    sources, skipped_no_rule = [], 0
    if digest and Path(digest).exists():
        sources += parse_digest(digest)
    if nod_export and Path(nod_export).exists():
        entries, skipped_no_rule = parse_nod_export(nod_export)
        sources += entries

    today = datetime.now().strftime("%Y-%m-%d")
    new_rows, dupes = [], 0
    for e in sources:
        if e["id"] in known_ids:
            dupes += 1
            continue
        row = {**e, "status": "staged", "reason": "", "staged_at": today}
        staging.append(row)
        new_rows.append(row)
        known_ids.add(e["id"])

    # Gate every still-staged row (new + previously staged), so a rule
    # held only for a battery failure gets retried on the next run.
    candidates, held_now = [], []
    for row in staging:
        if row.get("status") == "held" and row.get("reason", "").startswith("gate:"):
            continue  # gate holds are final until the rule text changes
        ok, reason = gate_rule(row["rule"], known_norm - {_norm(row["rule"])})
        if ok:
            candidates.append(row)
        else:
            row["status"], row["reason"] = "held", f"gate: {reason}"
            held_now.append(row)

    battery_ok, battery_detail = True, "skipped"
    if candidates and not skip_battery:
        battery_ok, battery_detail = run_battery(battery_cmds or DEFAULT_BATTERY)

    promoted = []
    if candidates and battery_ok:
        live_norms = {_norm(e.get("rule", "")) for e in live}
        for row in candidates:
            if _norm(row["rule"]) in live_norms:  # twin arrived in same run
                row["status"] = "held"
                row["reason"] = "gate: duplicate of an existing learning"
                held_now.append(row)
                continue
            row["status"], row["reason"] = "live", ""
            row["promoted_at"] = today
            live.append(row)
            live_norms.add(_norm(row["rule"]))
            promoted.append(row)
        staging = [r for r in staging if r.get("status") != "live"]
        _append_prompt_notes(ledger_dir, promoted, today)
    elif candidates:
        for row in candidates:
            row["status"] = "held"
            row["reason"] = f"battery failed: {battery_detail[:200]}"
            held_now.append(row)

    _save(staging_path, "staging", staging)
    _save(live_path, "live", live)

    summary = {"sources": len(sources), "new": len(new_rows), "dupes": dupes,
               "skipped_no_rule": skipped_no_rule,
               "battery": "skipped" if skip_battery else ("pass" if battery_ok else "fail"),
               "promoted": len(promoted), "held": len(held_now),
               "live_total": len(live)}
    _write_report(report, summary, promoted, held_now, battery_detail, today)
    return summary


def _write_report(path, s, promoted, held, battery_detail, today):
    if not path:
        return
    lines = [f"# Train-mode run — {today}", "",
             f"- Sources parsed: {s['sources']} entries "
             f"({s['new']} new, {s['dupes']} already known, "
             f"{s['skipped_no_rule']} skipped — no rule stated)",
             f"- Battery: {s['battery']} — {battery_detail}",
             f"- Promoted to LIVE: {s['promoted']}",
             f"- Held in staging: {s['held']}",
             f"- Live learnings total: {s['live_total']}", ""]
    if promoted:
        lines.append("## Promoted")
        lines += [f"- ({r['source']}) {r['rule']}" for r in promoted] + [""]
    if held:
        lines.append("## Held (with reason)")
        lines += [f"- ({r['source']}) {r['rule']} — {r.get('reason', '')}"
                  for r in held] + [""]
    lines.append("Live = train_live.json + prompt_notes.md in the repo; "
                 "the Worker mirrors train_live.json into KV (ulearn:) "
                 "within ~1h of merge and injects it via memContext.")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="train_learn.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--digest", default=str(DEFAULT_DIGEST))
    r.add_argument("--nod-export", default=None)
    r.add_argument("--ledger-dir", default=str(DEFAULT_LEDGER_DIR))
    r.add_argument("--report", default=str(DEFAULT_REPORT))
    r.add_argument("--battery-cmd", action="append", default=None)
    r.add_argument("--skip-battery", action="store_true")
    a = ap.parse_args(argv)
    summary = run(digest=a.digest, nod_export=a.nod_export,
                  ledger_dir=a.ledger_dir, report=a.report,
                  battery_cmds=a.battery_cmd, skip_battery=a.skip_battery)
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
