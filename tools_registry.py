"""Julie agent engine (E2): the TOOLS REGISTRY.

E1 built the general agent loop (agent_loop.py) with a minimal,
hand-listed tool set (noop / echo stubs + one real tool, job_state).
E2 gives the loop a real tools layer: ONE registry that every tool
registers into, so the loop can call any tool in any order and the
brain is offered exactly — and only — what the registry holds.

A registry entry is the full contract the brain and the loop rely on:

    name         unique tool name (what the brain asks for)
    desc         ONE line — what the brain sees in the agentstep tool
                 list, so it must say what the tool does and its args
    schema       argument schema: {arg: {"type": "string"|"number"|
                 "boolean"|"object"|"array", "required": bool,
                 "desc": str}}. Args are validated against it BEFORE
                 the handler runs — bad args are a FAILED step with
                 the reason, never a handler crash on garbage.
    handler      callable(args: dict) following the agent_loop tool
                 contract: returns (ok, result) / {"ok", "result"} /
                 str / None, or raises (the loop turns a raise into a
                 FAILED step and feeds it back to the brain).
    mutating     True when the tool changes state (page, job, world)
                 instead of only reading.
    needs_allow  True when the tool is a mutating / external action
                 that must have the user's Allow before it may run
                 (defaults to the mutating flag). agent_loop REFUSES
                 an un-Allowed needs_allow call: the refusal is a
                 FAILED step fed back to the brain — the handler is
                 never executed silently.
    timeout      declared per-tool budget in seconds (metadata the
                 dispatch layer can enforce; the sync loop itself
                 does not preempt a running handler — see E2 report).
    cancel       E5: optional cooperative-cancellation hook (a
                 no-arg callable). A tool that can be interrupted
                 registers one; agent_loop then runs its handler
                 under stop polling and CALLS the hook when a stop
                 lands mid-run, so the handler can wind down
                 cleanly. Tools without a hook run synchronously
                 and are stopped at the next step checkpoint.
    stub         True for smoke-test stand-ins (noop / echo).

Real tools here WRAP the runner's existing implementations — nothing
is rewritten:

  - job_state            agent_loop.fetch_job_state (the runner job
                         endpoint read setup.get_job also uses)
  - browser_*            browse.py's action primitives (do_click /
                         do_type / do_select / snapshot) and
                         setup.py's goto / human_scroll, bound to one
                         live page via register_browser_tools(page)
  - file_* (E2.5)        workspace_tools.py's confined workspace
                         file primitives, bound to one per-job
                         workspace root via
                         register_workspace_tools(reg, root)
  - compute/verify (E7)  compute_tools.py's deterministic tools
                         (compute_csv / verify_file_contains /
                         verify_csv_rows), bound to the same root
                         via register_compute_tools(reg, root)
  - filter/subset (E8)   compute_tools.py's filter_csv (mutating,
                         needs Allow — produces a filtered/sorted
                         CSV by code) and verify_csv_subset
                         (read-only — checks an output against the
                         SOURCE rows), same registration call

GAP CLOSED (E2.5): E2 honestly recorded that there was NO file
read/list helper for a job workspace anywhere in the runner to wrap
(runner.py / create.py / setup.py / browse.py have no workspace
list/read primitive), so E2 registered no file tool. E2.5 closes
that gap with workspace_tools.py — purpose-built file_list /
file_read / file_write / file_append primitives, confined to a
per-job workspace root, registered via register_workspace_tools()
below exactly like the browser tools.

Production consumer (integration phase): agent_runner.py builds
one registry per agent job (default + workspace + compute tools)
and hands it to agent_loop through as_tools(). No existing
production flow (browse / setup / video) imports this module, and
providers.py / channel.py / brain content are untouched.
"""
import agent_loop

_ARG_TYPES = ("string", "number", "boolean", "object", "array")


def _type_ok(want, v):
    if want == "string":
        return isinstance(v, str)
    if want == "number":
        return isinstance(v, (int, float)) and not isinstance(v, bool)
    if want == "boolean":
        return isinstance(v, bool)
    if want == "object":
        return isinstance(v, dict)
    if want == "array":
        return isinstance(v, list)
    return True


