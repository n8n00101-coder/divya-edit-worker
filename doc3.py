"""Divya documentary engine v3 (built to Tab's editing standard v2, 2026-11-08).

topic/brief -> Wikipedia research -> LLM fact list with verbatim quotes (each verified against the source text;
unsourced/unverified facts are dropped) -> LLM script, one JSON item per sentence {text, query, alt_query, key, facts}
-> free TTS per clause (pluggable, default edge-tts) + owner-approved voice-polish chain (v5 flow)
-> one real Wikimedia Commons image per sentence (vision-checked, never repeated), Ken Burns, hard cuts, soft whoosh
-> drawn number card only for numbers / when nothing is found -> Pillow+raqm captions (Anton / Noto Sans Telugu)
-> Kevin MacLeod music by mood (CC-BY), ducked ~-22 dB under the voice -> 1080x1920 30 fps h264+aac, -14 LUFS
-> QC: a frame every 3 s checked by a vision model + Groq Whisper STT vs script; failing shots re-rendered once.
Free, CPU only. Never prints key values.

CLI test:  python doc3.py --brief "topic" --out outdir [--seconds 60]
"""
import argparse, asyncio, base64, difflib, io, json, math, multiprocessing as mp, os, random, re, subprocess, sys, tempfile, time, urllib.parse
import httpx
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps, features

W, H, FPS = 1080, 1920, 30
HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(HERE, "fonts")
UA = "DivyaDocBot/3.0 (https://github.com/n8n00101-coder/divya-edit-worker; n8n00101@gmail.com)"
SR = 48000
YELLOW, WHITE = (255, 214, 10), (255, 255, 255)
CAP_Y = 1440          # caption centre line (bottom third, above the Shorts UI)
CAP_MAXW = 860
PREROLL = 0.10
TAIL = 0.6
LOG = []


def log(*a):
    s = " ".join(str(x) for x in a)
    LOG.append(s)
    print("[doc3]", s, flush=True)


