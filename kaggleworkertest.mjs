/* v84 Worker tests: the Kaggle compute provider, end to end through
 * the real Worker fetch handler with an in-memory KV and a stubbed
 * Kaggle/GitHub API (no STATE binding -> wrapEnv is a no-op, exactly
 * the documented test configuration).
 *
 * Covers: keys/kaggle connect (consent gate, bad creds rejected, good
 * creds sealed — ciphertext never contains the key), status route
 * (metadata only, key never leaves), keys/test round-trip through the
 * sealed record, keys/save pointer for the two-field provider, the
 * keys list, keys/delete, the /job runner channel (owner's creds
 * unsealed for the runner ONLY; a user without Kaggle gets null), and
 * the voicebatch job creation route.
 *
 * Run: node kaggleworkertest.mjs
 */
import { pathToFileURL } from "node:url";
import path from "node:path";

const HERE = path.dirname(new URL(import.meta.url).pathname);
const NUM = "919999999999";
const NUM2 = "918888888888";
const TOKEN = "a".repeat(48); // appAuth requires 48 hex chars
const KUSER = "gooduser";
const KKEY = "0123456789abcdef0123456789abcdef";

let fails = 0;
function check(cond, msg) {
  console.log((cond ? "PASS " : "FAIL ") + msg);
  if (!cond) fails++;
}

// ---- in-memory KV -------------------------------------------------
const store = new Map();
const KV = {
  async get(k, opts) {
    const v = store.has(k) ? store.get(k) : null;
    if (v == null) return null;
    const type = typeof opts === "string" ? opts : (opts && opts.type) || "text";
    if (type === "json") { try { return JSON.parse(v); } catch { return null; } }
    if (type === "arrayBuffer") return new TextEncoder().encode(v).buffer;
    return v;
  },
  async put(k, v) { store.set(k, typeof v === "string" ? v : String(v)); },
  async delete(k) { store.delete(k); },
  async list() { return { keys: [...store.keys()].map(name => ({ name })) }; },
};

// ---- stubbed network ----------------------------------------------
const ghCalls = [];
const realFetch = globalThis.fetch;
globalThis.fetch = async (url, opts = {}) => {
  const u = String(url);
  if (u.includes("kaggle.com/api/v1/datasets/list")) {
    const want = "Basic " + Buffer.from(`${KUSER}:${KKEY}`).toString("base64");
    return (opts.headers && opts.headers.Authorization) === want
      ? new Response("[]", { status: 200, headers: { "content-type": "application/json" } })
      : new Response(JSON.stringify({ message: "unauthorized" }), { status: 401 });
  }
  if (u.includes("api.github.com")) {
    ghCalls.push(u);
    return new Response(null, { status: 204 });
  }
  return new Response("stub-404", { status: 404 });
};

const kek = Buffer.from(crypto.getRandomValues(new Uint8Array(32))).toString("base64");
const env = {
  KV, APP_KEK: kek, RUNNER_KEY: "test-runner", GH_TOKEN: "ghp_testtoken",
  GH_REPO: "owner/repo", OWNERS: NUM, FRIENDS: "", GROQ_KEY: "",
  WA_TOKEN: "", PHONE_ID: "",
};
const ctx = { waitUntil() {}, passThroughOnException() {} };
store.set(`sess:${TOKEN}`, NUM);

const worker = (await import(pathToFileURL(path.join(HERE, "cfworker", "divya.js")).href)).default;

