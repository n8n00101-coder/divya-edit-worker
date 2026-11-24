/* videogen Worker tests (2026-11-24): the free-AI-video route,
 * end to end through the real Worker fetch handler with an in-memory
 * KV and stubbed Kaggle/GitHub APIs (same harness shape as
 * kaggleworkertest.mjs).
 *
 * Covers: POST /api/videogen —
 *   no Kaggle connected -> 400 BEFORE any charge or dispatch;
 *   empty prompt -> 400;
 *   happy path -> TOK.COST.video_create (100000) drawn from the
 *     weekly bucket, job record {mode:"videogen", prompt, to},
 *     edit.yml dispatched, spend recorded against the job;
 *   dispatch failure -> 502 and the spend refunded bucket-exact;
 *   insufficient balance -> 429, no job, no dispatch.
 *
 * Run: node videogentest.mjs
 */
import { pathToFileURL } from "node:url";
import path from "node:path";

const HERE = path.dirname(new URL(import.meta.url).pathname);
const NUM = "919999999999";
const TOKEN = "b".repeat(48); // appAuth requires 48 hex chars
const KUSER = "gooduser";
const KKEY = "0123456789abcdef0123456789abcdef";

let fails = 0;
function check(cond, msg) {
  console.log((cond ? "PASS " : "FAIL ") + msg);
  if (!cond) fails++;
}

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

const ghCalls = [];
let ghStatus = 204;
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
    return new Response(null, { status: ghStatus });
  }
  return new Response("stub-404", { status: 404 });
};

const kek = Buffer.from(crypto.getRandomValues(new Uint8Array(32))).toString("base64");
const env = {
  KV, APP_KEK: kek, RUNNER_KEY: "test-runner", GH_TOKEN: "ghp_testtoken",
  GH_REPO: "owner/repo", OWNERS: "910000000000", FRIENDS: "910000000001",
  GROQ_KEY: "", WA_TOKEN: "", PHONE_ID: "",
};
const ctx = { waitUntil() {}, passThroughOnException() {} };
// A regular account user (email/password account session, phone NOT in
// OWNERS/FRIENDS): appAuth accepts the session, but tokSpend does real
// bucket accounting for them — an owner/friend session would be
// "unlimited" and could never prove the charge.
store.set("acct:u1", JSON.stringify({ uid: "u1", name: "Test User", email: "t@example.test", phone: NUM, pwv: 1, created: Date.now() }));
store.set(`sess:${TOKEN}`, "a:u1:1");

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

const istWeek = () => { const d = new Date(Date.now() + 19800000); const day = (d.getUTCDay() + 6) % 7; d.setUTCDate(d.getUTCDate() - day); return d.toISOString().slice(0, 10); };
const weekKey = () => `tokw:${NUM}:${istWeek()}`;
const weekSpent = () => parseInt(store.get(weekKey()) || "0", 10);

// ---- no Kaggle connected: refused before charge/dispatch -----------
let r = await call("POST", "/api/videogen", { prompt: "a cat in a garden" });
check(r.status === 400 && /Kaggle/.test(r.json?.error || ""), "no Kaggle connected -> 400 naming Kaggle");
check(weekSpent() === 0 && ghCalls.length === 0, "no-Kaggle refusal: no charge, no dispatch");

// ---- connect Kaggle (the v84 two-field card) ------------------------
r = await call("POST", "/api/keys/kaggle", { username: KUSER, key: KKEY, consent: true });
check(r.status === 200 && r.json?.ok === true, "kaggle connect works (prereq)");

// ---- empty prompt ----------------------------------------------------
r = await call("POST", "/api/videogen", { prompt: "   " });
check(r.status === 400, "empty prompt -> 400");
check(weekSpent() === 0 && ghCalls.length === 0, "empty prompt: no charge, no dispatch");

// ---- happy path --------------------------------------------------------
r = await call("POST", "/api/videogen", { prompt: "a cat walking in a sunny garden" });
check(r.status === 200 && r.json?.ok === true && !!r.json?.job, "videogen creates a job");
const jobId = r.json?.job;
const jrec = JSON.parse(store.get(`job:${jobId}`) || "{}");
check(jrec.mode === "videogen" && jrec.prompt === "a cat walking in a sunny garden" && jrec.to === NUM,
  "job record carries mode + prompt + owner");
check(ghCalls.some(u => u.includes("/actions/workflows/edit.yml/dispatches")), "edit.yml dispatched");
check(weekSpent() === 100000, "charged exactly TOK.COST.video_create (100000) from weekly");
check(!!store.get(`spend:${jobId}`), "spend recorded against the job (v51 discipline)");
check(store.get(`jobown:${jobId}`) === NUM, "jobown registered");

// ---- dispatch failure refunds ------------------------------------------
ghStatus = 500;
const before = weekSpent();
r = await call("POST", "/api/videogen", { prompt: "a second cat" });
check(r.status === 502, "dispatch failure -> 502");
check(weekSpent() === before, "dispatch failure: spend refunded bucket-exact");
ghStatus = 204;

// ---- insufficient balance ----------------------------------------------
store.set(weekKey(), "450000"); // weekLeft = 50000 < 100000, no pool/plan
r = await call("POST", "/api/videogen", { prompt: "a third cat" });
check(r.status === 429 && r.json?.quota === true, "insufficient balance -> 429 quota");
check(!store.has(`job:${r.json?.job}`), "429 path creates no job record");

console.log(fails ? `\n${fails} FAILURES` : "\nALL PASS");
process.exit(fails ? 1 : 0);