# ============================================================ LLM (Groq) ============================================================
CHAT_MODELS = ["openai/gpt-oss-120b", "moonshotai/kimi-k2-instruct-0905", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"]


def groq_keys():
    return [k.strip() for k in os.environ.get("GROQ_KEY", os.environ.get("GROQ_API_KEY", "")).split(",") if k.strip()] or ["none"]


def groq_chat(messages, temperature=0.5, max_tokens=6000, json_mode=True):
    last = ""
    for k in groq_keys():
        for m in CHAT_MODELS:
            est = sum(len(str(x.get("content", ""))) for x in messages) / 3.3
            body = {"model": m, "messages": messages, "temperature": temperature,
                    "max_tokens": int(max(1200, min(max_tokens, 7700 - est)))}  # free tier: input + max_tokens <= 8k TPM
            if m.startswith("openai/gpt-oss"):
                body["reasoning_effort"] = "medium"
            if json_mode:
                body["response_format"] = {"type": "json_object"}
            for attempt in range(3):
                try:
                    r = httpx.post("https://api.groq.com/openai/v1/chat/completions", json=body,
                                   headers={"Authorization": f"Bearer {k}"}, timeout=120)
                except Exception as e:
                    last = f"{m} {type(e).__name__}"; continue
                if r.status_code == 200:
                    out = r.json()["choices"][0]["message"].get("content") or ""
                    if out.strip():
                        return out
                last = f"{m} {r.status_code}"
                if r.status_code == 429:
                    try: ra = float(r.headers.get("retry-after", "8"))
                    except Exception: ra = 8
                    if ra > 65: break
                    time.sleep(ra + 1); continue
                break
    raise RuntimeError("LLM failed: " + last)


def ask_json(chat, prompt, tries=2):
    err = None
    for _ in range(tries):
        raw = chat([{"role": "system", "content": "You output strict JSON only. No markdown."}, {"role": "user", "content": prompt}])
        raw = re.sub(r"<think>[\s\S]*?</think>", "", raw)
        m = re.search(r"\{[\s\S]*\}", raw)
        try:
            return json.loads(m.group(0))
        except Exception as e:
            err = e
    raise ValueError(f"bad JSON from LLM: {err}")


# ============================================================ research + facts ============================================================
def http_get(url, params=None, timeout=40, tries=3):
    last = None
    for a in range(tries):
        try:
            r = httpx.get(url, params=params, headers={"User-Agent": UA}, timeout=timeout, follow_redirects=True)
            if r.status_code == 429 or r.status_code >= 500:
                last = f"HTTP {r.status_code}"; time.sleep(2 + 3 * a); continue
            return r
        except Exception as e:
            last = e; time.sleep(2 + 3 * a)
    raise RuntimeError(f"GET failed {url[:80]}: {last}")


def wiki_sources(query, n=2, wiki="en"):
    api = f"https://{wiki}.wikipedia.org/w/api.php"
    s = http_get(api, {"action": "query", "list": "search", "srsearch": query, "srlimit": 4, "format": "json"}).json()
    titles = [x["title"] for x in s.get("query", {}).get("search", [])][:n]
    out = []
    for t in titles:
        j = http_get(api, {"action": "query", "prop": "extracts", "explaintext": 1, "redirects": 1, "titles": t, "format": "json"}).json()
        for pg in j.get("query", {}).get("pages", {}).values():
            txt = pg.get("extract") or ""
            if len(txt) > 500:
                url = f"https://{wiki}.wikipedia.org/wiki/" + urllib.parse.quote(pg["title"].replace(" ", "_"))
                out.append({"title": pg["title"], "url": url, "text": txt})
    return out


def norm(s):
    s = s.lower().replace("\u2013", "-").replace("\u2014", "-").replace("\u2019", "'")
    s = re.sub(r"(?<=\d),(?=\d{3})", "", s)
    return re.sub(r"[^a-z0-9%.' -]+", " ", s).split()


def nums(s):
    return set(re.findall(r"\d+(?:\.\d+)?", re.sub(r"(?<=\d),(?=\d{3})", "", s)))


def quote_found(quote, text):
    q, t = " ".join(norm(quote)), " ".join(norm(text))
    if len(q) < 15:
        return False
    if q in t:
        return True
    sm = difflib.SequenceMatcher(None, t, q, autojunk=False)
    blk = sm.find_longest_match(0, len(t), 0, len(q))
    if blk.size >= 0.6 * len(q):
        return True
    # windowed fuzzy match around the longest common block
    a = max(0, blk.a - blk.b - 20)
    win = t[a:a + len(q) + 40]
    return difflib.SequenceMatcher(None, win, q, autojunk=False).ratio() >= 0.85


TOPIC_PROMPT = """You pick the subject for a 60-second faceless documentary Short (9:16) for the channel "Divya".
Owner request: <<{brief}>>
If the request has no clear topic (AUTO / "nuvve select chesko" / empty), choose a true, well-documented historical or science
incident with a strong visual record (photos/paintings on Wikimedia Commons). Avoid these recent topics: {recent}.
Language: English -> "en", Telugu -> "te", Hindi -> "hi"; if the owner says nothing about language use "{lang}".
Return JSON: {{"topic": "...", "wiki_queries": ["<best English Wikipedia article title>", "<optional second related article>"],
"lang": "en|te|hi", "voice": "female|male", "mood": "dark|sad|mystery|thoughtful|hopeful|tense|epic"}}"""

FACTS_PROMPT = """You are a fact checker. From the SOURCES below, extract 14-18 facts useful for a 60-second documentary about: {topic}.
Each fact must be copied from a source: give "quote" = an EXACT verbatim sentence fragment (12-30 words) from the source text that
proves it, and "source_url" = that source's URL. Prefer: one concrete real incident (who, where, when), surprising numbers,
human details, and the aftermath. Never add knowledge that is not in the quote.
Return JSON: {{"facts": [{{"id": 1, "fact": "<one short sentence>", "quote": "<verbatim>", "source_url": "<url>"}}]}}

SOURCES:
{sources}"""

SCRIPT_PROMPT = """Write the voice-over for a {seconds}-second vertical documentary Short about: {topic}.
Language of the voice-over: {langname}. Mood: {mood}.
Use ONLY these verified facts (cite their ids). Anything not in them must not be claimed:
{facts}

Rules (an expert editor's standard):
- Sentence 1 is the HOOK and is spoken in under 3 seconds: max 8 words, a bold claim, a striking number or a sharp question taken from a fact.
- Then tell it as ONE story, in time order, like a documentary narrator: the real incident with names, place and date from the facts,
  the build-up, the moment it went wrong, the human cost, the aftermath. Each sentence must lead into the next (no list of trivia).
- Short, spoken sentences: 6-14 words each, averaging about 10 words. One idea per sentence. Concrete nouns. Natural English grammar.
  No filler ("Did you know", "In this video", "Follow for more", "mind-blowing", "Let's dive in"). No hashtags or emojis.
- Write every number as DIGITS exactly as in the facts (e.g. "1,500", "20", "1912"), never in words.
- The LAST sentence loops back to the hook: it answers or echoes the opening line with new meaning (not a word-for-word copy),
  so the video can replay seamlessly.
- LENGTH IS STRICT: {n_lo}-{n_hi} sentences and {words}-{words_hi} words in total (it must fill {seconds} seconds of narration).
- For EACH sentence give:
  "query": an English Wikimedia Commons image search (2-5 words) for a REAL photo/painting showing exactly this sentence
           (specific: people, ship, place, object, year), e.g. "Titanic lifeboat 1912", not abstract ideas.
  "alt_query": a different, broader search for the same sentence.
  "key": the single most important word that appears verbatim in the sentence (a number, name or strong noun).
  "number": if the sentence's main point is a number, {{"value": "<the digits as written in the sentence, e.g. 1,500>", "unit": "<2-4 word label, e.g. lives lost>"}} else null. Use it on 2-3 sentences.
  "facts": list of fact ids the sentence relies on ([] only for the pure question hook or the loop line).
Return JSON: {{"title": "<2-5 word title>", "caption": "<post caption, 1 line + 3-5 hashtags>",
"sentences": [{{"text": "...", "query": "...", "alt_query": "...", "key": "...", "number": null, "facts": [1]}}]}}"""

SUPPORT_PROMPT = """Fact-check a documentary script against its verified facts.
Flag a sentence ONLY if it states a specific, checkable fact (a number, date, name, place, cause, or concrete event detail)
that none of the FACTS support. Do NOT flag: dramatic or emotional wording, interpretation, transitions, questions, the hook,
or a closing line that restates something already established. Paraphrase is fine.
FACTS:
{facts}
SENTENCES:
{sents}
Return JSON: {{"unsupported": [{{"n": <sentence number>, "why": "<short>"}}]}}"""


def support_check(chat, sents, good, lang):
    fl = "\n".join(f"{k}. {v['fact']} (quote: {v['quote'][:200]})" for k, v in good.items())
    sl = "\n".join(f"{i+1}. {s['text']}  [cites {s['facts']}]" for i, s in enumerate(sents))
    try:
        j = ask_json(chat, SUPPORT_PROMPT.format(facts=fl, sents=sl))
    except Exception as e:
        log("support check failed", e); return sents, []
    bad = {}
    for u in j.get("unsupported", []):
        try: bad[int(u.get("n")) - 1] = str(u.get("why", ""))[:120]
        except Exception: pass
    keep = [s for i, s in enumerate(sents) if i not in bad or (i in (0, len(sents) - 1) and not nums(s["text"]) - nums(fl))]
    cut = [{"text": sents[i]["text"], "why": "unsupported: " + w} for i, w in bad.items() if i < len(sents) and sents[i] not in keep]
    return keep, cut


WPS = {"en": 2.25, "te": 1.7, "hi": 2.2}  # measured edge-tts words/s at 1.0x (Neerja ~2.25)
LANGNAME = {"en": "English", "te": "Telugu (Telugu script, natural spoken Telugu)", "hi": "Hindi (Devanagari)"}


def build_script(brief, chat, recent="", seconds=60, lang_default="en"):
    t = ask_json(chat, TOPIC_PROMPT.format(brief=brief or "AUTO", recent=recent or "none", lang=lang_default))
    lang = t.get("lang") if t.get("lang") in LANGNAME else lang_default
    topic = str(t.get("topic") or brief)
    srcs = []
    for q in (t.get("wiki_queries") or [topic])[:2]:
        try:
            for s in wiki_sources(q, n=1):
                if s["url"] not in [x["url"] for x in srcs]:
                    srcs.append(s)
        except Exception as e:
            log("wiki fail", q, e)
    if not srcs:
        raise ValueError("no sources found for topic")
    src_txt = "\n\n".join(f"[{s['url']}]\n{s['text'][:7000]}" for s in srcs)
    fj = ask_json(chat, FACTS_PROMPT.format(topic=topic, sources=src_txt))
    by_url = {s["url"]: s["text"] for s in srcs}
    facts, dropped = [], []
    for f in fj.get("facts", []):
        url = str(f.get("source_url", "")).strip()
        txt = by_url.get(url) or next((v for k, v in by_url.items() if urllib.parse.unquote(k) == urllib.parse.unquote(url)), None)
        q = str(f.get("quote", ""))
        ok = bool(txt) and quote_found(q, txt) and nums(str(f.get("fact", ""))) <= nums(q) | nums(txt)
        (facts if ok else dropped).append({"id": int(f.get("id", len(facts) + len(dropped) + 1)), "fact": str(f.get("fact", "")),
                                          "quote": q, "source_url": url})
    log(f"facts verified {len(facts)} dropped {len(dropped)}")
    if len(facts) < 4:
        raise ValueError(f"only {len(facts)} verified facts")
    words = int(seconds * WPS.get(lang, 1.9) * POLISH_TEMPO * 0.86)
    n_lo, n_hi = max(8, words // 10 + 2), max(12, words // 7 + 2)
    words_hi = int(words * 1.12)
    fl = "\n".join(f"{f['id']}. {f['fact']}  (quote: \"{f['quote'][:160]}\")" for f in facts)
    good = {f["id"]: f for f in facts}
    best = None; feedback = ""
    for attempt in range(2):
        sj = ask_json(chat, SCRIPT_PROMPT.format(seconds=seconds, topic=topic, langname=LANGNAME[lang], mood=t.get("mood", "thoughtful"),
                                                 facts=fl, words=words, words_hi=words_hi, n_lo=n_lo, n_hi=n_hi)
                          + (f"\n\nYour previous draft was rejected: {feedback}. Fix that." if feedback else ""))
        sents, cut = [], []
        raw = [s for s in sj.get("sentences", []) if str(s.get("text", "")).strip()]
        for i, s in enumerate(raw):
            text = re.sub(r"[#*_`\"]", "", str(s["text"])).strip()
            ids = [int(x) for x in (s.get("facts") or []) if str(x).isdigit()]
            bad_ids = [x for x in ids if x not in good]
            fact_txt = " ".join(good[x]["fact"] + " " + good[x]["quote"] for x in (ids if any(x in good for x in ids) else good))
            unsupported_nums = nums(text) - nums(fact_txt)
            if bad_ids or unsupported_nums:
                cut.append({"text": text, "why": f"unverified ids {bad_ids}" if bad_ids else f"numbers not in facts {sorted(unsupported_nums)}"})
                continue
            num = s.get("number") if isinstance(s.get("number"), dict) else None
            if num and not (nums(str(num.get("value", ""))) and nums(str(num.get("value", ""))) <= nums(text)):
                num = None
            key = str(s.get("key") or "").strip()
            sents.append({"text": text, "query": str(s.get("query") or topic)[:80], "alt_query": str(s.get("alt_query") or topic)[:80],
                          "key": key, "number": num, "facts": [x for x in ids if x in good]})
        sents, cut2 = support_check(chat, sents, good, lang)
        cut += cut2
        nw = sum(len(x["text"].split()) for x in sents)
        log(f"script attempt {attempt+1}: {len(sents)} kept, {len(cut)} cut, {nw} words (target {words})")
        est_s = nw / (WPS.get(lang, 1.9) * POLISH_TEMPO) + 0.45 * max(0, len(sents) - 1)
        feedback = "; ".join(x for x in [f"too short (~{est_s:.0f}s): only {nw} words, need {words}-{words_hi}" if est_s < seconds * 0.85 else "",
                                          ("these sentences were not supported by the cited facts: " + " | ".join(c["text"] for c in cut)) if len(cut) > 3 else ""] if x)
        cand = {"topic": topic, "lang": lang, "voice": t.get("voice", "female"), "mood": t.get("mood", "thoughtful"),
                "title": str(sj.get("title") or topic)[:40], "caption": str(sj.get("caption", ""))[:400],
                "sentences": sents, "facts": facts, "dropped_facts": dropped, "cut_sentences": cut, "sources": [s["url"] for s in srcs]}
        score = len(sents) - 2 * len(cut)
        if best is None or score > best["_score"]:
            cand["_score"] = score
            best = cand
        if not feedback:
            break
    if len(best["sentences"]) < 6:
        raise ValueError("script too short after fact filtering")
    return best


# ============================================================ voice (pluggable) ============================================================
VOICES = {("en", "female"): "en-IN-NeerjaNeural", ("en", "male"): "en-IN-PrabhatNeural",
          ("te", "female"): "te-IN-ShrutiNeural", ("te", "male"): "te-IN-MohanNeural",
          ("hi", "female"): "hi-IN-SwaraNeural", ("hi", "male"): "hi-IN-MadhurNeural"}


async def tts_edge(text, lang, gender, out_mp3):
    """Free Microsoft Edge neural TTS at 1.0x. Returns word list [(start_s, dur_s, word)]."""
    import edge_tts
    voice = os.environ.get("DIVYA_VOICE") or VOICES.get((lang, gender)) or VOICES[(lang, "female")]
    last = None
    for attempt in range(4):
        try:
            words, buf = [], bytearray()
            async for ch in edge_tts.Communicate(text, voice, rate="+0%", boundary="WordBoundary").stream():
                if ch["type"] == "audio":
                    buf += ch["data"]
                elif ch["type"] == "WordBoundary":
                    words.append((ch["offset"] / 1e7, ch["duration"] / 1e7, ch["text"]))
            if not buf:
                raise RuntimeError("no audio")
            open(out_mp3, "wb").write(bytes(buf))
            return words
        except Exception as e:
            last = e; await asyncio.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"TTS failed: {last}")


# To swap the voice: write `async def tts_x(text, lang, gender, out_path) -> [(start, dur, word)]` (word list may be [] ->
# captions fall back to proportional timing), add it here, and set env DIVYA_TTS=x.
TTS_BACKENDS = {"edge": tts_edge}


def tts_backend():
    return TTS_BACKENDS.get(os.environ.get("DIVYA_TTS", "edge"), tts_edge)


# ---- owner-approved voice polish (port of work/v5/flow.py, approved 2026-11-07) ----
POLISH_TEMPO = float(os.environ.get("DIVYA_TEMPO", "1.10"))
COMMA_PAUSE, STOP_PAUSE = 0.25, 0.55
POLISH_CHAIN = ("highpass=f=220,equalizer=f=300:t=q:w=1:g=-10,equalizer=f=150:t=q:w=1:g=-6,equalizer=f=450:t=q:w=1.2:g=-3,"
                "equalizer=f=2800:t=q:w=1:g=2,asplit[a][b];[a]lowpass=f=600,acompressor=threshold=0.05:ratio=6:attack=3:release=60:makeup=1[lo];"
                "[b]highpass=f=600[hi];[lo][hi]amix=inputs=2:normalize=0,deesser=i=0.8:m=0.8:f=0.4,equalizer=f=5500:t=q:w=1.2:g=-6,"
                "equalizer=f=8000:t=q:w=1.2:g=-9,highshelf=f=4500:g=-6,lowpass=f=9500")


def read_audio(path, sr=SR):
    o = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "f32le", "-ac", "1", "-ar", str(sr), "-"], capture_output=True, check=True)
    return np.frombuffer(o.stdout, np.float32).copy()


