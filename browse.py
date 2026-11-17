"""Julie browse driver (R51 browser parity): a GENERAL browser agent.

Until now Julie's only browser was setup.py — hardcoded per-provider
signup scripts. There was no way to ask for an arbitrary web task
("open this site, find X, fill this form"), which is what Muse's and
Hark's browsers do and what Ajju ordered in R51. This runner closes
that gap on the same rails (GitHub Actions + Playwright + the Worker
runner channel), reusing setup.py's proven machinery unmodified:
profile browser, live frames, Take Control, progress, result posts.

Shape: the runner is the HANDS, the Worker is the BRAIN. Each step the
runner snapshots the page (URL, title, visible text, and the visible
interactive elements — each tagged with a data-julie-idx the runner
can resolve back to a real element), POSTs it to
/api/setup/runner/brainstep, and executes the ONE JSON action the
Worker's brain returns (goto / click / type / select / scroll / back /
wait / ask / done / fail / human). Element targeting is by INDEX from the
snapshot — never by a selector the model invents — so a click either
lands on a real visible element or the step reports exactly why not.

Honesty rules (Ajju's standing orders):
- done is reported ONLY with an answer the brain composed from page
  text it was actually shown; the final URL + title ride along.
- A step that fails says so (the brain sees the failure and replans,
  or the run fails with the step + reason after the step budget).
- Bot walls / captchas / sign-ins are NEVER evaded: the run pauses
  for Take Control (one human step, in Julie's own browser) and
  resumes when the user taps Continue — or fails honestly.
- A click is judged by its EFFECT (URL or DOM changed), because a
  click that navigates can raise in Playwright even though it landed
  (the before-ladder proved the old primitive misreported exactly
  that as failure).
"""
import os, re, sys, time, json
import httpx

# setup.py reads its env at import time; browse.yml sets the same vars
# setup.yml does, with PROVIDER=browse.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import setup as S
from playwright.sync_api import sync_playwright

WORKER = S.WORKER
KEY = S.KEY
JOB = S.JOB
H = S.H

MAX_STEPS = 40
DEADLINE_S = 30 * 60  # workflow timeout is 45 min; finish well inside it
BLOCK_TEXT_MARKERS = ("anonymized error code", "if this persists, please email us",
                      "unusual traffic", "are you a robot", "verify you are human",
                      # DuckDuckGo's image challenge (found live on the
                      # ladder: the run waited 39 steps on a captcha
                      # because no marker matched its text)
                      "bots use duckduckgo too", "complete the following challenge",
                      "confirm this search was made by a human", "select all squares",
                      "i'm not a robot", "checking your browser", "just a moment")


def brain_step(goal, snapshot, history):
    """Ask the Worker brain for the next action. Returns the action
    dict, or None when the brain is unreachable / answered nothing
    usable (the caller retries, then fails honestly)."""
    for attempt in range(2):
        try:
            r = httpx.post(f"{WORKER}/api/setup/runner/brainstep", params={"job": JOB},
                           json={"goal": goal, "snapshot": snapshot, "history": history[-8:]},
                           headers=H, timeout=90)
            if r.status_code == 200:
                a = (r.json() or {}).get("action")
                if isinstance(a, dict) and a.get("action"):
                    return a
                print(f"brainstep: unusable reply (attempt {attempt + 1})", flush=True)
            else:
                print(f"brainstep HTTP {r.status_code} (attempt {attempt + 1})", flush=True)
        except Exception as e:
            print(f"brainstep failed (attempt {attempt + 1}):", e, flush=True)
        time.sleep(3)
    return None


