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

let outbox = [], cards = [], images = [], dispatches = [], brainImpl = async () => "Sare, ardham ayyindhi.";
let ytStub = null, mediaStub = {};
globalThis.fetch = async (url, opts = {}) => {
  const u = String(url);
  // v113 stubs: WA media meta/download, YouTube channels + resumable
  // upload, OAuth refresh — driven by ytStub / mediaStub.
  const metaM = u.match(/^https:\/\/graph\.facebook\.com\/v21\.0\/([^/]+)$/);
  if (metaM && mediaStub[metaM[1]] && !(opts && opts.body)) return Response.json({ url: `https://stubcdn.test/${metaM[1]}`, mime_type: "video/mp4", file_size: mediaStub[metaM[1]].size });
  if (u.startsWith("https://stubcdn.test/")) { const ms = mediaStub[u.slice(21)]; return new Response(new Uint8Array((ms && ms.bytes) || 32)); }
  if (u.includes("www.googleapis.com/youtube/v3/channels")) {
    if (u.includes("managedByMe=true")) { const mg = (ytStub && ytStub.managed) || { status: 400, items: [] }; return mg.status === 200 ? Response.json({ items: mg.items }) : Response.json({ error: { message: "managedByMe requires onBehalfOfContentOwner" } }, { status: mg.status }); }
    return Response.json({ items: (ytStub && ytStub.mine) || [] });
  }
  if (u.includes("oauth2.googleapis.com/token")) {
    if (ytStub && ytStub.refreshFails) return Response.json({ error: "invalid_grant", error_description: "Token has been expired or revoked." }, { status: 400 });
    return Response.json({ access_token: "tok-refreshed", expires_in: 3600 });
  }
  if (u.includes("openidconnect.googleapis.com")) return Response.json({ email: "rig@example.com", name: "Rig User" }); // v114: OAuth callback userinfo (S39)
  if (u.includes("upload/youtube/v3/videos")) {
    ytStub.sessionCalls++;
    if (ytStub.uploadMode === "quota") return Response.json({ error: { errors: [{ reason: "quotaExceeded", domain: "youtube.quota" }], message: "The request cannot be completed because you have exceeded your quota." } }, { status: 403 });
    return new Response(null, { status: 200, headers: { location: "https://upload.stub.test/session1" } });
  }
  if (u.startsWith("https://upload.stub.test/")) { ytStub.transferCalls++; return Response.json({ id: "vid123" }); }
  if (u.includes("graph.facebook.com")) {
    if (u.includes("/media")) return Response.json({ id: "media_test_1" }); // v111: WA media upload (image sends)
    let body = {}; try { body = JSON.parse(opts.body || "{}"); } catch {}
    if (body.type === "text" && body.text && body.text.body) outbox.push({ to: body.to, text: body.text.body });
    if (body.type === "image") images.push({ to: body.to, id: (body.image || {}).id, caption: (body.image || {}).caption || "" });
    if (body.type === "interactive") cards.push({ to: body.to, kind: body.interactive && body.interactive.type, ids: JSON.stringify(body.interactive || {}).match(/"(conn:[a-z]+|waallow:(yes|no|always)|waproc:(stop|continue|feed|feedoff)|ytpick:[a-z0-9]+)"/g) || [] });
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
  outbox = []; cards = []; images = []; dispatches = [];
  ytStub = { mine: [], managed: { status: 400, items: [] }, refreshFails: false, uploadMode: "ok", sessionCalls: 0, transferCalls: 0 };
  mediaStub = {};
  return { kv, env };
}
const imgCount = () => images.length;
const FRAME_B64 = Buffer.from("fake-jpeg-frame-bytes").toString("base64");
async function seedFrame(w, job, fp) {
  await w.kv.put(`tcframe:${job}`, JSON.stringify({ img: FRAME_B64, url: "https://console.groq.com/login", at: Date.now(), fp: fp || "fp1" }));
}
async function sendInteractive(world, id) {
  const before = outbox.length;
  const promises = [];
  const ctx = { waitUntil(p) { promises.push(Promise.resolve(p)); } };
  const body = { entry: [{ changes: [{ field: "messages", value: { messages: [{ from: USER, id: "m" + (++seq), type: "interactive", interactive: { type: "button_reply", button_reply: { id, title: "Allow" } } }] } }] }] };
  const req = new Request("https://worker.test/webhook", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
  await worker.fetch(req, world.env, ctx);
  for (let i = 0; i < 5; i++) { const ps = promises.splice(0); if (!ps.length) break; await Promise.all(ps); }
  return outbox.slice(before).filter(o => o.to === USER).map(o => o.text);
}
async function runnerPost(world, path, job, payload) {
  const before = outbox.length;
  const promises = [];
  const ctx = { waitUntil(p) { promises.push(Promise.resolve(p)); } };
  const req = new Request(`https://worker.test/api/setup/runner/${path}?job=${job}`, { method: "POST", headers: { "content-type": "application/json", "x-runner-key": "rk-test" }, body: JSON.stringify(payload) });
  await worker.fetch(req, world.env, ctx);
  for (let i = 0; i < 6; i++) { const ps = promises.splice(0); if (!ps.length) break; await Promise.all(ps); }
  return outbox.slice(before).filter(o => o.to === USER).map(o => o.text);
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

// v113 helpers: an inbound WA video message, a runner-leg report to
// /api/runner/yt, and an app-chat turn (the parity entry point).
async function sendVideo(world, mediaId, caption) {
  const before = outbox.length;
  const promises = [];
  const ctx = { waitUntil(p) { promises.push(Promise.resolve(p)); } };
  const msg = { from: USER, id: "m" + (++seq), type: "video", video: { id: mediaId, ...(caption ? { caption } : {}) } };
  const body = { entry: [{ changes: [{ field: "messages", value: { messages: [msg] } }] }] };
  const req = new Request("https://worker.test/webhook", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
  await worker.fetch(req, world.env, ctx);
  for (let i = 0; i < 6; i++) { const ps = promises.splice(0); if (!ps.length) break; await Promise.all(ps); }
  return outbox.slice(before).filter(o => o.to === USER).map(o => o.text);
}
async function ytRunnerPost(world, job, payload) {
  const before = outbox.length;
  const promises = [];
  const ctx = { waitUntil(p) { promises.push(Promise.resolve(p)); } };
  const req = new Request(`https://worker.test/api/runner/yt?job=${job}`, { method: "POST", headers: { "content-type": "application/json", "x-runner-key": "rk-test" }, body: JSON.stringify(payload) });
  await worker.fetch(req, world.env, ctx);
  for (let i = 0; i < 6; i++) { const ps = promises.splice(0); if (!ps.length) break; await Promise.all(ps); }
  return outbox.slice(before).filter(o => o.to === USER).map(o => o.text);
}
async function appChat(world, text) {
  const promises = [];
  const ctx = { waitUntil(p) { promises.push(Promise.resolve(p)); } };
  const req = new Request("https://worker.test/api/chat", { method: "POST", headers: { "content-type": "application/json", authorization: "Bearer " + "a".repeat(48) }, body: JSON.stringify({ text, lang: "te" }) });
  const res = await worker.fetch(req, world.env, ctx);
  for (let i = 0; i < 6; i++) { const ps = promises.splice(0); if (!ps.length) break; await Promise.all(ps); }
  return res.json().catch(() => ({}));
}
async function seedYt(w, list, def, toks) {
  await w.kv.put(`gaccts:${USER}`, JSON.stringify({ list, def }));
  for (const [id, tok] of Object.entries(toks || {})) await w.kv.put(id === def ? `tok:${USER}:youtube` : `tok:${USER}:youtube#${id}`, JSON.stringify(tok));
}
const freshTok = who => ({ access_token: "tok-fresh", refresh_token: "rt", at: Date.now(), expires_in: 3600, who });

const ERRAND_RX = /open the julie app|julie app lo|in the menu|tap setup|app lo setup open|setup open chesi|#\/setup/i;
const FABRICATED_RX = /\b\d{1,3}\s?%\s*(complete|ayindhi|done|finished)|script outline|voice-?over recording queued|visuals sourcing|\bsingle instance\b|text-generation|neural[-\s]?voice|stock[-\s]?footage|\b\d+\s+service connections\b/i;
const LIMIT_RX = /limit full|free limit/i;
const CANNED_RX = /pani naadhe, needhi kaadhu/i;
const TE_MARK = /(nenu|nee|neeku|cheyu|cheyyi|undhi|unnay|ledhu|ayyindhi|ayindhi|ayyayi|ippudu|nadusth|chestha|chesthunna|ikkade|malli|sare|emi|enni|ayindha|theeskunna|start chesa)/i;

const results = [];
function scoreReply(scn, userText, reply, expect) {
  const flags = [];
  const joined = reply.join("\n");
  if (!reply.length) flags.push("NO-REPLY");
  if (expect.must && !expect.must.test(joined)) flags.push("NOT-ANSWERED");
  if (ERRAND_RX.test(joined)) flags.push("ERRAND");
  if (CANNED_RX.test(joined)) flags.push("CANNED");
  if (FABRICATED_RX.test(joined)) flags.push("FABRICATED");
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

// ===== v109 scenarios: the 2026-11-17 real-phone transcript + a stubbed chain run =====
// S10 — the EXACT morning flow: keys question (truthful state), "shared brains
// ante enti" (truth sheet, no invented architecture), WA allow, email in chat,
// then the two questions that fabricated live: "Chesava" + "Entha percent
// complete ayindhi" — both must be answered from the CHAIN record (23
// providers, 0 settled at that point), never from the brain. The brain stub
// below returns the RECORDED live fabrications, so pre-fix code fails here
// exactly the way the phone did.
{
  const w = makeWorld();
  await seedAccount(w, "markk34200@gmail.com");
  brainImpl = async () => "\"Shared brains\" ante nenu (Julie) okka centralized AI service lo run avuthunna system. Single instance — neeku separate personal server, API keys create cheyyalani avasaram ledu. So, \"shared brains\" means nenu oka common AI engine (OpenAI, TTS, stock-footage library, etc.) use chesthunna.";
  scoreReply("S10a", "Ipudu nee dhaggara enni api keys unnay?", await send(w, "Ipudu nee dhaggara enni api keys unnay?"), { must: /own API keys levu/, maxLen: 300 });
  const rShared = await send(w, "Shared brains ante enti artham ayela chepu");
  scoreReply("S10b", "Shared brains ante enti artham ayela chepu", rShared, { must: /free-model pool/, maxLen: 340 });
  scoreState("S10b", "no OpenAI claim", !/openai/i.test(rShared.join(" ")));
  const r1 = await send(w, "Free ai models ni brain ki api keys create pettu, brain lo");
  scoreReply("S10c", "Free ai models ni brain ki api keys create pettu", r1, { must: /allow/i, maxLen: 400 });
  scoreState("S10c", "allow card sent", cards.some(c => c.ids.some(i => i.includes("waallow:yes"))));
  const r2 = await send(w, "Sare");
  scoreReply("S10d", "Sare (allow, email on file)", r2, { must: /start chesa/i, maxLen: 340 });
  scoreState("S10d", "chain created via wa", ((await w.kv.get(`setupchain:${USER}`)) || "").includes('"via":"wa"'));
  scoreState("S10d", "setup dispatched", dispatches.some(d => d.url.includes("setup.yml")));
  brainImpl = async () => "Sare, start chesa. Ready ayyaka ikkade pampistha.";
  scoreReply("S10e", "Chesava (setup running)", await send(w, "Chesava"), { must: /Setup progress: 0\/23/, maxLen: 500 });
  brainImpl = async () => "Sare, 30% complete. Next step: script outline finished, voice-over recording queued, visuals sourcing underway. I will keep you updated.";
  scoreReply("S10f", "Entha percent complete ayindhi", await send(w, "Entha percent complete ayindhi"), { must: /Setup progress: 0\/23 ayyayi \(0%\)/, maxLen: 500 });
}
// S11 — the Allow BUTTON tap is the same grant as typing "sare"
{
  const w = makeWorld(); brainImpl = async () => "Sare, ardham ayyindhi.";
  await seedAccount(w, "tap@example.com");
  await send(w, "Setup cheyu");
  scoreState("S11", "allow card sent", cards.some(c => c.ids.some(i => i.includes("waallow:yes"))));
  const r = await sendInteractive(w, "waallow:yes");
  scoreReply("S11", "[tap Allow ✓]", r, { must: /start chesa/i, maxLen: 340 });
  scoreState("S11", "consent recorded", !!(await w.kv.get(`setupconsent:${USER}`)));
  scoreState("S11", "chain created", !!(await w.kv.get(`setupchain:${USER}`)));
  scoreState("S11", "setup dispatched", dispatches.some(d => d.url.includes("setup.yml")));
}
// S12 — stubbed chain run: per-provider progress reaches the WA chat as it
// happens, and the finalize message is the full created/failed list
{
  const w = makeWorld(); brainImpl = async () => "Sare, ardham ayyindhi.";
  await w.kv.put(`setupchain:${USER}`, JSON.stringify({ providers: ["groq", "cohere"], done: [], failed: [], current: "joba01", email: "t@example.com", pass: "x", at: Date.now(), browser: "profile", via: "wa" }));
  await w.kv.put(`setupjob:joba01`, JSON.stringify({ job: "joba01", user: USER, provider: "groq", state: "running", step: "creating key", at: Date.now(), upd: Date.now() }));
  await runnerPost(w, "key", "joba01", { provider: "groq", key: "gsk-test-key-0123456789" }); // keys travel sealed via runner/key, never in the result post
  const p1 = await runnerPost(w, "result", "joba01", { provider: "groq", status: "done" });
  scoreReply("S12a", "[runner: groq done]", p1, { must: /Groq.*ready.*\(1\/2\)/, maxLen: 200 });
  const chain1 = JSON.parse((await w.kv.get(`setupchain:${USER}`)) || "{}");
  scoreState("S12a", "chain advanced to cohere", chain1.current && chain1.current !== "joba01");
  await w.kv.put(`setupjob:${chain1.current}`, JSON.stringify({ job: chain1.current, user: USER, provider: "cohere", state: "running", step: "creating key", at: Date.now(), upd: Date.now() }));
  const p2 = await runnerPost(w, "result", chain1.current, { provider: "cohere", status: "failed", error: "signup wall — email verification failed" });
  scoreReply("S12b", "[runner: cohere failed -> finalize list]", p2, { must: /Setup complete.*Groq/, maxLen: 400 });
  scoreState("S12b", "final list names the failure", /Cohere/.test(p2.join(" ")));
  scoreState("S12b", "chain cleared", !(await w.kv.get(`setupchain:${USER}`)));
  const fin = JSON.parse((await w.kv.get(`setupdone:${USER}`)) || "{}");
  scoreState("S12b", "setupdone recorded", fin.state === "done" && (fin.done || []).includes("groq"));
  scoreState("S12b", "connect card followed (google/youtube missing)", cards.some(c => c.ids.some(i => i.includes("conn:"))));
}
// S13 — fabrication guard: even an UNROUTED brain fabrication is replaced
{
  const w = makeWorld();
  await w.kv.put(`setupchain:${USER}`, JSON.stringify({ providers: ["groq", "cohere", "together"], done: ["groq"], failed: [], current: "jobb02", email: "t@example.com", at: Date.now(), via: "wa" }));
  await w.kv.put(`setupjob:jobb02`, JSON.stringify({ job: "jobb02", user: USER, provider: "cohere", state: "running", step: "signing up", at: Date.now(), upd: Date.now() }));
  brainImpl = async () => "Sare, 30% complete. Next step: script outline finished, voice-over recording queued, visuals sourcing underway.";
  const r = await send(w, "Em chesthunnav ippudu, ela velthondhi pani");
  scoreReply("S13", "Em chesthunnav ippudu (brain fabricates)", r, { must: /Setup progress: 1\/3/, maxLen: 500 });
}
// S14 — status question with NOTHING running: one honest line, no invention
{
  const w = makeWorld();
  brainImpl = async () => "Sare, 45% complete ayindhi, script outline finished.";
  scoreReply("S14", "Chesava (nothing running)", await send(w, "Chesava"), { must: /em job run avvatledhu/, maxLen: 300 });
}

// ===== v110 scenarios: the 2026-11-17 14:03–14:45 screenshot, verbatim =====
// S15 — "Enni conncet chesav ipati varaku" (14:03). Live, Julie answered
// with the fabrication stubbed below ("I've established 3 service
// connections so far: the text-generation model, the neural-voice TTS
// engine, and the stock-footage library."). The truth in this world:
// 2 keys under the WA number (Groq, OpenRouter) + 1 under the linked
// app account (Gemini) + a chain with 3/4 settled. The answer must be
// the reporter's: 3 keys BY NAME + the chain's settled list.
{
  const w = makeWorld();
  await seedAccount(w, "markk34200@gmail.com");
  await seedKeys(w, ["groq", "openrouter"]);
  await w.kv.put(`ukey:u_test1:gemini`, JSON.stringify({ ct: "aa.bb", ok: true, at: Date.now(), source: "divya" }));
  await w.kv.put(`setupchain:${USER}`, JSON.stringify({ providers: ["groq", "openrouter", "cohere", "together"], done: ["groq", "openrouter"], failed: ["cohere"], failReason: { cohere: "email verification failed" }, current: "jobc03", email: "markk34200@gmail.com", at: Date.now(), via: "wa" }));
  await w.kv.put(`setupjob:jobc03`, JSON.stringify({ job: "jobc03", user: USER, provider: "together", state: "running", step: "signing up", at: Date.now(), upd: Date.now() }));
  brainImpl = async () => "I've established 3 service connections so far: the text-generation model, the neural-voice TTS engine, and the stock-footage library.";
  const r = await send(w, "Enni conncet chesav ipati varaku");
  scoreReply("S15a", "Enni conncet chesav ipati varaku", r, { must: /3 API keys ready/, maxLen: 560 });
  scoreReply("S15a", "Enni conncet chesav ipati varaku", r, { must: /Groq, OpenRouter, Gemini/, maxLen: 560 });
  scoreReply("S15a", "Enni conncet chesav ipati varaku", r, { must: /Setup chain.*3\/4/, maxLen: 560 });
  // S15b — the same fabrication behind an UNROUTED message: the guard
  // replaces it with the real state reporter, never lets it through.
  const r2 = await send(w, "Okay cheppu");
  scoreReply("S15b", "Okay cheppu (brain fabricates connections)", r2, { must: /Setup progress: 3\/4/, maxLen: 560 });
}
// S16 — the allow card carries all THREE options (Ajju: "allow, always
// allow, dont allow lantivi asalu adagaledhu"); each tap's state
// semantics are verified.
{
  const w = makeWorld(); brainImpl = async () => "Sare, ardham ayyindhi.";
  await seedAccount(w, "tap@example.com");
  await send(w, "Setup cheyu");
  scoreState("S16a", "card has Allow", cards.some(c => c.ids.some(i => i.includes("waallow:yes"))));
  scoreState("S16a", "card has Always allow", cards.some(c => c.ids.some(i => i.includes("waallow:always"))));
  scoreState("S16a", "card has Don't allow", cards.some(c => c.ids.some(i => i.includes("waallow:no"))));
  const r = await sendInteractive(w, "waallow:always");
  scoreReply("S16a", "[tap Always allow]", r, { must: /Always allow/, maxLen: 460 });
  scoreReply("S16a", "[tap Always allow]", r, { must: /start chesa/i, maxLen: 460 });
  scoreState("S16a", "standing grant recorded", !!(await w.kv.get(`setupalways:${USER}`)));
  scoreState("S16a", "grant mirrored to app account", !!(await w.kv.get(`setupalways:u_test1`)));
  scoreState("S16a", "consent recorded", !!(await w.kv.get(`setupconsent:${USER}`)));
  scoreState("S16a", "chain created", !!(await w.kv.get(`setupchain:${USER}`)));
  scoreState("S16a", "setup dispatched", dispatches.some(d => d.url.includes("setup.yml")));
}
{
  // S16b — with a standing grant on file, a fresh setup ask does NOT
  // re-ask: it proceeds (and still reports the start).
  const w = makeWorld(); brainImpl = async () => "Sare, ardham ayyindhi.";
  await seedAccount(w, "tap@example.com");
  await w.kv.put(`setupalways:${USER}`, JSON.stringify({ at: Date.now(), scope: "accounts+keys+captchas+server", via: "wa" }));
  const r = await send(w, "Setup cheyu");
  scoreReply("S16b", "Setup cheyu (always-allow on file)", r, { must: /start chesa/i, maxLen: 340 });
  scoreState("S16b", "no allow card re-sent", !cards.some(c => c.ids.some(i => i.includes("waallow"))));
  scoreState("S16b", "chain created", !!(await w.kv.get(`setupchain:${USER}`)));
}
{
  // S16c — Don't allow: stop + disarm + nothing starts.
  const w = makeWorld(); brainImpl = async () => "Sare, ardham ayyindhi.";
  await seedAccount(w, "tap@example.com");
  await send(w, "Setup cheyu");
  const r = await sendInteractive(w, "waallow:no");
  scoreReply("S16c", "[tap Don't allow]", r, { must: /start cheyyaledhu/, maxLen: 300 });
  scoreState("S16c", "ask disarmed", !(await w.kv.get(`wasetupask:${USER}`)));
  scoreState("S16c", "no consent", !(await w.kv.get(`setupconsent:${USER}`)));
  scoreState("S16c", "no chain", !(await w.kv.get(`setupchain:${USER}`)));
  scoreState("S16c", "no dispatch", dispatches.length === 0);
}
// S17 — pause honesty (the 14:45 screenshot's ⏸️ messages): each kind
// is labelled truthfully, carries its action or its scheduled skip,
// and a Google-door / unreadable-mail pause sends the connect card
// AT the pause.
{
  const w = makeWorld(); brainImpl = async () => "Sare, ardham ayyindhi.";
  await w.kv.put(`setupchain:${USER}`, JSON.stringify({ providers: ["together", "serper"], done: [], failed: [], current: "jobt1", email: "t@example.com", at: Date.now(), via: "wa" }));
  await w.kv.put(`setupjob:jobt1`, JSON.stringify({ job: "jobt1", user: USER, provider: "together", state: "running", step: "signing up", at: Date.now(), upd: Date.now() }));
  const p = await runnerPost(w, "progress", "jobt1", { state: "paused", reason: "signin", step: "waiting for sign-in" });
  scoreReply("S17a", "[runner: together paused signin]", p, { must: /Google sign-in maatrame/, maxLen: 800 });
  scoreReply("S17a", "[runner: together paused signin]", p, { must: /skip chesi chain continue/, maxLen: 800 });
  scoreState("S17a", "connect card sent AT the pause", cards.some(c => c.ids.some(i => i.includes("conn:google"))));
}
{
  const w = makeWorld(); brainImpl = async () => "Sare, ardham ayyindhi.";
  await w.kv.put(`setupchain:${USER}`, JSON.stringify({ providers: ["serper"], done: [], failed: [], current: "jobs1", email: "t@example.com", at: Date.now(), via: "wa" }));
  await w.kv.put(`setupjob:jobs1`, JSON.stringify({ job: "jobs1", user: USER, provider: "serper", state: "running", step: "signing up", at: Date.now(), upd: Date.now() }));
  const p = await runnerPost(w, "progress", "jobs1", { state: "paused", reason: "captcha", step: "waiting" });
  scoreReply("S17b", "[runner: serper paused captcha]", p, { must: /captcha \(bot check\)/, maxLen: 800 });
  scoreReply("S17b", "[runner: serper paused captcha]", p, { must: /Take Control/, maxLen: 800 });
  scoreState("S17b", "never the generic sign-in label", !/sign-in kosam aagindhi/.test(p.join(" ")));
}
{
  const w = makeWorld(); brainImpl = async () => "Sare, ardham ayyindhi.";
  await w.kv.put(`setupchain:${USER}`, JSON.stringify({ providers: ["cohere"], done: [], failed: [], current: "jobe1", email: "t@example.com", at: Date.now(), via: "wa" }));
  await w.kv.put(`setupjob:jobe1`, JSON.stringify({ job: "jobe1", user: USER, provider: "cohere", state: "running", step: "signing up", at: Date.now(), upd: Date.now() }));
  const p = await runnerPost(w, "progress", "jobe1", { state: "paused", reason: "email", step: "waiting for verification" });
  scoreReply("S17c", "[runner: cohere paused email, no gmail grant]", p, { must: /feed cheyyalenu/, maxLen: 800 });
  scoreState("S17c", "connect card sent AT the pause", cards.some(c => c.ids.some(i => i.includes("conn:google"))));
}
{
  const w = makeWorld(); brainImpl = async () => "Sare, ardham ayyindhi.";
  await w.kv.put(`tok:${USER}:google`, JSON.stringify({ at: Date.now(), who: "t@example.com" }));
  await w.kv.put(`setupchain:${USER}`, JSON.stringify({ providers: ["cohere"], done: [], failed: [], current: "jobe2", email: "t@example.com", at: Date.now(), via: "wa" }));
  await w.kv.put(`setupjob:jobe2`, JSON.stringify({ job: "jobe2", user: USER, provider: "cohere", state: "running", step: "signing up", at: Date.now(), upd: Date.now() }));
  const p = await runnerPost(w, "progress", "jobe2", { state: "paused", reason: "email", step: "waiting for verification" });
  scoreReply("S17d", "[runner: cohere paused email, gmail connected]", p, { must: /nene feed chestha/, maxLen: 800 });
  scoreState("S17d", "no card needed when the feed works", !cards.some(c => c.ids.some(i => i.includes("conn:"))));
}
// S18 — per-provider outcome lines fire in the REAL post order
// (terminal progress FIRST, result second — setup.py v104): the
// progress post tells the user; the result post must NOT repeat it.
{
  const w = makeWorld(); brainImpl = async () => "Sare, ardham ayyindhi.";
  await w.kv.put(`setupchain:${USER}`, JSON.stringify({ providers: ["groq", "cohere"], done: [], failed: [], current: "jobd1", email: "t@example.com", at: Date.now(), via: "wa" }));
  await w.kv.put(`setupjob:jobd1`, JSON.stringify({ job: "jobd1", user: USER, provider: "groq", state: "running", step: "signing up", at: Date.now(), upd: Date.now() }));
  const p1 = await runnerPost(w, "progress", "jobd1", { state: "failed", note: "paused-captcha time ayipoyindhi — user complete cheyyaledhu" });
  scoreReply("S18a", "[runner progress: groq failed]", p1, { must: /Groq fail.*\(1\/2\)/, maxLen: 400 });
  const chain1 = JSON.parse((await w.kv.get(`setupchain:${USER}`)) || "{}");
  scoreState("S18a", "chain advanced to cohere", !!chain1.current && chain1.current !== "jobd1");
  const p2 = await runnerPost(w, "result", "jobd1", { provider: "groq", status: "failed", error: "paused-captcha time ayipoyindhi" });
  scoreState("S18a", "result post does NOT repeat the line", !p2.some(t => /✗|fail ayyindhi/.test(t)));
  await runnerPost(w, "key", chain1.current, { provider: "cohere", key: "cohere-test-key-0123456789" }); // production order: verified key lands before the terminal progress event
  const p3 = await runnerPost(w, "progress", chain1.current, { state: "done", note: "ready" });
  scoreReply("S18b", "[runner progress: cohere done]", p3, { must: /Cohere.*ready.*\(2\/2\)/, maxLen: 900 });
  scoreReply("S18b", "[runner progress: cohere done]", p3, { must: /Setup complete/, maxLen: 900 });
  scoreState("S18b", "chain cleared at finalize", !(await w.kv.get(`setupchain:${USER}`)));
}

// ===== v111 scenarios: WA feature + process parity (Ajju 2026-11-17) =====
// S19 — on-demand process view (P1): "browser em chesthundhi,
// process chupu" while a setup job runs -> the step line + the
// job's LATEST screenshot as an image + the action card (Stop /
// Process feed). The frame comes from tcframe:<job> — the same
// record the app's live view reads.
{
  const w = makeWorld(); brainImpl = async () => "Sare, ardham ayyindhi.";
  await w.kv.put(`setupchain:${USER}`, JSON.stringify({ providers: ["groq", "cohere"], done: [], failed: [], current: "jobp1", email: "t@example.com", at: Date.now(), via: "wa" }));
  await w.kv.put(`setupjob:jobp1`, JSON.stringify({ job: "jobp1", user: USER, provider: "groq", state: "running", step: "creating account", url: "https://console.groq.com/keys", at: Date.now(), upd: Date.now() }));
  await seedFrame(w, "jobp1", "fp1");
  const r = await send(w, "Browser em chesthundhi, process chupu");
  scoreReply("S19a", "Browser em chesthundhi, process chupu", r, { must: /Groq setup: nadusthundhi — creating account/, maxLen: 500 });
  scoreState("S19a", "screenshot sent as image", imgCount() === 1 && images[0].id === "media_test_1");
  scoreState("S19a", "action card has Stop", cards.some(c => c.ids.some(i => i.includes("waproc:stop"))));
  scoreState("S19a", "action card has Process feed", cards.some(c => c.ids.some(i => i.includes("waproc:feed"))));
  // S19b — the same view for a BROWSE job (browsecur resolution).
  const w2 = makeWorld(); brainImpl = async () => "Sare, ardham ayyindhi.";
  await w2.kv.put(`browsecur:${USER}`, JSON.stringify({ job: "jobb9", at: Date.now() }));
  await w2.kv.put(`setupjob:jobb9`, JSON.stringify({ job: "jobb9", user: USER, provider: "browse", flow: "browse", task: "example.com lo price chudu", state: "running", step: "reading page", url: "https://example.com/item", at: Date.now(), upd: Date.now() }));
  await seedFrame(w2, "jobb9", "fp1");
  const r2 = await send(w2, "Process chupu");
  scoreReply("S19b", "Process chupu (browse job)", r2, { must: /Browse: nadusthundhi — reading page/, maxLen: 600 });
  scoreState("S19b", "browse screenshot sent", imgCount() === 1);
}
// S20 — QUIET BY DEFAULT + pause carries the screen (P1): a mid-job
// step change sends NOTHING unprompted; the transition into a
// captcha pause sends the honest pause text AND the screenshot of
// the wall.
{
  const w = makeWorld(); brainImpl = async () => "Sare, ardham ayyindhi.";
  await w.kv.put(`setupchain:${USER}`, JSON.stringify({ providers: ["serper"], done: [], failed: [], current: "jobq1", email: "t@example.com", at: Date.now(), via: "wa" }));
  await w.kv.put(`setupjob:jobq1`, JSON.stringify({ job: "jobq1", user: USER, provider: "serper", state: "running", step: "signing up", at: Date.now(), upd: Date.now() }));
  const p0 = await runnerPost(w, "progress", "jobq1", { state: "running", step: "filling form" });
  scoreState("S20a", "mid-job step change sends nothing", p0.length === 0 && imgCount() === 0);
  await seedFrame(w, "jobq1", "fp1");
  const p1 = await runnerPost(w, "progress", "jobq1", { state: "paused", reason: "captcha", step: "waiting" });
  scoreReply("S20b", "[runner: serper paused captcha]", p1, { must: /captcha \(bot check\)/, maxLen: 900 });
  scoreState("S20b", "pause carries the screenshot", imgCount() === 1 && /ee screen meedha aagindhi/.test(images[0].caption));
}
// S21 — PROCESS FEED opt-in (P1): "process chupinchu step by step"
// arms the feed for THAT job; step changes stream line + new frame;
// the terminal post clears the flag; the NEXT job starts quiet.
{
  const w = makeWorld(); brainImpl = async () => "Sare, ardham ayyindhi.";
  await w.kv.put(`setupchain:${USER}`, JSON.stringify({ providers: ["groq", "cohere"], done: [], failed: [], current: "jobf1", email: "t@example.com", at: Date.now(), via: "wa" }));
  await w.kv.put(`setupjob:jobf1`, JSON.stringify({ job: "jobf1", user: USER, provider: "groq", state: "running", step: "signing up", at: Date.now(), upd: Date.now() }));
  await seedFrame(w, "jobf1", "fp1");
  const r = await send(w, "Process chupinchu step by step");
  scoreReply("S21a", "Process chupinchu step by step", r, { must: /Process feed ON/, maxLen: 600 });
  scoreState("S21a", "feed armed for this job", ((JSON.parse((await w.kv.get(`wafeed:${USER}`)) || "{}")).job === "jobf1"));
  scoreState("S21a", "current frame sent at opt-in", imgCount() === 1);
  await seedFrame(w, "jobf1", "fp2");
  const p1 = await runnerPost(w, "progress", "jobf1", { state: "running", step: "entering details" });
  scoreReply("S21b", "[feed: step change]", p1, { must: /▸ .*entering details/, maxLen: 400 });
  scoreState("S21b", "new frame streamed", imgCount() === 2);
  const p2 = await runnerPost(w, "progress", "jobf1", { state: "running", step: "entering details" });
  scoreState("S21b", "same step + same frame = silence", p2.length === 0 && imgCount() === 2);
  await runnerPost(w, "key", "jobf1", { provider: "groq", key: "gsk-test-key-0123456789" });
  const p3 = await runnerPost(w, "progress", "jobf1", { state: "done", note: "ready" });
  scoreReply("S21c", "[feed: groq done]", p3, { must: /Groq.*ready/, maxLen: 400 });
  scoreState("S21c", "feed cleared at terminal", !(await w.kv.get(`wafeed:${USER}`)));
  const chain2 = JSON.parse((await w.kv.get(`setupchain:${USER}`)) || "{}");
  scoreState("S21c", "chain advanced", !!chain2.current && chain2.current !== "jobf1");
  const p4 = await runnerPost(w, "progress", chain2.current, { state: "running", step: "signing up" });
  scoreState("S21c", "next job starts quiet (no feed lines)", !p4.some(t => /▸/.test(t)) && imgCount() === 2);
  // S21d — feed off by text.
  await send(w, "Process chupinchu");
  scoreState("S21d", "feed re-armed", !!(await w.kv.get(`wafeed:${USER}`)));
  const rOff = await send(w, "Feed off");
  scoreReply("S21d", "Feed off", rOff, { must: /feed OFF/, maxLen: 200 });
  scoreState("S21d", "feed disarmed", !(await w.kv.get(`wafeed:${USER}`)));
}
// S22 — a structured ASK pause (OTP) also carries the screenshot.
{
  const w = makeWorld(); brainImpl = async () => "Sare, ardham ayyindhi.";
  await w.kv.put(`setupchain:${USER}`, JSON.stringify({ providers: ["groq"], done: [], failed: [], current: "jobo1", email: "t@example.com", at: Date.now(), via: "wa" }));
  await w.kv.put(`setupjob:jobo1`, JSON.stringify({ job: "jobo1", user: USER, provider: "groq", state: "running", step: "signing up", at: Date.now(), upd: Date.now() }));
  await seedFrame(w, "jobo1", "fp1");
  const p = await runnerPost(w, "progress", "jobo1", { state: "paused", reason: "sms", step: "waiting for code", awaiting: { id: "a1", provider: "groq", kind: "otp", prompt: "Groq nunchi SMS code vachindhi — ikkada pampu.", at: Date.now(), expires: Date.now() + 600000, attempts: 1 } });
  scoreReply("S22", "[runner: groq OTP ask]", p, { must: /SMS code/, maxLen: 400 });
  scoreState("S22", "ask pause carries the screenshot", imgCount() === 1);
}
// S23 — RETRY pass (P3): setupdone carries 1 ready + 3 failed
// (email door, signin door, captcha). Google is connected, so the
// ask gets the offer + allow card; the Allow tap starts a MERGED
// chain (providers = full set, done carried over) whose first job
// is the first failed provider — one continuous record.
{
  const w = makeWorld(); brainImpl = async () => "Sare, ardham ayyindhi.";
  await seedAccount(w, "markk34200@gmail.com");
  await w.kv.put(`tok:${USER}:google`, JSON.stringify({ at: Date.now(), who: "markk34200@gmail.com" }));
  await w.kv.put(`setupdone:${USER}`, JSON.stringify({ state: "failed", done: ["openrouter"], failed: ["groq", "together", "serper"], skipped: { serper: { kind: "captcha", at: Date.now() } }, failReason: { groq: "email verification failed", together: "paused-signin — user step time ayipoyindhi", serper: "paused-captcha — user complete cheyyaledhu" }, at: Date.now() }));
  const r = await send(w, "Failed vi malli try cheyu");
  scoreReply("S23a", "Failed vi malli try cheyu", r, { must: /Fail ayinavi: Groq, Together AI, Serper/, maxLen: 700 });
  scoreReply("S23a", "Failed vi malli try cheyu", r, { must: /captcha vasthe/, maxLen: 700 });
  scoreState("S23a", "retry allow card sent", cards.some(c => c.ids.some(i => i.includes("waallow:yes"))));
  scoreState("S23a", "retry pend armed", !!(await w.kv.get(`waretrypend:${USER}`)));
  scoreState("S23a", "no chain before the allow", !(await w.kv.get(`setupchain:${USER}`)));
  const r2 = await sendInteractive(w, "waallow:yes");
  scoreReply("S23b", "[tap Allow — retry]", r2, { must: /Retry start chesa/, maxLen: 500 });
  const chain = JSON.parse((await w.kv.get(`setupchain:${USER}`)) || "{}");
  scoreState("S23b", "merged chain: full provider set", (chain.providers || []).length === 4);
  scoreState("S23b", "merged chain: done carried over", (chain.done || []).join() === "openrouter");
  scoreState("S23b", "retry marked on the record", !!(chain.retry && (chain.retry.of || []).length === 3));
  const cur = JSON.parse((await w.kv.get(`setupjob:${chain.current}`)) || "{}");
  scoreState("S23b", "first retry job is Groq", cur.provider === "groq");
  scoreState("S23b", "retry dispatched", dispatches.some(d => d.url.includes("setup.yml")));
  scoreState("S23b", "retry pend consumed", !(await w.kv.get(`waretrypend:${USER}`)));
}
// S24 — retry BEFORE the connect: the door providers need Google;
// without a grant the offer sends the connect card FIRST and starts
// nothing. Once the grant exists, the same ask produces the offer.
{
  const w = makeWorld(); brainImpl = async () => "Sare, ardham ayyindhi.";
  await seedAccount(w, "markk34200@gmail.com");
  await w.kv.put(`setupdone:${USER}`, JSON.stringify({ state: "failed", done: [], failed: ["together"], failReason: { together: "paused-signin — user step time ayipoyindhi" }, at: Date.now() }));
  const r = await send(w, "Failed providers malli try cheyu");
  scoreReply("S24a", "Failed providers malli try cheyu (no grant)", r, { must: /Google connect kavali/, maxLen: 700 });
  scoreState("S24a", "connect card sent first", cards.some(c => c.ids.some(i => i.includes("conn:google"))));
  scoreState("S24a", "nothing armed, nothing started", !(await w.kv.get(`waretrypend:${USER}`)) && !(await w.kv.get(`setupchain:${USER}`)));
  await w.kv.put(`tok:${USER}:google`, JSON.stringify({ at: Date.now(), who: "markk34200@gmail.com" }));
  const r2 = await send(w, "Failed providers malli try cheyu");
  scoreReply("S24b", "Failed providers malli try cheyu (grant on file)", r2, { must: /malli try cheyala/, maxLen: 700 });
  scoreState("S24b", "retry pend armed after connect", !!(await w.kv.get(`waretrypend:${USER}`)));
}
// S25 — History + deploy list as WA reads (P2).
{
  const w = makeWorld(); brainImpl = async () => "Sare, ardham ayyindhi.";
  await w.kv.put(`histcount:${USER}`, "2");
  await w.kv.put(`hist:${USER}:2`, JSON.stringify({ n: 2, title: "Space documentary", state: "done", at: Date.now() }));
  await w.kv.put(`hist:${USER}:1`, JSON.stringify({ n: 1, title: "Ocean short", state: "failed", at: Date.now() }));
  const r = await send(w, "Naa videos history chupu");
  scoreReply("S25a", "Naa videos history chupu", r, { must: /Space documentary — ready/, maxLen: 500 });
  scoreReply("S25a", "Naa videos history chupu", r, { must: /Ocean short — fail/, maxLen: 500 });
  await w.kv.put(`udeploy:${USER}`, JSON.stringify({ sites: [{ name: "mysite", url: "https://mysite.pages.dev" }], databases: [{ name: "db1" }] }));
  const r2 = await send(w, "Naa sites list chupu");
  scoreReply("S25b", "Naa sites list chupu", r2, { must: /mysite/, maxLen: 400 });
  scoreReply("S25b", "Naa sites list chupu", r2, { must: /db1/, maxLen: 400 });
}
// S26 — a WA "Stop" halts the setup CHAIN too (P2): pre-fix it only
// cancelled video jobs and answered "emi run avvatledhu" over a
// running chain. The chain outcome is recorded before it clears.
{
  const w = makeWorld(); brainImpl = async () => "Sare, ardham ayyindhi.";
  await w.kv.put(`setupchain:${USER}`, JSON.stringify({ providers: ["groq", "cohere"], done: ["groq"], failed: [], current: "jobs9", email: "t@example.com", at: Date.now(), via: "wa" }));
  await w.kv.put(`setupjob:jobs9`, JSON.stringify({ job: "jobs9", user: USER, provider: "cohere", state: "running", step: "signing up", at: Date.now(), upd: Date.now() }));
  const r = await send(w, "Stop");
  scoreReply("S26", "Stop (chain running)", r, { must: /setup stop chesa/, maxLen: 400 });
  scoreState("S26", "chain cleared", !(await w.kv.get(`setupchain:${USER}`)));
  const fin = JSON.parse((await w.kv.get(`setupdone:${USER}`)) || "{}");
  scoreState("S26", "outcome recorded as stopped with done kept", fin.state === "stopped" && (fin.done || []).join() === "groq");
  const j = JSON.parse((await w.kv.get(`setupjob:jobs9`)) || "{}");
  scoreState("S26", "job marked stopped", j.state === "stopped");
  // S26b — the process card's Continue button resumes a paused job.
  const w2 = makeWorld(); brainImpl = async () => "Sare, ardham ayyindhi.";
  await w2.kv.put(`setupchain:${USER}`, JSON.stringify({ providers: ["groq"], done: [], failed: [], current: "jobc9", email: "t@example.com", at: Date.now(), via: "wa" }));
  await w2.kv.put(`setupjob:jobc9`, JSON.stringify({ job: "jobc9", user: USER, provider: "groq", state: "paused", pauseReason: "captcha", pausedAt: Date.now(), at: Date.now(), upd: Date.now() }));
  const r2 = await sendInteractive(w2, "waproc:continue");
  scoreReply("S26b", "[tap Continue]", r2, { must: /Continue chesa/, maxLen: 300 });
  const j2 = JSON.parse((await w2.kv.get(`setupjob:jobc9`)) || "{}");
  scoreState("S26b", "job running again", j2.state === "running" && !j2.pauseReason);
}

// ===== v112 scenarios: total-failure forensic (Ajju 2026-11-17 16:10-16:11) =====
// S27 — BUG A verbatim: a quote-reply to the Connect card, "Inko youtube
// acc conncet cheyocha", got the bare refusal "Sorry, I can't help."
// live. The brain stub returns the RECORDED refusal; the structural
// connections router must answer instead (yes + connect card), and on
// a non-connect question the refusal family must never reach the user
// (pool re-ask, then the honest brain-down line).
{
  const w = makeWorld();
  await w.kv.put(`gaccts:${USER}`, JSON.stringify({ list: [{ id: "g1", email: "a@example.com", ytChannel: "", ytNoChannel: true, gmail: false, yt: true, state: "ok", at: Date.now() }], def: "g1" }));
  brainImpl = async () => "Sorry, I can't help.";
  const r = await send(w, "Inko youtube acc conncet cheyocha");
  scoreState("S27a", "refusal never reaches the user", !/can(?:'|’)?t help/i.test(r.join(" ")));
  scoreReply("S27a", "Inko youtube acc conncet cheyocha", r, { must: /Inko account connect cheyoche/, maxLen: 700 });
  scoreState("S27a", "connect card sent", cards.some(c => c.ids.some(i => i.includes("conn:youtube"))));
  // S27b — the refusal family on a NON-connect question: first pool
  // answer refuses, the re-ask answers; a pool that only refuses
  // yields the brain-down line, never the refusal.
  const w2 = makeWorld(); let calls = 0;
  brainImpl = async () => (++calls === 1 ? "Sorry, I can't help." : "Muse ante Meta valla AI assistant — code, content, chala panulalo help chesthundhi.");
  const r2 = await send(w2, "Muse ante enti?");
  scoreState("S27b", "pool re-ask replaced the refusal", !/can(?:'|’)?t help/i.test(r2.join(" ")) && /Muse ante/i.test(r2.join(" ")));
  const w3 = makeWorld();
  brainImpl = async () => "I cannot assist with that request.";
  const r3 = await send(w3, "Muse ante enti?");
  scoreState("S27c", "always-refusing pool -> brain-down line, never the refusal", !/cannot assist/i.test(r3.join(" ")) && /brain okka nimisham/i.test(r3.join(" ")));
}
// S28 — BUG B verbatim: "Neeku enni youtube accs conncet ayi unnay"
// answered live with the SETUP fail list. Seed BOTH states — 2 YouTube
// grants (both no-channel, the 16:10/16:11 ground truth) and the
// finished 0/23 setup record — the answer must be the YouTube count
// and contain NO setup fail list.
{
  const w = makeWorld();
  await w.kv.put(`gaccts:${USER}`, JSON.stringify({ list: [
    { id: "g1", email: "a@example.com", ytChannel: "", ytNoChannel: true, gmail: false, yt: true, state: "ok", at: Date.now() },
    { id: "g2", email: "b@example.com", ytChannel: "", ytNoChannel: true, gmail: false, yt: true, state: "ok", at: Date.now() },
  ], def: "g1" }));
  await w.kv.put(`setupdone:${USER}`, JSON.stringify({ state: "failed", done: [], failed: ["groq", "openrouter", "gemini", "cloudflare", "cohere", "together", "sambanova", "fireworks", "cerebras", "nvidia", "mistral", "ai21", "voyage", "tavily", "serper", "exa", "deepgram", "assemblyai", "elevenlabs", "stability", "jina", "kaggle", "pexels"], at: Date.now() }));
  brainImpl = async () => "Sare, ardham ayyindhi.";
  const r = await send(w, "Neeku enni youtube accs conncet ayi unnay");
  scoreReply("S28", "Neeku enni youtube accs conncet ayi unnay", r, { must: /YouTube: 2 accounts connect ayyayi/, maxLen: 800 });
  scoreReply("S28", "Neeku enni youtube accs conncet ayi unnay", r, { must: /channel kanipinchaledu/, maxLen: 800 });
  scoreState("S28", "NO setup fail list in a connections answer", !/Ayyina setup result/.test(r.join(" ")) && !/Groq/.test(r.join(" ")));
  // Neighbouring phrasings from the amendment audit:
  const r2 = await send(w, "enni google accs connect ayyayi");
  scoreState("S28b", "google phrasing -> connections reporter, asked service leads with its zero", /Google: inka okka account kuda connect avvaledu/.test(r2.join(" ")) && !/Ayyina setup result/.test(r2.join(" ")));
  const r3 = await send(w, "naa channel connect lo undha");
  scoreState("S28c", "channel phrasing -> YouTube connections answer", /YouTube: 2 accounts/.test(r3.join(" ")));
}
// S29 — P1 identity: NO ph: index (acctFind by phone finds nothing —
// today's production state), the name lives ONLY on the account the
// chain email resolves to. The chain must start with that name on the
// record, so the runner never asks in chat. Pre-fix userName was "".
{
  const w = makeWorld();
  await w.kv.put(`em:peru@example.com`, "u_test9");
  await w.kv.put(`acct:u_test9`, JSON.stringify({ uid: "u_test9", name: "Peru Test", email: "peru@example.com", phone: "", pphone: "" }));
  brainImpl = async () => "Sare, ardham ayyindhi.";
  await send(w, "Free ai models ni brain ki api keys create pettu");
  await send(w, "Sare");
  const r = await send(w, "peru@example.com");
  const chain = JSON.parse((await w.kv.get(`setupchain:${USER}`)) || "null");
  scoreState("S29", "chain created", !!chain);
  scoreState("S29", "userName resolved from the email account record", !!chain && chain.userName === "Peru Test");
  scoreState("S29", "userPhone is the WA number itself", !!chain && chain.userPhone === USER);
  scoreState("S29", "setup dispatched", dispatches.some(d => d.url.includes("setup.yml")));
}
// S30 — mail-feed keyspace bridge: the Gmail grant lives ONLY under
// the linked app account (u_test1); the paused job's user is the WA
// phone. Pre-fix the feed recorded no-gmail-token forever (Groq +
// Cohere today). Post-fix the feed must REACH the grant — any outcome
// except no-gmail-token proves the bridge (the stub 404s the Gmail
// API, so the recorded reason is a fetch outcome, not a found link).
{
  const w = makeWorld();
  await seedAccount(w, "markk@example.com");
  await w.kv.put(`gaccts:u_test1`, JSON.stringify({ list: [{ id: "g1", email: "markk@example.com", ytChannel: "", ytNoChannel: false, gmail: true, yt: false, state: "ok", at: Date.now() }], def: "g1" }));
  await w.kv.put(`tok:u_test1:google`, JSON.stringify({ access_token: "tok-fresh", refresh_token: "rt", at: Date.now(), expires_in: 3600, who: "markk@example.com" }));
  await w.kv.put(`setupchain:${USER}`, JSON.stringify({ providers: ["groq"], done: [], failed: [], current: "jobf1", email: "markk@example.com", at: Date.now(), via: "wa" }));
  await w.kv.put(`setupjob:jobf1`, JSON.stringify({ job: "jobf1", user: USER, provider: "groq", state: "paused", pauseReason: "email", verifyWait: true, email: "markk@example.com", pausedAt: Date.now(), at: Date.now(), upd: Date.now() }));
  brainImpl = async () => "Sare, ardham ayyindhi.";
  await runnerPost(w, "job", "jobf1", {});
  const j = JSON.parse((await w.kv.get(`setupjob:jobf1`)) || "{}");
  scoreState("S30", "feed reached the linked account's Gmail grant", !!j.mailFetch && j.mailFetch !== "no-gmail-token");
}

// ===== v113 scenarios: WA→YouTube upload (the audit's 8) =====
// S31 — audit #1: a video SENT in the WA chat is staged (history
// entry + bytes) and a bare follow-up "YouTube lo upload cheyu"
// finds it: confirm summary (title, description head, tag count,
// privacy=unlisted, channel name) -> "cheyu" -> WA start line ->
// resumable session -> watch link; history stamped.
{
  const w = makeWorld(); brainImpl = async () => "Sare, ardham ayyindhi.";
  await seedYt(w, [{ id: "g1", email: "a@example.com", ytChannel: "Chan One", ytChannelId: "chan1", ytNoChannel: false, gmail: false, yt: true, state: "ok", at: Date.now() }], "g1", { g1: freshTok('channel "Chan One"') });
  mediaStub["wamid-vid-1"] = { size: 1000, bytes: 64 };
  const r0 = await sendVideo(w, "wamid-vid-1");
  scoreState("S31", "ask line offers the upload path", /YouTube lo upload cheyu/.test(r0.join(" ")));
  const staged = JSON.parse((await w.kv.get(`hist:${USER}:1`)) || "null");
  scoreState("S31", "staged history entry (src wa-upload, done)", !!staged && staged.src === "wa-upload" && staged.state === "done" && staged.mediaId === "wamid-vid-1");
  scoreState("S31", "staged bytes in upl:", !!(await w.kv.get(`upl:${staged.job}`)));
  const r1 = await send(w, "YouTube lo upload cheyu");
  scoreState("S31", "confirm names the channel", /Chan One/.test(r1.join(" ")));
  scoreState("S31", "confirm shows privacy unlisted", /Privacy: unlisted/.test(r1.join(" ")));
  scoreState("S31", "confirm shows description + tag count", /Description:/.test(r1.join(" ")) && /Tags: 3/.test(r1.join(" ")));
  const r2 = await send(w, "cheyu");
  const j2 = r2.join("\n");
  scoreState("S31", "start line precedes the result", j2.indexOf("Upload start chesa") >= 0 && j2.indexOf("Upload start chesa") < j2.indexOf("watch?v=vid123"));
  scoreState("S31", "watch link delivered", /watch\?v=vid123/.test(j2));
  scoreState("S31", "resumable session + one transfer", ytStub.sessionCalls === 1 && ytStub.transferCalls === 1);
  const after = JSON.parse((await w.kv.get(`hist:${USER}:1`)) || "{}");
  scoreState("S31", "history stamped with the video id", !!after.yt && after.yt.videoId === "vid123");
  scoreState("S31", "pending cleared on success", !(await w.kv.get(`uppend:${USER}`)));
}
// S32 — audit #2: two channel-bearing accounts -> the picker CARD
// appears; the tap fixes the account; an explicitly named channel
// in text wins with no card at all.
{
  const w = makeWorld(); brainImpl = async () => "Sare, ardham ayyindhi.";
  await w.kv.put(`histcount:${USER}`, "1");
  await w.kv.put(`hist:${USER}:1`, JSON.stringify({ n: 1, job: "jobx1", title: "Cats", topic: "cats", state: "done", has_result: true, at: Date.now(), yt: null, ig: null }));
  await w.kv.put(`upl:jobx1`, "fakevideobytes");
  await seedYt(w, [
    { id: "g1", email: "a@example.com", ytChannel: "Chan One", ytChannelId: "chan1", ytNoChannel: false, gmail: false, yt: true, state: "ok", at: Date.now() },
    { id: "g2", email: "b@example.com", ytChannel: "Chan Two", ytChannelId: "chan2", ytNoChannel: false, gmail: false, yt: true, state: "ok", at: Date.now() },
  ], "g1", { g1: freshTok('channel "Chan One"'), g2: freshTok('channel "Chan Two"') });
  const r1 = await send(w, "upload video 1 to YouTube");
  scoreState("S32", "picker lists both channels", /Chan One/.test(r1.join(" ")) && /Chan Two/.test(r1.join(" ")));
  scoreState("S32", "picker CARD sent with both rows", cards.some(c => c.ids.some(i => i.includes("ytpick:g1"))) && cards.some(c => c.ids.some(i => i.includes("ytpick:g2"))));
  scoreState("S32", "no pending before the pick", !(await w.kv.get(`uppend:${USER}`)) && !!(await w.kv.get(`uppick:${USER}`)));
  const r2 = await sendInteractive(w, "ytpick:g2");
  scoreState("S32", "confirm names the TAPPED channel", /Chan Two/.test(r2.join(" ")));
  const pend = JSON.parse((await w.kv.get(`uppend:${USER}`)) || "{}");
  scoreState("S32", "pending fixed to the tapped account", pend.ytAcct === "g2");
  const w2 = makeWorld(); brainImpl = async () => "Sare, ardham ayyindhi.";
  await w2.kv.put(`histcount:${USER}`, "1");
  await w2.kv.put(`hist:${USER}:1`, JSON.stringify({ n: 1, job: "jobx1", title: "Cats", topic: "cats", state: "done", has_result: true, at: Date.now(), yt: null, ig: null }));
  await w2.kv.put(`upl:jobx1`, "fakevideobytes");
  await seedYt(w2, [
    { id: "g1", email: "a@example.com", ytChannel: "Chan One", ytChannelId: "chan1", ytNoChannel: false, gmail: false, yt: true, state: "ok", at: Date.now() },
    { id: "g2", email: "b@example.com", ytChannel: "Chan Two", ytChannelId: "chan2", ytNoChannel: false, gmail: false, yt: true, state: "ok", at: Date.now() },
  ], "g1", { g1: freshTok('channel "Chan One"'), g2: freshTok('channel "Chan Two"') });
  const r3 = await send(w2, "upload video 1 to YouTube Chan Two");
  scoreState("S32b", "named channel wins, no picker", /Chan Two/.test(r3.join(" ")) && !(await w2.kv.get(`uppick:${USER}`)));
  scoreState("S32b", "pending fixed to the named account", (JSON.parse((await w2.kv.get(`uppend:${USER}`)) || "{}").ytAcct === "g2"));
}
// S33 — audit #3: only a ytNoChannel account -> named guidance +
// connect card, and ZERO calls to the YouTube upload endpoint.
{
  const w = makeWorld(); brainImpl = async () => "Sare, ardham ayyindhi.";
  await w.kv.put(`histcount:${USER}`, "1");
  await w.kv.put(`hist:${USER}:1`, JSON.stringify({ n: 1, job: "jobx1", title: "Cats", topic: "cats", state: "done", has_result: true, at: Date.now(), yt: null, ig: null }));
  await w.kv.put(`upl:jobx1`, "fakevideobytes");
  await seedYt(w, [{ id: "g1", email: "solo@example.com", ytChannel: "", ytChannelId: "", ytNoChannel: true, gmail: false, yt: true, state: "ok", at: Date.now() }], "g1", { g1: { ...freshTok(""), noChannel: true } });
  const r = await send(w, "upload video 1 to YouTube");
  scoreState("S33", "guidance names the account + the missing channel", /solo@example\.com/.test(r.join(" ")) && /channel ledhu/.test(r.join(" ")));
  scoreState("S33", "connect card attached", cards.some(c => c.ids.some(i => i.includes("conn:youtube"))));
  scoreState("S33", "ZERO upload-endpoint calls", ytStub.sessionCalls === 0 && ytStub.transferCalls === 0);
  scoreState("S33", "no pending created", !(await w.kv.get(`uppend:${USER}`)));
}
// S34 — audit #4: the noChannel flag heals at re-check — the channel
// was created after the connect (mine=true), and the Brand-Account
// shape (mine empty, managedByMe finds it) heals the same way.
{
  const w = makeWorld(); brainImpl = async () => "Sare, ardham ayyindhi.";
  await w.kv.put(`histcount:${USER}`, "1");
  await w.kv.put(`hist:${USER}:1`, JSON.stringify({ n: 1, job: "jobx1", title: "Cats", topic: "cats", state: "done", has_result: true, at: Date.now(), yt: null, ig: null }));
  await w.kv.put(`upl:jobx1`, "fakevideobytes");
  await seedYt(w, [{ id: "g1", email: "solo@example.com", ytChannel: "", ytChannelId: "", ytNoChannel: true, gmail: false, yt: true, state: "ok", at: Date.now() }], "g1", { g1: { ...freshTok(""), noChannel: true } });
  ytStub.mine = [{ id: "chanNew1", snippet: { title: "New Chan" } }];
  const r = await send(w, "upload video 1 to YouTube");
  scoreState("S34", "confirm proceeds on the healed channel", /New Chan/.test(r.join(" ")));
  const idx = JSON.parse((await w.kv.get(`gaccts:${USER}`)) || "{}");
  scoreState("S34", "index healed: flag cleared, title + ID stored", idx.list[0].ytNoChannel === false && idx.list[0].ytChannel === "New Chan" && idx.list[0].ytChannelId === "chanNew1");
  const r2 = await send(w, "cheyu");
  scoreState("S34", "upload completes after the heal", /watch\?v=vid123/.test(r2.join(" ")));
  const w2 = makeWorld(); brainImpl = async () => "Sare, ardham ayyindhi.";
  await w2.kv.put(`histcount:${USER}`, "1");
  await w2.kv.put(`hist:${USER}:1`, JSON.stringify({ n: 1, job: "jobx1", title: "Cats", topic: "cats", state: "done", has_result: true, at: Date.now(), yt: null, ig: null }));
  await w2.kv.put(`upl:jobx1`, "fakevideobytes");
  await seedYt(w2, [{ id: "g1", email: "brand@example.com", ytChannel: "", ytChannelId: "", ytNoChannel: true, gmail: false, yt: true, state: "ok", at: Date.now() }], "g1", { g1: { ...freshTok(""), noChannel: true } });
  ytStub.managed = { status: 200, items: [{ id: "brandchan1", snippet: { title: "Brand Chan" } }] };
  const r3 = await send(w2, "upload video 1 to YouTube");
  scoreState("S34b", "Brand-Account shape heals via managedByMe", /Brand Chan/.test(r3.join(" ")));
  const idx2 = JSON.parse((await w2.kv.get(`gaccts:${USER}`)) || "{}");
  scoreState("S34b", "brand channel stored with its ID", idx2.list[0].ytChannel === "Brand Chan" && idx2.list[0].ytChannelId === "brandchan1" && idx2.list[0].ytNoChannel === false);
}
// S35 — audit #5: expired grant (refresh fails) -> the failure reply
// carries the reconnect card AND the pending upload survives; after
// a reconnect the same "cheyu" completes the SAME pending upload.
{
  const w = makeWorld(); brainImpl = async () => "Sare, ardham ayyindhi.";
  await w.kv.put(`histcount:${USER}`, "1");
  await w.kv.put(`hist:${USER}:1`, JSON.stringify({ n: 1, job: "jobx1", title: "Cats", topic: "cats", state: "done", has_result: true, at: Date.now(), yt: null, ig: null }));
  await w.kv.put(`upl:jobx1`, "fakevideobytes");
  await seedYt(w, [{ id: "g1", email: "a@example.com", ytChannel: "Chan One", ytChannelId: "chan1", ytNoChannel: false, gmail: false, yt: true, state: "ok", at: Date.now() }], "g1", { g1: { access_token: "tok-stale", refresh_token: "rt", at: Date.now() - 7200e3, expires_in: 3600, who: 'channel "Chan One"' } });
  ytStub.refreshFails = true;
  await send(w, "upload video 1 to YouTube");
  const r = await send(w, "cheyu");
  scoreState("S35", "expired outcome is named honestly", /expire/i.test(r.join(" ")));
  scoreState("S35", "reconnect card attached to the failure", cards.some(c => c.ids.some(i => i.includes("conn:youtube"))));
  scoreState("S35", "pending upload survives the failure", !!(await w.kv.get(`uppend:${USER}`)));
  scoreState("S35", "no upload attempted on a dead token", ytStub.sessionCalls === 0);
  // the reconnect lands (fresh grant, same account) — the SAME
  // pending upload now posts on the next "cheyu".
  await w.kv.put(`tok:${USER}:youtube`, JSON.stringify(freshTok('channel "Chan One"')));
  const idx = JSON.parse((await w.kv.get(`gaccts:${USER}`)) || "{}"); idx.list[0].state = "ok"; await w.kv.put(`gaccts:${USER}`, JSON.stringify(idx));
  const r2 = await send(w, "cheyu");
  scoreState("S35", "same pending upload completes after reconnect", /watch\?v=vid123/.test(r2.join(" ")));
  scoreState("S35", "pending cleared after the success", !(await w.kv.get(`uppend:${USER}`)));
}
// S36 — audit #6: quota 403 -> the honest quota line, no retry loop,
// pending upload kept.
{
  const w = makeWorld(); brainImpl = async () => "Sare, ardham ayyindhi.";
  await w.kv.put(`histcount:${USER}`, "1");
  await w.kv.put(`hist:${USER}:1`, JSON.stringify({ n: 1, job: "jobx1", title: "Cats", topic: "cats", state: "done", has_result: true, at: Date.now(), yt: null, ig: null }));
  await w.kv.put(`upl:jobx1`, "fakevideobytes");
  await seedYt(w, [{ id: "g1", email: "a@example.com", ytChannel: "Chan One", ytChannelId: "chan1", ytNoChannel: false, gmail: false, yt: true, state: "ok", at: Date.now() }], "g1", { g1: freshTok('channel "Chan One"') });
  ytStub.uploadMode = "quota";
  await send(w, "upload video 1 to YouTube");
  const r = await send(w, "cheyu");
  scoreState("S36", "quota answered as its own fact (try tomorrow)", /quota/i.test(r.join(" ")) && /repu/.test(r.join(" ")));
  scoreState("S36", "no retry loop (one session call)", ytStub.sessionCalls === 1 && ytStub.transferCalls === 0);
  scoreState("S36", "pending kept after quota", !!(await w.kv.get(`uppend:${USER}`)));
  scoreState("S36", "Google's raw message never surfaces", !/request cannot be completed/i.test(r.join(" ")));
}
// S37 — audit #7: the RUNNER leg — a WA-sent video too big for KV
// (media pointer only) dispatches a ytupload job carrying the media
// id + a minted token (never in chat); runner progress posts become
// WA lines; the terminal post sends the link, stamps history and
// settles the pending upload. A runner failure names its stage.
{
  const w = makeWorld(); brainImpl = async () => "Sare, ardham ayyindhi.";
  await w.kv.put(`histcount:${USER}`, "1");
  await w.kv.put(`hist:${USER}:1`, JSON.stringify({ n: 1, job: "stagebig", title: "Big WA video", topic: "Big WA video", kind: "upload", src: "wa-upload", state: "done", has_result: false, size: 50000000, mediaId: "wamid-big", at: Date.now(), yt: null, ig: null }));
  await seedYt(w, [{ id: "g1", email: "a@example.com", ytChannel: "Chan One", ytChannelId: "chan1", ytNoChannel: false, gmail: false, yt: true, state: "ok", at: Date.now() }], "g1", { g1: freshTok('channel "Chan One"') });
  await send(w, "upload video 1 to YouTube");
  const r = await send(w, "cheyu");
  scoreState("S37", "runner leg announced as started", /upload start ayyindhi/.test(r.join(" ")));
  let ytJob = null, ytJobId = null;
  for (const k of w.kv.m.keys()) if (k.startsWith("job:")) { const rec = JSON.parse(w.kv.m.get(k)); if (rec.mode === "ytupload") { ytJob = rec; ytJobId = k.slice(4); } }
  scoreState("S37", "ytupload job record created", !!ytJob);
  scoreState("S37", "job carries the media id + metadata", !!ytJob && ytJob.media_id === "wamid-big" && ytJob.yt_meta && ytJob.yt_meta.privacy === "unlisted");
  scoreState("S37", "job carries the minted token", !!ytJob && ytJob.yt_token === "tok-fresh");
  scoreState("S37", "token never appears in chat", !outbox.some(o => /tok-fresh/.test(o.text || "")));
  scoreState("S37", "edit workflow dispatched for the job", dispatches.some(d => d.url.includes("edit.yml") && d.inputs && d.inputs.job === ytJobId));
  scoreState("S37", "pending kept while the runner works", !!(await w.kv.get(`uppend:${USER}`)));
  const p1 = await ytRunnerPost(w, ytJobId, { state: "progress", pct: 30 });
  scoreState("S37", "progress 25% line relayed", /25%/.test(p1.join(" ")));
  const p2 = await ytRunnerPost(w, ytJobId, { state: "progress", pct: 55 });
  scoreState("S37", "progress 50% line relayed", /50%/.test(p2.join(" ")));
  const p3 = await ytRunnerPost(w, ytJobId, { state: "done", videoId: "runnervid1" });
  scoreState("S37", "final watch link sent", /watch\?v=runnervid1/.test(p3.join(" ")));
  const after = JSON.parse((await w.kv.get(`hist:${USER}:1`)) || "{}");
  scoreState("S37", "history stamped by the runner leg", !!after.yt && after.yt.videoId === "runnervid1");
  scoreState("S37", "pending settled at terminal", !(await w.kv.get(`uppend:${USER}`)));
  const w2 = makeWorld(); brainImpl = async () => "Sare, ardham ayyindhi.";
  await w2.kv.put(`histcount:${USER}`, "1");
  await w2.kv.put(`hist:${USER}:1`, JSON.stringify({ n: 1, job: "stagebig", title: "Big WA video", topic: "Big WA video", kind: "upload", src: "wa-upload", state: "done", has_result: false, size: 50000000, mediaId: "wamid-big", at: Date.now(), yt: null, ig: null }));
  await seedYt(w2, [{ id: "g1", email: "a@example.com", ytChannel: "Chan One", ytChannelId: "chan1", ytNoChannel: false, gmail: false, yt: true, state: "ok", at: Date.now() }], "g1", { g1: freshTok('channel "Chan One"') });
  await send(w2, "upload video 1 to YouTube");
  await send(w2, "cheyu");
  let ytJobId2 = null;
  for (const k of w2.kv.m.keys()) if (k.startsWith("job:")) { const rec = JSON.parse(w2.kv.m.get(k)); if (rec.mode === "ytupload") ytJobId2 = k.slice(4); }
  const pf = await ytRunnerPost(w2, ytJobId2, { state: "failed", stage: "transfer", kind: "error", error: "network down" });
  scoreState("S37b", "runner failure names the stage + channel", /transfer stage/.test(pf.join(" ")) && /Chan One/.test(pf.join(" ")));
  scoreState("S37b", "pending kept after a runner failure", !!(await w2.kv.get(`uppend:${USER}`)));
}
// S38 — audit #8: app-chat parity — the same sequence through
// /api/chat (appTalk) reaches the same chatUpload flow: confirm
// summary, then "cheyu" posts and the reply carries the link.
{
  const w = makeWorld(); brainImpl = async () => "Sare, ardham ayyindhi.";
  await w.kv.put(`sess:${"a".repeat(48)}`, USER);
  await w.kv.put(`histcount:${USER}`, "1");
  await w.kv.put(`hist:${USER}:1`, JSON.stringify({ n: 1, job: "jobx1", title: "Cats", topic: "cats", state: "done", has_result: true, at: Date.now(), yt: null, ig: null }));
  await w.kv.put(`upl:jobx1`, "fakevideobytes");
  await seedYt(w, [{ id: "g1", email: "a@example.com", ytChannel: "Chan One", ytChannelId: "chan1", ytNoChannel: false, gmail: false, yt: true, state: "ok", at: Date.now() }], "g1", { g1: freshTok('channel "Chan One"') });
  const a1 = await appChat(w, "upload video 1 to YouTube");
  scoreState("S38", "app confirm names channel + privacy", /Chan One/.test(a1.reply || "") && /Privacy: unlisted/.test(a1.reply || ""));
  const a2 = await appChat(w, "cheyu");
  scoreState("S38", "app cheyu posts, link in the reply", /watch\?v=vid123/.test(a2.reply || ""));
  scoreState("S38", "same resumable path (1 session + 1 transfer)", ytStub.sessionCalls === 1 && ytStub.transferCalls === 1);
}

// ===== v114 scenarios: live-state fix pass (2026-11-17 verification sweep) =====
// S39 — DEFECT 1: the finalize record (setupdone) is GONE (the live
// failure), but the outcome JOURNAL survives. A Google-connect
// completion must re-fire the retry offer with the FULL failed set
// rebuilt from the journal — 22 failed + Deepgram arriving via the
// skipped bucket = all 23 providers.
const FAILED22 = ["groq", "openrouter", "gemini", "cloudflare", "cohere", "together", "sambanova", "fireworks", "cerebras", "nvidia", "mistral", "ai21", "voyage", "tavily", "serper", "exa", "assemblyai", "elevenlabs", "stability", "jina", "kaggle", "pexels"];
const JOURNAL39 = { state: "failed", done: [], failed: FAILED22, skipped: { deepgram: { kind: "captcha", at: Date.now() }, serper: { kind: "captcha", at: Date.now() }, elevenlabs: { kind: "captcha", at: Date.now() } }, failReason: { groq: "email verification failed — no Gmail grant in the job keyspace", cohere: "email verification failed — no Gmail grant in the job keyspace", gemini: "no-google-token", together: "paused-signin", fireworks: "paused-signin", stability: "paused-signin", serper: "paused-captcha", deepgram: "paused-captcha", elevenlabs: "paused-captcha" }, at: Date.now() };
async function oauthGet(world, path) {
  const before = outbox.length;
  const promises = [];
  const ctx = { waitUntil(p) { promises.push(Promise.resolve(p)); } };
  const req = new Request("https://worker.test" + path, { method: "GET" });
  await worker.fetch(req, world.env, ctx);
  for (let i = 0; i < 6; i++) { const ps = promises.splice(0); if (!ps.length) break; await Promise.all(ps); }
  return outbox.slice(before).filter(o => o.to === USER).map(o => o.text);
}
{
  const w = makeWorld(); brainImpl = async () => "Sare, ardham ayyindhi.";
  await w.kv.put(`setuphist:${USER}`, JSON.stringify(JOURNAL39));
  await w.kv.put(`oauth:st39`, JSON.stringify({ prov: "google", user: USER }));
  const r = await oauthGet(w, "/oauth/google?state=st39&code=testcode");
  scoreState("S39a", "connect completion re-fires the retry offer from the JOURNAL", /malli try cheyala/.test(r.join(" ")) && /Groq/.test(r.join(" ")) && /Pexels/.test(r.join(" ")));
  scoreState("S39a", "offer names the captcha tap honestly", /captcha vasthe/.test(r.join(" ")));
  const pend = JSON.parse((await w.kv.get(`waretrypend:${USER}`)) || "{}");
  scoreState("S39a", "retry armed with the FULL 23-provider failed set", Array.isArray(pend.ids) && pend.ids.length === 23 && pend.ids.includes("deepgram") && pend.ids.includes("pexels") && pend.ids.includes("groq"));
  scoreState("S39a", "allow card sent with the offer", cards.some(c => c.ids.some(i => i.includes("waallow:yes"))));
  // S39b — the phrase trigger reads the journal the same way (door
  // class un-granted here: connect card first, nothing armed).
  const w2 = makeWorld(); brainImpl = async () => "Sare, ardham ayyindhi.";
  await w2.kv.put(`setuphist:${USER}`, JSON.stringify(JOURNAL39));
  const r2 = await send(w2, "failed vi malli try cheyu");
  scoreState("S39b", "phrase offer rebuilt from the journal", /Google connect kavali/.test(r2.join(" ")) && /Groq/.test(r2.join(" ")) && /Pexels/.test(r2.join(" ")));
  scoreState("S39b", "connect card sent, nothing armed while door-grant missing", cards.some(c => c.ids.some(i => i.includes("conn:google"))) && !(await w2.kv.get(`waretrypend:${USER}`)));
  // S39c — last-resort rebuild: no setupdone, no journal — the
  // chain's own terminal job records reconstruct the outcome.
  const w3 = makeWorld(); brainImpl = async () => "Sare, ardham ayyindhi.";
  for (const [job, prov] of [["jobr1", "groq"], ["jobr2", "cohere"], ["jobr3", "pexels"]])
    await w3.kv.put(`setupjob:${job}`, JSON.stringify({ job, user: USER, provider: prov, state: "failed", chain: ["groq", "cohere", "pexels"], note: "flow failed", at: Date.now() - 3600e3, upd: Date.now() - 3600e3 }));
  const r3 = await send(w3, "failed vi malli try cheyu");
  scoreState("S39c", "offer rebuilt from surviving job records", /Google connect kavali/.test(r3.join(" ")) && /Groq/.test(r3.join(" ")) && /Cohere/.test(r3.join(" ")) && /Pexels/.test(r3.join(" ")));
  // S39d — a finalize now writes the journal alongside setupdone.
  const w4 = makeWorld(); brainImpl = async () => "Sare, ardham ayyindhi.";
  await w4.kv.put(`setupchain:${USER}`, JSON.stringify({ providers: ["groq", "cohere"], done: [], failed: [], current: "jobz01", email: "t@example.com", pass: "x", at: Date.now(), browser: "profile", via: "wa" }));
  await w4.kv.put(`setupjob:jobz01`, JSON.stringify({ job: "jobz01", user: USER, provider: "groq", state: "running", step: "creating key", at: Date.now(), upd: Date.now() }));
  await runnerPost(w4, "key", "jobz01", { provider: "groq", key: "gsk-test-key-0123456789" });
  await runnerPost(w4, "result", "jobz01", { provider: "groq", status: "done" });
  const chain4 = JSON.parse((await w4.kv.get(`setupchain:${USER}`)) || "{}");
  await w4.kv.put(`setupjob:${chain4.current}`, JSON.stringify({ job: chain4.current, user: USER, provider: "cohere", state: "running", step: "creating key", at: Date.now(), upd: Date.now() }));
  await runnerPost(w4, "result", chain4.current, { provider: "cohere", status: "failed", error: "signup wall" });
  const hist4 = JSON.parse((await w4.kv.get(`setuphist:${USER}`)) || "{}");
  scoreState("S39d", "finalize journals the outcome", (hist4.done || []).includes("groq") && (hist4.failed || []).includes("cohere"));
  scoreState("S39d", "setupdone still written", !!(await w4.kv.get(`setupdone:${USER}`)));
}
// S40 — DEFECT 2: the malformed YouTube grant (the live shape,
// verbatim): who = the no-channel SENTENCE, noChannel unset, no
// channel ID — in the tok record (derivation path) AND persisted in
// the index. The count question must answer no-channel honestly and
// never name the sentence as a channel; the re-check heal must fire
// for the ID-less record and restore the real channel.
{
  const w = makeWorld(); brainImpl = async () => "Sare, ardham ayyindhi.";
  await w.kv.put(`tok:${USER}:youtube`, JSON.stringify({ access_token: "tok-stale", refresh_token: "rt", at: Date.now() - 8 * 86400e3, expires_in: 3600, who: "(ee account lo YouTube channel kanipinchaledu)" }));
  const r = await send(w, "Neeku enni youtube accs conncet ayi unnay");
  scoreState("S40a", "malformed tok record -> honest no-channel count", /YouTube: 1 account/.test(r.join(" ")) && /channel kanipinchaledu/.test(r.join(" ")));
  scoreState("S40a", "the sentence is never named as a channel", !/— channel:/.test(r.join(" ")));
  const w2 = makeWorld(); brainImpl = async () => "Sare, ardham ayyindhi.";
  await w2.kv.put(`gaccts:${USER}`, JSON.stringify({ list: [{ id: "a6iemaj", email: "", ytChannel: "(ee account lo YouTube channel kanipinchaledu)", ytChannelId: "", ytNoChannel: false, gmail: false, yt: true, state: "expired", at: Date.now() - 8 * 86400e3 }], def: "a6iemaj" }));
  await w2.kv.put(`tok:${USER}:youtube`, JSON.stringify({ access_token: "tok-stale", refresh_token: "rt", at: Date.now() - 8 * 86400e3, expires_in: 3600, who: "(ee account lo YouTube channel kanipinchaledu)" }));
  const r2 = await send(w2, "Neeku enni youtube accs conncet ayi unnay");
  scoreState("S40b", "persisted malformed index -> honest no-channel count", /YouTube: 1 account/.test(r2.join(" ")) && /channel kanipinchaledu/.test(r2.join(" ")) && !/— channel:/.test(r2.join(" ")));
  const w3 = makeWorld(); brainImpl = async () => "Sare, ardham ayyindhi.";
  await w3.kv.put(`histcount:${USER}`, "1");
  await w3.kv.put(`hist:${USER}:1`, JSON.stringify({ n: 1, job: "jobx1", title: "Cats", topic: "cats", state: "done", has_result: true, at: Date.now(), yt: null, ig: null }));
  await w3.kv.put(`upl:jobx1`, "fakevideobytes");
  await w3.kv.put(`gaccts:${USER}`, JSON.stringify({ list: [{ id: "a6iemaj", email: "", ytChannel: "(ee account lo YouTube channel kanipinchaledu)", ytChannelId: "", ytNoChannel: false, gmail: false, yt: true, state: "ok", at: Date.now() }], def: "a6iemaj" }));
  await w3.kv.put(`tok:${USER}:youtube`, JSON.stringify(freshTok("(ee account lo YouTube channel kanipinchaledu)")));
  ytStub.mine = [{ id: "UC999", snippet: { title: "Quiet One" } }];
  const r3 = await send(w3, "upload video 1 to YouTube");
  scoreState("S40c", "heal fires for the ID-less record — confirm names the REAL channel", /Quiet One/.test(r3.join(" ")));
  const idx3 = JSON.parse((await w3.kv.get(`gaccts:${USER}`)) || "{}");
  scoreState("S40c", "index healed with the channel ID", idx3.list[0].ytChannelId === "UC999" && idx3.list[0].ytChannel === "Quiet One" && idx3.list[0].ytNoChannel === false);
  const tok3 = JSON.parse((await w3.kv.get(`tok:${USER}:youtube`)) || "{}");
  scoreState("S40c", "token record healed (who + ID, flag cleared)", tok3.who === 'channel "Quiet One"' && tok3.ytChannelId === "UC999" && !tok3.noChannel);
}
// S41 — DEFECT 3a guard: a verification-mail wait with NO viable
// Gmail grant fails the provider fast (3 dead feed outcomes, the
// class reason on the job) — never mailTries in the dozens. With a
// viable grant the same polls are ordinary fetch outcomes and the
// job keeps waiting.
{
  const w = makeWorld(); brainImpl = async () => "Sare, ardham ayyindhi.";
  await w.kv.put(`setupchain:${USER}`, JSON.stringify({ providers: ["groq"], done: [], failed: [], current: "jobd1", email: "t@example.com", at: Date.now(), via: "wa" }));
  await w.kv.put(`setupjob:jobd1`, JSON.stringify({ job: "jobd1", user: USER, provider: "groq", state: "paused", pauseReason: "email", verifyWait: true, email: "t@example.com", pausedAt: Date.now(), at: Date.now(), upd: Date.now() }));
  for (let i = 0; i < 3; i++) {
    await runnerPost(w, "job", "jobd1", {});
    const j = JSON.parse((await w.kv.get(`setupjob:jobd1`)) || "{}");
    if (j.state === "paused") { j.mailFetchAt = 0; await w.kv.put(`setupjob:jobd1`, JSON.stringify(j)); } // simulate the 20s feed throttle elapsing
  }
  const jEnd = JSON.parse((await w.kv.get(`setupjob:jobd1`)) || "{}");
  scoreState("S41a", "dead-grant mail wait fails the provider fast", jEnd.state === "failed" && /no viable Gmail grant/.test(jEnd.note || ""));
  scoreState("S41a", "tries stayed in single digits", (jEnd.mailTries || 0) <= 3 && (jEnd.mailDead || 0) === 3);
  const w2 = makeWorld(); brainImpl = async () => "Sare, ardham ayyindhi.";
  await w2.kv.put(`gaccts:${USER}`, JSON.stringify({ list: [{ id: "g1", email: "a@example.com", ytChannel: "", ytNoChannel: false, gmail: true, yt: false, state: "ok", at: Date.now() }], def: "g1" }));
  await w2.kv.put(`tok:${USER}:google`, JSON.stringify({ access_token: "tok-fresh", refresh_token: "rt", at: Date.now(), expires_in: 3600, who: "a@example.com" }));
  await w2.kv.put(`setupchain:${USER}`, JSON.stringify({ providers: ["groq"], done: [], failed: [], current: "jobd2", email: "a@example.com", at: Date.now(), via: "wa" }));
  await w2.kv.put(`setupjob:jobd2`, JSON.stringify({ job: "jobd2", user: USER, provider: "groq", state: "paused", pauseReason: "email", verifyWait: true, email: "a@example.com", pausedAt: Date.now(), at: Date.now(), upd: Date.now() }));
  for (let i = 0; i < 3; i++) {
    await runnerPost(w2, "job", "jobd2", {});
    const j = JSON.parse((await w2.kv.get(`setupjob:jobd2`)) || "{}");
    if (j.state === "paused") { j.mailFetchAt = 0; await w2.kv.put(`setupjob:jobd2`, JSON.stringify(j)); }
  }
  const j2End = JSON.parse((await w2.kv.get(`setupjob:jobd2`)) || "{}");
  scoreState("S41b", "viable grant -> ordinary fetch outcomes, job keeps waiting", j2End.state === "paused" && j2End.mailFetch === "gmail-error" && !(j2End.mailDead > 0));
}
// S42 — DEFECT 3b guard: a stall-finalized chain settles its current
// job — the job record must not outlive its chain in "queued" (the
// 14 stranded resend/brevo jobs of 2026-11-15/16).
{
  const w = makeWorld(); brainImpl = async () => "Sare, ardham ayyindhi.";
  await w.kv.put(`setupchain:${USER}`, JSON.stringify({ providers: ["resend"], done: [], failed: [], current: "jobq9", email: "t@example.com", at: Date.now() - 40 * 60000, via: "wa" }));
  await w.kv.put(`setupjob:jobq9`, JSON.stringify({ job: "jobq9", user: USER, provider: "resend", state: "queued", step: "starting", at: Date.now() - 40 * 60000, upd: Date.now() - 31 * 60000 }));
  const r = await send(w, "Chesava");
  scoreState("S42", "watchdog stall-finalizes the chain", /Setup aagipoyindhi/.test(r.join(" ")));
  const j = JSON.parse((await w.kv.get(`setupjob:jobq9`)) || "{}");
  scoreState("S42", "the stranded job settles WITH its chain", j.state === "failed" && /stalled/.test(j.step || ""));
  const hist42 = JSON.parse((await w.kv.get(`setuphist:${USER}`)) || "{}");
  scoreState("S42", "stall outcome journaled", hist42.state === "stalled");
}

// ===== v115 scenarios: WA spam loop / unexecuted skip / double consent + stop-silence + run-the-rest (Ajju 2026-11-17 17:29–17:38) =====
// S43 — the pause spam loop: N identical pause posts for ONE pause
// produce exactly ONE WA text + ONE image. A new screen (frame fp
// change) is a real state change -> one more. A record rewrite that
// flips the job to a terminal state and back must NOT resurrect it
// (sticky terminal) and must NOT re-send.
{
  const w = makeWorld(); brainImpl = async () => "Sare, ardham ayyindhi.";
  await w.kv.put(`setupchain:${USER}`, JSON.stringify({ providers: ["groq", "openrouter"], done: [], failed: [], current: "jobp1", email: "t@example.com", at: Date.now(), via: "wa" }));
  await w.kv.put(`setupjob:jobp1`, JSON.stringify({ job: "jobp1", user: USER, provider: "groq", state: "running", step: "signing up", email: "t@example.com", at: Date.now(), upd: Date.now() }));
  await seedFrame(w, "jobp1", "fpA");
  const post = note => runnerPost(w, "progress", "jobp1", { state: "paused", step: "verify-email", note, reason: "email", verifyWait: true, url: "https://console.groq.com/login" });
  const first = await post("Groq verification link kosam Gmail check chesthunna — check 1");
  scoreState("S43a", "first pause post sends exactly one text", first.length === 1 && /Groq/.test(first[0]));
  scoreState("S43a", "first pause post sends exactly one image", imgCount() === 1);
  let extra = [];
  for (let i = 2; i <= 6; i++) extra = extra.concat(await post(`Groq verification link kosam Gmail check chesthunna — check ${i}`));
  scoreState("S43a", "5 identical pause posts send NOTHING more", extra.length === 0 && imgCount() === 1);
  await seedFrame(w, "jobp1", "fpB"); // a genuinely new screen
  const changed = await post("Groq verification link kosam Gmail check chesthunna — check 7");
  scoreState("S43b", "new screen -> exactly one more text + image", changed.length === 1 && imgCount() === 2);
  // the flip attack: the feed settles the job (terminal), the runner's
  // next heartbeat tries to flip it back to paused
  const jFlip = JSON.parse((await w.kv.get(`setupjob:jobp1`)) || "{}");
  jFlip.state = "failed"; jFlip.note = "email verification — no viable Gmail grant";
  await w.kv.put(`setupjob:jobp1`, JSON.stringify(jFlip));
  const flip = await post("Groq verification link kosam Gmail check chesthunna — check 8");
  const jAfter = JSON.parse((await w.kv.get(`setupjob:jobp1`)) || "{}");
  scoreState("S43c", "terminal state is sticky — heartbeat swallowed, nothing sent", flip.length === 0 && imgCount() === 2);
  scoreState("S43c", "job stays failed (no resurrection)", jAfter.state === "failed");
}
// S43b — the single remind: same pause, >=10 min later -> ONE remind;
// after that, silence (never a third).
{
  const w = makeWorld(); brainImpl = async () => "Sare, ardham ayyindhi.";
  await w.kv.put(`setupchain:${USER}`, JSON.stringify({ providers: ["groq", "openrouter"], done: [], failed: [], current: "jobp2", email: "t@example.com", at: Date.now(), via: "wa" }));
  await w.kv.put(`setupjob:jobp2`, JSON.stringify({ job: "jobp2", user: USER, provider: "groq", state: "running", step: "signing up", email: "t@example.com", at: Date.now(), upd: Date.now() }));
  await seedFrame(w, "jobp2", "fpA");
  const post = () => runnerPost(w, "progress", "jobp2", { state: "paused", step: "verify-email", note: "wait", reason: "email", verifyWait: true, url: "https://console.groq.com/login" });
  await post();
  const j1 = JSON.parse((await w.kv.get(`setupjob:jobp2`)) || "{}");
  j1.pauseTold.at = Date.now() - 11 * 60000; // the one pause is now 11 minutes old
  await w.kv.put(`setupjob:jobp2`, JSON.stringify(j1));
  const remind = await post();
  scoreState("S43d", "one remind after >=10 min", remind.length === 1);
  const again = await post();
  scoreState("S43d", "never a third message for the same pause", again.length === 0);
}
// S44 — Ajju's 17:32 skip, verbatim: "Leave groq conncer other keys"
// must SETTLE Groq and ADVANCE — never a mere progress report.
{
  const w = makeWorld(); brainImpl = async () => "Ok, stop chesthanu.";
  await w.kv.put(`setupchain:${USER}`, JSON.stringify({ providers: ["groq", "openrouter", "cohere"], done: [], failed: [], current: "jobsk1", email: "t@example.com", at: Date.now(), via: "wa" }));
  await w.kv.put(`setupjob:jobsk1`, JSON.stringify({ job: "jobsk1", user: USER, provider: "groq", state: "paused", pauseReason: "email", verifyWait: true, email: "t@example.com", pausedAt: Date.now(), at: Date.now(), upd: Date.now() }));
  const r = await send(w, "Leave groq conncer other keys");
  scoreReply("S44", "Leave groq conncer other keys", r, { must: /Groq skip chesa/, maxLen: 220 });
  scoreState("S44", "reply carries the new progress count", /1\/3/.test(r.join(" ")));
  scoreState("S44", "brain never answered (no stop line)", !/stop chesthanu/.test(r.join(" ")));
  const chain = JSON.parse((await w.kv.get(`setupchain:${USER}`)) || "{}");
  scoreState("S44", "groq settled as user-skipped on the chain", (chain.failed || []).includes("groq") && ((chain.skipped || {}).groq || {}).kind === "user");
  scoreState("S44", "chain advanced to a new job", !!chain.current && chain.current !== "jobsk1" && dispatches.length >= 1);
  const j = JSON.parse((await w.kv.get(`setupjob:jobsk1`)) || "{}");
  scoreState("S44", "skipped job marked stopped/user-skipped (runner aborts its wait)", j.state === "stopped" && j.step === "user-skipped");
}
// S45 — the 17:29–17:31 consent transcript, replayed: exactly ONE
// allow card, at most ONE email ask, exactly ONE start line, zero
// re-asks. Post-start acknowledgements route to status, never to a
// brain-invented second gate.
{
  const w = makeWorld(); brainImpl = async () => "Proceed cheyyadaniki 'sare' ani confirm cheppu.";
  const r1 = await send(w, "Api keys conncet chesko");
  scoreState("S45a", "setup ask = exactly one allow card", cards.filter(c => c.ids.some(i => i.includes("waallow:yes"))).length === 1);
  scoreState("S45a", "setup ask text is ONE short line — no canned lecture", r1.length === 1 && !/pani naadhe/.test(r1.join(" ")) && r1.join(" ").length <= 160);
  const r2 = await sendInteractive(w, "waallow:yes");
  scoreState("S45b", "allow tap -> the ONE email ask (no email on file)", r2.length === 1 && /email/.test(r2.join(" ")) && /Allow theeskunna/.test(r2.join(" ")));
  const r3 = await send(w, "mike0123l098@gmail.com");
  scoreState("S45c", "email answer starts the chain — exactly one start line", r3.length === 1 && /Setup start chesa/.test(r3.join(" ")) && !!(await w.kv.get(`setupchain:${USER}`)));
  const chainAt = JSON.parse((await w.kv.get(`setupchain:${USER}`)) || "{}").at;
  const dispAt = dispatches.length;
  const r4 = await send(w, "K");
  scoreState("S45d", "'K' after start -> status line, no re-ask, no second start", r4.length === 1 && /Setup progress/.test(r4.join(" ")) && !/confirm cheppu/.test(r4.join(" ")) && !/Setup start chesa/.test(r4.join(" ")));
  const r5 = await send(w, "Dheeniki ok chepa anthe");
  scoreState("S45e", "'dheeniki ok chepa anthe' -> status line, no re-ask, no second start", r5.length === 1 && /Setup progress/.test(r5.join(" ")) && !/confirm cheppu/.test(r5.join(" ")) && !/Setup start chesa/.test(r5.join(" ")));
  const chainEnd = JSON.parse((await w.kv.get(`setupchain:${USER}`)) || "{}");
  scoreState("S45f", "still the SAME single chain (no duplicate start)", chainEnd.at === chainAt && dispatches.length === dispAt);
  const allTxt = [...r1, ...r2, ...r3, ...r4, ...r5].join("\n");
  scoreState("S45g", "whole transcript: one start line, zero confirm re-asks", (allTxt.match(/Setup start chesa/g) || []).length === 1 && !/confirm cheppu/.test(allTxt));
}
// S46 — mailDead consistency (Fix 4): with no viable Google grant the
// provider fails within the guard's bound FROM THE FIRST pause cycle
// and the chain ADVANCES in the same cycle; one outcome line, no
// pause spam afterwards, the corpse cannot be resurrected.
{
  const w = makeWorld(); brainImpl = async () => "Sare, ardham ayyindhi.";
  await w.kv.put(`setupchain:${USER}`, JSON.stringify({ providers: ["groq", "openrouter"], done: [], failed: [], current: "jobm1", email: "t@example.com", at: Date.now(), via: "wa" }));
  await w.kv.put(`setupjob:jobm1`, JSON.stringify({ job: "jobm1", user: USER, provider: "groq", state: "paused", pauseReason: "email", verifyWait: true, email: "t@example.com", pausedAt: Date.now(), at: Date.now(), upd: Date.now() }));
  for (let i = 0; i < 3; i++) {
    await runnerPost(w, "job", "jobm1", {});
    const j = JSON.parse((await w.kv.get(`setupjob:jobm1`)) || "{}");
    if (j.state === "paused") { j.mailFetchAt = 0; await w.kv.put(`setupjob:jobm1`, JSON.stringify(j)); } // simulate the 20s feed throttle elapsing
  }
  const jEnd = JSON.parse((await w.kv.get(`setupjob:jobm1`)) || "{}");
  scoreState("S46a", "provider failed within the guard bound (3 dead outcomes)", jEnd.state === "failed" && (jEnd.mailDead || 0) === 3 && (jEnd.mailTries || 0) <= 3);
  const chain = JSON.parse((await w.kv.get(`setupchain:${USER}`)) || "{}");
  scoreState("S46b", "chain advanced in the same cycle (groq failed, new current job)", (chain.failed || []).includes("groq") && !!chain.current && chain.current !== "jobm1" && dispatches.length >= 1);
  const groqLines = outbox.filter(o => /Groq/.test(o.text));
  scoreState("S46c", "exactly ONE outcome line for the failure, zero pause texts", groqLines.length === 1 && !outbox.some(o => /email verification kosam wait/.test(o.text)));
  const late = await runnerPost(w, "progress", "jobm1", { state: "paused", step: "verify-email", note: "check 9", reason: "email", verifyWait: true, url: "https://console.groq.com/login" });
  const jLate = JSON.parse((await w.kv.get(`setupjob:jobm1`)) || "{}");
  scoreState("S46d", "late heartbeat on the corpse is swallowed (still failed, nothing sent)", late.length === 0 && jLate.state === "failed");
}
// S47 — Defect A: STOP MEANS SILENCE. After the user's Stop, every
// further runner post for the chain is swallowed — no pause text, no
// image, no ask prompt, no resurrection.
{
  const w = makeWorld(); brainImpl = async () => "Sare, ardham ayyindhi.";
  await w.kv.put(`setupchain:${USER}`, JSON.stringify({ providers: ["groq", "openrouter"], done: [], failed: [], current: "jobst1", email: "t@example.com", at: Date.now(), via: "wa" }));
  await w.kv.put(`setupjob:jobst1`, JSON.stringify({ job: "jobst1", user: USER, provider: "groq", state: "running", step: "signing up", email: "t@example.com", at: Date.now(), upd: Date.now() }));
  await seedFrame(w, "jobst1", "fpA");
  const stop = await send(w, "Stop");
  scoreState("S47a", "stop confirmed in one line", stop.length === 1 && /Aapesa/.test(stop[0]));
  const p1 = await runnerPost(w, "progress", "jobst1", { state: "paused", step: "verify-email", note: "check 3", reason: "email", verifyWait: true, url: "https://console.groq.com/login" });
  scoreState("S47b", "post-stop pause post relays NOTHING (no text, no image)", p1.length === 0 && imgCount() === 0);
  const p2 = await runnerPost(w, "progress", "jobst1", { state: "paused", step: "await-otp", note: "code", reason: "sms", url: "https://console.groq.com/login", awaiting: { id: "a1", provider: "groq", kind: "otp", prompt: "Groq code ikkade pampu", at: Date.now(), expires: Date.now() + 600000, attempts: 1 } });
  scoreState("S47c", "post-stop ask post relays NOTHING", p2.length === 0 && imgCount() === 0);
  const p3 = await runnerPost(w, "progress", "jobst1", { state: "failed", step: "error", note: "late fail" });
  scoreState("S47d", "post-stop terminal post relays NOTHING", p3.length === 0 && imgCount() === 0);
  const jEnd = JSON.parse((await w.kv.get(`setupjob:jobst1`)) || "{}");
  scoreState("S47e", "job stays stopped (no resurrection)", jEnd.state === "stopped");
}
// S48 — Defect B, verbatim: "Groq kakunda verey models try cheyu" +
// "Fasst" over a stopped chain with the 23-failure retry set. ONE
// reply: the run starts with Groq excluded. No allow card, no canned
// lecture, no brain stop line — the brain is never invoked.
{
  const w = makeWorld(); brainImpl = async () => "Ok, stop chesthanu.";
  const ALL23 = ["groq", "openrouter", "gemini", "cloudflare", "cohere", "together", "sambanova", "fireworks", "cerebras", "nvidia", "mistral", "ai21", "voyage", "tavily", "serper", "exa", "deepgram", "assemblyai", "elevenlabs", "stability", "jina", "kaggle", "pexels"];
  await w.kv.put(`setupdone:${USER}`, JSON.stringify({ state: "stopped", done: [], failed: ALL23, skipped: { serper: { kind: "captcha", at: Date.now() }, deepgram: { kind: "captcha", at: Date.now() }, elevenlabs: { kind: "captcha", at: Date.now() } }, failReason: { groq: "email verification — no viable Gmail grant", cohere: "email verification — no viable Gmail grant", together: "paused-signin", fireworks: "paused-signin", serper: "paused-captcha", deepgram: "paused-captcha", elevenlabs: "paused-captcha" }, provider: "groq", note: "User stopped the setup.", at: Date.now() }));
  await w.kv.put(`setupconsent:${USER}`, JSON.stringify({ at: Date.now(), scope: "accounts+keys+captchas+server", providers: ALL23, email: "mike0123l098@gmail.com" }));
  await w.kv.put(`gaccts:${USER}`, JSON.stringify({ list: [{ id: "g1", email: "mike0123l098@gmail.com", ytChannel: "", ytNoChannel: false, gmail: true, yt: false, state: "ok", at: Date.now() }], def: "g1" }));
  await w.kv.put(`tok:${USER}:google`, JSON.stringify({ access_token: "tok-fresh", refresh_token: "rt", at: Date.now(), expires_in: 3600, who: "mike0123l098@gmail.com" }));
  const r1 = await send(w, "Groq kakunda verey models try cheyu");
  scoreState("S48a", "run-the-rest = exactly ONE reply", r1.length === 1);
  scoreReply("S48a", "Groq kakunda verey models try cheyu", r1, { must: /Groq vadilesi migatha 22 models start chesa/, maxLen: 200 });
  scoreState("S48b", "no allow card, no connect card, no lecture, no stop line", cards.length === 0 && !/pani naadhe/.test(r1.join(" ")) && !/stop chesthanu/.test(r1.join(" ")));
  const chain = JSON.parse((await w.kv.get(`setupchain:${USER}`)) || "{}");
  scoreState("S48c", "chain started with Groq EXCLUDED (22 providers)", Array.isArray(chain.providers) && chain.providers.length === 22 && !chain.providers.includes("groq") && dispatches.length >= 1);
  const chainAt = chain.at;
  const r2 = await send(w, "Fasst");
  scoreState("S48d", "'Fasst' -> one progress line, same chain, no new card", r2.length === 1 && /Setup progress/.test(r2.join(" ")) && cards.length === 0);
  const chain2 = JSON.parse((await w.kv.get(`setupchain:${USER}`)) || "{}");
  scoreState("S48e", "still the same chain (no duplicate start)", chain2.at === chainAt);
}

const byFlag = {};
for (const r of results) byFlag[r.flag] = (byFlag[r.flag] || 0) + 1;
console.log("\n==== WA PROCESS BATTERY ====");
console.log("wrong-reply flags:", JSON.stringify(byFlag));
console.log("total wrong replies:", results.filter(r => !r.flag.startsWith("STATE:")).length, "| state failures:", stateFails);
if (VERBOSE) for (const r of results) console.log("-", r.scn, r.flag, "|", r.userText, "=>", r.reply);
process.exit(results.length ? 1 : 0);