def write_wav(path, x, sr=SR):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(sr), "-ac", "1", "-i", "-", path],
                   input=np.asarray(x, np.float32).tobytes(), check=True)


def ff_filter(x, af, sr=SR):
    o = subprocess.run(["ffmpeg", "-v", "error", "-f", "f32le", "-ar", str(sr), "-ac", "1", "-i", "-", "-filter_complex", af,
                        "-f", "f32le", "-ac", "1", "-ar", str(sr), "-"], input=np.asarray(x, np.float32).tobytes(), capture_output=True, check=True)
    return np.frombuffer(o.stdout, np.float32).copy()


def _analyse(x, sr):
    hop = int(sr * .01); win = hop * 3; w = np.hanning(win); fr = np.fft.rfftfreq(win, 1 / sr); R = []
    for i in range(0, max(1, len(x) - win), hop):
        f = x[i:i + win] * w
        if len(f) < win:
            break
        S = np.abs(np.fft.rfft(f)) ** 2 + 1e-12
        R.append((10 * np.log10(np.mean(f ** 2) + 1e-12), S[(fr > 80) & (fr < 400)].sum() / S.sum()))
    R = np.array(R if R else [(-90, 0)]); R[:, 0] -= np.percentile(R[:, 0], 95)
    return R, hop


