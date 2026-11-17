// v107 WhatsApp PROCESS battery (Ajju 2026-11-17): drives the REAL
// Worker /webhook handler with simulated inbound WhatsApp messages —
// stub KV (real record shapes), stub network (Groq brain, GitHub
// dispatch, Meta send). Every outbound WhatsApp text is captured and
// scored: answered what was asked? / user's language (Tenglish)? /
// pushed a manual errand? / unverified state claim? / canned lecture?
// Run: node wa107test.mjs [--verbose]
// Exit 0 = every expectation met (post-fix target). Pre-fix failures
// ARE the wrong-reply catalogue.
import { readFileSync, writeFileSync } from "fs";
import { pathToFileURL } from "url";

const VERBOSE = process.argv.includes("--verbose");
const SRC = readFileSync(new URL("./divya.js", import.meta.url), "utf8");
writeFileSync("/tmp/_divya_under_test.mjs", SRC);
const worker = (await import(pathToFileURL("/tmp/_divya_under_test.mjs").href)).default;

const USER = "919999999999"; // owner number for the battery
const CHAT_MODELS = ["openai/gpt-oss-120b", "moonshotai/kimi-k2-instruct-0905", "moonshotai/kimi-k2-instruct", "qwen/qwen3-32b", "llama-3.3-70b-versatile", "openai/gpt-oss-20b", "llama-3.1-8b-instant"];

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

let outbox = [], dispatches = [], brainImpl = async () => "Sare, ardham ayyindhi.";
globalThis.fetch = async (url, opts = {}) => {
  const u = String(url);
  if (u.includes("graph.facebook.com")) {
    let body = {}; try { body = JSON.parse(opts.body || "{}"); } catch {}
    if (body.type === "text" && body.text && body.text.body) outbox.push({ to: body.to, text: body.text.body });
    return Response.json({ messages: [{ id: "wamid.test" }] });
  }
  if (u.includes("api.groq.com") && u.includes("/models")) {
    return Response.json({ data: CHAT_MODELS.map(id => ({ id, active: true })) });
  }
  if (u.includes("api.groq.com") && u.includes("/chat/completions")) {
    let msgs = []; try { msgs = JSON.parse(opts.body || "{}").messages || []; } catch {}
    const content = await brainImpl(msgs);
    return Response.json({ choices: [{ message: { content } }] });
  }
  if (u.includes("api.github.com") && u.includes("/dispatches")) {
    let body = {}; try { body = JSON.parse(opts.body || "{}"); } catch {}
    dispatches.push({ url: u, inputs: body.inputs || {} });
    return new Response(null, { status: 204 });
  }
  if (u.includes("openrouter.ai") || u.includes("generativelanguage.googleapis.com")) return Response.json({ error: "stub-down" }, { status: 500 });
  return new Response("stub-404", { status: 404 });
};

