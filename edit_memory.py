"""edit_memory.py — Julie v84: persistent EDITING memory + Knowledge Base.

Two SQLite stores in one file (default: <repo>/julie_edit_memory.db,
override with env JULIE_EDIT_MEMORY or the db_path argument):

1. EDITING MEMORY (Stage 6 / P4) — deliberately separate from the
   conversational memory (hmem/umem in the Worker). It records, per
   job and scene: the selected footage, the REJECTED footage and the
   reason it was rejected, the editing decision taken, QC failures,
   corrections attempted and the final result, plus user-approved
   preferences. Its one hard behavioural contract: a visual rejected
   in Job 1 for a given context must be avoidable in Job 2 when the
   context is similar (token overlap on the scene's narration/why).

2. KNOWLEDGE BASE (Stage 6 / P5) — structured, versioned documentary
   editing rules converted (original concise wording) from Julie's
   handbook/research documents. Every rule carries: id, category,
   description, applies_when, measurable_check, priority, source,
   version, approval_status. Stored in a normal table + an FTS5
   index when the SQLite build offers FTS5 (checked at runtime;
   graceful LIKE fallback otherwise). Thresholds are CONFIG values,
   not laws — they live in the `config` table and can be calibrated.

3. LEARNING PROPOSALS (Stage 7 / P6) — a digest generator over the
   editing memory: repeated QC failures / rejection patterns become
   PROPOSED rule changes. A proposal NEVER activates itself: its
   status stays 'proposed' until approve_proposal() is called by a
   human-approved path, mirroring self_learn.py's approval gate.

Everything here is stdlib-only (sqlite3) and deterministic — no LLM,
no network. All functions are safe to call when the DB is missing or
unwritable: writes no-op with a printed warning, reads return empty.
"""

import json
import os
import re
import sqlite3
import time

SCHEMA_VERSION = 1

DEFAULT_CONFIG = {
    # Audio targets are STARTING points (YouTube practice), not laws.
    "loudness_lufs_target": -14.0,
    "loudness_tolerance": 1.0,
    "true_peak_max_dbtp": -1.0,
    "silence_gap_max_s": 0.8,
    "max_correction_rounds": 2,
    "vision_max_frames_per_candidate": 2,
    "vision_max_candidates_per_scene": 2,
    "vision_max_calls_per_job": 80,
    "similarity_min_token_overlap": 0.34,
}


def _tokens(text):
    return {t for t in re.findall(r"[a-z0-9]+", str(text or "").lower())
            if len(t) > 2}


def token_overlap(a, b):
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(1, min(len(ta), len(tb)))


def default_db_path():
    env = os.environ.get("JULIE_EDIT_MEMORY")
    if env:
        return env
    return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "julie_edit_memory.db")