def _fade(x, sr, a=.02, b=.04):
    na, nb = min(len(x) // 2, int(sr * a)), min(len(x) // 2, int(sr * b)); x = x.copy()
    if na: x[:na] *= np.linspace(0, 1, na)
    if nb: x[-nb:] *= np.linspace(1, 0, nb)
    return x


def polish_clause(x, sr=SR):
    """Trim (keep 100 ms before first voiced frame, <=120 ms soft tail), attenuate breaths/unvoiced runs >=180 ms,
    EQ + low-band compressor + de-esser chain, atempo. Returns (audio, trim_start_s)."""
    R, hop = _analyse(x, sr); db, lo = R[:, 0], R[:, 1]
    voiced = (db > -22) & (lo > 0.08); sound = db > -48
    v = np.where(voiced)[0]
    if len(v) == 0:
        v = np.where(sound)[0]
    if len(v) == 0:
        return ff_filter(x, f"[0:a]{POLISH_CHAIN},atempo={POLISH_TEMPO}"), 0.0
    s = max(0, v[0] - 10)
    e0 = e = v[-1] + 1
    while e < len(db) and sound[e] and e < e0 + 12:
        e += 1
    e = min(len(db), e + 3)
    seg = x[s * hop:e * hop].copy()
    lab = [(not voiced[t]) and db[t] < -30 for t in range(s, e)]
    t = 0
    while t < len(lab):
        if lab[t]:
            u = t
            while u < len(lab) and lab[u]:
                u += 1
            if u - t >= 18:
                g = np.ones(len(seg), np.float32); A, B = t * hop, min(len(seg), u * hop); g[A:B] = 0.1
                r = min(int(sr * .01), (B - A) // 2)
                if r: g[A:A + r] = np.linspace(1, .1, r); g[B - r:B] = np.linspace(.1, 1, r)
                seg *= g
            t = u
        else:
            t += 1
    seg = _fade(seg, sr)
    out = ff_filter(seg, f"[0:a]{POLISH_CHAIN},atempo={POLISH_TEMPO}")
    return _fade(out, sr, .005, .03), s * hop / sr


def split_clauses(text):
    parts = [p.strip() for p in re.split(r"(?<=[,;:\u2014])\s+", text) if p.strip()]
    merged = []
    for p in parts:  # do not split off tiny fragments
        if merged and len(p.split()) < 3:
            merged[-1] += " " + p
        else:
            merged.append(p)
    return merged or [text]


async def voice_sentence(text, lang, gender, wd, idx):
    """One TTS clip per clause -> polished, joined with 0.25 s comma pauses. Returns (wav_path, duration, words)."""
    tts = tts_backend()
    chunks, words, t = [], [], 0.0
    for ci, cl in enumerate(split_clauses(text)):
        raw = f"{wd}/raw{idx}_{ci}.mp3"
        ws = await tts(cl, lang, gender, raw)
        x = read_audio(raw)
        y, trim = polish_clause(x)
        for (o, d, w) in ws:
            words.append((max(0.0, t + (o - trim) / POLISH_TEMPO), d / POLISH_TEMPO, w))
        if not ws:  # proportional fallback
            toks = cl.split(); L = len(y) / SR; tot = sum(len(k) for k in toks) or 1; acc = 0
            for k in toks:
                dd = L * len(k) / tot; words.append((t + acc, dd, k)); acc += dd
        chunks.append(y); t += len(y) / SR
        if ci < len(split_clauses(text)) - 1:
            chunks.append(np.zeros(int(SR * COMMA_PAUSE), np.float32)); t += COMMA_PAUSE
    y = np.concatenate(chunks)
    y = ff_filter(y, "loudnorm=I=-16:TP=-1.5:LRA=11")[:len(y)]
    path = f"{wd}/vo{idx}.wav"; write_wav(path, y)
    return path, len(y) / SR, words


def pause_after(text, i, n):
    """250-600 ms: full stop 0.55 s (owner flow), questions/hook a touch longer, never > 0.6."""
    if i == n - 1:
        return 0.0
    p = STOP_PAUSE if text.rstrip()[-1:] in ".!?" else COMMA_PAUSE
    if i == 0 or text.rstrip().endswith("?"):
        p = 0.6
    return max(0.25, min(0.6, p))


# ============================================================ visuals ============================================================
BAD_TITLE = re.compile(r"(logo|icon|flag of|coat of arms|map|diagram|chart|graph|signature|svg|seal of|plan of|blueprint|"
                       r"locator|scheme|stamp|banknote|coin|text|letter|page \d|title page|poster)", re.I)


def commons_search(q, limit=14):
    r = http_get("https://commons.wikimedia.org/w/api.php", {
        "action": "query", "format": "json", "generator": "search", "gsrsearch": f"{q} filetype:bitmap", "gsrnamespace": 6,
        "gsrlimit": limit, "prop": "imageinfo", "iiprop": "url|size|mime|extmetadata", "iiurlwidth": 1280,
        "iiextmetadatafilter": "Artist|LicenseShortName|ObjectName|ImageDescription"})
    pages = sorted(r.json().get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 99))
    out = []
    for p in pages:
        ii = (p.get("imageinfo") or [{}])[0]
        if ii.get("mime") not in ("image/jpeg", "image/png", "image/webp"):
            continue
        if ii.get("width", 0) < 700 or ii.get("height", 0) < 450 or BAD_TITLE.search(p["title"]):
            continue
        md = ii.get("extmetadata", {})
        strip = lambda v: re.sub(r"<[^>]+>", "", str((md.get(v) or {}).get("value", ""))).strip()[:140]
        out.append({"title": p["title"], "thumb": ii.get("thumburl") or ii["url"], "page": ii.get("descriptionurl", ""),
                    "artist": strip("Artist") or "unknown", "license": strip("LicenseShortName") or "see file page",
                    "w": ii.get("width"), "h": ii.get("height")})
    return out


def dhash(im, n=8):
    g = np.asarray(im.convert("L").resize((n + 1, n), Image.BILINEAR), np.int16)
    return (g[:, 1:] > g[:, :-1]).flatten()


def fetch_image(url):
    r = http_get(url, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"image HTTP {r.status_code}")
    im = Image.open(io.BytesIO(r.content)); im = ImageOps.exif_transpose(im).convert("RGB")
    return im


def jpeg_bytes(im, maxside=512, q=82):
    im = im.copy(); im.thumbnail((maxside, maxside)); b = io.BytesIO(); im.save(b, "JPEG", quality=q); return b.getvalue()


# ---------------- vision (Gemini preferred, Groq fallback) ----------------
GEMINI_MODELS = ["gemini-2.5-flash", "gemini-2.0-flash"]
GROQ_VISION = [m for m in os.environ.get("GROQ_VISION_MODELS", "qwen/qwen3.8-27b,meta-llama/llama-4-scout-17b-16e-instruct").split(",") if m]
VISION_STATE = {"gemini_ok": None, "used": {}}
REJECTED = set()  # (sentence, image url) pairs the vision check already refused


def gemini_keys():
    return [k.strip() for k in os.environ.get("GEMINI_KEY", "").split(",") if k.strip()]


def vision(prompt, jpgs, max_tokens=500):
    """Returns (text, provider). jpgs: list of jpeg bytes."""
    if gemini_keys() and VISION_STATE["gemini_ok"] is not False:
        parts = [{"text": prompt}] + [{"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(j).decode()}} for j in jpgs]
        for k in gemini_keys():
            for m in GEMINI_MODELS:
                try:
                    r = httpx.post(f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent", headers={"x-goog-api-key": k},
                                   json={"contents": [{"parts": parts}], "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"}},
                                   timeout=90)
                    if r.status_code == 200:
                        VISION_STATE["gemini_ok"] = True
                        txt = "".join(p.get("text", "") for p in r.json()["candidates"][0]["content"]["parts"])
                        VISION_STATE["used"][f"gemini:{m}"] = VISION_STATE["used"].get(f"gemini:{m}", 0) + 1
                        return txt, f"gemini:{m}"
                    log("gemini", m, r.status_code)
                    if r.status_code == 429:
                        time.sleep(5)
                except Exception as e:
                    log("gemini err", type(e).__name__)
        if VISION_STATE["gemini_ok"] is None:
            VISION_STATE["gemini_ok"] = False
    content = [{"type": "text", "text": prompt}] + [{"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(j).decode()}} for j in jpgs]
    last = ""; keys = groq_keys()
    for m in GROQ_VISION:
        dead = False
        for attempt in range(5):
            ra_min = 60.0
            for k in keys:
                try:
                    r = httpx.post("https://api.groq.com/openai/v1/chat/completions", headers={"Authorization": f"Bearer {k}"},
                                   json={"model": m, "messages": [{"role": "user", "content": content}], "temperature": 0.1, "max_tokens": max_tokens},
                                   timeout=90)
                except Exception as e:
                    last = type(e).__name__; continue
                if r.status_code == 200:
                    VISION_STATE["used"][f"groq:{m}"] = VISION_STATE["used"].get(f"groq:{m}", 0) + 1
                    return re.sub(r"<think>[\s\S]*?</think>", "", r.json()["choices"][0]["message"].get("content") or ""), f"groq:{m}"
                last = f"{m} {r.status_code}"
                if r.status_code == 429:
                    try: ra_min = min(ra_min, float(r.headers.get("retry-after", "10")))
                    except Exception: ra_min = min(ra_min, 10)
                    continue
                dead = True; break
            if dead:
                break
            time.sleep(min(30, ra_min) + 1)
    raise RuntimeError("vision failed: " + last)


def vjson(prompt, jpgs, max_tokens=500):
    txt, prov = vision(prompt, jpgs, max_tokens)
    m = re.search(r"\{[\s\S]*\}", txt)
    try:
        return json.loads(m.group(0)), prov
    except Exception:
        return {"_raw": txt[:300]}, prov


def image_ok(im, sentence, query):
    j, _ = vjson(f"""You are picking B-roll for a documentary Short.
Narration line: "{sentence}"
Search used: "{query}"
Is this image a good literal illustration of THIS line (same subject, object, person, place or era)? Reject it if it is mostly
text / a document scan / a map / a diagram / a logo / blank / unrelated / a modern image for a historical line.
Answer ONLY JSON: {{"ok": true|false, "shows": "<what it shows, max 12 words>"}}""", [jpeg_bytes(im, 384)], max_tokens=200)
    if "ok" not in j:
        return None, "unchecked"
    return bool(j.get("ok")), str(j.get("shows", ""))[:100]


def pick_visual(sh, used_urls, used_hashes, check=True, skip=()):
    """Find an unused, vision-approved Commons image for a shot. Returns dict or None."""
    tried = 0; fallback = None
    qs = [sh["query"], sh["alt_query"]]
    if sh.get("key") and sh.get("topic_hint"):
        qs.append(f"{sh['key']} {sh['topic_hint']}")
    for q in qs:
        try:
            cands = commons_search(q)
        except Exception as e:
            log("commons fail", q, e); cands = []
        for c in cands:
            if c["thumb"] in used_urls or c["thumb"] in skip or (sh["text"], c["thumb"]) in REJECTED:
                continue
            if tried >= 5:
                break
            try:
                im = fetch_image(c["thumb"])
            except Exception as e:
                log("img fail", c["title"][:50], e); continue
            hsh = dhash(im)
            if any(np.count_nonzero(hsh != h) <= 6 for h in used_hashes):
                continue
            tried += 1
            try:
                ok, shows = (True, "") if not check else image_ok(im, sh["text"], q)
            except Exception as e:
                log("vision unavailable, taking first result:", str(e)[:80]); ok, shows = None, "unchecked"
            if ok is None and fallback is None:
                fallback = (c, im, hsh, q)
            if ok:
                c.update({"img": im, "hash": hsh, "shows": shows, "query_used": q}); return c
            elif ok is False:
                REJECTED.add((sh["text"], c["thumb"]))
                log("rejected", c["title"][:60], "->", shows)
        if tried >= 5:
            break
    if fallback:
        c, im, hsh, q = fallback; c.update({"img": im, "hash": hsh, "shows": "unchecked", "query_used": q}); return c
    return None


def compose_photo(im, seed):
    """Prepare an oversized 9:16 canvas (for Ken Burns). Landscape -> blurred fill + large foreground; portrait -> cover."""
    S = 1.14; cw, ch = int(W * S), int(H * S)
    ar = im.width / im.height
    bg = ImageOps.fit(im, (cw // 4, ch // 4), Image.BILINEAR).filter(ImageFilter.GaussianBlur(10)).resize((cw, ch), Image.BILINEAR)
    bg = Image.blend(bg, Image.new("RGB", bg.size, (0, 0, 0)), 0.5)
    if ar <= 0.9:
        return ImageOps.fit(im, (cw, ch), Image.LANCZOS, centering=(0.5, 0.42))
    fw = int(cw * min(1.45, max(1.0, 1.2 * ar / 1.5)))  # crop at most ~30 % of width
    fh = int(fw / ar)
    if fh > ch * 0.62:
        fh = int(ch * 0.62); fw = int(fh * ar)
    fg = im.resize((fw, fh), Image.LANCZOS)
    x = (cw - fw) // 2; y = int(ch * 0.40 - fh / 2)
    bg.paste(fg, (x, y))
    return bg


def draw_card(kind, text, unit, bg_img):
    """Drawn number card (or key-word card when nothing was found), over a dark blurred copy of the previous visual."""
    S = 1.14; cw, ch = int(W * S), int(H * S)
    if bg_img is not None:
        base = ImageOps.fit(bg_img, (cw // 6, ch // 6)).filter(ImageFilter.GaussianBlur(6)).resize((cw, ch), Image.BILINEAR)
        base = Image.blend(base, Image.new("RGB", base.size, (8, 8, 10)), 0.78)
    else:
        base = Image.new("RGB", (cw, ch), (10, 10, 12))
    return {"base": base, "kind": kind, "text": text, "unit": unit}


_fonts = {}


def fnt(name, size):
    k = (name, int(size))
    if k not in _fonts:
        _fonts[k] = ImageFont.truetype(os.path.join(FONTS, name), int(size), layout_engine=ImageFont.Layout.RAQM)
    return _fonts[k]


def card_frame(card, t, d):
    im = card["base"].copy(); dr = ImageDraw.Draw(im); cw, ch = im.size
    if card["kind"] == "number":
        val = card["text"]; m = re.search(r"\d[\d,\.]*", val)
        k = min(1.0, t / 0.7); k = 1 - (1 - k) ** 3
        if m:
            target = float(m.group(0).replace(",", ""))
            cur = target * k
            dec = len(m.group(0).split(".")[1]) if "." in m.group(0) else 0
            s = f"{cur:,.{dec}f}" if "," in m.group(0) else f"{cur:.{dec}f}"
            val = val[:m.start()] + s + val[m.end():]
        size = 300
        while size > 120 and dr.textlength(card["text"], font=fnt("Anton-Regular.ttf", size)) > cw * 0.8:
            size -= 10
        f = fnt("Anton-Regular.ttf", size)
        w = dr.textlength(val, font=f); dr.text(((cw - w) / 2, ch * 0.33), val, font=f, fill=YELLOW)
        if card["unit"]:
            fu = fnt("Anton-Regular.ttf", 84); u = card["unit"].upper()
            while dr.textlength(u, font=fu) > cw * 0.8 and fu.size > 40:
                fu = fnt("Anton-Regular.ttf", fu.size - 6)
            w = dr.textlength(u, font=fu); dr.text(((cw - w) / 2, ch * 0.33 + size * 1.25), u, font=fu, fill=WHITE)
    else:
        fname = "NotoSansTelugu.ttf" if re.search(r"[\u0c00-\u0c7f]", card["text"]) else "Anton-Regular.ttf"
        size = 190; txt = card["text"] if fname != "Anton-Regular.ttf" else card["text"].upper()
        while size > 70 and dr.textlength(txt, font=fnt(fname, size)) > cw * 0.82:
            size -= 8
        f = fnt(fname, size); w = dr.textlength(txt, font=f)
        dr.text(((cw - w) / 2, ch * 0.36), txt, font=f, fill=WHITE)
    return im


def ken_burns(canvas, t, d, seed):
    rng = random.Random(seed)
    z0, z1 = (1.0, 1.10) if rng.random() < 0.6 else (1.10, 1.0)
    px, py = rng.choice([-1, 1]) * rng.uniform(15, 45), rng.uniform(-25, 25)
    u = min(1.0, max(0.0, t / max(d, 0.1)))
    z = z0 + (z1 - z0) * u
    cw, ch = canvas.size
    vw, vh = cw / z / 1.14 * 1.0, ch / z / 1.14
    cx = cw / 2 + px * (u - 0.5) * 2; cy = ch / 2 + py * (u - 0.5) * 2
    box = (cx - vw / 2, cy - vh / 2, cx + vw / 2, cy + vh / 2)
    return canvas.transform((W, H), Image.EXTENT, box, Image.BILINEAR)


# ============================================================ captions ============================================================
def cap_font(lang, size_mul=1.0):
    if lang == "te":
        return fnt("NotoSansTelugu.ttf", int(54 * size_mul))
    return fnt("Anton-Regular.ttf", int(58 * size_mul))


def chunk_words(words, text, lang, maxw=4):
    """Group (start, dur, word) into caption lines of <=4 words, breaking at punctuation."""
    groups, cur = [], []
    for w in words:
        cur.append(w)
        if len(cur) >= maxw or re.search(r"[,.;:?!]$", w[2]):
            groups.append(cur); cur = []
    if cur:
        if groups and len(cur) == 1 and len(groups[-1]) < maxw:
            groups[-1] += cur
        else:
            groups.append(cur)
    return groups


def clean_tok(s):
    return re.sub(r"[^\w\u0c00-\u0c7f\u0900-\u097f%]+", "", s.lower())


def render_caption(tokens, key, lang, size_mul=1.0):
    """RGBA strip with white words, key word yellow, thick black outline + soft shadow."""
    f = cap_font(lang, size_mul)
    while True:
        disp = [t.upper() if lang == "en" else t for t in tokens]
        sp = f.getlength(" ")
        widths = [f.getlength(t) for t in disp]
        total = sum(widths) + sp * (len(disp) - 1)
        if total <= CAP_MAXW or f.size < 34:
            break
        f = ImageFont.truetype(f.path, f.size - 4, layout_engine=ImageFont.Layout.RAQM)
    asc, desc = f.getmetrics(); hh = asc + desc + 40
    im = Image.new("RGBA", (int(total) + 60, hh), (0, 0, 0, 0))
    sh = Image.new("RGBA", im.size, (0, 0, 0, 0)); ds = ImageDraw.Draw(sh); d = ImageDraw.Draw(im)
    keys = {clean_tok(k) for k in re.split(r"\s+", key or "") if clean_tok(k)}
    x = 30
    for t, wdt in zip(disp, widths):
        col = YELLOW if clean_tok(t) in keys else WHITE
        ds.text((x + 4, 24), t, font=f, fill=(0, 0, 0, 160), stroke_width=6, stroke_fill=(0, 0, 0, 160))
        d.text((x, 20), t, font=f, fill=col, stroke_width=5, stroke_fill=(0, 0, 0))
        x += wdt + sp
    sh = sh.filter(ImageFilter.GaussianBlur(5))
    return Image.alpha_composite(sh, im)


# ============================================================ timeline + render ============================================================
def build_timeline(p):
    """Sentence timing -> shots (one visual each, ~2.5-5 s) and caption events."""
    t = PREROLL; shots, caps = [], []
    n = len(p["sentences"])
    for i, s in enumerate(p["sentences"]):
        s["start"] = t; s["end"] = t + s["adur"]
        nxt = s["end"] + s["pause"]
        seg_end = nxt if i < n - 1 else s["end"] + TAIL
        d = seg_end - t
        nsh = 1 if d <= 5.2 else (2 if d <= 10 else 3)
        for k in range(nsh):
            a = t + d * k / nsh; b = t + d * (k + 1) / nsh
            shots.append({"sent": i, "k": k, "start": a, "end": b, "text": s["text"],
                          "query": s["query"] if k == 0 else s["alt_query"], "alt_query": s["alt_query"] if k == 0 else s["query"],
                          "number": s["number"] if k == 0 else None, "key": s["key"],
                          "topic_hint": " ".join(re.findall(r"[A-Za-z0-9]+", p.get("topic", ""))[:3])})
        for g in chunk_words(s["words"], s["text"], p["lang"]):
            caps.append({"sent": i, "start": t + g[0][0], "tokens": [w[2] for w in g], "key": s["key"]})
        t = nxt if i < n - 1 else seg_end
    for j, c in enumerate(caps):
        c["end"] = caps[j + 1]["start"] if j + 1 < len(caps) and caps[j + 1]["sent"] == c["sent"] else \
            min(p["sentences"][c["sent"]]["end"] + 0.25, caps[j + 1]["start"] if j + 1 < len(caps) else 1e9)
    p["shots"], p["caps"], p["total"] = shots, caps, t
    return p


def assign_visuals(p, check=True, redo=None):
    """redo: {shot_index: set(urls to avoid)} -> only those shots are re-picked."""
    used_urls = set(); used_hashes = []
    for j, sh in enumerate(p["shots"]):
        if redo is None or j not in redo:
            if sh.get("src"):
                used_urls.add(sh["src"]["thumb"]); used_hashes.append(sh["src"]["hash"])
    prev_img = None
    for j, sh in enumerate(p["shots"]):
        if redo is not None and j not in redo:
            if sh.get("src"): prev_img = sh["src"]["img"]
            continue
        sh.pop("card", None); sh.pop("src", None)
        if sh.get("number") and sh["end"] - sh["start"] <= 5.5:
            sh["card"] = draw_card("number", sh["number"]["value"], sh["number"].get("unit", ""), prev_img)
            sh["kind"] = "number"; continue
        c = pick_visual(sh, used_urls, used_hashes, check=check, skip=(redo or {}).get(j, set()))
        if c:
            used_urls.add(c["thumb"]); used_hashes.append(c["hash"]); sh["src"] = c; sh["kind"] = "photo"; prev_img = c["img"]
            log(f"shot {j} s{sh['sent']}: {c['title'][:70]}")
        elif sh.get("number"):
            sh["card"] = draw_card("number", sh["number"]["value"], sh["number"].get("unit", ""), prev_img); sh["kind"] = "number"
        else:
            sh["card"] = draw_card("word", sh["key"] or sh["text"].split()[0], "", prev_img); sh["kind"] = "card"
            log(f"shot {j}: nothing found -> key-word card")
    for j, sh in enumerate(p["shots"]):
        sh["canvas"] = compose_photo(sh["src"]["img"], j) if sh.get("src") else None


_P = None


def frame_at(T):
    p = _P
    sh = next((s for s in p["shots"] if s["start"] <= T < s["end"]), p["shots"][-1])
    j = p["shots"].index(sh); t = T - sh["start"]; d = sh["end"] - sh["start"]
    if sh.get("canvas") is not None:
        im = ken_burns(sh["canvas"], t, d, j)
    else:
        im = ken_burns(card_frame(sh["card"], t, d), t, d, j + 7) if sh["kind"] != "number" else \
            card_frame(sh["card"], t, d).resize((W, H), Image.BILINEAR)
    c = next((c for c in p["caps"] if c["start"] <= T < c["end"]), None)
    if c is not None:
        key = id(c)
        if key not in p["_capcache"]:
            p["_capcache"][key] = render_caption(c["tokens"], c["key"], p["lang"], c.get("size_mul", 1.0))
        strip = p["_capcache"][key]
        im.paste(strip, (int((W - strip.width) / 2), int(CAP_Y - strip.height / 2)), strip)
    return im


def _render_chunk(args):
    f0, f1, out = args
    pr = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                           "-c:v", "libx264", "-preset", "veryfast", "-crf", "17", "-pix_fmt", "yuv420p", out], stdin=subprocess.PIPE)
    for fi in range(f0, f1):
        pr.stdin.write(frame_at(fi / FPS).tobytes())
    pr.stdin.close(); pr.wait(); return out


def render_video(p, wd, workers=None):
    global _P
    p["_capcache"] = {}
    _P = p; nf = int(round(p["total"] * FPS)); k = workers or max(1, min(4, os.cpu_count() or 1))
    cuts = [nf * i // k for i in range(k + 1)]
    jobs = [(cuts[i], cuts[i + 1], f"{wd}/part{i}.mp4") for i in range(k)]
    with mp.get_context("fork").Pool(k) as pool:
        parts = pool.map(_render_chunk, jobs)
    open(f"{wd}/parts.txt", "w").write("".join(f"file '{x}'\n" for x in parts))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", f"{wd}/parts.txt", "-c", "copy", f"{wd}/raw.mp4"], check=True)
    return f"{wd}/raw.mp4"


# ============================================================ audio: music + sfx + mix ============================================================
MUSIC = {  # Kevin MacLeod (incompetech.com), CC BY 4.0
    "dark": ["Lightless Dawn", "Darkest Child", "Gathering Darkness"],
    "sad": ["Heartbreaking", "Sad Trio", "Despair and Triumph"],
    "mystery": ["Comfortable Mystery 4", "Hidden Agenda", "Investigations", "Atlantean Twilight"],
    "thoughtful": ["Dreamer", "Healing", "Clean Soul", "Ether Vox"],
    "hopeful": ["Inspired", "Wholesome", "Floating Cities"],
    "tense": ["Stormfront", "Volatile Reaction", "Dark Walk"],
    "epic": ["Impact Prelude", "Rising Tide"],
}


def music_credit(title):
    return (f'"{title}" Kevin MacLeod (incompetech.com)\nLicensed under Creative Commons: By Attribution 4.0 License\n'
            "http://creativecommons.org/licenses/by/4.0/")


def get_music(mood, wd, seed=0):
    opts = MUSIC.get(mood) or MUSIC["thoughtful"]
    order = opts[seed % len(opts):] + opts[:seed % len(opts)]
    for title in order:
        url = "https://incompetech.com/music/royalty-free/mp3-royaltyfree/" + urllib.parse.quote(title) + ".mp3"
        try:
            r = http_get(url, timeout=60, tries=2)
            if r.status_code == 200 and len(r.content) > 100_000:
                path = f"{wd}/music.mp3"; open(path, "wb").write(r.content)
                return path, title
            log("music", title, r.status_code)
        except Exception as e:
            log("music fail", title, e)
    return None, None


def sfx_track(p, total, path):
    n = int(SR * total); out = np.zeros(n, np.float32); rng = np.random.RandomState(3)
    L = int(0.32 * SR); tt = np.arange(L) / SR; nz = rng.randn(L)
    nz = np.convolve(nz, np.ones(24) / 24, "same")  # soft, dull whoosh
    whoosh = (nz * (np.sin(np.pi * tt / tt[-1]) ** 3) * 0.10).astype(np.float32)
    Lb = int(0.6 * SR); tb = np.arange(Lb) / SR
    hit = (np.sin(2 * np.pi * np.cumsum(50 + 90 * np.exp(-tb * 18)) / SR) * np.exp(-tb * 7) * 0.30).astype(np.float32)

    def add(sig, t0):
        a = int(t0 * SR); e = min(n, a + len(sig))
        if 0 <= a < n: out[a:e] += sig[:e - a]
    for sh in p["shots"][1:]:
        add(whoosh, sh["start"] - 0.22)
    for sh in p["shots"]:
        if sh.get("kind") == "number":
            add(hit, sh["start"])
    write_wav(path, out)


def loud_measure(path):
    o = subprocess.run(["ffmpeg", "-hide_banner", "-i", path, "-af", "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True)
    return json.loads(re.findall(r"\{[\s\S]*?\}", o.stderr)[-1])


def mix_audio(p, wd):
    total = p["total"]; ins = []; fc = ""
    for i, s in enumerate(p["sentences"]):
        ins += ["-i", s["audio"]]; ms = int(s["start"] * 1000)
        fc += f"[{i}:a]adelay={ms}|{ms}[a{i}];"
    n = len(p["sentences"])
    fc += "".join(f"[a{i}]" for i in range(n)) + f"amix=inputs={n}:normalize=0,apad,atrim=0:{total:.3f}[o]"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *ins, "-filter_complex", fc, "-map", "[o]", "-ar", str(SR), "-ac", "1", f"{wd}/voice.wav"], check=True)
    sfx_track(p, total, f"{wd}/sfx.wav")
    mpath, title = get_music(p.get("mood", "thoughtful"), wd, seed=len(p["topic"]))
    p["music"] = title
    if mpath:
        # music bed -33 LUFS pre-duck (voice is -16): ~17 dB under in gaps, ~-22..-23 dB under while she speaks (sidechain duck)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-stream_loop", "-1", "-i", mpath, "-t", f"{total:.3f}", "-af",
                        f"loudnorm=I=-33:TP=-8:LRA=11,afade=t=in:d=0.6,afade=t=out:st={max(0, total - 1.8):.2f}:d=1.8",
                        "-ar", str(SR), "-ac", "1", f"{wd}/music.wav"], check=True)
        fc = ("[0:a]asplit[v1][v2];[1:a][v2]sidechaincompress=threshold=0.02:ratio=6:attack=20:release=400:makeup=1[md];"
              "[v1][md][2:a]amix=inputs=3:normalize=0[o]")
        ins = ["-i", f"{wd}/voice.wav", "-i", f"{wd}/music.wav", "-i", f"{wd}/sfx.wav"]
    else:
        fc = "[0:a][1:a]amix=inputs=2:normalize=0[o]"; ins = ["-i", f"{wd}/voice.wav", "-i", f"{wd}/sfx.wav"]
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *ins, "-filter_complex", fc, "-map", "[o]", "-ar", str(SR), f"{wd}/premix.wav"], check=True)
    m = loud_measure(f"{wd}/premix.wav")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", f"{wd}/premix.wav", "-af",
                    f"loudnorm=I=-14:TP=-1.5:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:"
                    f"measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true", "-ar", str(SR), f"{wd}/mix.wav"], check=True)
    return f"{wd}/mix.wav"


def export(raw, mix, out, total):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", raw, "-i", mix, "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "medium",
                    "-crf", "21", "-maxrate", "2000k", "-bufsize", "4000k", "-r", str(FPS), "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
                    "-ar", "48000", "-t", f"{total:.3f}", "-movflags", "+faststart", out], check=True)
    if os.path.getsize(out) > 15_500_000:  # WhatsApp 16 MB
        kb = max(700, int(14.5 * 8192 / total) - 140); small = out.replace(".mp4", "_wa.mp4")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", out, "-c:v", "libx264", "-preset", "medium", "-b:v", f"{kb}k", "-maxrate", f"{int(kb*1.15)}k",
                        "-bufsize", f"{kb*2}k", "-c:a", "copy", "-movflags", "+faststart", small], check=True)
        os.replace(small, out)
    return out