let seq = 0;
function makeWorld() {
  const kv = new KVStub();
  const env = {
    KV: kv, OWNERS: USER, FRIENDS: "", GROQ_KEY: "gk-test", WA_TOKEN: "wa-test", PHONE_ID: "1555000111",
    GH_TOKEN: "gh-test", GH_REPO: "test/repo", RUNNER_KEY: "rk-test", VERIFY_TOKEN: "vt",
    APP_KEK: Buffer.alloc(32, 7).toString("base64"), FORWARD_SECRET: "",
  };
  outbox = []; dispatches = [];
  return { kv, env };
}
async function send(world, text) {
  const before = outbox.length;
  const promises = [];
  const ctx = { waitUntil(p) { promises.push(Promise.resolve(p)); } };
  const body = { entry: [{ changes: [{ field: "messages", value: { messages: [{ from: USER, id: "m" + (++seq), type: "text", text: { body: text } }] } }] }] };
  const req = new Request("https://worker.test/webhook", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
  await worker.fetch(req, world.env, ctx);
  for (let i = 0; i < 5; i++) { const ps = promises.splice(0); if (!ps.length) break; await Promise.all(ps); }
  return outbox.slice(before).filter(o => o.to === USER).map(o => o.text);
}

const ERRAND_RX = /open the julie app|julie app lo|in the menu|tap setup|app lo setup open|setup open chesi|#\/setup/i;
const LIMIT_RX = /limit full|free limit/i;
const CANNED_RX = /pani naadhe, needhi kaadhu/i;
const TE_MARK = /(nenu|nee|neeku|cheyu|cheyyi|undhi|unnay|ledhu|ayyindhi|ayindhi|chestha|chesthunna|ikkade|malli|sare|emi|enni|ayindha|theeskunna|start chesa)/i;

const results = [];
function scoreReply(scn, userText, reply, expect) {
  const flags = [];
  const joined = reply.join("\n");
  if (!reply.length) flags.push("NO-REPLY");
  if (expect.must && !expect.must.test(joined)) flags.push("NOT-ANSWERED");
  if (ERRAND_RX.test(joined)) flags.push("ERRAND");
  if (CANNED_RX.test(joined)) flags.push("CANNED");
  if (LIMIT_RX.test(joined)) flags.push("STATE-CLAIM");
  if (expect.maxLen && joined.length > expect.maxLen) flags.push("LECTURE");
  if (joined.length > 120 && !TE_MARK.test(joined)) flags.push("ENGLISH");
  for (const f of flags) results.push({ scn, userText, flag: f, reply: joined.slice(0, 220) });
  if (VERBOSE || flags.length) console.log(`${flags.length ? "WRONG" : "ok   "} [${scn}] U: ${userText}\n      J: ${joined.slice(0, 200)}${flags.length ? "\n      flags: " + flags.join(",") : ""}`);
  return flags;
}
let stateFails = 0;
function scoreState(scn, name, cond) {
  if (!cond) { stateFails++; results.push({ scn, userText: "(state)", flag: "STATE:" + name, reply: "" }); console.log(`WRONG [${scn}] state: ${name}`); }
  else if (VERBOSE) console.log(`ok    [${scn}] state: ${name}`);
}

async function seedKeys(w, ids) {
  for (const id of ids) await w.kv.put(`ukey:${USER}:${id}`, JSON.stringify({ ct: "aa.bb", ok: true, at: Date.now(), source: "divya" }));
}
async function seedAccount(w, email) {
  await w.kv.put(`ph:${USER}`, "u_test1");
  await w.kv.put(`acct:u_test1`, JSON.stringify({ uid: "u_test1", name: "Test User", email, phone: USER }));
}

// S1 — greeting only
{
  const w = makeWorld(); brainImpl = async () => "Sare, ardham ayyindhi.";
  const r = await send(w, "Hlo");
  scoreReply("S1", "Hlo", r, { maxLen: 200 });
  scoreState("S1", "no dispatch", dispatches.length === 0);
}
// S2 — factual state questions (3 keys + setup done seeded)
{
  const w = makeWorld(); brainImpl = async () => "Sare, ardham ayyindhi.";
  await seedKeys(w, ["groq", "openrouter", "gemini"]);
  await w.kv.put(`setupdone:${USER}`, JSON.stringify({ state: "done", done: ["groq", "openrouter", "gemini"], failed: [], at: Date.now() }));
  await w.kv.put(`tokp:${USER}`, "250000");
  scoreReply("S2a", "Ipudu nee dhaggara enni api keys unnay", await send(w, "Ipudu nee dhaggara enni api keys unnay"), { must: /3/, maxLen: 280 });
  scoreReply("S2b", "Enni models unnay ippudu", await send(w, "Enni models unnay ippudu"), { must: /model/i, maxLen: 280 });
  scoreReply("S2c", "Setup ayindha?", await send(w, "Setup ayindha?"), { must: /3/, maxLen: 280 }); // must carry the REAL done-count (3), not a brain guess
  scoreReply("S2d", "Tokens enni unnay", await send(w, "Tokens enni unnay"), { must: /token/i, maxLen: 320 });
}
// S3 — how/process question (the 2026-11-16 incident question)
{
  const w = makeWorld(); brainImpl = async () => "Sare, start chesa [[CREATE: x]]";
  const Q = "Nenu oka topic isthe ela edits chesthav first starting nundi last output ready aye varaku ela edits chesthav motham detailed ga chepu";
  const r = await send(w, Q);
  scoreReply("S3", Q, r, { must: /emi start cheyyaledu/ });
  scoreState("S3", "no dispatch", dispatches.length === 0);
}

// S4 — setup needed; user says "ask HERE, I'll allow" (the 2026-11-17 incident).
// Turn-1 brain stub = the RECORDED live reply (brain fed SYS produced it live).
{
  const w = makeWorld();
  await seedAccount(w, "test@example.com");
  brainImpl = async () => "Open the Julie app and tap Setup in the menu. From there you can grant the required permissions and the system will take care of the rest.";
  const r1 = await send(w, "Ikade adugu allow chestha");
  scoreReply("S4", "Ikade adugu allow chestha", r1, { must: /allow/i, maxLen: 320 });
  brainImpl = async () => "Sare, ardham ayyindhi.";
  const r2 = await send(w, "sare");
  scoreReply("S4", "sare (the allow)", r2, { must: /start/i, maxLen: 320 });
  scoreState("S4", "consent recorded", !!(await w.kv.get(`setupconsent:${USER}`)));
  scoreState("S4", "chain created", !!(await w.kv.get(`setupchain:${USER}`)));
  scoreState("S4", "setup dispatched", dispatches.some(d => d.url.includes("setup.yml")));
}
// S4b — setup with NO account/email on file: allow -> email asked in chat -> chain starts
{
  const w = makeWorld(); brainImpl = async () => "Sare, ardham ayyindhi.";
  const r1 = await send(w, "Setup cheyu");
  scoreReply("S4b", "Setup cheyu", r1, { must: /allow/i, maxLen: 320 });
  const r2 = await send(w, "sare");
  scoreReply("S4b", "sare (the allow)", r2, { must: /email/i, maxLen: 320 });
  const r3 = await send(w, "test@example.com");
  scoreReply("S4b", "test@example.com", r3, { must: /start/i, maxLen: 320 });
  scoreState("S4b", "chain created with email", (await w.kv.get(`setupchain:${USER}`) || "").includes("test@example.com"));
  scoreState("S4b", "setup dispatched", dispatches.some(d => d.url.includes("setup.yml")));
}
// S5+S6 — plain video order, then stop mid-job
{
  const w = makeWorld();
  brainImpl = async () => "Sare, start chesa — script, visuals, voice, captions, edit, motham nene A to Z chestha. Ready ayyaka ikkade pampistha.\n[[CREATE: space documentary, English voice, short 30s 9:16]]";
  const r1 = await send(w, "Oka video cheyu, topic: space");
  scoreReply("S5", "Oka video cheyu, topic: space", r1, { must: /start chesa/i, maxLen: 320 });
  scoreState("S5", "edit dispatched", dispatches.some(d => d.url.includes("edit.yml")));
  scoreState("S5", "busy set", !!(await w.kv.get(`busy:${USER}`)));
  brainImpl = async () => "Sare, ardham ayyindhi.";
  const r2 = await send(w, "Cheyaku");
  scoreReply("S6", "Cheyaku", r2, { must: /cancel|aapesa|stop/i, maxLen: 320 });
  scoreState("S6", "busy cleared", !(await w.kv.get(`busy:${USER}`)));
}
// S7 — unrelated factual questions while a job runs
{
  const w = makeWorld();
  await seedKeys(w, ["groq", "gemini"]);
  brainImpl = async () => "Sare, start chesa — motham nene chestha.\n[[CREATE: ocean, English voice, short 30s 9:16]]";
  await send(w, "Oka video cheyu, topic: ocean");
  brainImpl = async () => "Sare, ardham ayyindhi.";
  scoreReply("S7", "Tokens enni unnay (job running)", await send(w, "Tokens enni unnay"), { must: /token/i, maxLen: 320 });
  scoreReply("S7", "enni api keys unnay (job running)", await send(w, "enni api keys unnay"), { must: /2/, maxLen: 280 });
  scoreState("S7", "job untouched (busy still set)", !!(await w.kv.get(`busy:${USER}`)));
}
// S8 — OTP answer during a setup pause
{
  const w = makeWorld(); brainImpl = async () => "Sare, ardham ayyindhi.";
  await w.kv.put(`setupchain:${USER}`, JSON.stringify({ providers: ["groq"], done: [], failed: [], current: "jobotp1", email: "test@example.com", at: Date.now() }));
  await w.kv.put(`setupjob:jobotp1`, JSON.stringify({ job: "jobotp1", user: USER, provider: "groq", state: "paused", pauseReason: "sms", awaiting: { id: "a1", provider: "groq", kind: "otp", prompt: "Groq nunchi SMS code vachindhi — ikkada pampu.", at: Date.now(), expires: Date.now() + 600000, attempts: 1 }, at: Date.now(), upd: Date.now() }));
  const r = await send(w, "123456");
  scoreReply("S8", "123456 (OTP answer)", r, { must: /theeskunna|enter/i, maxLen: 320 });
  const j = JSON.parse((await w.kv.get("setupjob:jobotp1")) || "{}");
  scoreState("S8", "code delivered to job", !!(j.userInput && j.userInput.value === "123456"));
}
// S9 — provider-down complaint with keys ready (isSetupQuestion territory)
{
  const w = makeWorld(); brainImpl = async () => "Sare, ardham ayyindhi.";
  await seedKeys(w, ["groq", "openrouter", "gemini"]);
  await w.kv.put(`setupdone:${USER}`, JSON.stringify({ state: "done", done: ["groq", "openrouter", "gemini"], failed: [], at: Date.now() }));
  scoreReply("S9", "Groq down ayindha, AI pani cheyyatledu", await send(w, "Groq down ayindha, AI pani cheyyatledu"), { must: /ready|check/i, maxLen: 280 });
}

const byFlag = {};
for (const r of results) byFlag[r.flag] = (byFlag[r.flag] || 0) + 1;
console.log("\n==== WA PROCESS BATTERY ====");
console.log("wrong-reply flags:", JSON.stringify(byFlag));
console.log("total wrong replies:", results.filter(r => !r.flag.startsWith("STATE:")).length, "| state failures:", stateFails);
if (VERBOSE) for (const r of results) console.log("-", r.scn, r.flag, "|", r.userText, "=>", r.reply);
process.exit(results.length ? 1 : 0);