def validate_args(schema, args):
    """Check args against a tool's schema. Returns an error string,
    or None when the args are acceptable. Missing optional args and
    extra args are fine (handlers read what they know); a missing
    required arg or a wrong-typed arg is not."""
    if not isinstance(args, dict):
        return "args must be an object"
    for name, spec in (schema or {}).items():
        if not isinstance(spec, dict):
            continue
        if name not in args or args.get(name) is None:
            if spec.get("required"):
                return f"missing required arg {name!r}"
            continue
        want = spec.get("type")
        if want in _ARG_TYPES and not _type_ok(want, args[name]):
            return f"arg {name!r} must be {want}, got {type(args[name]).__name__}"
    return None


class Registry:
    """An ordered set of tool entries. One registry per job context:
    default_registry() for the context-free tools, plus
    register_browser_tools(registry, page) when a live browser page
    exists (browser handlers close over that page)."""

    def __init__(self):
        self._tools = {}

    def register(self, name, desc, schema, handler, *, mutating=False,
                 needs_allow=None, timeout=60, stub=False, cancel=None):
        """Add one tool. needs_allow defaults to the mutating flag:
        a read-only tool never needs Allow; a mutating/external one
        does unless the registrant explicitly says otherwise (e.g.
        browser_scroll moves only the local view). cancel (E5) is
        the tool's cooperative-cancellation hook — see the module
        docstring."""
        if not name or not callable(handler):
            raise ValueError("a tool needs a name and a callable handler")
        if cancel is not None and not callable(cancel):
            raise ValueError("cancel must be a callable or None")
        if name in self._tools:
            raise ValueError(f"tool {name!r} already registered")
        entry = {
            "name": str(name),
            "desc": str(desc or ""),
            "schema": dict(schema or {}),
            "handler": handler,
            "mutating": bool(mutating),
            "needs_allow": bool(mutating if needs_allow is None else needs_allow),
            "timeout": int(timeout),
            "stub": bool(stub),
            "cancel": cancel,
        }
        self._tools[entry["name"]] = entry
        return entry

    def get(self, name):
        return self._tools.get(name)

    def names(self):
        return list(self._tools)

    def __contains__(self, name):
        return name in self._tools

    def __len__(self):
        return len(self._tools)

    def brain_list(self):
        """What the brain is offered through agentstep: names +
        one-line descriptions, in registration order — built from
        this registry and nothing else, so a tool the registry does
        not hold can never be offered (and agentstep + the loop both
        reject a call naming one)."""
        return [{"name": e["name"], "desc": e["desc"]}
                for e in self._tools.values()]

    def as_tools(self):
        """agent_loop-compatible tool dicts. Each dict's run()
        validates args against the entry's schema first (bad args =
        (False, reason), handler untouched), then calls the handler.
        The entry's mutating / needs_allow flags ride along so the
        loop's Allow gate can see them, and a registered cancel hook
        (E5) rides along so the loop can signal cooperative
        cancellation when a stop lands mid-run."""
        out = []
        for e in self._tools.values():
            d = {
                "name": e["name"],
                "desc": e["desc"],
                "schema": e["schema"],
                "mutating": e["mutating"],
                "needs_allow": e["needs_allow"],
                "run": self._runner(e),
            }
            if callable(e.get("cancel")):
                d["cancel"] = e["cancel"]
            out.append(d)
        return out

    @staticmethod
    def _runner(entry):
        def run(args):
            err = validate_args(entry["schema"], args or {})
            if err:
                return False, f"bad args for {entry['name']}: {err}"
            return entry["handler"](args or {})
        return run


# ------------------------------------------------------- default tools

def default_registry():
    """The context-free tools: E1's set, registered properly.
    noop / echo are stubs (marked as such); job_state and get_history
    are REAL — they wrap agent_loop's job-record reads over the runner
    channel."""
    reg = Registry()
    reg.register(
        "noop",
        "Do nothing and report ok. Stub for smoke tests.",
        {}, agent_loop._tool_noop, stub=True)
    reg.register(
        "echo",
        "Return the given text unchanged. Args: {text}. Stub.",
        {"text": {"type": "string", "required": True,
                  "desc": "the text to return"}},
        agent_loop._tool_echo, stub=True)
    reg.register(
        "job_state",
        "Read this job's own record (state, current step, note, recorded step count, plan). Read-only, no side effects.",
        {}, agent_loop._tool_job_state)
    reg.register(
        "get_history",
        "Retrieve the full step history from the job record. Args: {limit?, offset?} — limit defaults to 100, offset defaults to 0 (most recent first). Read-only, no side effects.",
        {"limit": {"type": "number", "required": False, "desc": "max steps to return (default 100, max 500)"},
         "offset": {"type": "number", "required": False, "desc": "skip this many most-recent steps (default 0)"}},
        agent_loop._tool_get_history, mutating=False, needs_allow=False, stub=False)
    return reg