class EditMemory:
    """SQLite editing memory + KB. Context-manager friendly."""

    def __init__(self, db_path=None):
        self.db_path = db_path or default_db_path()
        self.ok = False
        self.fts5 = False
        try:
            self.db = sqlite3.connect(self.db_path)
            self.db.row_factory = sqlite3.Row
            self._init_schema()
            self.ok = True
        except Exception as e:  # never crash the pipeline over memory
            print(f"edit_memory: disabled ({str(e)[:120]})")
            self.db = None

    # ------------------------------------------------------------ schema
    def _init_schema(self):
        c = self.db
        c.executescript("""
        CREATE TABLE IF NOT EXISTS meta(
            key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS config(
            key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS decisions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT, scene_id TEXT, ts REAL,
            kind TEXT,            -- selected | rejected | decision | qc_failure | correction | result | preference
            visual_key TEXT,      -- stable identity of the footage/visual (clip id or content hash)
            context TEXT,         -- narration + why text the decision was made for
            reason TEXT,          -- rejection reason / decision rationale
            detail TEXT);         -- JSON extras
        CREATE INDEX IF NOT EXISTS idx_dec_visual ON decisions(visual_key);
        CREATE INDEX IF NOT EXISTS idx_dec_kind ON decisions(kind);
        CREATE TABLE IF NOT EXISTS rules(
            rule_id TEXT PRIMARY KEY, category TEXT, description TEXT,
            applies_when TEXT, measurable_check TEXT, priority TEXT,
            source TEXT, version INTEGER, approval_status TEXT);
        CREATE TABLE IF NOT EXISTS proposals(
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL,
            title TEXT, evidence TEXT, proposed_change TEXT,
            status TEXT DEFAULT 'proposed');
        """)
        try:
            c.execute("CREATE VIRTUAL TABLE IF NOT EXISTS rules_fts "
                      "USING fts5(rule_id, category, description, "
                      "applies_when, measurable_check)")
            self.fts5 = True
        except sqlite3.OperationalError:
            self.fts5 = False
        for k, v in DEFAULT_CONFIG.items():
            c.execute("INSERT OR IGNORE INTO config(key, value) VALUES(?,?)",
                      (k, json.dumps(v)))
        c.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('schema', ?)",
                  (str(SCHEMA_VERSION),))
        c.commit()

    def close(self):
        try:
            if self.db:
                self.db.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()

    # ------------------------------------------------------------ config
    def config(self, key, default=None):
        if not self.ok:
            return DEFAULT_CONFIG.get(key, default)
        try:
            row = self.db.execute("SELECT value FROM config WHERE key=?",
                                  (key,)).fetchone()
            if row:
                return json.loads(row["value"])
        except Exception:
            pass
        return DEFAULT_CONFIG.get(key, default)

    def set_config(self, key, value):
        if not self.ok:
            return False
        self.db.execute("INSERT OR REPLACE INTO config(key, value) "
                        "VALUES(?,?)", (key, json.dumps(value)))
        self.db.commit()
        return True

    # ------------------------------------------------------- memory writes
    def _record(self, job_id, scene_id, kind, visual_key, context,
                reason, detail=None):
        if not self.ok:
            return False
        try:
            self.db.execute(
                "INSERT INTO decisions(job_id, scene_id, ts, kind, "
                "visual_key, context, reason, detail) VALUES(?,?,?,?,?,?,?,?)",
                (job_id, scene_id, time.time(), kind, visual_key, context,
                 reason, json.dumps(detail or {})))
            self.db.commit()
            return True
        except Exception as e:
            print(f"edit_memory: record failed ({str(e)[:100]})")
            return False

    def record_selection(self, job_id, scene_id, visual_key, context,
                         detail=None):
        return self._record(job_id, scene_id, "selected", visual_key,
                            context, "", detail)

    def record_rejection(self, job_id, scene_id, visual_key, context,
                         reason, detail=None):
        return self._record(job_id, scene_id, "rejected", visual_key,
                            context, reason, detail)

    def record_decision(self, job_id, scene_id, decision, context="",
                        visual_key="", detail=None):
        return self._record(job_id, scene_id, "decision", visual_key,
                            context, decision, detail)

    def record_qc_failure(self, job_id, rule, detail_text, scene_id=""):
        return self._record(job_id, scene_id, "qc_failure", "",
                            rule, detail_text)

    def record_correction(self, job_id, scene_id, what, result):
        return self._record(job_id, scene_id, "correction", "",
                            what, result)

    def record_result(self, job_id, result, detail=None):
        return self._record(job_id, "", "result", "", "", result, detail)

    def record_preference(self, key, value):
        return self._record("", "", "preference", key, "", str(value))

    def preferences(self):
        if not self.ok:
            return {}
        rows = self.db.execute(
            "SELECT visual_key, reason FROM decisions WHERE kind='preference'"
        ).fetchall()
        return {r["visual_key"]: r["reason"] for r in rows}

    # ------------------------------------------------------ memory reads
    def was_rejected(self, visual_key):
        if not self.ok or not visual_key:
            return None
        row = self.db.execute(
            "SELECT * FROM decisions WHERE kind='rejected' AND visual_key=? "
            "ORDER BY ts DESC LIMIT 1", (visual_key,)).fetchone()
        return dict(row) if row else None

    def should_avoid(self, visual_key, context, threshold=None):
        """The two-job contract: True (+ the original rejection record)
        when this exact visual was rejected before AND the new context
        is similar to the context it was rejected in."""
        rec = self.was_rejected(visual_key)
        if not rec:
            return False, None
        thr = threshold if threshold is not None else float(
            self.config("similarity_min_token_overlap"))
        if token_overlap(rec.get("context", ""), context) >= thr:
            return True, rec
        return False, None

    def rejection_reason_for(self, visual_key, context):
        avoid, rec = self.should_avoid(visual_key, context)
        if avoid:
            return (f"rejected in job {rec.get('job_id')} for a similar "
                    f"scene: {rec.get('reason')}")
        return None

    def decisions_for_job(self, job_id):
        if not self.ok:
            return []
        rows = self.db.execute(
            "SELECT * FROM decisions WHERE job_id=? ORDER BY id",
            (job_id,)).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------ KB
    def add_rule(self, rule, approve=False):
        """rule: dict with rule_id, category, description, applies_when,
        measurable_check, priority, source, version. approval_status is
        'proposed' unless approve=True (a human-approved path)."""
        if not self.ok:
            return False
        status = "approved" if approve else "proposed"
        try:
            self.db.execute(
                "INSERT OR REPLACE INTO rules(rule_id, category, "
                "description, applies_when, measurable_check, priority, "
                "source, version, approval_status) VALUES(?,?,?,?,?,?,?,?,?)",
                (rule["rule_id"], rule.get("category", ""),
                 rule.get("description", ""), rule.get("applies_when", ""),
                 rule.get("measurable_check", ""), rule.get("priority", "P2"),
                 rule.get("source", ""), int(rule.get("version", 1)), status))
            if self.fts5:
                self.db.execute("DELETE FROM rules_fts WHERE rule_id=?",
                                (rule["rule_id"],))
                self.db.execute(
                    "INSERT INTO rules_fts(rule_id, category, description, "
                    "applies_when, measurable_check) VALUES(?,?,?,?,?)",
                    (rule["rule_id"], rule.get("category", ""),
                     rule.get("description", ""), rule.get("applies_when", ""),
                     rule.get("measurable_check", "")))
            self.db.commit()
            return True
        except Exception as e:
            print(f"edit_memory: add_rule failed ({str(e)[:100]})")
            return False

    def load_rules(self, only_approved=True):
        if not self.ok:
            return []
        q = "SELECT * FROM rules"
        if only_approved:
            q += " WHERE approval_status='approved'"
        q += " ORDER BY rule_id"
        return [dict(r) for r in self.db.execute(q).fetchall()]

    def search_rules(self, query, only_approved=True):
        if not self.ok:
            return []
        if self.fts5:
            try:
                rows = self.db.execute(
                    "SELECT r.* FROM rules_fts f JOIN rules r "
                    "ON r.rule_id = f.rule_id WHERE rules_fts MATCH ? "
                    + ("AND r.approval_status='approved'" if only_approved else "")
                    + " ORDER BY r.rule_id",
                    (query,)).fetchall()
                return [dict(r) for r in rows]
            except sqlite3.OperationalError:
                pass
        like = f"%{query}%"
        rows = self.db.execute(
            "SELECT * FROM rules WHERE (description LIKE ? OR category "
            "LIKE ? OR applies_when LIKE ?)"
            + (" AND approval_status='approved'" if only_approved else "")
            + " ORDER BY rule_id", (like, like, like)).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------- learning proposals
    def propose_from_history(self, min_repeats=2):
        """Stage 7 digest: group repeated QC failures + rejection
        reasons; each repeated pattern becomes a PROPOSAL (never an
        active rule). Returns the list of new proposals created."""
        if not self.ok:
            return []
        created = []
        rows = self.db.execute(
            "SELECT context, COUNT(*) n FROM decisions WHERE "
            "kind='qc_failure' GROUP BY context HAVING n>=? ORDER BY n DESC",
            (min_repeats,)).fetchall()
        for r in rows:
            title = f"Recurring QC failure: {r['context']} (x{r['n']})"
            if self.db.execute("SELECT 1 FROM proposals WHERE title=?",
                               (title,)).fetchone():
                continue
            self.db.execute(
                "INSERT INTO proposals(ts, title, evidence, "
                "proposed_change, status) VALUES(?,?,?,?, 'proposed')",
                (time.time(), title,
                 f"{r['n']} recorded QC failures of this rule across jobs",
                 f"Add or tighten a Knowledge Base rule for "
                 f"'{r['context']}' and a pre-render check that catches "
                 f"it before assembly."))
            created.append(title)
        rows = self.db.execute(
            "SELECT reason, COUNT(*) n FROM decisions WHERE "
            "kind='rejected' AND reason != '' GROUP BY reason "
            "HAVING n>=? ORDER BY n DESC", (min_repeats,)).fetchall()
        for r in rows:
            title = f"Recurring footage rejection: {r['reason'][:60]} (x{r['n']})"
            if self.db.execute("SELECT 1 FROM proposals WHERE title=?",
                               (title,)).fetchone():
                continue
            self.db.execute(
                "INSERT INTO proposals(ts, title, evidence, "
                "proposed_change, status) VALUES(?,?,?,?, 'proposed')",
                (time.time(), title,
                 f"{r['n']} rejections with this reason",
                 "Tighten the footage-selection scoring so candidates "
                 "matching this rejection pattern are deprioritised "
                 "before download."))
            created.append(title)
        self.db.commit()
        return created

    def list_proposals(self, status=None):
        if not self.ok:
            return []
        q = "SELECT * FROM proposals"
        args = ()
        if status:
            q += " WHERE status=?"
            args = (status,)
        return [dict(r) for r in self.db.execute(q + " ORDER BY id", args)]

    def approve_proposal(self, proposal_id):
        """Human approval gate — the ONLY way a proposal can move.
        Approving records it; turning it into an active KB rule still
        goes through add_rule(..., approve=True) by the approver."""
        if not self.ok:
            return False
        cur = self.db.execute(
            "UPDATE proposals SET status='approved' WHERE id=? AND "
            "status='proposed'", (proposal_id,))
        self.db.commit()
        return cur.rowcount == 1


