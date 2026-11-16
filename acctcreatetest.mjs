// v103 account-creation Worker rig: profile-serialization guard +
// AWAITING_USER ask storage / chat routing, in the kaggleworkertest
// style (in-memory KV, stubbed fetch, real fetch handler).
//
// Proves:
//  - an active profile-mode setup chain REFUSES a browse start, and
//    an active browse job REFUSES a profile-mode setup/start — while
//    an explicitly ephemeral chain is exempt (the guard, both ways);
//  - a runner progress post with an awaiting block stores it on the
//    job record and appends the ask to the user's chat history
//    EXACTLY ONCE per ask (heartbeat re-posts don't duplicate it; a
//    re-ask with a new id appends again);
//  - a code-shaped chat reply is delivered to the waiting job as
//    userInput, and Julie's confirmation never echoes the code;
//  - a non-code chat message is NOT consumed by the ask;
//  - setup/status never exposes userInput or the delivered code;
//  - setup/answer validates by kind (bad phone value rejected).
import path from "node:path";
import { pathToFileURL } from "node:url";

const HERE = path.dirname(new URL(import.meta.url).pathname);
let fails = 0;
function check(cond, label) {
  console.log((cond ? "PASS " : "FAIL ") + label);
  if (!cond) fails++;
}

const store = new Map();
const KV = {
  async get(k) { return store.has(k) ? store.get(k) : null; },
  async put(k, v) { store.set(k, String(v)); },
  async delete(k) { store.delete(k); },
  async list() { return { keys: [...store.keys()].map(name => ({ name })) }; },
};
globalThis.fetch = async (url) => {
  const u = String(url);
  if (u.includes("api.github.com")) return new Response(null, { status: 204 });
  return new Response("stub-404", { status: 404 });
};