# ============================================================ QC ============================================================
def stt(path, wd, lang):
    a = f"{wd}/qc_audio.mp3"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", path, "-vn", "-ac", "1", "-ar", "16000", "-b:a", "48k", a], check=True)
    last = ""
    for k in groq_keys():
        for m in ["whisper-large-v3-turbo", "whisper-large-v3"]:
            try:
                with open(a, "rb") as fh:
                    r = httpx.post("https://api.groq.com/openai/v1/audio/transcriptions", headers={"Authorization": f"Bearer {k}"},
                                   data={"model": m, "language": lang, "response_format": "json", "temperature": "0"},
                                   files={"file": ("a.mp3", fh, "audio/mpeg")}, timeout=180)
                if r.status_code == 200:
                    return r.json().get("text", ""), m
                last = f"{m} {r.status_code}"
            except Exception as e:
                last = type(e).__name__
    raise RuntimeError("STT failed: " + last)


def wer(ref, hyp):
    r, h = norm(ref), norm(hyp)
    r = [x.strip(".'") for x in r]; h = [x.strip(".'") for x in h]
    d = np.zeros((len(r) + 1, len(h) + 1), int); d[:, 0] = range(len(r) + 1); d[0, :] = range(len(h) + 1)
    for i in range(1, len(r) + 1):
        for j in range(1, len(h) + 1):
            d[i, j] = min(d[i - 1, j] + 1, d[i, j - 1] + 1, d[i - 1, j - 1] + (r[i - 1] != h[j - 1]))
    return d[len(r), len(h)] / max(1, len(r))


