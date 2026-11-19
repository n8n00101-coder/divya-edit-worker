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
    stub         True for smoke-test stand-ins (noop / echo).

Real tools here WRAP the runner's existing implementations — nothing
is rewritten:

  - job_state            agent_loop.fetch_job_state (the runner job
                         endpoint read setup.get_job also uses)
  - browser_*            browse.py's action primitives (do_click /
                         do_type / do_select / snapshot) and
                         setup.py's goto / human_scroll, bound to one
                         live page via register_browser_tools(page)

GAP (honest, per the E2 brief): there is NO file read/list helper for
a job workspace anywhere in the runner today (runner.py / create.py /
setup.py / browse.py have no workspace list/read primitive to wrap),
so no file tool is registered — inventing one is a later phase's
decision, not E2's.

Additive only: no production flow (browse / setup / video) imports
this module yet, and providers.py / channel.py / brain content are
untouched. agent_loop consumes the registry through as_tools().
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
                 needs_allow=None, timeout=60, stub=False):
        """Add one tool. needs_allow defaults to the mutating flag:
        a read-only tool never needs Allow; a mutating/external one
        does unless the registrant explicitly says otherwise (e.g.
        browser_scroll moves only the local view)."""
        if not name or not callable(handler):
            raise ValueError("a tool needs a name and a callable handler")
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
        loop's Allow gate can see them."""
        out = []
        for e in self._tools.values():
            out.append({
                "name": e["name"],
                "desc": e["desc"],
                "schema": e["schema"],
                "mutating": e["mutating"],
                "needs_allow": e["needs_allow"],
                "run": self._runner(e),
            })
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
    noop / echo are stubs (marked as such); job_state is REAL — it
    wraps agent_loop's job-record read over the runner channel."""
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
        "Read this job's own record (state, current step, note, recorded step count). Read-only, no side effects.",
        {}, agent_loop._tool_job_state)
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