# ------------------------------------------------------- browser tools

def register_browser_tools(reg, page):
    """Register the browser actions browse.py already executes,
    bound to one live Playwright page. Handlers wrap the EXISTING
    implementations — browse.do_click / do_type / do_select /
    snapshot and setup.goto / human_scroll — with the arg/outcome
    translation browse.run_browse itself performs (same clamps, same
    result strings). browse.py / setup.py are imported lazily: they
    pull in Playwright, which only the browser runner has.

    Classification: read = snapshot only. open / click / type /
    select can send data or change external state, so they are
    mutating AND need Allow. scroll / back only move the local view
    of the page the job already opened (mutating page state, no
    Allow). wait changes nothing."""
    import browse as B
    import setup as S

    def _read(args):
        snap = B.snapshot(page)
        els = snap.get("elements") or []
        lines = [f"url: {snap.get('url') or ''}",
                 f"title: {snap.get('title') or ''}",
                 "text: " + str(snap.get("text") or "")[:1200]]
        if els:
            lines.append("elements:")
            for e in els[:40]:
                lines.append(f"  {e.get('i')}: <{e.get('tag') or ''}> "
                             f"{str(e.get('label') or '')[:60]}")
        return True, "\n".join(lines)

    def _open(args):
        url = str(args.get("url") or "")
        if not (url.startswith("https://") or url.startswith("http://")):
            return False, f"bad url {url!r} — http(s) matrame"
        ok = S.goto(page, url)
        return bool(ok), "opened" if ok else f"open failed for {url}"

    def _click(args):
        return B.do_click(page, int(args["i"]))

    def _type(args):
        return B.do_type(page, int(args["i"]), str(args.get("text") or ""),
                         bool(args.get("submit")))

    def _select(args):
        return B.do_select(page, int(args["i"]), str(args.get("value") or ""))

    def _scroll(args):
        S.human_scroll(page, float(args.get("dy") or 600))
        return True, "scrolled"

    def _back(args):
        page.go_back(wait_until="domcontentloaded", timeout=20000)
        return True, "went back"

    def _wait(args):
        ms = max(200, min(10000, int(args.get("ms") or 1500)))
        page.wait_for_timeout(ms)
        return True, "waited"

    reg.register(
        "browser_read",
        "Read the current page state: URL, title, visible text and the indexed interactive elements (use the indices for click/type/select). Read-only.",
        {}, _read)
    reg.register(
        "browser_open",
        "Open a URL in the job's browser. Args: {url}.",
        {"url": {"type": "string", "required": True, "desc": "http(s) URL"}},
        _open, mutating=True, timeout=90)
    reg.register(
        "browser_click",
        "Click the snapshot element with index i. Args: {i}.",
        {"i": {"type": "number", "required": True,
               "desc": "element index from browser_read"}},
        _click, mutating=True, timeout=30)
    reg.register(
        "browser_type",
        "Type text into the snapshot element with index i. Args: {i, text, submit?}.",
        {"i": {"type": "number", "required": True,
               "desc": "element index from browser_read"},
         "text": {"type": "string", "required": True, "desc": "text to type"},
         "submit": {"type": "boolean", "required": False,
                    "desc": "press Enter after typing"}},
        _type, mutating=True, timeout=30)
    reg.register(
        "browser_select",
        "Choose a dropdown option by value on the snapshot element with index i. Args: {i, value}.",
        {"i": {"type": "number", "required": True,
               "desc": "element index from browser_read"},
         "value": {"type": "string", "required": True,
                   "desc": "option value to select"}},
        _select, mutating=True, timeout=30)
    reg.register(
        "browser_scroll",
        "Scroll the page by dy pixels (default 600). Args: {dy?}.",
        {"dy": {"type": "number", "required": False,
                "desc": "pixels to scroll"}},
        _scroll, mutating=True, needs_allow=False, timeout=30)
    reg.register(
        "browser_back",
        "Go back to the previous page. No args.",
        {}, _back, mutating=True, needs_allow=False, timeout=30)
    reg.register(
        "browser_wait",
        "Wait ms milliseconds (200-10000, default 1500). Args: {ms?}.",
        {"ms": {"type": "number", "required": False,
                "desc": "milliseconds to wait"}},
        _wait, timeout=15)
    return reg