QC_PROMPT = """You are the final QC editor for a vertical documentary Short. This is the frame at {t:.1f} s.
The narrator is saying: "{line}"
The burned-in caption should read: "{cap}" (white words, one key word in yellow).
Judge strictly as a professional editor and answer ONLY JSON:
{{"visual": "<what the picture shows, max 12 words>",
 "matches_line": true|false,     // does the picture literally illustrate what is being said (same subject/object/person/place/era)?
 "text_cut_off": true|false,     // is any on-screen text cut by the frame edge or clipped?
 "text_overlap": true|false,     // does on-screen text overlap other text or make the caption unreadable?
 "empty_or_broken": true|false,  // blank, black, mostly flat colour, corrupted, or a placeholder?
 "issue": "<short reason if any check fails, else empty>"}}"""


def run_qc(p, video, wd, round_no):
    fdir = f"{wd}/qc_frames_r{round_no}"; os.makedirs(fdir, exist_ok=True)
    total = p["total"]; ts = [round(x, 2) for x in np.arange(1.0, total - 0.2, 3.0)]
    frames = []
    for t in ts:
        fp = f"{fdir}/f_{t:05.1f}.jpg"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t}", "-i", video, "-frames:v", "1", "-vf", "scale=540:960", "-q:v", "3", fp], check=True)
        sh_i = next((j for j, s in enumerate(p["shots"]) if s["start"] <= t < s["end"]), len(p["shots"]) - 1)
        sh = p["shots"][sh_i]
        c = next((c for c in p["caps"] if c["start"] <= t < c["end"]), None)
        cap = " ".join(c["tokens"]) if c else "(no caption at this moment)"
        try:
            j, prov = vjson(QC_PROMPT.format(t=t, line=sh["text"], cap=cap), [open(fp, "rb").read()])
        except Exception as e:
            j, prov = {"error": str(e)[:120]}, "none"
        ok = (j.get("matches_line") is True) and not j.get("text_cut_off") and not j.get("text_overlap") and not j.get("empty_or_broken")
        if sh.get("kind") == "number":  # a drawn number card illustrates its number by design; judge only text/empty checks
            ok = not j.get("text_cut_off") and not j.get("text_overlap") and not j.get("empty_or_broken")
        frames.append({"t": t, "frame": os.path.basename(fp), "shot": sh_i, "kind": sh.get("kind"), "line": sh["text"], "caption": cap,
                       "image": (sh.get("src") or {}).get("title"), "vision": j, "provider": prov, "pass": bool(ok)})
    # repeats: identical source images (perceptual hash) across shots
    hs = [(j, s["src"]["hash"]) for j, s in enumerate(p["shots"]) if s.get("src")]
    repeats = [[a, b] for x, (a, ha) in enumerate(hs) for (b, hb) in hs[x + 1:] if np.count_nonzero(ha != hb) <= 6]
    # shot lengths
    lens = [round(s["end"] - s["start"], 2) for s in p["shots"]]
    script = " ".join(s["text"] for s in p["sentences"])
    try:
        hyp, model = stt(video, wd, p["lang"]); w = wer(script, hyp)
    except Exception as e:
        hyp, model, w = f"(failed: {e})", None, 1.0
    hook_s = p["sentences"][0]["adur"] + PREROLL
    rep = {"round": round_no, "frames": frames, "frames_pass": sum(f["pass"] for f in frames), "frames_total": len(frames),
           "repeated_images": repeats, "shot_lengths_s": lens, "stt_model": model, "stt_text": hyp, "wer": round(w, 3),
           "hook_spoken_by_s": round(hook_s, 2), "duration_s": round(total, 2)}
    rep["pass"] = (rep["frames_pass"] == rep["frames_total"]) and not repeats and w <= 0.12
    return rep


