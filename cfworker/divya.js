// Divya — 24/7 WhatsApp brain on Cloudflare Workers (free plan, no card).
// Chat + screenshot reading happen here. Video edits go to GitHub Actions (4 vCPU, free on public repo).
// Secrets (set in dashboard / API): WA_TOKEN, GROQ_KEY, GH_TOKEN, VERIFY_TOKEN, RUNNER_KEY
// Vars: PHONE_ID, OWNERS (comma list, e.g. 919951950173), GH_REPO (owner/repo)
// KV binding: KV

const G = "https://graph.facebook.com/v21.0";
const SYSTEM = `Nuvvu "Divya" — owner ki close friend laanti personal AI agent. Owner tho EPPUDU romanized Telugu + English mix (Tenglish) lo chat cheyyi. (Idi nee CHAT language matrame — videos lo voice ye language lo aina cheyagalavu.)
Format: plain text matrame. Markdown (**, ##, bullets) vaddu. 1-3 chinna lines. Max 1 emoji.
Nee powers (nijamga unnavi matrame):
1) ZERO nunchi documentary-style videos CREATE: footage avasaram ledu. Topic ivvakapothe nuve select chestav. Story script, natural neural voice-over in ENGLISH, TELUGU leda HINDI (male/female), animated scenes + 3D character, camera moves, transitions, background music + sound effects, word-by-word captions, 9:16. Duration owner cheppinattu (default ~1 min).
2) Owner pampina video ni edit cheyagalavu (caption lo instruction, leda "edit: ...").
3) Questions, ideas, plans.
Voice gurinchi nijam: idi best free neural voice, chala natural ga untundi kani 100% real human kaadu — adigithe ide cheppu.
YouTube/Instagram upload inka connect avvaledu — adigithe "inka setup avvutondi" ani cheppu.
Owner video adigithe (or voice language/style/length marchamani adigithe) ADDDU cheppaku, footage adagaku. Chinna reply: "Sare, start chesa. Ready ayyaka ikkade pampistha." laanti neutral line (time promise, "ready chesthanu" vaddu). Reply chivara separate line lo exactly [[CREATE: <owner request full details in English: topic or AUTO, voice language, male/female, length, style>]] rayi.
Nijayithi: pani avvakunda "aipoyindi" anaku. Leni tools unnayi ani cheppaku. Secrets/keys evariki cheppaku.`;

async function wa(env, to, payload) {
  return fetch(`${G}/${env.PHONE_ID}/messages`, {
    method: "POST",
    headers: { Authorization: `Bearer ${env.WA_TOKEN}`, "content-type": "application/json" },
    body: JSON.stringify({ messaging_product: "whatsapp", to, ...payload }),
  });
}
const say = (env, to, text) => wa(env, to, { type: "text", text: { body: text.slice(0, 4000) } });

const CHAT_MODELS = ["openai/gpt-oss-120b", "moonshotai/kimi-k2-instruct-0905", "moonshotai/kimi-k2-instruct", "qwen/qwen3-32b", "llama-3.3-70b-versatile", "openai/gpt-oss-20b", "llama-3.1-8b-instant"];
const VISION_MODELS = ["meta-llama/llama-4-scout-17b-16e-instruct", "meta-llama/llama-4-maverick-17b-128e-instruct"];

async function liveModels(env, key) {
  const c = await env.KV.get("groq:models");
  if (c) return JSON.parse(c);
  const r = await fetch("https://api.groq.com/openai/v1/models", { headers: { Authorization: `Bearer ${key}` } });
  if (!r.ok) return [];
  const ids = (await r.json()).data.filter(m => m.active !== false).map(m => m.id);
  await env.KV.put("groq:models", JSON.stringify(ids), { expirationTtl: 3600 * 6 });
  return ids;
}

async function groq(env, messages, vision = false) {
  const keys = (env.GROQ_KEY || "").split(",").map(s => s.trim()).filter(Boolean);
  if (!keys.length) { await env.KV.put("dbg:groq", "no GROQ_KEY", { expirationTtl: 86400 }); }
  for (const k of keys) {
    const live = await liveModels(env, k);
    let order = vision ? VISION_MODELS : CHAT_MODELS;
    if (live.length) {
      order = order.filter(m => live.includes(m));
      if (!order.length) order = live.filter(m => vision ? /llama-4|vision|scout|maverick/i.test(m) : !/whisper|guard|tts|playai|orpheus|compound|prompt/i.test(m)).slice(0, 4);
    }
    for (const model of order) {
      const r = await fetch("https://api.groq.com/openai/v1/chat/completions", {
        method: "POST",
        headers: { Authorization: `Bearer ${k}`, "content-type": "application/json" },
        body: JSON.stringify({ model, messages, temperature: 0.7, max_tokens: 900, ...(model.startsWith("openai/gpt-oss") ? { reasoning_effort: "low" } : {}) }),
      });
      if (r.ok) {
        const out = ((await r.json()).choices[0].message.content || "").replace(/<think>[\s\S]*?<\/think>/g, "").trim();
        if (out) return out;
      }
      await env.KV.put("dbg:groq", `${new Date().toISOString()} ${model} ${r.status} ${(await r.text()).slice(0, 300)}`, { expirationTtl: 86400 * 2 });
      if (r.status === 401) break;
    }
  }
  return "Sorry ra, naa AI brain ki ippudu chinna problem vachindi. Owner ki report chesa, konchem sepu lo malli try cheyyi 🙏";
}