# ---------------------------------------------------- workspace tools

def register_workspace_tools(reg, root, job_record=None):
    """Register the E2.5 + E10 workspace file tools (file_list / file_read
    read-only; file_write / file_append / edit_file mutating + needs Allow;
    search_text / list_files read-only; run_command mutating + needs Allow),
    confined to the per-job workspace directory `root`. The real
    implementation lives in workspace_tools.py (imported lazily,
    like browse/setup above); see that module for the confinement
    contract — any path escaping the root is refused as a FAILED
    step and the filesystem outside the root is never touched.

    E10: job_record is used for read-before-edit enforcement.
    It should be a mutable dict-like object that persists across
    tool calls (the job record in agent_loop)."""
    import workspace_tools
    return workspace_tools.register_workspace_tools(reg, root, job_record)


def register_plan_tool(reg, job_record):
    """Register the E10 set_plan tool, bound to one job record dict.

    The brain declares/replaces its plan (ordered {title, status}
    steps); the plan is stored on the record and in the recorded
    step's result, so it survives a kill+resume (agent_loop's
    _plan_from_result reads it back; run_loop restores it from seed
    history). Classification: mutating (it writes the record — so
    it never lifts the E3 verify-first guard), but needs_allow is
    False: it touches nothing outside the job's own record, so no
    user Allow is spent on bookkeeping. Opt-in registration: a
    caller that does not register it offers the brain exactly the
    tools it built (the E2/E4 offered-list contract)."""
    def _set_plan(args):
        if job_record is None:
            return False, ("set_plan unavailable: no job record is "
                           "bound to this run")
        return agent_loop._apply_set_plan(args, job_record)

    reg.register(
        "set_plan",
        "Declare or replace your plan for this job: an ordered list "
        "of steps with statuses. Args: {steps: [{title, status}]} — "
        "status is pending | in_progress | done. Stored on the job "
        "record; update it as steps complete.",
        {"steps": {"type": "array", "required": True,
                   "desc": "ordered plan steps: [{title, status}]"}},
        _set_plan, mutating=True, needs_allow=False, timeout=15)
    return reg


def register_director_tools(reg, job_record):
    """Register the DIRECTOR LAYER tools (2026-11-24), bound to one
    job record dict: director_plan (vision + steps with acceptance
    checks + risks, written before any work), director_check (one
    plan step verified against its acceptance, with evidence),
    director_review (the final deliver / rework / fail verdict).
    The handlers live in agent_loop (_apply_director_*) and store
    on the job record + mirror to the Worker, so the record IS the
    audit trail. Classification mirrors set_plan: mutating (they
    write the record — so they never lift the E3 verify-first
    guard), needs_allow False (bookkeeping inside the job's own
    record spends no user Allow). The loop's gates (agent_loop
    run_loop, director=True) supply the enforcement; these tools
    are the brain's side of the contract."""
    def _plan(args):
        if job_record is None:
            return False, ("director_plan unavailable: no job record "
                           "is bound to this run")
        return agent_loop._apply_director_plan(args, job_record)

    def _check(args):
        if job_record is None:
            return False, ("director_check unavailable: no job record "
                           "is bound to this run")
        return agent_loop._apply_director_check(args, job_record)

    def _review(args):
        if job_record is None:
            return False, ("director_review unavailable: no job "
                           "record is bound to this run")
        return agent_loop._apply_director_review(args, job_record)

    reg.register(
        "director_plan",
        "Record the director plan BEFORE any other work. Args: "
        "{vision, steps: [{title, acceptance}], risks: []}. The "
        "engine refuses all other tools until this exists.",
        {"vision": {"type": "string", "required": True,
                    "desc": "the finished deliverable + what good looks like"},
         "steps": {"type": "array", "required": True,
                   "desc": "ordered steps: [{title, acceptance}]"},
         "risks": {"type": "array", "required": False,
                   "desc": "risks/unknowns to verify, not assume"}},
        _plan, mutating=True, needs_allow=False, timeout=15)
    reg.register(
        "director_check",
        "Check ONE plan step against its acceptance, in plan order. "
        "Args: {step: 1-based number, verdict: 'pass'|'fail', "
        "evidence: what the tool results showed}.",
        {"step": {"type": "integer", "required": True,
                  "desc": "1-based plan step number"},
         "verdict": {"type": "string", "required": True,
                     "desc": "pass | fail"},
         "evidence": {"type": "string", "required": True,
                      "desc": "evidence from real tool results"}},
        _check, mutating=True, needs_allow=False, timeout=15)
    reg.register(
        "director_review",
        "Final review of the deliverable vs the vision + all step "
        "checks. Args: {verdict: 'deliver'|'rework'|'fail', summary, "
        "defects: []}. Required before done.",
        {"verdict": {"type": "string", "required": True,
                     "desc": "deliver | rework | fail"},
         "summary": {"type": "string", "required": True,
                     "desc": "the review's judgement, in your words"},
         "defects": {"type": "array", "required": False,
                     "desc": "known defects, honestly listed"}},
        _review, mutating=True, needs_allow=False, timeout=15)
    return reg


