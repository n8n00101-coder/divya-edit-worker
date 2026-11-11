"""
divya_codegen.py - makes Divya write NEW effect code for every video, test it, fix it, and fall back safely.

Flow:  plan (topic -> objects -> scene ideas)  ->  write code  ->  sandbox test  ->  fix loop (max 2)
       ->  keep passing functions  ->  fallback to libraries for anything missing  ->  save fingerprint.

Works with any OpenAI-compatible chat API (Groq, OpenRouter, Together, local Ollama).
Env: LLM_BASE_URL (e.g. https://api.groq.com/openai/v1), LLM_API_KEY, LLM_MODEL.
Use the strongest free coder model you have; the sandbox + retry loop makes smaller models usable.

    python divya_codegen.py plan.json out_dir/
plan.json = {"topic": "...", "mood": "...", "scenes": [{"text": "...", "hit_word": "...", "tags": ["phone"]}],
             "accent": [255,210,0], "recent_families": ["wipe","3d_cube"]}
"""
import json, os, re, sys, subprocess, urllib.request, pathlib, random

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
def _rd(n): return (HERE / n).read_text() if (HERE / n).exists() else ""
FEWSHOT = _rd("video_fx_example.py")
FEWSHOT_VIS = _rd("fewshot_visuals.py")
FEWSHOT_EX = _rd("fewshot_examples.py")

# v32 (Divya adapter): the pipeline sets CHAT to its own chat function
# (runner.groq_chat via codegen.py); llm() uses it when set, else the env
# LLM_* OpenAI-compatible endpoint (standalone use).
CHAT = None

def llm(messages, temperature=0.8, max_tokens=3500):
    if CHAT is not None:
        return CHAT(messages, temperature=temperature, max_tokens=max_tokens)
    url = os.environ["LLM_BASE_URL"].rstrip("/") + "/chat/completions"
    body = json.dumps({"model": os.environ["LLM_MODEL"], "messages": messages,
                       "temperature": temperature, "max_tokens": max_tokens}).encode()
    req = urllib.request.Request(url, body, {"Content-Type": "application/json",
                                             "Authorization": "Bearer " + os.environ["LLM_API_KEY"]})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)["choices"][0]["message"]["content"]

SYSTEM = """You are Divya's motion coder. You write small, original Python effects for ONE short video.
Tools you may use: math, random, numpy as np, PIL (Image, ImageDraw, ImageFilter, ImageChops),
effects_lib (EASES, _xf, _alpha, _p, _mask_reveal, _bbox_field), transitions_lib (EASES, _grid, _mix, _soft,
_rot_plane, _project, _quad, f_linear, f_radial, f_noise, ...), motion_graphics (MG templates).
Interfaces (Divya renders 1080x1920; the kit was written for 720x1280):
  def tr_<name>(A, B, p) -> PIL RGB image   (p=0 returns A, p=1 returns B, same size as A)
    MUST be size-agnostic: derive w, h from A.size (never hard-code 720x1280).
  def fx_<name>(layer, t, start, dur) -> PIL RGBA image (same size as layer, content stays inside 8%/10% safe box)
    MUST be size-agnostic: derive w, h from layer.size.
  def vis_<name>(t, st=0, d=1.0, accent=(r,g,b), words=None) -> PIL RGBA 720x1280: a REAL OBJECT of the topic, drawn and animated in.
    vis_ ALWAYS returns 720x1280 RGBA (Divya upscales it 1.5x); use visuals_lib's W, H (720, 1280).
    words = [(start, dur, text), ...] — the scene's word timings (scene-local seconds).
    WORD-TIMING (v34, Hark's word_t pattern — this is what makes a video feel alive):
    time the animation to SPECIFIC words, never just the scene clock. A word's
    start time is words[min(idx, len(words)-1)][0]. Examples: a counter counts
    up while the number words are spoken; a stamp slams on the verdict word
    ("banned"); dots fill one by one as the number is spoken; a phone number
    types out character by character as the voice reads it; a stopwatch sector
    sweeps while the rate is spoken. If words is None, fall back to progress
    p = (t-st)/d.
Visual recipe (visuals_lib helpers: _L, _p, _oe, _ob, place, shadow, texture, _font, wrap, scene_bg, VIS):
  1 silhouette (polygon / rounded rect)  2 material (flat colour + texture())  3 two-four details that make it
  recognisable (label, lines, text)  4 depth: shadow()  5 ONE accent element  6 build-in motion from p (pop, slide,
  draw-on, fill, drop) — and WORD-TIMED: the key change lands on a specific word (use words=, see the interface
  above). Real text (headline, numbers, names) beats grey lines. Never a stick figure when an object fits.
Rules: each function is built from a REAL object of the topic; one comment line above each function saying which
sentence it serves and why; under 40 ms per 720x1280 frame (prefer numpy over pixel loops); no file, network or
subprocess use; no reuse of the families listed as recent. Return only one ```python block.
v36 rules (Blind's frame review — these are the rules that stop the mistakes repeating):
- FIXED ZONES (1080x1920 frame): title 120-450, visual 480-1410, caption band 1440-1725 (captions ONLY),
  source 1755-1845. No layer may cross into another zone. If two layers intersect, scale the visual to 80%
  or move it; still hitting, drop the smaller item.
- MIN FONTS: title 96 px, captions 72 px, labels 44 px, source 30 px. Anything smaller is rejected.
- ONE EFFECT AT A TIME per layer (never stacked); max 1 emphasis per scene; every effect finishes
  >=150 ms before the cut. The camera is STATIC — no zoom, push-in, pan, or camera move of any kind, ever.
- EFFECTS LAND ON THE WORD: the visual lands 80 ms before its hit word (use words=), the SFX on the word.
  The typewriter reveals WHOLE WORDS only (never a trailing partial word) and holds the final text 400 ms.
- HOOK AT FRAME 1: the biggest number or shock line is on screen at frame 1 — no slow fade-in.
- PATTERN BREAK at 40-60%: one scene with a different layout (full-bleed visual).
- NEVER THE SAME LOOK as the previous video (A Investigative, B Science/health, C Story/emotional, D Data/money);
  the topic mood picks the look, and the transition family follows the topic object.
- A source line on EVERY fact/number scene (small, bottom).
- No blank frames: every frame has a background + at least one visible element.
- Typography: Anton for the headline, Oswald for labels, tracking +2 on labels, ONE keyword in yellow per line.
- Motion: ease-out cubic for entries, back-ease with 6% overshoot for pops, never linear; stagger child
  items 60-80 ms. Backgrounds are radial gradients (never flat) with 3% film grain; 3 layers per scene
  (far shapes drifting 2-6 px/s, mid main visual, near dust)."""