def loudness_report(path):
    m = loud_measure(path)
    return {"integrated_lufs": float(m["input_i"]), "true_peak_db": float(m["input_tp"])}


def probe(path):
    o = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_name,width,height,r_frame_rate,sample_rate:format=duration,size",
                        "-of", "json", path], capture_output=True, text=True)
    return json.loads(o.stdout)


# ============================================================ credits ============================================================
def write_credits(p, path):
    L = [f"{p['title']} - credits", "", "IMAGES (Wikimedia Commons):"]
    for j, sh in enumerate(p["shots"]):
        if sh.get("src"):
            s = sh["src"]
            L.append(f"- {sh['start']:.1f}s: {s['title'].replace('File:', '')} | {s['artist']} | {s['license']} | {s['page']}")
        else:
            L.append(f"- {sh['start']:.1f}s: drawn {sh.get('kind')} card (Divya)")
    L += ["", "MUSIC:", music_credit(p["music"]) if p.get("music") else "(none - download failed)", "",
          f"VOICE: Microsoft Edge neural TTS ({os.environ.get('DIVYA_VOICE') or VOICES.get((p['lang'], p.get('voice', 'female')))}), Divya voice polish chain",
          "", "FACT SOURCES:"]
    for f in p["facts"]:
        L.append(f"- [{f['id']}] {f['fact']} <{f['source_url']}>")
    open(path, "w", encoding="utf-8").write("\n".join(L) + "\n")


