"""learning_loop.py — Julie v84 Stage 7 (P6): the approval-based
learning loop.

Verified behaviour of the existing components (inspected 2026-11-14
on main 5263eac, NOT assumed):
- learn.py distils rules/few-shot effects from tutorials & books
  into a JSON store (divya-learn.json); it learns new visual effects,
  it does NOT learn from editing mistakes, and nothing in the create
  pipeline calls it (only the chat/teaching path does).
- self_learn.py runs a daily web-research job whose improvements are
  PENDING until a human approves them (approve() applies the note to
  the prompt) — the approval-gate pattern already exists there.

This module adds the missing mistake-driven half, following the same
gate: job -> QC results -> editing mistakes -> repeated patterns ->
PROPOSED rule improvements (digest with evidence) -> approval
required -> only an approved proposal may become an active KB rule,
and even then only via the explicit activate() call below, made by
an approving human path. NOTHING here auto-activates a rule.
"""

import edit_memory


def build_digest(mem, min_repeats=2):
    """Create proposals from repeated patterns in editing memory and
    return the full digest (all proposals with their status)."""
    created = mem.propose_from_history(min_repeats=min_repeats)
    return {"new_proposals": created,
            "proposals": mem.list_proposals(),
            "approval_required": True,
            "note": "Proposals are inert until approved; approval "
                    "never happens automatically."}


def approve(mem, proposal_id):
    """The human gate. Marks a proposal approved (delegates to the
    memory store's guarded UPDATE). Returns True only if a pending
    proposal actually transitioned."""
    return mem.approve_proposal(proposal_id)


def activate(mem, proposal_id):
    """Turn an APPROVED proposal into an active Knowledge Base rule.
    Refuses (returns False) for any proposal that is not approved —
    this refusal is the learning loop's core safety property, and it
    is covered by v84test test 16."""
    for p in mem.list_proposals():
        if p["id"] == proposal_id:
            if p["status"] != "approved":
                return False
            rule = {"rule_id": f"LRN-{proposal_id}",
                    "category": "learned",
                    "description": p["proposed_change"],
                    "applies_when": "learned from repeated job evidence",
                    "measurable_check": p["evidence"],
                    "priority": "P2",
                    "source": f"learning loop proposal {proposal_id}: {p['title']}",
                    "version": 1}
            return mem.add_rule(rule, approve=True)
    return False


def digest_from_jobs(jobs, db_path=None, min_repeats=2):
    """Convenience: record a list of job outcome dicts into memory,
    then build the digest. jobs: [{job_id, qc_failures: [rule,...],
    rejections: [{visual, context, reason}]}]."""
    mem = edit_memory.EditMemory(db_path)
    try:
        for j in jobs or []:
            for rule in j.get("qc_failures") or []:
                mem.record_qc_failure(j.get("job_id", ""), rule,
                                      "recorded by learning loop digest")
            for r in j.get("rejections") or []:
                mem.record_rejection(j.get("job_id", ""), "",
                                     r.get("visual", ""), r.get("context", ""),
                                     r.get("reason", ""))
        return build_digest(mem, min_repeats=min_repeats)
    finally:
        mem.close()


if __name__ == "__main__":
    import os
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        db = os.path.join(td, "m.db")
        d = digest_from_jobs([
            {"job_id": "j1", "qc_failures": ["R12", "R12"]},
            {"job_id": "j2", "qc_failures": ["R12"]},
        ], db_path=db)
        print("proposals:", [p["title"] for p in d["proposals"]])
        mem = edit_memory.EditMemory(db)
        pid = d["proposals"][0]["id"]
        assert activate(mem, pid) is False, "unapproved proposal activated!"
        assert approve(mem, pid) is True
        assert activate(mem, pid) is True
        print("learning_loop self-check OK (gate held, then activated after approval)")
        mem.close()