function b64(buf) {
  const bytes = new Uint8Array(buf); let s = "";
  for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  return btoa(s);
}

async function media(env, id) {
  const meta = await (await fetch(`${G}/${id}`, { headers: { Authorization: `Bearer ${env.WA_TOKEN}` } })).json();
  const r = await fetch(meta.url, { headers: { Authorization: `Bearer ${env.WA_TOKEN}` } });
  return { buf: await r.arrayBuffer(), mime: meta.mime_type || "image/jpeg" };
}

async function history(env, user) { return JSON.parse((await env.KV.get(`h:${user}`)) || "[]"); }
async function remember(env, user, h) { await env.KV.put(`h:${user}`, JSON.stringify(h.slice(-12)), { expirationTtl: 86400 * 3 }); }

async function startEdit(env, user, mediaId, instruction) {
  const job = crypto.randomUUID().slice(0, 8);
  await env.KV.put(`job:${job}`, JSON.stringify({ media_id: mediaId, instruction, to: user }), { expirationTtl: 86400 });
  const r = await fetch(`https://api.github.com/repos/${env.GH_REPO}/actions/workflows/edit.yml/dispatches`, {
    method: "POST",
    headers: { Authorization: `token ${env.GH_TOKEN}`, "User-Agent": "divya", Accept: "application/vnd.github+json" },
    body: JSON.stringify({ ref: "main", inputs: { job } }),
  });
  if (r.status === 204) return say(env, user, `🎬 Edit start chesa (job ${job}). Ready ayyaka ikkade pampistha.`);
  return say(env, user, `Edit machine start avvaledu (GitHub ${r.status}). Owner ki report chesa.`);
}

async function startCreate(env, user, brief) {
  const job = crypto.randomUUID().slice(0, 8);
  const recent = JSON.parse((await env.KV.get(`topics:${user}`)) || "[]").slice(-15).join("; ");
  const hu = (await history(env, user)).filter(x => x.role === "user").slice(-4).map(x => x.content).join(" | ");
  const ctx = hu ? `\nOwner's recent messages (romanized Telugu): ${hu}` : "";
  await env.KV.put(`job:${job}`, JSON.stringify({ mode: "create", brief: (brief === "AUTO" ? "AUTO" : brief) + ctx, recent, to: user }), { expirationTtl: 86400 });
  const r = await fetch(`https://api.github.com/repos/${env.GH_REPO}/actions/workflows/edit.yml/dispatches`, {
    method: "POST",
    headers: { Authorization: `token ${env.GH_TOKEN}`, "User-Agent": "divya", Accept: "application/vnd.github+json" },
    body: JSON.stringify({ ref: "main", inputs: { job } }),
  });
  if (r.status !== 204) return say(env, user, `Video machine start avvaledu (GitHub ${r.status}). Konchem sepu tarvatha malli adugu.`);
}

