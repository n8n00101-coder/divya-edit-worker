// v117 (Nod Phase 1.5) REPLY-SYSTEM battery: drives the REAL Worker
// /webhook (WhatsApp) and /api/chat (app) handlers with a stubbed
// brain, replaying the reply-failure classes Phase 1.5 targets:
//  - unasked style/options MENU DUMP from the brain (2026-11-16 class)
//  - FABRICATED progress in the APP path (WA got the net in v109;
//    the app never did — 2026-11-17 fabrication class)
//  - REPLY_SYSTEM block present in BOTH surfaces' system prompts
//  - asked-for styles pass through; normal short replies untouched;
//    exactly ONE reply per message.
// Run: node replytest.mjs [--verbose]. Exit 0 = all expectations met.
import { readFileSync, writeFileSync } from "fs";
import { pathToFileURL } from "url";

const VERBOSE = process.argv.includes("--verbose");
const SRC = readFileSync(new URL("./divya.js", import.meta.url), "utf8");
writeFileSync("/tmp/_divya_replytest.mjs", SRC);
const worker = (await import(pathToFileURL("/tmp/_divya_replytest.mjs").href)).default;

const USER = "919999999999";
const CHAT_MODELS = ["openai/gpt-oss-120b", "openai/gpt-oss-20b"];

class KVStub {
  constructor() { this.m = new Map(); }
  async get(k, opts) {
    const v = this.m.has(k) ? this.m.get(k) : null;
    if (v == null) return null;
    const t = typeof opts === "string" ? opts : (opts && opts.type) || "text";
    if (t === "json") { try { return JSON.parse(v); } catch { return null; } }
    if (t === "arrayBuffer") return new TextEncoder().encode(v).buffer;
    return v;
  }
  async put(k, v) { this.m.set(k, typeof v === "string" ? v : String(v)); }
  async delete(k) { this.m.delete(k); }
  async list({ prefix = "" } = {}) { return { keys: [...this.m.keys()].filter(k => k.startsWith(prefix)).map(name => ({ name })) }; }
  async mget(keys) { const o = {}; for (const k of keys) o[k] = this.m.has(k) ? this.m.get(k) : null; return o; }
}

let outbox = [], dispatches = [], brainImpl = async () => "Sare.", lastBrainMsgs = null;
globalThis.fetch = async (url, opts = {}) => {
  const u = String(url);
  if (u.includes("graph.facebook.com")) {
    let body = {}; try { body = JSON.parse(opts.body || "{}"); } catch {}
    if (body.type === "text" && body.text && body.text.body) outbox.push({ to: body.to, text: body.text.body });
    return Response.json({ messages: [{ id: "wamid.test" }] });
  }
  if (u.includes("api.groq.com") && u.includes("/models")) return Response.json({ data: CHAT_MODELS.map(id => ({ id, active: true })) });
  if (u.includes("api.groq.com") && u.includes("/chat/completions")) {
    let msgs = []; try { msgs = JSON.parse(opts.body || "{}").messages || []; } catch {}
    lastBrainMsgs = msgs;
    const content = await brainImpl(msgs);
    return Response.json({ choices: [{ message: { content } }] });
  }
  if (u.includes("api.github.com") && u.includes("/dispatches")) { dispatches.push({ url: u }); return new Response(null, { status: 204 }); }
  if (u.includes("openrouter.ai") || u.includes("generativelanguage.googleapis.com")) return Response.json({ error: "stub-down" }, { status: 500 });
  return new Response("stub-404", { status: 404 });
};

