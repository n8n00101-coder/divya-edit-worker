// E1 Worker rig (in the chainfixtest style: in-memory KV, stubbed
// fetch, real fetch handler). Covers the two additive runner
// endpoints agent_loop.py talks to:
//
//   POST setup/runner/agentstep  — the general agent-step brain
//     (brainstep's sibling): gated to provider:"agent" jobs, runs the
//     owner's chat chain, validates that a tool call names a tool the
//     runner actually offered.
//   POST setup/runner/agentsteps — appends one step entry to the job
//     record's steps[] (the persistence E3 resume builds on); a
//     terminal record is final (terminal-sticky, like progress).
//
// The model is stubbed at the fetch layer: the shared Gemini key path
// in chatWithFallback returns scripted replies from a queue, so the
// rig proves the endpoint's parsing + validation, not a real model.
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

// --- stubbed network: the Gemini chat path returns scripted replies --
let modelQueue = [];
globalThis.fetch = async (url) => {
  const u = String(url);
  if (u.includes("generativelanguage.googleapis.com")) {
    const text = modelQueue.length ? modelQueue.shift() : "";
    return Response.json({ candidates: [{ content: { parts: [{ text }] } }] });
  }
  return new Response("stub-404", { status: 404 });
};

const NUM = "919876543210";
const kek = Buffer.from(crypto.getRandomValues(new Uint8Array(32))).toString("base64");
const env = {
  KV, APP_KEK: kek, RUNNER_KEY: "test-runner", GH_TOKEN: "ghp_testtoken",
  GH_REPO: "owner/repo", OWNERS: NUM, FRIENDS: "", GROQ_KEY: "",
  GEMINI_KEY: "test-gemini-key",
};
const ctx = { waitUntil() {}, passThroughOnException() {} };

const worker = (await import(pathToFileURL(path.join(HERE, "cfworker", "divya.js")).href)).default;

