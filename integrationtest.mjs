// Integration rig (Worker half): the agent-job production wiring in
// cfworker/divya.js, in the e1test.mjs style — in-memory KV, stubbed
// fetch, the real fetch handler.
//
// Covers what the integration phase added:
//   POST /api/agent            — authenticated creation: token gate
//     (tokSpend, TOK.COST.agent), busy rule, evidence/files shape
//     checks, setupjob record (provider "agent"), agentcur pointer,
//     agent.yml dispatch, spend record; dispatch failure refunds.
//   setup/runner/agentstep     — the brain answers on a REAL created
//     record (creation → brain path end to end at the Worker layer).
//   setup/runner/result        — an agent "unverified" outcome is
//     stored as unverified (not coerced to failed), the answer/note
//     land on the record, and the creation spend is refunded exactly
//     once from the durable spend record.
//   setup/runner/progress      — "unverified" is accepted as a state
//     (not coerced to running) and is terminal-sticky.
//   setup/runner/agentsteps    — a terminal unverified record is
//     final (late steps swallowed).
//   GET  /api/status + /api/setup/status — the agent job's truthful
//     record-derived status rides both shapes.
//   POST /api/setup/stop       — the shared Stop halts an agent job.
//
// The runner half (agent_runner.py claiming and executing a job) is
// integrationtest.py. The model is stubbed at the fetch layer like
// e1test (scripted Gemini replies); GitHub dispatches are captured
// and answered 204 (or a failure, when a check arms it).
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
  async mget(keys) { const arr = Array.isArray(keys) ? keys : [keys]; const o = {}; for (const k of arr) o[k] = store.has(k) ? store.get(k) : null; return o; },
};

// --- stubbed network --------------------------------------------------
let modelQueue = [];
let dispatches = [];
let dispatchFails = false;
globalThis.fetch = async (url, opts) => {
  const u = String(url);
  if (u.includes("generativelanguage.googleapis.com")) {
    const text = modelQueue.length ? modelQueue.shift() : "";
    return Response.json({ candidates: [{ content: { parts: [{ text }] } }] });
  }
  if (u.includes("api.github.com")) {
    let input = null;
    try { input = JSON.parse((opts && opts.body) || "{}"); } catch {}
    dispatches.push({ url: u, input });
    if (dispatchFails) return new Response("boom", { status: 500 });
    return new Response(null, { status: 204 });
  }
  if (u.includes("graph.facebook.com")) return Response.json({ ok: true });
  return new Response("stub-404", { status: 404 });
};

const NUM = "919876543210";        // paying user (account session — NOT owner/friend, so spends are real)
const NUM3 = "919876543213";       // nearly-out-of-tokens user
const NUM4 = "919876543214";       // dispatch-failure user
const TOK1 = "a".repeat(48), TOK3 = "b".repeat(48), TOK4 = "c".repeat(48);
// Real app users authenticate with ACCOUNT sessions (sess -> a:<uid>:<pwv>
// + an acct:<uid> record); a bare phone session only passes appAuth for
// owners/friends, who are token-unlimited and could never prove a spend.
function seedUser(num, tok) {
  const uid = "u" + num.slice(-6);
  store.set(`acct:${uid}`, JSON.stringify({ uid, name: "Test", email: "", phone: num, pwv: 1, created: 1 }));
  store.set(`sess:${tok}`, `a:${uid}:1`);
}
seedUser(NUM, TOK1);
seedUser(NUM3, TOK3);
seedUser(NUM4, TOK4);
const istWeek = () => { const d = new Date(Date.now() + 19800000); const day = (d.getUTCDay() + 6) % 7; d.setUTCDate(d.getUTCDate() - day); return d.toISOString().slice(0, 10); };
store.set(`tokw:${NUM3}:${istWeek()}`, "495000"); // 5,000 of the weekly 500,000 left — under the 10,000 agent cost

const kek = Buffer.from(crypto.getRandomValues(new Uint8Array(32))).toString("base64");
const env = {
  KV, APP_KEK: kek, RUNNER_KEY: "test-runner", GH_TOKEN: "ghp_testtoken",
  GH_REPO: "owner/repo", OWNERS: "910000000001", FRIENDS: "", GROQ_KEY: "",
  GEMINI_KEY: "test-gemini-key",
};
const ctx = { waitUntil() {}, passThroughOnException() {} };
const worker = (await import(pathToFileURL(path.join(HERE, "cfworker", "divya.js")).href)).default;

