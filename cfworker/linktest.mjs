// Shadow programme Wave 2 battery (C-01 identity + model R1–R4):
// drives the REAL Worker /webhook + /internal/scout with stub KV and
// stub network. Proves, against the live code paths:
//  L1 (R2) a key sealed under the user's OTHER number answers their
//      chat when link: records join the two keyspaces;
//  L2 (R1) a keyless user's chat is answered by the shared OpenRouter
//      tier riding an owner's sealed key (env.OPENROUTER_KEY unset —
//      the live bindings state), not by nothing;
//  L3 (R3+R4) a forced scout sweep finds the owner's Gemini key under
//      a LINKED uid and adds a Gemini model (per-provider cap);
//  L4 (C-06) the WA keys question counts the linked keyspace's key.
// Pre-fix (v115-era tree): L1/L2 end at the brain-down line, L3 skips
// Gemini with "no owner test key", L4 reports 0 keys.
// Run: node linktest.mjs
import { readFileSync, writeFileSync } from "fs";
import { pathToFileURL } from "url";

const SRC = readFileSync(new URL("./divya.js", import.meta.url), "utf8");
writeFileSync("/tmp/_divya_link_under_test.mjs", SRC);
const worker = (await import(pathToFileURL("/tmp/_divya_link_under_test.mjs").href)).default;

class KVStub {
  constructor() { this.m = new Map(); }
  async get(k, opts) {
    const v = this.m.has(k) ? this.m.get(k) : null;
    if (v == null) return null;
    const t = typeof opts === "string" ? opts : (opts && opts.type) || "text";
    if (t === "json") { try { return JSON.parse(v); } catch { return null; } }
    return v;
  }
  async put(k, v) { this.m.set(k, typeof v === "string" ? v : String(v)); }
  async delete(k) { this.m.delete(k); }
  async list({ prefix = "", limit = 1000 } = {}) { return { keys: [...this.m.keys()].filter(k => k.startsWith(prefix)).slice(0, limit).map(name => ({ name })), list_complete: true }; }
  async mget(keys) { const o = {}; for (const k of keys) o[k] = this.m.has(k) ? this.m.get(k) : null; return o; }
}

const outbox = [];
globalThis.fetch = async (url, opts = {}) => {
  const u = String(url);
  if (u.includes("graph.facebook.com")) {
    try { const b = JSON.parse(opts.body || "{}"); outbox.push({ to: b.to, text: (b.text && b.text.body) || "" }); } catch {}
    return Response.json({ messages: [{ id: "wamid.x" }] });
  }
  if (u.includes("api.groq.com")) return Response.json({ error: "down" }, { status: 500 });
  if (u.includes("openrouter.ai/api/v1/chat/completions")) {
    const auth = (opts.headers && (opts.headers.Authorization || opts.headers.authorization)) || "";
    if (auth === "Bearer sk-or-test-key") return Response.json({ choices: [{ message: { content: "LINKTEST ANSWER" } }] });
    return Response.json({ error: "bad key" }, { status: 401 });
  }
  if (u.includes("openrouter.ai/api/v1/models")) return Response.json({ data: [{ id: "openai/gpt-oss-120b:free" }] });
  if (u.includes("generativelanguage.googleapis.com/v1beta/models?")) {
    return Response.json({ models: [{ name: "models/gemini-2.5-flash-lite", supportedGenerationMethods: ["generateContent"] }] });
  }
  if (u.includes(":generateContent")) {
    const body = JSON.parse(opts.body || "{}");
    const asked = (((body.contents || [])[0] || {}).parts || []).map(p => p.text || "").join(" ");
    const m = asked.match(/token and nothing else: (\S+)/);
    return Response.json({ candidates: [{ content: { parts: [{ text: m ? m[1] : "?" }] } }] });
  }
  return new Response("stub-404", { status: 404 });
};