async function handle(env, m) {
  const user = m.from;
  const owners = (env.OWNERS || "").split(",").map(s => s.trim());
  if (!owners.includes(user)) return;
  if (await env.KV.get(`seen:${m.id}`)) return;
  await env.KV.put(`seen:${m.id}`, "1", { expirationTtl: 86400 });

  if (m.type === "video" || (m.type === "document" && (m.document?.mime_type || "").startsWith("video"))) {
    const id = (m.video || m.document).id, cap = (m.video || m.document).caption || "";
    await env.KV.put(`lastvideo:${user}`, id, { expirationTtl: 86400 * 2 });
    if (cap.trim()) return startEdit(env, user, id, cap);
    return say(env, user, "Video vachindi 👍 Em edit cheyyali? (ex: \"edit: 30s reel, Telugu captions, music\")");
  }

  if (m.type === "image" || (m.type === "document" && (m.document?.mime_type || "").startsWith("image"))) {
    const obj = m.image || m.document;
    const { buf, mime } = await media(env, obj.id);
    if (buf.byteLength > 4_000_000) return say(env, user, "Image chala pedda ga undi (4MB paina). Screenshot ga pampu.");
    const q = obj.caption || "Ee screenshot lo em undo cheppu, important vishayalu, emaina cheyyalsina pani unte cheppu.";
    const ans = await groq(env, [
      { role: "system", content: SYSTEM },
      { role: "user", content: [{ type: "text", text: q }, { type: "image_url", image_url: { url: `data:${mime};base64,${b64(buf)}` } }] },
    ], true);
    const h = await history(env, user); h.push({ role: "user", content: `[screenshot] ${q}` }, { role: "assistant", content: ans });
    await remember(env, user, h);
    return say(env, user, ans);
  }

  if (m.type === "text") {
    const text = m.text.body.trim();
    if (/^edit\s*[:\-]/i.test(text)) {
      const vid = await env.KV.get(`lastvideo:${user}`);
      if (!vid) return say(env, user, "Mundu video pampu, tarvatha edit instruction.");
      return startEdit(env, user, vid, text.replace(/^edit\s*[:\-]\s*/i, ""));
    }
    const h = await history(env, user); h.push({ role: "user", content: text });
    let ans = await groq(env, [{ role: "system", content: SYSTEM }, ...h]);
    const mm = ans.match(/\[\[\s*CREATE\s*:\s*([^\]]*)\]\]/i);
    ans = ans.replace(/\[\[[^\]]*\]\]/g, "").replace(/\*\*|__|^#+\s*/gm, "").trim();
    h.push({ role: "assistant", content: ans }); await remember(env, user, h);
    if (ans) await say(env, user, ans);
    if (mm) return startCreate(env, user, (mm[1] || "AUTO").trim() || "AUTO");
    return;
  }

  return say(env, user, "Ee type message inka ardham chesukolenu. Text, screenshot leda video pampu.");
}

export default {
  async fetch(req, env, ctx) {
    const url = new URL(req.url);
    if (url.pathname === "/webhook" && req.method === "GET") {
      if (url.searchParams.get("hub.mode") === "subscribe" && url.searchParams.get("hub.verify_token") === env.VERIFY_TOKEN)
        return new Response(url.searchParams.get("hub.challenge") || "");
      return new Response("forbidden", { status: 403 });
    }
    if (url.pathname === "/webhook" && req.method === "POST") {
      const body = await req.json().catch(() => ({}));
      const msgs = (body.entry || []).flatMap(e => (e.changes || []).flatMap(c => c.value?.messages || []));
      const fields = (body.entry || []).flatMap(e => (e.changes || []).map(c => c.field + (c.value?.statuses ? ":status" : "") + (c.value?.messages ? ":msg" : "")));
      ctx.waitUntil(env.KV.put("dbg:last", JSON.stringify({ t: new Date().toISOString(), fields, from: msgs.map(m => (m.from || "").slice(-4)), type: msgs.map(m => m.type) }), { expirationTtl: 86400 * 2 }));
      ctx.waitUntil(Promise.all(msgs.map(m => handle(env, m).catch(e => { console.log("err", String(e)); return env.KV.put("dbg:err", new Date().toISOString() + " " + String(e).slice(0, 300), { expirationTtl: 86400 * 2 }); }))));
      return new Response("ok");
    }
    // GitHub runner fetches its job + creds here (shared RUNNER_KEY, never in public logs).
    if (url.pathname === "/job" && req.method === "POST") {
      if (req.headers.get("x-runner-key") !== env.RUNNER_KEY) return new Response("no", { status: 403 });
      const { job } = await req.json();
      const j = await env.KV.get(`job:${job}`);
      if (!j) return new Response("missing", { status: 404 });
      return Response.json({ ...JSON.parse(j), WA_TOKEN: env.WA_TOKEN, GROQ_KEY: env.GROQ_KEY, PHONE_ID: env.PHONE_ID });
    }
    if (url.pathname === "/done" && req.method === "POST") {
      if (req.headers.get("x-runner-key") !== env.RUNNER_KEY) return new Response("no", { status: 403 });
      const { to, topic } = await req.json();
      if (to && topic) {
        const t = JSON.parse((await env.KV.get(`topics:${to}`)) || "[]"); t.push(String(topic).slice(0, 80));
        await env.KV.put(`topics:${to}`, JSON.stringify(t.slice(-40)));
      }
      return Response.json({ ok: true });
    }
    if (url.pathname === "/health") return Response.json({ ok: true, name: "divya" });
    return new Response("Divya is awake.");
  },
};
