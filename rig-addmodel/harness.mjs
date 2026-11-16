// v100 ADD-MODEL PROVIDER harness — runs the REAL merged Worker in Node
// with a Map-backed KV and stubbed provider endpoints. Proves R54:
// a bare PROVIDER name ("cerebras") + key is enough — Julie enumerates,
// ranks (free first), tests, seals, saves, and names the model.
// Usage: node harness.mjs <worker-file.mjs>
import { copyFileSync } from "node:fs";

const srcPath = process.argv[2];
if (!srcPath) { console.error("usage: node harness.mjs <worker.mjs>"); process.exit(2); }
copyFileSync(srcPath, new URL("./worker.mjs", import.meta.url));
const worker = (await import("./worker.mjs")).default;

// ---------- KV stub ----------
const map = new Map();
const KV = {
  async get(k, type) { const v = map.has(k) ? map.get(k) : null; if (v === null) return null; if (type === "arrayBuffer") return v instanceof Uint8Array ? v.buffer.slice(v.byteOffset, v.byteOffset + v.byteLength) : new TextEncoder().encode(String(v)).buffer; return v instanceof Uint8Array ? new TextDecoder().decode(v) : v; },
  async put(k, v) { map.set(k, String(v)); },
  async delete(k) { map.delete(k); },
  async list({ prefix } = {}) { return { keys: [...map.keys()].filter(k => !prefix || k.startsWith(prefix)).map(name => ({ name })) }; },
};
const env = { KV, APP_KEK: Buffer.alloc(32, 7).toString("base64"), GOOGLE_CLIENT_ID: "cid", GOOGLE_CLIENT_SECRET: "csecret", OWNERS: "", FRIENDS: "" };

// ---------- provider fetch stub ----------
const GOOD_CSK = "csk-GOODKEYaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
const BAD_CSK = "csk-BADKEYbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
const GSK = "gsk_GOODKEYaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
const CEREBRAS_MODELS = ["gpt-oss-120b", "llama-3.3-70b", "qwen-3-32b", "llama3.1-8b", "embed-fake-1"];
const GROQ_MODELS = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "whisper-large-v3"];
const calls = [];
globalThis.fetch = async (url, opts = {}) => {
  const u = String(url);
  const auth = (opts.headers && (opts.headers.Authorization || opts.headers.authorization)) || "";
  let model = "";
  try { model = JSON.parse(opts.body || "{}").model || ""; } catch {}
  calls.push({ u, method: opts.method || "GET", auth, model });
  const J = (o, st = 200) => new Response(JSON.stringify(o), { status: st, headers: { "content-type": "application/json" } });
  if (u === "https://api.cerebras.ai/v1/models") {
    if (auth === "Bearer " + BAD_CSK) return J({ error: { message: "Invalid API key" } }, 401);
    if (auth === "Bearer " + GOOD_CSK) return J({ data: CEREBRAS_MODELS.map(id => ({ id })) });
    return J({ error: { message: "unauthorized" } }, 401);
  }
  if (u === "https://api.cerebras.ai/v1/chat/completions") {
    if (auth !== "Bearer " + GOOD_CSK) return J({ error: { message: "Invalid API key" } }, 401);
    if (CEREBRAS_MODELS.includes(model) && model !== "embed-fake-1") return J({ choices: [{ message: { content: "ok" } }] });
    return J({ error: { message: "model not found" } }, 400);
  }
  if (u === "https://api.groq.com/openai/v1/models") return J({ data: GROQ_MODELS.map(id => ({ id })) });
  if (u === "https://api.groq.com/openai/v1/chat/completions") {
    if (GROQ_MODELS.includes(model) && model !== "whisper-large-v3") return J({ choices: [{ message: { content: "ok" } }] });
    return J({ error: { message: "model not found" } }, 404);
  }
  return J({ error: "unstubbed " + u }, 404);
};