def register_fetch_tool(reg):
    """Register fetch_url: the read-only verify instrument — GET a
    URL and read back its status, title and text head, with an
    optional exact-substring check. This is how a job verifies a
    deliverable that lives at a URL (a published page) instead of
    trusting its own write. http/https only; local/private hosts
    refused. Read-only, no Allow."""
    def _fetch(args):
        import re as _re
        import httpx
        url = str(args.get("url") or "").strip()
        if not _re.match(r"^https?://", url):
            return False, "fetch_url needs an http(s) URL"
        host = _re.sub(r"^https?://", "", url).split("/")[0] \
            .split("@")[-1].split(":")[0].lower()
        if host in ("localhost",) or host.startswith("127.") \
                or host.startswith("169.254.") or host == "::1":
            return False, "refused: local/private hosts are not fetched"
        contains = str(args.get("contains") or "")
        try:
            r = httpx.get(url, follow_redirects=True, timeout=25,
                          headers={"user-agent": "JulieAgent/1.0 (fetch_url verify)"})
        except Exception as e:
            return False, f"fetch failed: {str(e)[:160]}"
        text = r.text or ""
        m = _re.search(r"<title[^>]*>(.*?)</title>", text,
                       _re.I | _re.S)
        title = _re.sub(r"\s+", " ", m.group(1)).strip()[:120] if m else ""
        plain = _re.sub(r"<[^>]+>", " ", text)
        plain = _re.sub(r"\s+", " ", plain).strip()[:900]
        bits = [f"status {r.status_code}", f"final url: {str(r.url)[:160]}"]
        if title:
            bits.append(f"title: {title}")
        if contains:
            bits.append(f"contains {contains!r}: "
                        f"{'YES' if contains in text else 'NO'}")
        bits.append("text: " + plain)
        return (r.status_code < 400), "; ".join(bits)[:1500]

    reg.register(
        "fetch_url",
        "Fetch a URL and read it back — verify a published page "
        "yourself. Args: {url, contains?}. Returns status, title, "
        "and whether 'contains' appears in the page.",
        {"url": {"type": "string", "required": True,
                 "desc": "http(s) URL to fetch"},
         "contains": {"type": "string", "required": False,
                      "desc": "exact text that must appear in the page"}},
        _fetch, mutating=False, needs_allow=False, timeout=40)
    return reg