# ============================================================ main ============================================================
async def make_video(brief, chat=None, notify=None, workdir=None, recent="", seconds=60, lang="en", qc=True, plan=None):
    chat = groq_chat  # own Groq client (JSON mode); the runner sets GROQ_KEY
    wd = workdir or tempfile.mkdtemp(prefix="doc3_"); os.makedirs(wd, exist_ok=True)
    if not features.check("raqm"):
        log("WARNING: Pillow has no raqm -> Telugu shaping would break")
    p = plan or build_script(brief, chat, recent, seconds, lang)
    json.dump(p, open(f"{wd}/plan.json", "w"), indent=1, ensure_ascii=False, default=str)
    if notify: await notify(f"Script ready: {p['title']} ({len(p['sentences'])} lines, {len(p['facts'])} checked facts). Voice + visuals chestunna.")
    n = len(p["sentences"])
    for i, s in enumerate(p["sentences"]):
        s["audio"], s["adur"], s["words"] = await voice_sentence(s["text"], p["lang"], p.get("voice", "female"), wd, i)
        s["pause"] = pause_after(s["text"], i, n)
    build_timeline(p)
    log(f"voice total {p['total']:.1f}s, {len(p['shots'])} shots")
    assign_visuals(p, check=qc)
    mix = mix_audio(p, wd)
    out = f"{wd}/divya_doc3.mp4"
    export(render_video(p, wd), mix, out, p["total"])
    report = {"engine": "doc3", "topic": p["topic"], "rounds": []}
    if qc:
        r1 = run_qc(p, out, wd, 1); report["rounds"].append(r1); log(f"QC1 frames {r1['frames_pass']}/{r1['frames_total']} wer {r1['wer']} pass {r1['pass']}")
        if not r1["pass"]:
            redo, capfix = {}, 0
            for f in r1["frames"]:
                if f["pass"]:
                    continue
                v = f["vision"]; sh = p["shots"][f["shot"]]
                if (v.get("matches_line") is False or v.get("empty_or_broken")) and sh.get("kind") != "number":
                    redo.setdefault(f["shot"], set()).add((sh.get("src") or {}).get("thumb", ""))
                if v.get("text_cut_off") or v.get("text_overlap"):
                    for c in p["caps"]:
                        if c["start"] <= f["t"] < c["end"]:
                            c["size_mul"] = 0.85; capfix += 1
            for a, b in r1["repeated_images"]:
                redo.setdefault(b, set()).add(p["shots"][b]["src"]["thumb"])
            if redo or capfix:
                log(f"re-render: {len(redo)} shots, {capfix} captions")
                assign_visuals(p, check=True, redo=redo)
                mix = mix_audio(p, wd)  # number-card hits may have moved
                export(render_video(p, wd), mix, out, p["total"])
                r2 = run_qc(p, out, wd, 2); report["rounds"].append(r2)
                log(f"QC2 frames {r2['frames_pass']}/{r2['frames_total']} wer {r2['wer']} pass {r2['pass']}")
        last = report["rounds"][-1]
        report["pass"] = last["pass"]
        weak = [f"{f['t']}s: {f['vision'].get('issue') or 'visual does not match line'}" for f in last["frames"] if not f["pass"]]
        if last["repeated_images"]: weak.append(f"repeated images {last['repeated_images']}")
        if last["wer"] > 0.12: weak.append(f"STT mismatch WER {last['wer']}")
        report["weak"] = weak
    report.update({"loudness": loudness_report(out), "probe": probe(out), "vision_calls": VISION_STATE["used"],
                   "facts": p["facts"], "dropped_facts": p["dropped_facts"], "cut_sentences": p["cut_sentences"], "music": p.get("music"),
                   "script": [{"text": s["text"], "query": s["query"], "key": s["key"], "number": s["number"], "facts": s["facts"],
                               "start": round(s["start"], 2), "dur": round(s["adur"], 2)} for s in p["sentences"]],
                   "shots": [{"start": round(s["start"], 2), "end": round(s["end"], 2), "kind": s.get("kind"),
                              "image": (s.get("src") or {}).get("title"), "shows": (s.get("src") or {}).get("shows")} for s in p["shots"]],
                   "log": LOG[-80:]})
    json.dump(report, open(f"{wd}/qc_report.json", "w"), indent=1, ensure_ascii=False, default=str)
    write_credits(p, f"{wd}/credits.txt")
    return {"path": out, "topic": p["topic"], "title": p["title"].upper(), "lang": p["lang"], "duration": p["total"],
            "script": "\n".join(s["text"] for s in p["sentences"]), "caption": p.get("caption", ""), "qc": report,
            "credits": f"{wd}/credits.txt", "qc_report": f"{wd}/qc_report.json", "plan": {"sentences": p["sentences"]}}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--brief", default="AUTO"); ap.add_argument("--out", default="out3"); ap.add_argument("--seconds", type=int, default=60)
    ap.add_argument("--lang", default="en"); ap.add_argument("--no-qc", action="store_true"); ap.add_argument("--plan")
    a = ap.parse_args()
    pl = json.load(open(a.plan)) if a.plan else None
    res = asyncio.run(make_video(a.brief, None, workdir=os.path.abspath(a.out), seconds=a.seconds, lang=a.lang, qc=not a.no_qc, plan=pl))
    print(json.dumps({k: res[k] for k in ("path", "title", "duration", "lang")}, default=str))
    print("QC pass:", res["qc"].get("pass"), "weak:", res["qc"].get("weak"))
