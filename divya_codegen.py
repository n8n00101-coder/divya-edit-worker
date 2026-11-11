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
  def vis_<name>(t, st=0, d=1.0, accent=(r,g,b)) -> PIL RGBA 720x1280: a REAL OBJECT of the topic, drawn and animated in.
    vis_ ALWAYS returns 720x1280 RGBA (Divya upscales it 1.5x); use visuals_lib's W, H (720, 1280).
Visual recipe (visuals_lib helpers: _L, _p, _oe, _ob, place, shadow, texture, _font, wrap, scene_bg, VIS):
  1 silhouette (polygon / rounded rect)  2 material (flat colour + texture())  3 two-four details that make it
  recognisable (label, lines, text)  4 depth: shadow()  5 ONE accent element  6 build-in motion from p (pop, slide,
  draw-on, fill, drop). Real text (headline, numbers, names) beats grey lines. Never a stick figure when an object fits.
Rules: each function is built from a REAL object of the topic; one comment line above each function saying which
sentence it serves and why; under 40 ms per 720x1280 frame (prefer numpy over pixel loops); no file, network or
subprocess use; no reuse of the families listed as recent. Return only one ```python block."""

def step_plan(plan):
    msg = f"""Topic: {plan['topic']}
Mood: {plan.get('mood','')}
Scenes: {json.dumps(plan['scenes'])}
1) List 6 real objects of this topic.
2) For every scene give ONE motion idea built from one object, tied to its hit word (enter or emphasis).
3) For every scene change give ONE transition idea built from an object.
3b) For every scene give the MAIN VISUAL: the real object to draw (map, document, packet, organ, machine, place ...),
    its details/text, and how it animates in. Reuse a library visual only if it fits exactly; else write a new vis_.
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