SNAPSHOT_JS = r"""() => {
  const els = [];
  const nodes = Array.from(document.querySelectorAll('a, button, input, select, textarea, [role="button"], [role="link"], [role="tab"], [tabindex], [onclick]'));
  // Priority pass: elements inside overlays (fixed/sticky ancestors,
  // dialog/modal/consent containers) are indexed FIRST. Cookie
  // banners, sign-in modals and paywalls live there — and they sit at
  // the END of the DOM, so plain DOM order + a cap silently dropped
  // them (the cookiebot ladder rung: 90 nav/carousel elements filled
  // the snapshot and the banner buttons never reached the brain).
  const prio = (el) => {
    let n = el;
    for (let d = 0; d < 6 && n; d++, n = n.parentElement) {
      const idc = ((n.id || '') + ' ' + (typeof n.className === 'string' ? n.className : '')).toLowerCase();
      if (/cookie|consent|gdpr|banner|dialog|modal|popup/.test(idc)) return 0;
      if (n.getAttribute && n.getAttribute('role') === 'dialog') return 0;
      try { const st = getComputedStyle(n); if (st.position === 'fixed' || st.position === 'sticky') return 0; } catch (e) {}
    }
    return 1;
  };
  const vis = nodes.filter((el) => {
    const r = el.getBoundingClientRect();
    const st = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && st.visibility !== 'hidden' && st.display !== 'none' && !el.disabled;
  });
  vis.sort((a, b) => prio(a) - prio(b)); // stable: DOM order kept inside each group
  for (const el of vis) {
    if (els.length >= 120) break;
    const i = els.length;
    el.setAttribute('data-julie-idx', String(i));
    const label = (el.innerText || el.value || el.getAttribute('aria-label') || el.getAttribute('placeholder') || el.getAttribute('name') || el.getAttribute('title') || '').replace(/\s+/g, ' ').trim().slice(0, 80);
    els.push({ i, tag: el.tagName.toLowerCase(), type: (el.getAttribute('type') || '').slice(0, 20),
               label, href: (el.getAttribute('href') || '').slice(0, 120),
               name: (el.getAttribute('name') || '').slice(0, 40) });
  }
  const text = ((document.body && document.body.innerText) || '').replace(/\n{3,}/g, '\n\n').slice(0, 4500);
  return { url: location.href, title: document.title || '', text, elements: els };
}"""


def snapshot(page):
    """The page state the brain decides from. Retries once — a
    navigation mid-snapshot is normal, not a failure."""
    for attempt in range(2):
        try:
            snap = page.evaluate(SNAPSHOT_JS)
            try:
                snap["cookie_banner"] = bool(S._consent_banner_present(page))
            except Exception:
                snap["cookie_banner"] = False
            return snap
        except Exception as e:
            if attempt == 0:
                page.wait_for_timeout(1000)
                continue
            raise


_CONSENT_RX = re.compile(r"(?i)^(reject( all)?|deny( all)?|decline|accept( all)?|allow( all)?|agree|i accept|ok|use necessary cookies only|necessary only|only necessary|only essential|continue without accepting|save settings|confirm my choices|got it)$")


def _looks_like_consent_button(e):
    lab = (e.get("label") or "").strip()
    return len(lab) <= 42 and bool(_CONSENT_RX.match(lab))


def dom_stamp(page):
    try:
        return page.evaluate("() => (location.href + '|' + (document.body ? document.body.innerHTML.length : 0))")
    except Exception:
        return ""


def el_by_idx(page, i):
    loc = page.locator(f'[data-julie-idx="{int(i)}"]')
    if loc.count() == 0:
        return None
    return loc.first


def do_click(page, i):
    """Click element i. Judged by effect: success when the click call
    lands, or when the URL/DOM changed even if Playwright raised on
    the navigation the click caused."""
    el = el_by_idx(page, i)
    if el is None:
        return False, f"element {i} no longer on the page"
    before = dom_stamp(page)
    try:
        el.scroll_into_view_if_needed(timeout=3000)
    except Exception:
        pass
    S._cursor_to(page, el)
    err = ""
    try:
        el.click(timeout=8000)
    except Exception as e:
        err = str(e)[:140]
    page.wait_for_timeout(900)
    after = dom_stamp(page)
    if not err:
        return True, "clicked"
    if after != before:
        return True, "clicked (page changed)"
    return False, f"click failed: {err}"


def do_type(page, i, text, submit):
    el = el_by_idx(page, i)
    if el is None:
        return False, f"element {i} no longer on the page"
    tag = ""
    try:
        tag = (el.evaluate("e => e.tagName.toLowerCase()") or "")
    except Exception:
        pass
    if tag == "select":
        return False, "that element is a dropdown — use select, not type"
    try:
        el.scroll_into_view_if_needed(timeout=3000)
    except Exception:
        pass
    S._cursor_to(page, el)
    try:
        el.click(timeout=5000)
    except Exception:
        pass
    filled = False
    try:
        el.fill(text, timeout=6000)
        filled = True
    except Exception:
        try:
            page.keyboard.type(text, delay=20)
            filled = True
        except Exception as e:
            return False, f"type failed: {str(e)[:140]}"
    if submit:
        try:
            page.keyboard.press("Enter")
        except Exception:
            pass
        page.wait_for_timeout(1200)
    return filled, "typed" if filled else "type failed"