// ---------- helpers ----------
const ctx = { waitUntil(p) { this._p = p; } };
async function call(method, path, { token, body } = {}) {
  const req = new Request("https://divya-app.n8n00101.workers.dev" + path, {
    method, headers: { "content-type": "application/json", ...(token ? { authorization: "Bearer " + token } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  const res = await worker.fetch(req, env, ctx);
  const text = await res.text();
  let json = null; try { json = JSON.parse(text); } catch {}
  return { status: res.status, json, text };
}
let pass = 0, fail = 0;
const T = (name, cond, extra = "") => { if (cond) { pass++; console.log("PASS", name); } else { fail++; console.log("FAIL", name, extra); } };
async function signup(email) {
  const r = await call("POST", "/api/auth/signup", { body: { name: "T User", email, password: "Test!2345" } });
  if (!r.json?.token) throw new Error("signup failed " + r.text);
  return { token: r.json.token, n: "u_" + map.get(`em:${email}`) };
}
const savedModel = n => { const v = map.get(`umodel:${n}`); return v ? JSON.parse(v) : null; };
const sealedKey = n => map.get(`ukey:${n}:custom`) || null;

// ---------- 1. FORM: "cerebras" + good key -> enumerated, ranked, saved ----------
{
  const u = await signup("cerebras@example.com");
  const before = calls.length;
  const r = await call("POST", "/api/model/save", { token: u.token, body: { name: "cerebras", key: GOOD_CSK, consent: true } });
  T("1a save ok", r.status === 200 && r.json?.ok === true, r.text.slice(0, 300));
  T("1b who is Cerebras", r.json?.who === "Cerebras", JSON.stringify(r.json));
  T("1c strongest free model connected (gpt-oss-120b)", r.json?.model === "gpt-oss-120b", r.json?.model);
  T("1d also lists other usable models, embed filtered", Array.isArray(r.json?.also) && r.json.also.includes("llama-3.3-70b") && !r.json.also.includes("embed-fake-1"), JSON.stringify(r.json?.also));
  const mine = calls.slice(before);
  T("1e Julie called GET /models herself", mine.some(c => c.u === "https://api.cerebras.ai/v1/models" && c.method === "GET"));
  T("1f ONE real chat test call with the picked model", mine.filter(c => c.u.endsWith("/chat/completions")).length === 1 && mine.find(c => c.u.endsWith("/chat/completions"))?.model === "gpt-oss-120b", JSON.stringify(mine));
  const rec = savedModel(u.n);
  T("1g umodel saved with provider base", !!rec && rec.model === "gpt-oss-120b" && rec.base === "https://api.cerebras.ai/v1" && rec.who === "Cerebras", JSON.stringify(rec));
  const sk = sealedKey(u.n);
  T("1h key sealed (stored, never in plain text)", !!sk && !sk.includes(GOOD_CSK));
  const got = await call("GET", "/api/model", { token: u.token });
  T("1i GET /api/model shows the connected model", got.json?.model?.model === "gpt-oss-120b" && got.json?.model?.who === "Cerebras", JSON.stringify(got.json));
}

// ---------- 2. FORM: "cerebras" + BAD key -> provider named as rejecting, nothing saved ----------
{
  const u = await signup("badkey@example.com");
  const r = await call("POST", "/api/model/save", { token: u.token, body: { name: "cerebras", key: BAD_CSK, consent: true } });
  T("2a save refused", r.status === 400 && r.json?.ok === false, r.text.slice(0, 300));
  T("2b kind is auth", r.json?.kind === "auth", JSON.stringify(r.json));
  T("2c reply names Cerebras as the rejector", /Cerebras/.test(r.json?.error || "") && /reject/i.test(r.json?.error || ""), r.json?.error);
  T("2d nothing saved", !savedModel(u.n) && !sealedKey(u.n));
}

// ---------- 3. FORM regression: known Groq model id resolves exactly as before ----------
{
  const u = await signup("groqid@example.com");
  const r = await call("POST", "/api/model/save", { token: u.token, body: { name: "llama-3.3-70b-versatile", key: GSK, consent: true } });
  T("3a save ok", r.status === 200 && r.json?.ok === true, r.text.slice(0, 300));
  T("3b exact model + Groq", r.json?.model === "llama-3.3-70b-versatile" && r.json?.who === "Groq", JSON.stringify(r.json));
}

// ---------- 4. FORM: provider name "groq" -> enumerates and picks the flagship ----------
{
  const u = await signup("groqprov@example.com");
  const r = await call("POST", "/api/model/save", { token: u.token, body: { name: "groq", key: GSK, consent: true } });
  T("4a save ok", r.status === 200 && r.json?.ok === true, r.text.slice(0, 300));
  T("4b flagship picked, whisper filtered", r.json?.model === "llama-3.3-70b-versatile", r.json?.model);
}

// ---------- 5. FORM: unknown nonsense name -> asks AND offers the Automate path ----------
{
  const u = await signup("unknown@example.com");
  const r = await call("POST", "/api/model/save", { token: u.token, body: { name: "frobnicate", key: "zzzzzzzzzzzzzzzzzzzzzzzz", consent: true } });
  T("5a refused as resolve", r.status === 400 && r.json?.kind === "resolve", r.text.slice(0, 300));
  T("5b offers Automate path", /Automate/.test(r.json?.error || "") && /setup cheyu/i.test(r.json?.error || ""), r.json?.error);
  T("5c old bounce copy gone", !/couldn't tell which provider/i.test(r.json?.error || ""));
  T("5d nothing saved", !savedModel(u.n) && !sealedKey(u.n));
}

// ---------- 6. CHAT: "cerebras <key>" behaves identically + key redacted from history ----------
{
  const u = await signup("chatuser@example.com");
  const r = await call("POST", "/api/chat", { token: u.token, body: { text: "cerebras " + GOOD_CSK } });
  T("6a chat reply names the connected model", /gpt-oss-120b/.test(r.json?.reply || ""), JSON.stringify(r.json).slice(0, 300));
  T("6b model saved from chat too", savedModel(u.n)?.model === "gpt-oss-120b", JSON.stringify(savedModel(u.n)));
  let leak = false;
  for (const [k, v] of map) if (String(v).includes(GOOD_CSK) && !String(k).startsWith("ukey:")) leak = true;
  const sealedOk = !String(sealedKey(u.n) || "").includes(GOOD_CSK);
  T("6c raw key appears NOWHERE outside the sealed slot", !leak && sealedOk);
}

// ---------- 7. CHAT: bad key -> clear provider-rejection reply, nothing saved ----------
{
  const u = await signup("chatbad@example.com");
  const r = await call("POST", "/api/chat", { token: u.token, body: { text: "cerebras " + BAD_CSK } });
  T("7a chat reply names Cerebras + rejection", /Cerebras/.test(r.json?.reply || "") && /reject/i.test(r.json?.reply || ""), JSON.stringify(r.json).slice(0, 300));
  T("7b nothing saved", !savedModel(u.n) && !sealedKey(u.n));
}

console.log(`\n== ${pass} passed, ${fail} failed ==`);
process.exit(fail ? 1 : 0);
