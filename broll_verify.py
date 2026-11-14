"""broll_verify.py — Julie v84 Stage 3 (P1): B-roll vision verification.

For every footage candidate: sample representative frames, ask the
existing vision stack (doc3.vision/vjson — the same free rotation the
stills path uses) whether the ACTUAL visual content matches the
narration + the scene's recorded 'why', and reject unrelated footage
with the reason recorded. Keyword matching is NOT verification.

Hard limits (Ajju's brief, also Knowledge Base rule VF-3):
- at most 2 sampled frames per candidate,
- at most 2 candidates checked per scene,
- a per-job vision-call budget (default from edit_memory config,
  hard cap for the 60-90 s test is set by the caller),
- verdicts cached by CONTENT HASH (perceptual dHash of a sampled
  frame + the narration context) — a cached verdict never costs a
  second call,
- when vision is unavailable or errors, the verdict is UNVERIFIED —
  never a silent pass. The caller decides the fallback (keep the
  keyword-best candidate but report it UNVERIFIED).

The verifier is injectable (verifier=frames, narration, why -> dict)
so tests run fully offline with stubs. The default verifier lazily
imports doc3 (heavy) only when a real check is attempted.
"""

import hashlib
import json
import os
import subprocess
import tempfile

MAX_FRAMES = 2
MAX_CANDIDATES = 2


def dhash_file(path, size=8):
    """Perceptual hash of an image file (same algorithm family as
    doc3.dhash) — implemented locally so importing this module stays
    light. Returns a hex string or None."""
    try:
        from PIL import Image
        im = Image.open(path).convert("L").resize((size + 1, size))
        px = list(im.getdata())
        bits = []
        for r in range(size):
            row = px[r * (size + 1):(r + 1) * (size + 1)]
            bits += [1 if row[i] > row[i + 1] else 0 for i in range(size)]
        val = 0
        for b in bits:
            val = (val << 1) | b
        return f"{val:0{size * size // 4}x}"
    except Exception:
        return None


def sample_frames(clip_path, n=MAX_FRAMES, workdir=None):
    """Extract up to n frames spread across the clip (ffmpeg)."""
    n = max(1, min(MAX_FRAMES, int(n)))
    out = []
    try:
        dur = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(clip_path)],
            capture_output=True, text=True, timeout=30)
        total = float(dur.stdout.strip() or 0)
    except Exception:
        total = 0.0
    td = workdir or tempfile.mkdtemp(prefix="v84frames_")
    os.makedirs(td, exist_ok=True)
    for i in range(n):
        t = (total * (i + 1) / (n + 1)) if total else i * 2.0
        p = os.path.join(td, f"frame_{i}.jpg")
        r = subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.2f}", "-i",
             str(clip_path), "-frames:v", "1", "-vf", "scale=540:-2", p],
            capture_output=True, timeout=60)
        if r.returncode == 0 and os.path.exists(p) and os.path.getsize(p) > 0:
            out.append(p)
    return out


def _default_verifier(frames, narration, why):
    """Real vision via doc3.vjson (free rotation). Returns
    {'verdict': 'pass'|'fail'|'uncertain', 'reason': str}."""
    import doc3  # lazy: heavy module, only on a real check
    prompt = (
        "You verify documentary B-roll. The narration line is: "
        f"\"{narration}\". The editor chose this clip because: \"{why}\". "
        "Look at the frames. Does the ACTUAL visual content match the "
        "narration's meaning? Reply ONLY JSON: "
        "{\"match\": true/false, \"reason\": \"short reason\"}. "
        "If the frames are ambiguous, use {\"match\": \"uncertain\", "
        "\"reason\": \"why\"}.")
    res = doc3.vjson(prompt, frames)
    if not isinstance(res, dict):
        return {"verdict": "uncertain", "reason": "vision gave no verdict"}
    m = res.get("match")
    if m is True:
        return {"verdict": "pass", "reason": str(res.get("reason", ""))[:200]}
    if m is False:
        return {"verdict": "fail", "reason": str(res.get("reason", ""))[:200]}
    return {"verdict": "uncertain",
            "reason": str(res.get("reason", "ambiguous frames"))[:200]}