def do_select(page, i, value):
    el = el_by_idx(page, i)
    if el is None:
        return False, f"element {i} no longer on the page"
    for kw in ({"value": value}, {"label": value}, {"index": None}):
        try:
            if kw["index"] is None:
                continue
            el.select_option(**kw, timeout=6000)
            return True, f"selected {value}"
        except Exception:
            continue
    try:
        opts = el.evaluate("e => Array.from(e.options).map(o => o.value + '=' + o.text)")
        return False, f"no option {value!r}; options: {'; '.join(opts)[:200]}"
    except Exception as e:
        return False, f"select failed: {str(e)[:120]}"


def step_label(action, snap):
    kind = action.get("action") or ""
    els = {e["i"]: e for e in (snap or {}).get("elements") or []}
    el = els.get(action.get("i") or -1) or {}
    lab = (el.get("label") or "")[:40]
    if kind == "goto":
        return f"Open {str(action.get('url') or '')[:60]}"
    if kind == "click":
        return f"Click '{lab}'" if lab else "Click"
    if kind == "type":
        return f"Type in '{lab}'" if lab else "Type"
    if kind == "select":
        return f"Select '{str(action.get('value') or '')[:30]}'"
    if kind == "scroll":
        return "Scroll"
    if kind == "back":
        return "Go back"
    if kind == "wait":
        return "Wait"
    return kind or "step"