async function runner(method, p, body, key = "test-runner") {
  const req = new Request("https://divya.test" + p, {
    method,
    headers: { "content-type": "application/json", "x-runner-key": key },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const r = await worker.fetch(req, env, ctx);
  const text = await r.text();
  let json = null;
  try { json = JSON.parse(text); } catch {}
  return { status: r.status, json, text };
}
const getRec = (k) => { try { return JSON.parse(store.get(k) || "null"); } catch { return null; } };
const putRec = (k, v) => store.set(k, JSON.stringify(v));

// --- seed job records -------------------------------------------------
putRec("setupjob:agentjob1", { user: NUM, provider: "agent", state: "running", task: "echo hi, then finish" });
putRec("setupjob:agentjob2", { user: NUM, provider: "agent", state: "stopped", task: "old job", steps: [{ n: 1, tool: "echo", ok: true, result: "hi" }] });
putRec("setupjob:browsejob1", { user: NUM, provider: "browse", state: "running", task: "open a page" });

// =====================================================================
// agentsteps — step recording on the job record
// =====================================================================
let r = await runner("POST", "/api/setup/runner/agentsteps?job=agentjob1", { step: { n: 1, tool: "echo", arg: "{\"text\":\"hi\"}", ok: true, result: "hi", at: 111 } }, "wrong-key");
check(r.status === 403, "S1 agentsteps without the runner key -> 403");

r = await runner("POST", "/api/setup/runner/agentsteps?job=nosuchjob", { step: { n: 1, tool: "echo", ok: true, result: "hi" } });
check(r.status === 404, "S2 agentsteps for a missing job -> 404");

r = await runner("POST", "/api/setup/runner/agentsteps?job=browsejob1", { step: { n: 1, tool: "echo", ok: true, result: "hi" } });
check(r.status === 400, "S3 agentsteps refuses a non-agent (browse) job -> 400");

r = await runner("POST", "/api/setup/runner/agentsteps?job=agentjob1", { step: { n: 1, tool: "echo", arg: "{\"text\":\"hi\"}", ok: true, result: "hi", at: 111 } });
check(r.status === 200 && r.json && r.json.ok === true && r.json.steps === 1, "S4 first step recorded (steps=1)");
let rec = getRec("setupjob:agentjob1");
check(rec && Array.isArray(rec.steps) && rec.steps.length === 1
  && rec.steps[0].tool === "echo" && rec.steps[0].ok === true
  && rec.steps[0].result === "hi" && rec.steps[0].n === 1,
  "S5 the record's steps[] carries the entry (tool/ok/result/n)");

r = await runner("POST", "/api/setup/runner/agentsteps?job=agentjob1", { step: { n: 2, tool: "flaky", arg: "", ok: false, result: "FAILED: boom" } });
rec = getRec("setupjob:agentjob1");
check(r.json && r.json.steps === 2 && rec.steps.length === 2
  && rec.steps[1].tool === "flaky" && rec.steps[1].ok === false,
  "S6 second step appended in order, failure recorded as-is");

r = await runner("POST", "/api/setup/runner/agentsteps?job=agentjob1", { step: { n: 3, tool: "submit", arg: "{}", ok: false, result: "", phase: "started" } });
rec = getRec("setupjob:agentjob1");
check(r.json && r.json.steps === 3 && rec.steps.length === 3
  && rec.steps[2].phase === "started" && rec.steps[2].tool === "submit",
  "S8 (E3) a started marker keeps its phase through the round trip");

r = await runner("POST", "/api/setup/runner/agentsteps?job=agentjob2", { step: { n: 2, tool: "echo", ok: true, result: "late" } });
rec = getRec("setupjob:agentjob2");
check(r.status === 200 && r.json && r.json.swallowed === "terminal"
  && rec.steps.length === 1,
  "S7 a terminal (stopped) record is final — late step swallowed, record unchanged");

// =====================================================================
// agentstep — the general step brain
// =====================================================================
r = await runner("POST", "/api/setup/runner/agentstep?job=browsejob1", { goal: "x", history: [], tools: [{ name: "echo", desc: "echo" }] });
check(r.status === 400, "B1 agentstep refuses a non-agent (browse) job -> 400");

modelQueue = ['{"action":"tool","tool":"echo","args":{"text":"hi"}}'];
r = await runner("POST", "/api/setup/runner/agentstep?job=agentjob1", { goal: "echo hi, then finish", history: [], tools: [{ name: "echo", desc: "echo text" }, { name: "noop", desc: "nothing" }] });
check(r.status === 200 && r.json && r.json.ok === true
  && r.json.action && r.json.action.action === "tool"
  && r.json.action.tool === "echo" && r.json.action.args.text === "hi",
  "B2 agentstep returns the model's tool call", );

modelQueue = ['{"action":"done","answer":"echoed hi"}'];
r = await runner("POST", "/api/setup/runner/agentstep?job=agentjob1", { goal: "echo hi, then finish", history: [{ action: "echo", arg: "{\"text\":\"hi\"}", result: "ok: hi" }], tools: [{ name: "echo", desc: "echo text" }] });
check(r.status === 200 && r.json && r.json.ok === true
  && r.json.action && r.json.action.action === "done"
  && r.json.action.answer === "echoed hi",
  "B3 agentstep returns done with the model's answer");

modelQueue = ['{"action":"tool","tool":"notoffered","args":{}}'];
r = await runner("POST", "/api/setup/runner/agentstep?job=agentjob1", { goal: "g", history: [], tools: [{ name: "echo", desc: "echo text" }] });
check(r.status === 200 && r.json && r.json.ok === false && r.json.error === "brain",
  "B4 a tool call naming an un-offered tool is rejected as unusable (error: brain)");

modelQueue = ["sorry, no json here"];
r = await runner("POST", "/api/setup/runner/agentstep?job=agentjob1", { goal: "g", history: [], tools: [{ name: "echo", desc: "echo text" }] });
check(r.status === 200 && r.json && r.json.ok === false && r.json.error === "brain",
  "B5 a non-JSON model reply is unusable (error: brain), never a fake action");

console.log(fails ? `\n${fails} FAILURES` : "\nALL PASS");
process.exit(fails ? 1 : 0);