const KEK = Buffer.alloc(32, 7).toString("base64");
async function seal(n, prov, plain) {
  const key = await crypto.subtle.importKey("raw", Buffer.from(KEK, "base64"), "AES-GCM", false, ["encrypt"]);
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ct = await crypto.subtle.encrypt({ name: "AES-GCM", iv, additionalData: new TextEncoder().encode(`${n}:${prov}`) }, key, new TextEncoder().encode(plain));
  return Buffer.from(iv).toString("base64") + "." + Buffer.from(ct).toString("base64");
}

const A = "917993610173", B = "919951950173", C = "919999999999", G = "u_gemuid";
const kv = new KVStub();
const env = { KV: kv, OWNERS: B, FRIENDS: `${A},${C}`, GROQ_KEY: "gk-shared-dead", WA_TOKEN: "wa-test", PHONE_ID: "1555000111", APP_KEK: KEK, RUNNER_KEY: "rk-test", GH_TOKEN: "" };
const ctxOf = ps => ({ waitUntil(p) { ps.push(Promise.resolve(p)); }, passThroughOnException() {} });
let seq = 0;
async function send(from, text) {
  const before = outbox.length;
  const ps = [];
  const body = { entry: [{ changes: [{ field: "messages", value: { messages: [{ from, id: "m" + (++seq), type: "text", text: { body: text } }] } }] }] };
  await worker.fetch(new Request("https://worker.test/webhook", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) }), env, ctxOf(ps));
  for (let i = 0; i < 6; i++) { const cur = ps.splice(0); if (!cur.length) break; await Promise.all(cur); }
  return outbox.slice(before).filter(o => o.to === from).map(o => o.text);
}

// Seed: Ajju's two numbers + the Gemini-holding uid in ONE link set
// (the shape linkIdentities writes: the full union under every member).
const setAll = JSON.stringify([A, B, G]);
await kv.put(`link:${A}`, setAll);
await kv.put(`link:${B}`, setAll);
await kv.put(`link:${G}`, setAll);
await kv.put(`ukey:${B}:openrouter`, JSON.stringify({ ct: await seal(B, "openrouter", "sk-or-test-key"), ok: true, at: Date.now(), source: "divya" }));
// The owner's Gemini key lives under the linked uid only.
await kv.put(`ukey:${G}:gemini`, JSON.stringify({ ct: await seal(G, "gemini", "gem-test-key"), ok: true, at: Date.now(), source: "divya" }));

let pass = 0, fail = 0;
const T = (name, cond, extra) => { if (cond) { pass++; console.log("PASS", name); } else { fail++; console.log("FAIL", name, extra ? "— " + extra : ""); } };

const r1 = await send(A, "What is the capital of France?");
T("L1 linked own key answers (R2)", r1.some(t => t.includes("LINKTEST ANSWER")), JSON.stringify(r1).slice(0, 200));

const r2 = await send(C, "What is the capital of France?");
T("L2 shared tier rides owner's sealed key (R1)", r2.some(t => t.includes("LINKTEST ANSWER")), JSON.stringify(r2).slice(0, 200));

const r4 = await send(A, "Naa daggara enni API keys unnayi?");
T("L4 keys question counts linked keyspaces (C-06)", r4.some(t => /1\s*API keys|OpenRouter/i.test(t) && !/levu/.test(t)), JSON.stringify(r4).slice(0, 200));

const ps3 = [];
const sres = await worker.fetch(new Request("https://worker.test/internal/scout", { method: "POST", headers: { "content-type": "application/json", "x-runner-key": "rk-test" }, body: "{}" }), env, ctxOf(ps3));
const sj = await sres.json().catch(() => ({}));
const addedGem = ((sj.sweep || {}).added || []).some(a => a.provider === "gemini" && a.model === "gemini-2.5-flash-lite");
T("L3 scout adds a Gemini model via the linked owner key (R3+R4)", sres.status === 200 && addedGem, JSON.stringify(sj.sweep || {}).slice(0, 300));
const models = JSON.parse((await kv.get("scout:models")) || "{}");
T("L3b scout:models now holds the Gemini model", (models.gemini || []).includes("gemini-2.5-flash-lite"));

console.log(`\nlinktest: ${pass} pass, ${fail} fail`);
process.exit(fail ? 1 : 0);