async function call(method, p, body, headers = {}) {
  const req = new Request("https://divya.test" + p, {
    method,
    headers: { "content-type": "application/json", ...headers },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const r = await worker.fetch(req, env, ctx);
  const text = await r.text();
  let json = null;
  try { json = JSON.parse(text); } catch {}
  return { status: r.status, json, text };
}
const app = (method, p, body, tok = TOK1) => call(method, p, body, { authorization: `Bearer ${tok}` });
const runner = (method, p, body) => call(method, p, body, { "x-runner-key": "test-runner" });
const getRec = (k) => { try { return JSON.parse(store.get(k) || "null"); } catch { return null; } };

const EVIDENCE = [{ tool: "verify_file_contains", args: { path: "summary.txt", contains: ["revenue: 300"] } }];
const FILES = { "orders.csv": "id,item,amount,status\n1,pen,100,completed\n" };

// =====================================================================
// Creation — happy path, token gate, record, dispatch
// =====================================================================
let r = await app("POST", "/api/agent", { task: "Summarise orders.csv", evidence: EVIDENCE, files: FILES, instructions: "Be exact." });
check(r.status === 200 && r.json && r.json.ok === true && typeof r.json.job === "string" && r.json.job.length >= 12,
  "C1 POST /api/agent creates a job (200, ok, job id)");
const JOB = r.json.job;
let rec = getRec(`setupjob:${JOB}`);
check(rec && rec.provider === "agent" && rec.flow === "agent" && rec.user === NUM
  && rec.task === "Summarise orders.csv" && rec.state === "queued",
  "C2 the record is a setupjob with provider 'agent', the task, state queued");
check(rec && JSON.stringify(rec.evidence) === JSON.stringify(EVIDENCE)
  && rec.files && rec.files["orders.csv"] === FILES["orders.csv"]
  && rec.instructions === "Be exact.",
  "C3 evidence, files and instructions ride the record verbatim");
const cur = getRec(`agentcur:${NUM}`);
check(cur && cur.job === JOB, "C4 agentcur points at the new job");
check(dispatches.length === 1 && dispatches[0].url.includes("agent.yml/dispatches")
  && dispatches[0].input && dispatches[0].input.inputs && dispatches[0].input.inputs.job === JOB,
  "C5 agent.yml was dispatched with the job id");
check(store.get(`tokw:${NUM}:${istWeek()}`) === "10000",
  "C6 the token gate charged exactly TOK.COST.agent (10,000) from the weekly bucket");
const spend = getRec(`spend:${JOB}`);
check(spend && spend.n === NUM && spend.cost === 10000 && spend.refunded === false,
  "C7 the spend is recorded against the job (refundable record)");

// =====================================================================
// Creation — busy rule, shape checks, quota
// =====================================================================
r = await app("POST", "/api/agent", { task: "second job" });
check(r.status === 409 && r.json && r.json.busy === true && store.get(`tokw:${NUM}:${istWeek()}`) === "10000",
  "C8 a second agent job while one is active -> 409 busy, no second charge");

r = await app("POST", "/api/agent", { task: "  " });
check(r.status === 400 && r.json && r.json.field === "task", "C9 an empty task -> 400 (field task)");

r = await app("POST", "/api/agent", { task: "x", evidence: [{ nope: 1 }] });
check(r.status === 400 && r.json && r.json.field === "evidence", "C10 a malformed evidence item -> 400 (field evidence)");

r = await app("POST", "/api/agent", { task: "x", files: { "../evil.txt": "x" } });
check(r.status === 400 && r.json && r.json.field === "files", "C11 a path-escaping seed file name -> 400 (field files)");

r = await app("POST", "/api/agent", { task: "too poor" }, TOK3);
check(r.status === 429 && r.json && r.json.quota === true && !getRec(`agentcur:${NUM3}`),
  "C12 balance under the cost -> 429 quota, no job created");

// =====================================================================
// Brain + steps on the REAL created record
// =====================================================================
modelQueue = ['{"action":"tool","tool":"compute_csv","args":{"path":"orders.csv","spec":{}}}'];
r = await runner("POST", `/api/setup/runner/agentstep?job=${JOB}`, { goal: "Summarise orders.csv", history: [], tools: [{ name: "compute_csv", desc: "compute" }] });
check(r.status === 200 && r.json && r.json.ok === true && r.json.action && r.json.action.tool === "compute_csv",
  "B1 agentstep answers on the created record (creation -> brain path works)");

r = await runner("POST", `/api/setup/runner/agentsteps?job=${JOB}`, { step: { n: 1, tool: "compute_csv", arg: "{}", ok: false, result: "", phase: "started", at: 111 } });
check(r.status === 200 && r.json && r.json.steps === 1, "B2 a started marker records");
r = await runner("POST", `/api/setup/runner/agentsteps?job=${JOB}`, { step: { n: 1, tool: "compute_csv", arg: "{}", ok: true, result: "rows 1", at: 112 } });
check(r.status === 200 && r.json && r.json.steps === 2, "B3 the completion records after it");

// =====================================================================
// Status surfacing — record truth only
// =====================================================================
r = await app("GET", "/api/status");
check(r.status === 200 && r.json && r.json.agent && r.json.agent.job === JOB
  && r.json.agent.state === "queued" && r.json.agent.steps
  && r.json.agent.steps.completed === 1 && r.json.agent.steps.ok === 1
  && r.json.agent.steps.inflight === 0 && r.json.agent.evidence.declared === 1,
  "S1 /api/status carries the agent job: state + step counts + declared evidence from the record");

r = await app("GET", "/api/setup/status");
check(r.status === 200 && r.json && r.json.agent && r.json.agent.job === JOB,
  "S2 /api/setup/status carries the same agent job (browse's status home)");

// =====================================================================
// Result — unverified stored honestly, spend refunded exactly once
// =====================================================================
r = await runner("POST", `/api/setup/runner/result?job=${JOB}`, { provider: "agent", status: "unverified", error: "missing evidence: no recorded OK verify_file_contains step" });
rec = getRec(`setupjob:${JOB}`);
check(r.status === 200 && rec && rec.state === "unverified",
  "R1 an agent result of 'unverified' is stored as unverified — NOT coerced to failed");
check(rec && rec.note === "missing evidence: no recorded OK verify_file_contains step",
  "R2 the gate's gap lands on the record as the note");
check(store.get(`tokw:${NUM}:${istWeek()}`) === "0",
  "R3 the creation spend is refunded (weekly bucket restored)");
check(getRec(`spend:${JOB}`) && getRec(`spend:${JOB}`).refunded === true,
  "R4 the spend record is flagged refunded");

r = await runner("POST", `/api/setup/runner/result?job=${JOB}`, { provider: "agent", status: "unverified", error: "duplicate post" });
check(store.get(`tokw:${NUM}:${istWeek()}`) === "0",
  "R5 a duplicate result post does NOT refund twice");

r = await runner("POST", `/api/setup/runner/agentsteps?job=${JOB}`, { step: { n: 2, tool: "echo", ok: true, result: "late" } });
rec = getRec(`setupjob:${JOB}`);
check(r.json && r.json.swallowed === "terminal" && rec.steps.length === 2,
  "R6 a terminal unverified record is final — late steps swallowed");

// =====================================================================
// Progress — unverified accepted + terminal-sticky; Stop halts a job
// =====================================================================
r = await app("POST", "/api/agent", { task: "second real job" });
check(r.status === 200 && r.json && r.json.ok === true, "P1 after a terminal job a new agent job can start");
const JOB2 = r.json.job;
r = await runner("POST", `/api/setup/runner/progress?job=${JOB2}`, { state: "unverified", step: "unverified", note: "gate failed" });
rec = getRec(`setupjob:${JOB2}`);
check(rec && rec.state === "unverified", "P2 progress accepts 'unverified' as a state (not coerced to running)");
r = await runner("POST", `/api/setup/runner/progress?job=${JOB2}`, { state: "running", step: "zombie", note: "zombie heartbeat" });
rec = getRec(`setupjob:${JOB2}`);
check(rec && rec.state === "unverified", "P3 a later non-terminal progress post cannot resurrect an unverified job (terminal-sticky)");

r = await app("POST", "/api/agent", { task: "third real job" });
check(r.status === 200 && r.json && r.json.ok === true, "T1 a third job starts (job2 is terminal)");
const JOB3 = r.json.job;
r = await app("POST", "/api/setup/stop", {});
rec = getRec(`setupjob:${JOB3}`);
check(r.status === 200 && rec && rec.state === "stopped",
  "T2 the shared setup/stop halts a running agent job (its loop polls this state)");

// =====================================================================
// Dispatch failure — spend refunded, record honest
// =====================================================================
dispatchFails = true;
r = await app("POST", "/api/agent", { task: "will not start" }, TOK4);
dispatchFails = false;
check(r.status === 502 && r.json && r.json.ok === false, "D1 a failed dispatch answers 502");
check(!store.get(`tokw:${NUM4}:${istWeek()}`) || store.get(`tokw:${NUM4}:${istWeek()}`) === "0", "D2 the spend was refunded in full (weekly bucket back to zero)");
const cur4 = getRec(`agentcur:${NUM4}`);
const rec4 = cur4 && getRec(`setupjob:${cur4.job}`);
check(rec4 && rec4.state === "failed", "D3 the record honestly shows failed (dispatch), never queued forever");

console.log(fails ? `\n${fails} FAILURES` : "\nALL PASS");
process.exit(fails ? 1 : 0);