let seq = 0;
function makeWorld() {
  const kv = new KVStub();
  const env = {
    KV: kv, OWNERS: USER, FRIENDS: "", GROQ_KEY: "gk-test", WA_TOKEN: "wa-test", PHONE_ID: "1555000111",
    GH_TOKEN: "ght-test", RUNNER_KEY: "rk-test", JWT_SECRET: "jwt-test", WA_APP_SECRET: "",
    APP_KEK: Buffer.alloc(32, 7).toString("base64"), FORWARD_SECRET: "",
  };
  outbox = []; dispatches = [];
  return { kv, env };
}
async function drain(ctx) { const ps = ctx._p || []; for (let i = 0; i < 6; i++) { const b = ps.splice(0); if (!b.length) break; await Promise.all(b); } }
async function send(world, text) {
  const before = outbox.length;
  const promises = [];
  const ctx = { waitUntil(p) { promises.push(Promise.resolve(p)); } }; ctx._p = promises;
  const body = { entry: [{ changes: [{ field: "messages", value: { messages: [{ from: USER, id: "m" + (++seq), type: "text", text: { body: text } }] } }] }] };
  const req = new Request("https://worker.test/webhook", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
  await worker.fetch(req, world.env, ctx);
  await drain(ctx);
  return outbox.slice(before).filter(o => o.to === USER).map(o => o.text);
}
async function appChat(world, text) {
  const promises = [];
  const ctx = { waitUntil(p) { promises.push(Promise.resolve(p)); } }; ctx._p = promises;
  const req = new Request("https://worker.test/api/chat", { method: "POST", headers: { "content-type": "application/json", authorization: "Bearer " + "a".repeat(48) }, body: JSON.stringify({ text, lang: "te" }) });
  await world.kv.put("sess:" + "a".repeat(48), USER);
  const res = await worker.fetch(req, world.env, ctx);
  await drain(ctx);
  return res.json().catch(() => ({}));
}

const MENU = "Choose a style for your video:\n1. Bold — big outline text\n2. Neon — glowing colours\n3. Minimal — clean and simple\n4. Cinematic — film look\n5. Vintage — retro feel\n6. Glitch — RGB glitch effect\nYe style kavali? Pick one.";
const FAB = "Your work is 30% complete — script outline finished, voice-over recording queued, visuals sourcing now.";
let pass = 0, fail = 0;
function check(name, cond, extra = "") {
  if (cond) { pass++; if (VERBOSE) console.log(`ok    ${name}`); }
  else { fail++; console.log(`WRONG ${name} ${extra}`); }
}

// R1 — WA: unasked menu dump collapses; REPLY_SYSTEM in WA prompt; one reply; no dispatch
{
  const w = makeWorld(); brainImpl = async () => MENU;
  const r = await send(w, "Space gurinchi cheppu");
  check("R1 one reply", r.length === 1, JSON.stringify(r));
  check("R1 menu collapsed", r.length === 1 && /Style nene choose chestha/.test(r[0]) && !/Neon/.test(r[0]), (r[0] || "").slice(0, 160));
  check("R1 REPLY_SYSTEM in WA sys", !!lastBrainMsgs && lastBrainMsgs.some(m => /REPLY SYSTEM/.test(String(m.content || ""))));
  check("R1 no dispatch", dispatches.length === 0);
}
// R2 — WA: normal short brain reply passes through untouched
{
  const w = makeWorld(); brainImpl = async () => "Naa favourite pista green colour.";
  const r = await send(w, "Julie neeku favourite colour enti?");
  check("R2 passthrough", r.length === 1 && /pista green/.test(r[0] || ""), (r[0] || "").slice(0, 160));
}
// R3 — WA: fabricated progress never reaches the user (v109 net replay)
{
  const w = makeWorld(); brainImpl = async () => FAB;
  const r = await send(w, "Aa pani em ayindhi?");
  const j = r.join("\n");
  check("R3 no fabrication", r.length >= 1 && !/%|script outline|visuals sourcing/i.test(j), j.slice(0, 160));
}
// R4 — APP: unasked menu dump collapses; REPLY_SYSTEM in app prompt
{
  const w = makeWorld(); brainImpl = async () => MENU;
  const res = await appChat(w, "Space gurinchi cheppu");
  check("R4 app menu collapsed", /Style nene choose chestha/.test(res.reply || "") && !/Neon/.test(res.reply || ""), (res.reply || "").slice(0, 160));
  check("R4 REPLY_SYSTEM in app sys", !!lastBrainMsgs && lastBrainMsgs.some(m => /REPLY SYSTEM/.test(String(m.content || ""))));
}
// R5 — APP: fabricated progress is replaced (Phase 1.5 parity — pre-fix this leaked verbatim)
{
  const w = makeWorld(); brainImpl = async () => FAB;
  const res = await appChat(w, "Ninna cheppina pani gurinchi cheppu");
  check("R5 app fabrication replaced", !/%|script outline|visuals sourcing/i.test(res.reply || "") && /confirm cheyalenu/.test(res.reply || ""), (res.reply || "").slice(0, 160));
}
// R6 — APP: user ASKS for styles -> menu passes through
{
  const w = makeWorld(); brainImpl = async () => MENU;
  const res = await appChat(w, "Styles em unnay? List cheppu");
  check("R6 asked menu passes", /Neon/.test(res.reply || ""), (res.reply || "").slice(0, 160));
}
// R7 — APP: normal short reply untouched by both guards
{
  const w = makeWorld(); brainImpl = async () => "Space lo 8 planets unnayi, Jupiter anniyikanna peddadhi.";
  const res = await appChat(w, "Space gurinchi okka line cheppu");
  check("R7 app passthrough", /Jupiter/.test(res.reply || ""), (res.reply || "").slice(0, 160));
}

console.log(`\nreplytest: ${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