def register_publish_tool(reg, root):
    """Register publish_app: publish ONE workspace HTML file as
    this job's live web app on Julie's own Worker (the
    setup/runner/agentpage route stores it under page:<job>; the
    public /p/<job> route serves it). The page slot is keyed by
    THIS job's id — the tool can only ever publish the job's own
    file to the job's own slot, the same confinement argument as
    the workspace writes (agent_runner Allows it on that basis).
    Returns the public URL; the job verifies it with fetch_url."""
    def _publish(args):
        import os
        import httpx
        import workspace_tools
        path = str(args.get("path") or "index.html")
        target = workspace_tools._confined(os.path.realpath(root), path)
        if target is None or target == os.path.realpath(root):
            return False, f"refused: {path!r} escapes the workspace"
        try:
            with open(target, encoding="utf-8") as f:
                html = f.read()
        except Exception as e:
            return False, f"cannot read {path}: {str(e)[:120]}"
        if len(html) > 131072:
            return False, (f"refused: {path} is {len(html)} chars — "
                           f"the publish cap is 131072 (one "
                           f"self-contained page)")
        if "<" not in html or ("<html" not in html.lower()
                               and "<!doctype" not in html.lower()):
            return False, (f"refused: {path} does not look like an "
                           f"HTML page")
        worker = agent_loop._worker()
        if not worker or not agent_loop._job_id():
            return False, "publish channel unavailable (no worker/job)"
        try:
            r = httpx.post(f"{worker}/api/setup/runner/agentpage",
                           params={"job": agent_loop._job_id()},
                           json={"html": html},
                           headers=agent_loop._headers(), timeout=30)
        except Exception as e:
            return False, f"publish failed: {str(e)[:160]}"
        if r.status_code != 200:
            return False, (f"publish refused by the Worker "
                           f"(HTTP {r.status_code})")
        url = str((r.json() or {}).get("url") or "")
        if not url:
            return False, "publish returned no URL"
        return True, f"published: {url} ({len(html)} chars from {path})"

    reg.register(
        "publish_app",
        "Publish a workspace HTML file as this job's live web app. "
        "Args: {path: 'index.html'}. Returns the public URL — "
        "verify it with fetch_url before reviewing.",
        {"path": {"type": "string", "required": False,
                  "desc": "workspace HTML file (default index.html)"}},
        _publish, mutating=True, needs_allow=True, timeout=45)
    return reg


# ----------------------------------------------------- compute tools

def register_compute_tools(reg, root):
    """Register the E7 deterministic compute + verify tools
    (compute_csv / verify_file_contains / verify_csv_rows) plus
    E8's filter_csv (mutating — needs Allow) and
    verify_csv_subset (read-only), confined to the per-job
    workspace directory `root`
    by the same helper the file tools use. The real implementation
    lives in compute_tools.py (imported lazily, like
    workspace_tools above); see that module for the exactness
    contract — facts are computed by code with Decimal arithmetic,
    and a failed check is a FAILED step, never a silent pass."""
    import compute_tools
    return compute_tools.register_compute_tools(reg, root)


# ----------------------------------------------------- youtube tools

def register_yt_tools(reg):
    """Register the deterministic YouTube packaging tools
    (yt_hook_score / yt_title_lint / yt_chapters_validate /
    yt_chapters_from_cues / yt_viral_rank / yt_retention_read /
    yt_package_rank). All read-only pure functions over their args —
    no files, no network, no collection, no publishing. The real
    implementation lives in yt_tools.py (imported lazily, like
    compute_tools above)."""
    import yt_tools
    return yt_tools.register_yt_tools(reg)


# ----------------------------------------------------- video tools

def register_video_tools(reg, root):
    """Register the read-only video analysis tools
    (video_scene_list / video_word_transcript), confined to the
    job workspace. Heavy dependencies load lazily inside the
    handlers; a missing dependency is a FAILED step, not a crash.
    The real implementation lives in video_tools.py."""
    import video_tools
    return video_tools.register_video_tools(reg, root)


# ------------------------------------------- routing / brand / research / style

def register_routing_tool(reg):
    """Register tool_select: the deterministic capability router.
    The brain classifies the task first and works with the minimal
    tool set the selector returns. Implementation: tool_routing.py."""
    import tool_routing
    return tool_routing.register_routing_tool(reg)


def register_brand_tools(reg, root):
    """Register the brand design system tools (brand_profile_get /
    brand_questions read-only; brand_profile_set mutating + Allow),
    confined to the job workspace. Implementation: brand_tools.py."""
    import brand_tools
    return brand_tools.register_brand_tools(reg, root)


def register_research_tools(reg):
    """Register yt_research_analyze: structured analysis of
    PROVIDED video data only — no fetching, no scraping.
    Implementation: research_tools.py."""
    import research_tools
    return research_tools.register_research_tools(reg)


def register_style_tools(reg, root):
    """Register style_profile_extract / script_check /
    audio_loudness (all read-only; loudness confined to the job
    workspace). Implementation: style_tools.py."""
    import style_tools
    return style_tools.register_style_tools(reg, root)