async function call(method, p, body, headers = {}) {
  const req = new Request("https://divya.test" + p, {
    method,
    headers: { "content-type": "application/json", authorization: `Bearer ${TOKEN}`, ...headers },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const r = await worker.fetch(req, env, ctx);
  const text = await r.text();
  let json = null;
  try { json = JSON.parse(text); } catch {}
  return { status: r.status, json, text };
}

// ---- keys/kaggle connect ------------------------------------------
let r = await call("POST", "/api/keys/kaggle", { username: KUSER, key: KKEY });
check(r.status === 400, "connect without consent is refused");

r = await call("POST", "/api/keys/kaggle", { username: KUSER, key: "f".repeat(32), consent: true });
check(r.status === 400 && !store.has(`ukey:${NUM}:kaggle`), "bad Kaggle credentials are rejected, nothing stored");

r = await call("POST", "/api/keys/kaggle", { username: KUSER, key: KKEY, consent: true });
check(r.status === 200 && r.json && r.json.ok === true && r.json.who === KUSER, "good credentials connect");
const recRaw = store.get(`ukey:${NUM}:kaggle`) || "";
const rec = JSON.parse(recRaw || "{}");
check(!!rec.ct && !recRaw.includes(KKEY) && rec.who === KUSER && rec.source === "manual" && rec.ok === true,
  "record is sealed (no plaintext key), labelled manual, marked ok");

r = await call("GET", "/api/keys/kaggle");
check(r.json && r.json.set === true && r.json.who === KUSER && !r.text.includes(KKEY),
  "status route: set + username only, key never returned");

r = await call("POST", "/api/keys/test", { provider: "kaggle" });
check(r.json && r.json.ok === true, "keys/test round-trips the sealed pair");

r = await call("POST", "/api/keys/save", { provider: "kaggle", key: KKEY, consent: true });
check(r.status === 400 && /Kaggle card/.test(r.json?.error || ""), "keys/save points kaggle to its two-field card");

r = await call("GET", "/api/keys");
const kp = (r.json?.providers || []).find(p => p.id === "kaggle");
check(!!kp && kp.set === true && kp.ok === true, "keys list includes kaggle as set + working");

// ---- /job runner channel ------------------------------------------
store.set("job:jobtest1", JSON.stringify({ mode: "voicebatch", lines: ["a"], lang: "en", to: NUM }));
store.set("job:jobtest2", JSON.stringify({ mode: "voicebatch", lines: ["a"], lang: "en", to: NUM2 }));
async function jobFetch(job) {
  const req = new Request("https://divya.test/job", {
    method: "POST", headers: { "content-type": "application/json", "x-runner-key": "test-runner" },
    body: JSON.stringify({ job }),
  });
  const resp = await worker.fetch(req, env, ctx);
  return resp.json();
}
const j1 = await jobFetch("jobtest1");
check(j1.KAGGLE && j1.KAGGLE.user === KUSER && j1.KAGGLE.key === KKEY,
  "/job unseals the owner's kaggle creds for the runner channel");
check(j1.ENGINE_REPO === "n8n00101-coder/julie-ai-voice-engine" && j1.GH_TOKEN === "ghp_testtoken",
  "/job carries the Actions route token + engine repo");
const j2 = await jobFetch("jobtest2");
check(j2.KAGGLE === null, "/job gives KAGGLE null to a user who never connected");

// ---- voicebatch creation ------------------------------------------
ghCalls.length = 0;
r = await call("POST", "/api/voicebatch", { lines: ["hello world", "second line"], lang: "en" });
check(r.json && r.json.ok === true && !!r.json.job, "voicebatch route creates a job");
const jrec = JSON.parse(store.get(`job:${r.json?.job}`) || "{}");
check(jrec.mode === "voicebatch" && jrec.lines.length === 2 && jrec.to === NUM,
  "voicebatch job record carries mode + lines + owner");
check(ghCalls.some(u => u.includes("/actions/workflows/edit.yml/dispatches")),
  "voicebatch dispatch went to edit.yml");
r = await call("POST", "/api/voicebatch", { lines: [], lang: "en" });
check(r.status === 400, "voicebatch with no lines is refused");

// ---- delete ---------------------------------------------------------
r = await call("POST", "/api/keys/delete", { provider: "kaggle" });
check(r.json && r.json.ok === true && !store.has(`ukey:${NUM}:kaggle`), "keys/delete removes the kaggle record");
r = await call("GET", "/api/keys/kaggle");
check(r.json && r.json.set === false, "status route reports not-set after delete");

globalThis.fetch = realFetch;
console.log(fails ? `\n${fails} FAILURES` : "\nALL PASS");
process.exit(fails ? 1 : 0);