def step_plan(plan):
    msg = f"""Topic: {plan['topic']}
Mood: {plan.get('mood','')}
Scenes: {json.dumps(plan['scenes'])}
1) List 6 real objects of this topic.
2) For every scene give ONE motion idea built from one object, tied to its hit word (enter or emphasis).
3) For every scene change give ONE transition idea built from an object.
3b) For every scene give the MAIN VISUAL: the real object to draw (map, document, packet, organ, machine, place ...),
    its details/text, and how it animates in — TIME IT TO A WORD: say which word index triggers the key change
    (e.g. "the stamp slams on word 2 'banned'", "the counter counts up during words 3-6"). Reuse a library visual
    only if it fits exactly; else write a new vis_.
4) Pick a motion personality (snappy / smooth / heavy / glitchy / playful) and say why.
Answer as JSON: {{"objects": [...], "personality": "...", "scene_fx": [{{"scene":1,"idea":"...","fn":"fx_name"}}],
"transitions": [{{"between":[1,2],"idea":"...","fn":"tr_name"}}],
"visuals": [{{"scene":1,"object":"...","details":"...","motion":"...","fn":"vis_name or library:<name>"}}]}}
Library visuals available: """ + ", ".join(__import__("visuals_lib").VIS) + """ and motion graphics: """ + ", ".join(__import__("motion_graphics").MG)
    out = llm([{"role": "system", "content": SYSTEM}, {"role": "user", "content": msg}], temperature=.9)
    return json.loads(re.search(r"\{.*\}", out, re.S).group(0))

def step_code(plan, ideas, feedback=None, prev=None):
    msg = f"""Write video_fx.py for these ideas. Accent colour: {plan.get('accent')}.
Do not use these families: {plan.get('recent_families', [])}.
Ideas: {json.dumps(ideas)}
Here is an example of the expected style (different topic, do NOT copy its ideas):
```python
{FEWSHOT}
```
Example of rich VISUAL functions (different topics, do NOT copy):
```python
{FEWSHOT_VIS}
```
More tr_/fx_ examples, five topics (money, sleep, space, history, health) — style reference only:
```python
{FEWSHOT_EX}
```"""
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": msg}]
    if feedback:
        msgs += [{"role": "assistant", "content": f"```python\n{prev}\n```"},
                 {"role": "user", "content": "The sandbox rejected some functions. Fix ONLY these problems and return the full file:\n" + feedback}]
    out = llm(msgs, temperature=.6 if feedback else .8)
    m = re.search(r"```python\n(.*?)```", out, re.S)
    return m.group(1) if m else out

