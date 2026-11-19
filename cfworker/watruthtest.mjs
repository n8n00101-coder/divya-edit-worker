// v120 WhatsApp SELF-KNOWLEDGE PARITY battery (Ajju's live phone
// screenshot, 2026-11-19 16:48 IST): drives the REAL Worker /webhook
// (WhatsApp) and /api/chat (app) handlers with the EXACT screenshot
// lines, in order, plus the pending-ask controls. Pre-fix failures:
// (1) "Are you connected with cloude code" on WA fell to the brain,
// which invented a "cloud-code platform" + a Setup grant path;
// (2) a bare "Ledha" after that factual answer got "Okay, no changes
// then." although no change was pending; (3) the Tenglish repeat got
// the parroted "cloud-code platform" wording, truth sheet missing.
// Post-fix: both surfaces answer Claude questions from the one truth
// sheet (not connected; own free-model pool + own keys + own server;
// engine TRAINED on Claude Code's method, not connected), and a bare
// negation is an answer ONLY to a real pending ask in the record.
// Run: node watruthtest.mjs [--verbose]. Exit 0 = all expectations met.
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
    if (u.includes("/media")) return Response.json({ id: "media_test_1" });
    let body = {}; try { body = JSON.parse(opts.body || "{}"); } catch {}
    if (body.type === "text" && body.text && body.text.body) outbox.push({ to: body.to, text: body.text.body });
    return Response.json({ messages: [{ id: "wamid.test" }] });
  }
  if (u.includes("api.groq.com") && u.includes("/models")) return Response.json({ data: CHAT_MODELS.map(id => ({ id, active: true })) });
  if (u.includes("api.groq.com") && u.includes("/chat/completions")) {
    let msgs = []; try { msgs = JSON.parse(opts.body || "{}").messages || []; } catch {}
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
    GH_TOKEN: ["gh", "test"].join("-"), RUNNER_KEY: "rk-test",
    APP_KEK: Buffer.alloc(32, 7).toString("base64"), FORWARD_SECRET: "",
  };
  outbox = []; dispatches = [];
  return { kv, env };
}
async function drain(ctx) { const ps = ctx._p || []; for (let i = 0; i < 6; i++) { const q = ps.splice(0); if (!q.length) break; await Promise.all(q); } }
function mkCtx() { const c = { _p: [], waitUntil(p) { c._p.push(Promise.resolve(p)); } }; return c; }
async function send(world, text) {
  const before = outbox.length;
  const ctx = mkCtx();
  const body = { entry: [{ changes: [{ field: "messages", value: { messages: [{ from: USER, id: "m" + (++seq), type: "text", text: { body: text } }] } }] }] };
  const req = new Request("https://worker.test/webhook", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
  await worker.fetch(req, world.env, ctx);
  await drain(ctx);
  return outbox.slice(before).filter(o => o.to === USER).map(o => o.text);
}
async function appChat(world, text, lang = "te") {
  await world.kv.put("sess:" + "a".repeat(48), USER);
  const ctx = mkCtx();
  const req = new Request("https://worker.test/api/chat", { method: "POST", headers: { "content-type": "application/json", authorization: "Bearer " + "a".repeat(48) }, body: JSON.stringify({ text, lang }) });
  const res = await worker.fetch(req, world.env, ctx);
  await drain(ctx);
  return res.json().catch(() => ({}));
}

const fails = [];
let checks = 0;
function check(scn, cond, label, got) {
  checks++;
  if (!cond) fails.push(`[${scn}] ${label}${got !== undefined ? " — got: " + String(got).slice(0, 220) : ""}`);
  if (VERBOSE || !cond) console.log(`${cond ? "ok   " : "FAIL "} [${scn}] ${label}${cond ? "" : " — got: " + String(got).slice(0, 220)}`);
}
const NO_CHANGES_RX = /no changes/i;
const GRANT_RX = /grant access/i;
const PLATFORM_RX = /cloud-code platform|cloud code platform/i;

// ---- S1: the screenshot itself, exact lines, in order (WhatsApp) ----
{
  const w = makeWorld();
  const r1 = await send(w, "Hlo");
  check("S1", r1.length >= 1, "Hlo gets a reply", r1.join("\n"));
  check("S1", !(await w.kv.get(`busy:${USER}`)) && !(await w.kv.get(`appjob:${USER}`)), "Hlo starts no job");

  const r2 = (await send(w, "Are you connected with cloude code")).join("\n");
  check("S1", /not connected to Claude/i.test(r2), "Q1: says NOT connected to Claude", r2);
  check("S1", /own free-model pool/i.test(r2), "Q1: own free-model pool", r2);
  check("S1", /own API keys/i.test(r2), "Q1: own API keys", r2);
  check("S1", /trained on Claude Code/i.test(r2), "Q1: trained-on-Claude-Code fact", r2);
  check("S1", !GRANT_RX.test(r2), "Q1: NO invented Setup grant path", r2);
  check("S1", !PLATFORM_RX.test(r2), "Q1: NO 'cloud-code platform' parrot", r2);

  const r3 = (await send(w, "Ledha")).join("\n");
  check("S1", r3.length > 0, "Ledha gets a reply", r3);
  check("S1", !NO_CHANGES_RX.test(r3), "Ledha: NEVER 'no changes'", r3);
  check("S1", /claude/i.test(r3), "Ledha: stays on the Claude topic", r3);
  check("S1", /not connected|connect avvaledhu/i.test(r3), "Ledha: confirms the fact plainly", r3);

  const r4 = (await send(w, "Cloude code neeku conncet avvaledha")).join("\n");
  check("S1", /connect avvaledhu/i.test(r4), "Q2: truth sheet again (not connected)", r4);
  check("S1", /train ayyindhi/i.test(r4), "Q2: trained fact present", r4);
  check("S1", /own free-model pool/i.test(r4), "Q2: own pool present", r4);
  check("S1", !PLATFORM_RX.test(r4) && !GRANT_RX.test(r4), "Q2: no parrot / no grant path", r4);
  check("S1", !(await w.kv.get(`busy:${USER}`)) && !(await w.kv.get(`appjob:${USER}`)), "whole exchange started no job");
}

// ---- S2: WA — a REAL pending setup allow ask: "Ledha" declines it ----
{
  const w = makeWorld();
  await w.kv.put(`wasetupask:${USER}`, JSON.stringify({ at: Date.now() })); // the exact record waSetupRespond arms
  const r = (await send(w, "Ledha")).join("\n");
  check("S2", /setup start cheyyaledhu/i.test(r), "pending setup ask: Ledha declines THAT ask", r);
  check("S2", !(await w.kv.get(`wasetupask:${USER}`)), "pending setup ask is cleared");
  check("S2", !NO_CHANGES_RX.test(r), "no 'no changes' wording", r);
}

// ---- S3: WA — a pending upload confirmation: "Ledha" declines it ----
{
  const w = makeWorld();
  await w.kv.put(`uppend:${USER}`, JSON.stringify({ num: 1, job: "jobx", targets: ["yt"], copy: { yt_title: "T" }, privacy: "unlisted", at: Date.now() }));
  const r = (await send(w, "Ledha")).join("\n");
  check("S3", /upload cheyyaledhu/i.test(r), "pending upload: Ledha declines the upload", r);
  check("S3", !(await w.kv.get(`uppend:${USER}`)), "pending upload is cleared");
}

// ---- S4: the same lines through the APP chat path — same truth ----
{
  const w = makeWorld();
  const a0 = await appChat(w, "Hlo");
  check("S4", !!a0.reply && !a0.video_started, "app Hlo: reply, no video started", JSON.stringify(a0).slice(0, 200));
  const a1 = String((await appChat(w, "Are you connected with cloude code")).reply || "");
  check("S4", /connect avvaledhu/i.test(a1), "app Q1: not connected (truth sheet)", a1);
  check("S4", /own free-model pool/i.test(a1) && /train ayyindhi/i.test(a1), "app Q1: own pool + trained fact", a1);
  check("S4", !GRANT_RX.test(a1) && !PLATFORM_RX.test(a1), "app Q1: no grant path / no parrot", a1);
  const a2 = String((await appChat(w, "Ledha")).reply || "");
  check("S4", !NO_CHANGES_RX.test(a2), "app Ledha: NEVER 'no changes'", a2);
  check("S4", /claude/i.test(a2) && /connect avvaledhu/i.test(a2), "app Ledha: confirms the Claude fact", a2);
  const a3 = String((await appChat(w, "Cloude code neeku conncet avvaledha")).reply || "");
  check("S4", /connect avvaledhu/i.test(a3) && /train ayyindhi/i.test(a3), "app Q2: truth sheet again", a3);
}

// ---- S5: app — a pending upload confirmation: "Ledha" declines it ----
{
  const w = makeWorld();
  await w.kv.put(`uppend:${USER}`, JSON.stringify({ num: 1, job: "jobx", targets: ["yt"], copy: { yt_title: "T" }, privacy: "unlisted", at: Date.now() }));
  const a = String((await appChat(w, "Ledha")).reply || "");
  check("S5", /upload cheyyaledhu/i.test(a), "app pending upload: Ledha declines the upload", a);
  check("S5", !(await w.kv.get(`uppend:${USER}`)), "app pending upload is cleared");
}

// ---- S6: WA — bare negation after an UNRELATED exchange: clarify ----
{
  const w = makeWorld();
  await send(w, "Space gurinchi cheppu"); // brain-stub small talk; no fact about Claude, nothing pending
  const r = (await send(w, "Ledha")).join("\n");
  check("S6", !NO_CHANGES_RX.test(r), "unrelated Ledha: NEVER 'no changes'", r);
  check("S6", /ardham kaaledhu/i.test(r), "unrelated Ledha: asks what the 'no' refers to", r);
}

console.log(`\nwatruthtest: ${checks - fails.length}/${checks} checks passed`);
if (fails.length) { console.log("FAILURES:\n" + fails.map(f => " - " + f).join("\n")); process.exit(1); }