# ------------------------------------------------------------- KB seed
# Original concise rules distilled from Julie's handbook/research docs
# (Blind/Hark mails + v79 spec + the v84 research library). Thresholds
# reference config keys — they are starting points, not universal laws.
SEED_RULES = [
    {"rule_id": "ST-1", "category": "story",
     "description": "A documentary has exactly one opening hook and one final ending; chapters continue the story, they do not re-open or re-close it.",
     "applies_when": "long documentary planning and assembly",
     "measurable_check": "structural lint: end-card/CTA scenes only in the final chapter; opening hook only in chapter 1",
     "priority": "P0", "source": "Blind mail 3 R8; v84 research Doc 3 ST-1", "version": 1},
    {"rule_id": "ST-2", "category": "story",
     "description": "Pass the whole-documentary arc (hook, central question, context, evidence, contradictions, emotional development, turning points, build-up, payoff, conclusion) into every chapter brief.",
     "applies_when": "long documentary chapter planning",
     "measurable_check": "chapter briefs contain the arc context block",
     "priority": "P0", "source": "v84 implementation brief P2", "version": 1},
    {"rule_id": "VF-1", "category": "visual",
     "description": "Choose footage by the MEANING of the narration line, never by a fixed scene-category template; record why each visual matches.",
     "applies_when": "every scene's footage selection",
     "measurable_check": "each footage scene carries a 'why' field; vision verification verdict recorded",
     "priority": "P0", "source": "Blind mail 3; v84 brief P1", "version": 1},
    {"rule_id": "VF-2", "category": "visual",
     "description": "Never reuse the same clip in one video, and never re-select a visual that editing memory says was rejected for a similar context.",
     "applies_when": "footage pool assignment",
     "measurable_check": "no duplicate clip ids per video; memory should_avoid() consulted before assignment",
     "priority": "P0", "source": "Blind mail 1 Part 2 (NO-REPEAT); v84 P4", "version": 1},
    {"rule_id": "VF-3", "category": "visual",
     "description": "Verify B-roll with sampled frames (max 2 per candidate, max 2 candidates per scene, capped calls per job, hash-cached). An UNVERIFIED visual is reported as UNVERIFIED, never as verified.",
     "applies_when": "B-roll selection when vision is available",
     "measurable_check": "verification log lines with verdict + call count within cap",
     "priority": "P0", "source": "v84 brief P1 limits", "version": 1},
    {"rule_id": "CT-1", "category": "cuts",
     "description": "A hard cut is the default. A transition or effect must earn its place; never stack effects on one moment.",
     "applies_when": "editing director review of the scene plan",
     "measurable_check": "director log: one primary effect per scene; transitions only at idea boundaries",
     "priority": "P1", "source": "Hark rule (one effect at a time); v84 P3", "version": 1},
    {"rule_id": "CT-2", "category": "cuts",
     "description": "Internal production labels (HOOK, FACT, CTA, NEXT…) never appear as on-screen titles.",
     "applies_when": "plan audit before render",
     "measurable_check": "compliance banned-title check",
     "priority": "P0", "source": "Blind mail 3 R6", "version": 1},
    {"rule_id": "AU-1", "category": "audio",
     "description": "Deliver at the configured loudness target (default about -14 LUFS, true peak at or below -1 dBTP); tolerance is configurable.",
     "applies_when": "assembled-file media audit",
     "measurable_check": "ffmpeg loudnorm/ebur128 measurement in compliance_report.json",
     "priority": "P0", "source": "Blind mail 3 R11; v84 brief §6", "version": 1},
    {"rule_id": "AU-2", "category": "audio",
     "description": "Silence is intentional only where the Director logs it (after a turning point, before the payoff, before the ending); unexplained gaps over the configured maximum are defects.",
     "applies_when": "media audit + director review",
     "measurable_check": "silence-gap check cross-referenced with director silence map",
     "priority": "P1", "source": "v84 research Doc 2-E; Sequence v2 §5", "version": 1},
    {"rule_id": "AU-3", "category": "audio",
     "description": "Music intensity follows the story arc (hook higher, build lower, dip at the turning point, lift at the payoff, decay at the ending) and always ducks under narration.",
     "applies_when": "director review + music mixing",
     "measurable_check": "director music curve logged per arc section",
     "priority": "P1", "source": "v84 P3; Sequence v2 §5.3", "version": 1},
    {"rule_id": "CC-1", "category": "colour",
     "description": "Keep one consistent visual treatment across the whole video; do not mix unrelated looks chapter to chapter.",
     "applies_when": "assembly and media audit",
     "measurable_check": "same grade/filter chain recorded for all chapters",
     "priority": "P2", "source": "v84 research Doc 3 (colour consistency)", "version": 1},
    {"rule_id": "FA-1", "category": "facts",
     "description": "Numbers and claims on screen must match the narration and a real source; a source line is shown only when sources are actually used, never faked from a rotation.",
     "applies_when": "plan audit + requirement verdicts",
     "measurable_check": "compliance source/number checks; verdicts PASS only with evidence",
     "priority": "P0", "source": "Blind mail 3 R1-R12", "version": 1},
    {"rule_id": "QC-1", "category": "qc",
     "description": "QC runs on every job, spec or no spec. A check that did not run is UNVERIFIED — never PASS. A failed check is reported and the video is still delivered (warn-and-deliver).",
     "applies_when": "every job's compliance report",
     "measurable_check": "compliance_report.json exists for a forced no-spec fixture with all checks present",
     "priority": "P0", "source": "Ajju Q8 decision; v84 brief P0-A", "version": 1},
    {"rule_id": "QC-2", "category": "qc",
     "description": "Correction is bounded: at most the configured number of rounds (default 2), the true round count is recorded, and an uncorrectable defect is reported honestly.",
     "applies_when": "chapter + assembled-file correction loops",
     "measurable_check": "compliance_report.json fix_rounds equals the attempts actually made",
     "priority": "P0", "source": "Blind FIX 5/R12; v84 brief P0-B", "version": 1},
]


def seed_knowledge_base(mem, approve=True):
    """Load SEED_RULES into the KB. Idempotent (INSERT OR REPLACE on
    rule_id, keeping the stored version unless the seed is newer)."""
    n = 0
    for r in SEED_RULES:
        existing = None
        if mem.ok:
            row = mem.db.execute("SELECT version FROM rules WHERE rule_id=?",
                                 (r["rule_id"],)).fetchone()
            existing = row["version"] if row else None
        if existing is not None and existing >= r["version"]:
            continue
        if mem.add_rule(r, approve=approve):
            n += 1
    return n


def open_default():
    return EditMemory()


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        m = EditMemory(os.path.join(td, "t.db"))
        assert m.ok and m.fts5
        print("seeded rules:", seed_knowledge_base(m))
        print("rules loaded:", len(m.load_rules()))
        print("search 'silence':", [r["rule_id"] for r in m.search_rules("silence")])
        m.record_rejection("job1", "s1", "clipX", "people feel alone in a crowd",
                           "clip shows an empty beach, unrelated")
        avoid, rec = m.should_avoid("clipX", "people feel alone even in a crowd of strangers")
        print("two-job avoid:", avoid, "|", (rec or {}).get("reason"))
        print("edit_memory self-check OK")