def run_browse(page, job):
    """The agent loop. Returns (status, answer_or_error)."""
    goal = str(job.get("task") or "").strip()
    if not goal:
        return "failed", "Browse job carries no task text."
    start_url = str(job.get("startUrl") or "").strip()
    history = []
    t0 = time.time()
    if start_url:
        if not S.goto(page, start_url):
            return "failed", f"Start page open avvaledu: {start_url}"
        history.append({"action": "goto", "arg": start_url, "result": "opened"})
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass
    steps = 0
    last_stamp = ""
    stale = 0
    while steps < MAX_STEPS:
        if time.time() - t0 > DEADLINE_S:
            return "failed", f"Time limit ayipoyindhi ({steps} steps tarvatha). Last page: {page.url}"
        # Stop / Take Control, exactly like setup jobs: the app flips
        # the job state; the runner obeys on its next poll. A Worker
        # blip during the poll must not kill the run unreported
        # (get_job raises SystemExit after its retries) — treat it as
        # "still running" and let the deadline bound the loop.
        try:
            j = S.get_job()
        except BaseException:
            j = {"state": "running"}
        st = j.get("state", "")
        if st == "stopped":
            return "stopped", ""
        if st == "paused":
            cfg = {"name": "Browse", "url": page.url}
            if not S.take_control(page, j, cfg):
                return "stopped", ""
            history.append({"action": "human", "result": "user took control, then continued"})
            continue
        try:
            snap = snapshot(page)
            # Never plan against a blank / half-loaded page: heavy
            # pages (and consent banners) render AFTER domcontentloaded
            # — the first cookiebot ladder run snapshot a page whose
            # banner script had loaded but whose buttons had not, and
            # the brain quite honestly found "no dismiss button". A
            # near-empty snapshot is a loading state, not a task
            # state: settle and re-snapshot (bounded) before asking.
            for _settle in range(2):
                if (snap.get("elements") or []) or len((snap.get("text") or "").strip()) >= 200:
                    break
                page.wait_for_timeout(2500)
                snap = snapshot(page)
            # Banner handling, runner-side, before any brain step is
            # spent: the banner flag is a HEURISTIC (any visible
            # cookie/consent container — a cookie-product page's own
            # furniture trips it), and banner buttons often render
            # seconds after the container. So: (1) try the production
            # dismiss primitive (frame-aware, reject-first) and
            # re-snapshot; (2) if it finds nothing, settle once and
            # retry — the buttons may still be rendering; (3) if
            # there are STILL no consent controls anywhere, the flag
            # is a false positive — clear it and note why in history,
            # so the brain works the task instead of chasing a
            # banner that is not there (the cookiebot ladder rung
            # failed exactly that way: "banner visible but no
            # dismiss button in the snapshot").
            for _b in range(2):
                if not snap.get("cookie_banner"):
                    break
                if any(_looks_like_consent_button(e) for e in snap.get("elements") or []):
                    break
                hit = ""
                try:
                    hit = S.dismiss_cookie_banner(page) or ""
                except Exception:
                    hit = ""
                if hit:
                    history.append({"action": "cookie-dismiss", "result": f"runner clicked {hit}"})
                    page.wait_for_timeout(800)
                    snap = snapshot(page)
                    break
                if _b == 0:
                    page.wait_for_timeout(3000)
                    snap = snapshot(page)
                    continue
                history.append({"action": "cookie-check", "result": "banner flagged but no consent controls exist (dismiss found nothing) — treated as no banner"})
                snap = dict(snap)
                snap["cookie_banner"] = False
        except Exception as e:
            return "failed", f"Page chadavadam fail ayyindhi: {str(e)[:160]}"
        # Bot wall? Never evade — hand the SAME browser to the user.
        wall = S.wall_hit(page)
        block_text = ""
        if not wall:
            low = (snap.get("text") or "").lower()
            for m in BLOCK_TEXT_MARKERS:
                if m in low:
                    block_text = m
                    break
        if wall or block_text:
            S.progress("paused", "wall", "Security check vachindhi — Take Control tho nuvve okka step cheyyi, tarvatha Continue nokku.", page.url, reason="captcha", tc=True)
            cfg = {"name": "Browse", "url": page.url}
            if not S.take_control(page, S.get_job(), cfg):
                return "failed", f"Security wall ({wall or block_text}) — Take Control lo step complete avvaledu."
            history.append({"action": "human", "result": f"wall ({wall or block_text}) handled by user via Take Control"})
            continue
        # Stagnation guard: if the page has not changed across 6
        # consecutive brain steps, more waiting will not fix it —
        # the Bing ladder rung burned all 40 steps on a results
        # shell that never rendered its results to this egress.
        # Fail honestly with the true last page instead.
        stamp = (snap.get("url") or "") + "|" + dom_stamp(page)
        if stamp == last_stamp:
            stale += 1
        else:
            stale = 0
            last_stamp = stamp
        if stale >= 6:
            return "failed", f"Page maraledhu — {stale} steps nunchi ade static page (content/results load avvatledhu). Last page: {page.url}"
        action = brain_step(goal, snap, history)
        if action is None:
            return "failed", "Brain nunchi response raaledhu (brainstep unreachable) — step plan cheyyalekapoya."
        kind = str(action.get("action") or "").lower()
        steps += 1
        if kind == "done":
            answer = str(action.get("answer") or "").strip()
            if not answer:
                history.append({"action": "done", "result": "rejected: empty answer — an answer must state what the page showed"})
                continue
            return "done", answer[:1800]
        if kind == "fail":
            return "failed", str(action.get("reason") or "Task complete avvaledu.")[:600]
        if kind == "human":
            reason = "signin" if str(action.get("reason") or "").lower().startswith("signin") else "captcha"
            S.progress("paused", "human", "Nee okka step kavali — Take Control lo complete chesi Continue nokku.", page.url, reason=reason, tc=True)
            cfg = {"name": "Browse", "url": page.url}
            if not S.take_control(page, S.get_job(), cfg):
                return "failed", "Take Control step complete avvaledu (time out / stopped)."
            history.append({"action": "human", "result": "user completed the step via Take Control"})
            continue
        if kind == "ask":
            # v106 (Muse parity / blind-first): a verification code or
            # one missing detail is asked IN CHAT (the v103 awaiting
            # protocol) and Julie types the answer into the page herself
            # — the user never has to find or work the field, which is
            # what makes this completable by a user who cannot see the
            # screen. The value is typed with real key events (OTP
            # auto-advance fires) and is NEVER written into history
            # (history goes to the brain), the result, or any log.
            akind = str(action.get("kind") or "otp").lower()
            if akind not in ("otp", "field"):
                akind = "otp"
            prompt = str(action.get("prompt") or "").strip()
            if not prompt:
                prompt = ("Nee phone ki vachina verification code ni ikkada cheppu — nenu enter chestha."
                          if akind == "otp" else "Oka detail kavali — ikkada cheppu, nenu enter chestha.")
            r = S.await_user_input(page, akind, prompt,
                                   field=(str(action.get("field") or "")[:40] or None))
            if r.get("stopped"):
                return "stopped", ""
            if r.get("timeout"):
                history.append({"action": "ask", "result": "user did not answer in time — ask again or use human"})
                continue
            val = str(r.get("value") or "")
            entered = False
            idx = action.get("i")
            if idx is not None and val:
                el = el_by_idx(page, int(idx))
                if el is not None:
                    try:
                        el.scroll_into_view_if_needed(timeout=3000)
                    except Exception:
                        pass
                    S._cursor_to(page, el)
                    try:
                        el.click(timeout=5000)
                    except Exception:
                        pass
                    try:
                        page.keyboard.type(val, delay=60)
                        entered = True
                    except Exception:
                        entered = False
                    page.wait_for_timeout(600)
            history.append({"action": "ask", "result": "user answered in chat; Julie entered it into the field (value hidden)" if entered else "user answered in chat (value hidden); no field was typed into"})
            S.progress("running", f"step-{steps}", "Answer enter chesa — continue chesthunna", page.url)
            continue
        # Execute one browser action.
        label = step_label(action, snap)
        S.progress("running", f"step-{steps}", label, page.url)
        ok, result = True, ""
        try:
            if kind == "goto":
                url = str(action.get("url") or "")
                if not (url.startswith("https://") or url.startswith("http://")):
                    ok, result = False, f"bad url {url!r} — http(s) matrame"
                else:
                    ok = S.goto(page, url)
                    result = "opened" if ok else f"open failed for {url}"
            elif kind == "click":
                ok, result = do_click(page, int(action.get("i")))
            elif kind == "type":
                ok, result = do_type(page, int(action.get("i")), str(action.get("text") or ""), bool(action.get("submit")))
            elif kind == "select":
                ok, result = do_select(page, int(action.get("i")), str(action.get("value") or ""))
            elif kind == "scroll":
                S.human_scroll(page, float(action.get("dy") or 600))
                result = "scrolled"
            elif kind == "back":
                page.go_back(wait_until="domcontentloaded", timeout=20000)
                result = "went back"
            elif kind == "wait":
                page.wait_for_timeout(max(200, min(10000, int(action.get("ms") or 1500))))
                result = "waited"
            else:
                ok, result = False, f"unknown action {kind!r}"
        except Exception as e:
            ok, result = False, f"{kind} error: {str(e)[:160]}"
        history.append({"action": kind, "arg": str(action.get("url") or action.get("text") or action.get("value") or action.get("i") or "")[:80],
                        "result": ("ok: " if ok else "FAILED: ") + result})
        S.progress("running", f"step-{steps}", label + ("" if ok else f" — {result}"), page.url)
    return "failed", f"Step limit ayipoyindhi ({MAX_STEPS} steps) — task inka complete avvaledu. Last page: {page.url}"


def main():
    job = S.get_job()
    print(f"browse: job task={str(job.get('task') or '')[:80]!r} browser_mode={S.BROWSER_MODE}", flush=True)
    S.fetch_profile()
    with sync_playwright() as p:
        browser = S.launch_browser(p)
        try:
            ctx = S.open_context(browser)
            page = ctx.new_page()
            S._CUR["page"] = page
            S.progress("running", "start", "Browser open chesthunna — task start.", str(job.get("startUrl") or ""))
            try:
                status, out = run_browse(page, job)
            except Exception as e:
                status, out = "failed", f"Browse run aagipoyindhi: {str(e)[:200]}"
            finally:
                S.close_context(ctx)
        finally:
            browser.close()
    if status == "done":
        S.report_result("browse", "done", extra={"answer": out})
        S.progress("done", "done", out[:280], "")
    elif status == "stopped":
        S.report_result("browse", "stopped")
        S.progress("stopped", "stopped", "Aapesaru — browse stop ayyindhi.", "")
    else:
        S.report_result("browse", "failed", error=out)
        S.progress("failed", "failed", out[:280], "")


if __name__ == "__main__":
    main()