class BrollVerifier:
    """Stateful verifier for one job: budget, cache, memory hooks."""

    def __init__(self, call_budget=18, cache_path=None, memory=None,
                 job_id="", verifier=None):
        self.budget = int(call_budget)
        self.calls_made = 0
        self.cache_path = cache_path
        self.cache = {}
        if cache_path and os.path.exists(cache_path):
            try:
                self.cache = json.loads(open(cache_path, encoding="utf-8").read())
            except Exception:
                self.cache = {}
        self.memory = memory
        self.job_id = job_id
        self.verifier = verifier or _default_verifier
        self.log = []

    def _save_cache(self):
        if not self.cache_path:
            return
        try:
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(self.cache, f)
        except OSError:
            pass

    def _cache_key(self, frame_hash, narration, why):
        ctx = hashlib.sha256(f"{narration}|{why}".encode()).hexdigest()[:16]
        return f"{frame_hash}:{ctx}"

    def verify_candidate(self, cand, narration, why, workdir=None):
        """cand: dict with at least 'id' and 'path' (local clip file).
        Returns (verdict, reason, from_cache). verdict in
        pass/fail/uncertain/unverified."""
        cid = str(cand.get("id") or cand.get("path") or "?")
        # --- editing-memory pre-check: a visual rejected in an earlier
        # job for a similar context is rejected here at zero cost.
        if self.memory is not None:
            reason = None
            try:
                reason = self.memory.rejection_reason_for(
                    cid, f"{narration} {why}")
            except Exception:
                reason = None
            if reason:
                self.log.append({"candidate": cid, "verdict": "fail",
                                 "reason": f"editing memory: {reason}",
                                 "calls": 0})
                return "fail", f"editing memory: {reason}", False
        frames = sample_frames(cand.get("path", ""), MAX_FRAMES, workdir)
        if not frames:
            self.log.append({"candidate": cid, "verdict": "unverified",
                             "reason": "could not sample frames", "calls": 0})
            return "unverified", "could not sample frames", False
        fh = dhash_file(frames[0]) or hashlib.sha256(
            open(frames[0], "rb").read()).hexdigest()[:16]
        key = self._cache_key(fh, narration, why)
        if key in self.cache:
            v = self.cache[key]
            self.log.append({"candidate": cid, "verdict": v["verdict"],
                             "reason": v["reason"], "calls": 0,
                             "cached": True})
            return v["verdict"], v["reason"], True
        if self.calls_made >= self.budget:
            self.log.append({"candidate": cid, "verdict": "unverified",
                             "reason": f"vision call budget ({self.budget}) reached",
                             "calls": 0})
            return "unverified", "vision call budget reached", False
        self.calls_made += 1
        try:
            res = self.verifier(frames, narration, why)
            verdict = res.get("verdict", "uncertain")
            reason = str(res.get("reason", ""))[:200]
        except Exception as e:
            verdict, reason = "unverified", f"vision unavailable: {str(e)[:100]}"
        self.cache[key] = {"verdict": verdict, "reason": reason}
        self._save_cache()
        self.log.append({"candidate": cid, "verdict": verdict,
                         "reason": reason, "calls": 1})
        if self.memory is not None and verdict == "fail":
            try:
                self.memory.record_rejection(
                    self.job_id, "", cid, f"{narration} {why}", reason)
            except Exception:
                pass
        return verdict, reason, False

    def verify_scene(self, candidates, narration, why, workdir=None):
        """Check up to MAX_CANDIDATES candidates for one scene.
        Returns (chosen_or_None, results). A candidate with verdict
        'pass' wins; 'uncertain' is kept as a truthful fallback;
        'fail' is rejected with its reason recorded."""
        results = []
        fallback = None
        for cand in (candidates or [])[:MAX_CANDIDATES]:
            verdict, reason, cached = self.verify_candidate(
                cand, narration, why, workdir)
            results.append({"candidate": str(cand.get("id") or "?"),
                            "verdict": verdict, "reason": reason,
                            "cached": cached})
            if verdict == "pass":
                return cand, results
            if verdict in ("uncertain", "unverified") and fallback is None:
                fallback = cand
        return fallback, results


def hamming_hex(a, b):
    try:
        return bin(int(a, 16) ^ int(b, 16)).count("1")
    except Exception:
        return 999


def find_repeated(clips, max_distance=5, workdir=None):
    """Repeated-footage detection over local clip files: sample one
    frame per clip, dHash it, and group near-identical hashes.
    Returns a list of groups (lists of clip ids) of size >= 2."""
    hashes = {}
    for c in clips or []:
        frames = sample_frames(c.get("path", ""), 1, workdir)
        if frames:
            h = dhash_file(frames[0])
            if h:
                hashes[str(c.get("id") or c.get("path"))] = h
    groups, used = [], set()
    ids = list(hashes)
    for i, a in enumerate(ids):
        if a in used:
            continue
        grp = [a]
        for b in ids[i + 1:]:
            if b not in used and hamming_hex(hashes[a], hashes[b]) <= max_distance:
                grp.append(b)
                used.add(b)
        if len(grp) > 1:
            used.add(a)
            groups.append(grp)
    return groups