const NUM = "919876543210";
const TOKEN = "a".repeat(48); // appAuth requires exactly 48 hex chars
const kek = Buffer.from(crypto.getRandomValues(new Uint8Array(32))).toString("base64");
const env = {
  KV, APP_KEK: kek, RUNNER_KEY: "test-runner", GH_TOKEN: "ghp_testtoken",
  GH_REPO: "owner/repo", OWNERS: NUM, FRIENDS: "", GROQ_KEY: "",
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
async function runner(method, p, body) {
  const req = new Request("https://divya.test" + p, {
    method,
    headers: { "content-type": "application/json", "x-runner-key": "test-runner" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const r = await worker.fetch(req, env, ctx);
  const text = await r.text();
  let json = null;
  try { json = JSON.parse(text); } catch {}
  return { status: r.status, json, text };
}
const getRec = k => { try { return JSON.parse(store.get(k) || "null"); } catch { return null; } };
const histText = () => (getRec(`h:${NUM}`) || []).map(m => m.content || "").join("\n");
const countOcc = (hay, needle) => hay.split(needle).length - 1;

// ---------- (0) the profile-serialization guard, both ways ----------
// Direction 1: an active profile chain blocks a browse start.
store.set(`setupchain:${NUM}`, JSON.stringify({ providers: ["kaggle"], current: "joba1", browser: "profile", at: Date.now(), upd: Date.now() }));
store.set("setupjob:joba1", JSON.stringify({ job: "joba1", user: NUM, provider: "kaggle", state: "running", step: "signup", upd: Date.now() }));
let r = await call("POST", "/api/setup/browse/start", { task: "look something up" });
check(r.json && r.json.ok === false && r.json.busy === true && !store.has(`browsecur:${NUM}`),
  "guard: active profile chain refuses a browse start (no browse job created)");

// Direction 2: an active browse job blocks a profile-mode chain start.
// (The current browse job is tracked by the browsecur:<n> pointer to a
// setupjob: record — browseJobFor's contract.)
store.delete(`setupchain:${NUM}`); store.delete("setupjob:joba1");
store.set(`browsecur:${NUM}`, JSON.stringify({ job: "jobb1", at: Date.now() }));
store.set("setupjob:jobb1", JSON.stringify({ job: "jobb1", user: NUM, provider: "browse", state: "running", step: "browsing", upd: Date.now() }));
r = await call("POST", "/api/setup/start", { email: "user@example.com", providers: ["kaggle"] });
check(r.json && r.json.ok === false && r.json.profileBusy === true && !store.has(`setupchain:${NUM}`),
  "guard: active browse job refuses a profile-mode setup/start");
// …but an explicitly ephemeral chain never touches the profile: exempt.
r = await call("POST", "/api/setup/start", { email: "user@example.com", providers: ["kaggle"], browser: "ephemeral" });
check(!r.json || r.json.profileBusy !== true, "guard: ephemeral chain is exempt from the profile guard");
store.delete(`setupchain:${NUM}`); store.delete(`browsecur:${NUM}`);
for (const k of [...store.keys()]) if (k.startsWith("setupjob:")) store.delete(k);

// ---------- awaiting: stored once, asked once ----------
store.set(`setupchain:${NUM}`, JSON.stringify({ providers: ["kaggle"], current: "jobc1", browser: "profile", at: Date.now(), upd: Date.now() }));
store.set("setupjob:jobc1", JSON.stringify({ job: "jobc1", user: NUM, provider: "kaggle", state: "running", step: "phone-verify", upd: Date.now() }));
const PROMPT1 = "Kaggle phone code vachindhi — chat lo code cheppu.";
const aw1 = { id: "kaggle-otp-1700000000-1", provider: "kaggle", kind: "otp", prompt: PROMPT1, at: Date.now(), expires: Date.now() + 600000, attempts: 1 };
r = await runner("POST", "/api/setup/runner/progress?job=jobc1", { state: "paused", step: "await-otp", reason: "sms", awaiting: aw1 });
let job = getRec("setupjob:jobc1");
check(r.status === 200 && job && job.awaiting && job.awaiting.id === aw1.id,
  "awaiting: progress post stores the structured ask on the job record");
check(countOcc(histText(), PROMPT1) === 1, "awaiting: the ask lands in the user's chat history exactly once");
// heartbeat re-post of the SAME ask: no duplicate chat line.
r = await runner("POST", "/api/setup/runner/progress?job=jobc1", { state: "paused", step: "await-otp", reason: "sms", awaiting: aw1 });
check(countOcc(histText(), PROMPT1) === 1, "awaiting: heartbeat re-post does not duplicate the chat ask");
// re-ask (attempt 2, new id + new prompt): appended again.
const PROMPT2 = "Aa code accept avvaledu — correct code malli cheppu.";
const aw2 = { ...aw1, id: "kaggle-otp-1700000300-2", prompt: PROMPT2, attempts: 2, at: Date.now(), expires: Date.now() + 600000 };
r = await runner("POST", "/api/setup/runner/progress?job=jobc1", { state: "paused", step: "await-otp", reason: "sms", awaiting: aw2 });
check(countOcc(histText(), PROMPT2) === 1 && getRec("setupjob:jobc1").awaiting.id === aw2.id,
  "awaiting: a re-ask replaces the ask and appends a new chat line");

// ---------- chat routing: the reply is the answer ----------
r = await call("POST", "/api/chat", { text: "482916" });
job = getRec("setupjob:jobc1");
check(job && job.userInput && job.userInput.value === "482916" && job.userInput.askId === aw2.id,
  "chat: a code-shaped reply is delivered to the waiting job (askId-matched)");
check(r.json && typeof r.json.reply === "string" && !r.json.reply.includes("482916"),
  "chat: Julie's confirmation never echoes the code");
// a non-code message is NOT an answer: fresh ask, chat about something else.
store.set("setupjob:jobc1", JSON.stringify({ job: "jobc1", user: NUM, provider: "kaggle", state: "paused", step: "await-otp", awaiting: { ...aw2, id: "kaggle-otp-1700000600-1", attempts: 1 }, upd: Date.now() }));
r = await call("POST", "/api/chat", { text: "weather ela undi?" });
job = getRec("setupjob:jobc1");
check(!job.userInput, "chat: a non-code message is not consumed by the OTP ask");
// setup/status must never expose the delivered value.
store.set("setupjob:jobc1", JSON.stringify({ ...(getRec("setupjob:jobc1") || {}), userInput: { value: "482916", askId: "kaggle-otp-1700000600-1", at: Date.now() } }));
r = await call("GET", "/api/setup/status");
check(r.text && !r.text.includes("userInput") && !r.text.includes("482916"),
  "status: setup/status strips userInput (the code never reaches the app payload)");

// ---------- setup/answer endpoint: same delivery, kind-validated ----------
store.set(`setupchain:${NUM}`, JSON.stringify({ providers: ["kaggle"], current: "jobd1", browser: "profile", at: Date.now(), upd: Date.now() }));
store.set("setupjob:jobd1", JSON.stringify({ job: "jobd1", user: NUM, provider: "kaggle", state: "paused", step: "await-field",
  awaiting: { id: "kaggle-field-1700000900-1", provider: "kaggle", kind: "field", field: "phone", prompt: "phone number cheppu", at: Date.now(), expires: Date.now() + 900000, attempts: 1 }, upd: Date.now() }));
r = await call("POST", "/api/setup/answer", { value: "not-a-phone" });
check(r.json && r.json.ok === false && r.json.error === "bad-value" && !getRec("setupjob:jobd1").userInput,
  "answer: an invalid phone value is rejected, nothing delivered");
r = await call("POST", "/api/setup/answer", { value: "+91 98765 43210" });
job = getRec("setupjob:jobd1");
check(r.json && r.json.ok === true && job.userInput && job.userInput.value === "+919876543210",
  "answer: a valid phone value is normalized and delivered to the waiting job");

console.log("");
if (fails) { console.log(`acctcreatetest.mjs: ${fails} FAIL`); process.exit(1); }
console.log("acctcreatetest.mjs: ALL PASS");