def sandbox(path):
    r = subprocess.run([sys.executable, str(HERE / "fx_sandbox.py"), str(path)], capture_output=True, text=True, timeout=90, cwd=HERE)
    try: return json.loads(r.stdout)
    except Exception: return {"ok": False, "error": (r.stderr or r.stdout)[-1500:]}

def feedback_text(rep):
    if "error" in rep: return rep["error"]
    return "\n".join(f"{k}: {v['why']}" for k, v in rep.get("functions", {}).items() if not v["ok"])

def main(plan_path, out_dir):
    plan = json.load(open(plan_path)); out = pathlib.Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    ideas = step_plan(plan); (out / "ideas.json").write_text(json.dumps(ideas, indent=1))
    code = step_code(plan, ideas); path = out / "video_fx.py"
    rep = {}
    for attempt in range(3):                      # first try + 2 fixes
        path.write_text(code); rep = sandbox(path)
        if rep.get("ok"): break
        if attempt < 2: code = step_code(plan, ideas, feedback_text(rep), code)
    passed = [k for k, v in rep.get("functions", {}).items() if v.get("ok")]
    # fallback: every idea whose function did not pass gets a library pick with the scene tags
    from transitions_lib import pick_transition
    from effects_lib import pick_fx
    used_t, used_f, fallback = set(), set(), {}
    for tr in ideas.get("transitions", []):
        if tr["fn"] not in passed:
            fallback[tr["fn"]] = pick_transition({"story"} | set(plan.get("tags", [])), used_t, recent_families=set(plan.get("recent_families", [])))["name"]
    from visuals_lib import pick_vis
    used_v = set()
    for v in ideas.get("visuals", []):
        fn = v.get("fn", "")
        if fn.startswith("library:"): fallback[fn] = fn.split(":", 1)[1]; continue
        if fn not in passed:
            sc = plan["scenes"][min(v.get("scene", 1)-1, len(plan["scenes"])-1)]
            name = pick_vis(set(sc.get("tags", [])) | set(plan["topic"].lower().split()), used_v); used_v.add(name); fallback[fn] = "visuals_lib:" + name
    for i, fx in enumerate(ideas.get("scene_fx", [])):
        if fx["fn"] not in passed:
            tags = set(plan["scenes"][min(i, len(plan["scenes"])-1)].get("tags", [])) | {"keyword"}
            fallback[fx["fn"]] = pick_fx("emphasis", tags, used_f)  # pick_fx returns the NAME string, not a dict
    result = {"passed_custom": passed, "fallback_from_library": fallback, "sandbox": rep,
              "fingerprint": {"personality": ideas.get("personality"), "custom_fns": passed,
                              "library_families": sorted({v.split('_')[0] for v in fallback.values()}),
                              "accent": plan.get("accent")}}
    (out / "codegen_result.json").write_text(json.dumps(result, indent=1))
    print(json.dumps(result, indent=1))

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])


# v36 (Blind E7): after 20 videos, the top 3 mistakes from the rejection log
# are added to the SYSTEM rules above. This reads the log (qc_rejections.jsonl)
# and returns the top 3 flaw kinds by count. The rule-update itself is a
# FUTURE step (a human reviews the top 3 and edits SYSTEM) — this function
# only reports them. The log lives at ~/workspace/qc_rejections.jsonl (the
# test script copies the per-video log there) or DIVYA_QC_LOG.
def qc_top_mistakes(path=None, n=3):
    import collections, json, os
    p = path or os.environ.get("DIVYA_QC_LOG") or os.path.expanduser("~/workspace/qc_rejections.jsonl")
    counts = collections.Counter()
    total = 0
    try:
        with open(p) as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                total += 1
                for flaw in rec.get("flaws", []):
                    # The flaw kind is the text after "scene N: " / "scene N @t: ",
                    # up to the first "(" — e.g. "label overlaps visual".
                    kind = flaw
                    for _pref in ("scene ",):
                        if _pref in kind:
                            kind = kind.split(": ", 1)[-1]
                    kind = kind.split(" (")[0].strip()
                    counts[kind] += 1
    except FileNotFoundError:
        return {"videos": 0, "top": []}
    return {"videos": total, "top": counts.most_common(n)}
