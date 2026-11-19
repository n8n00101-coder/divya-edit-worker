// Routing rig (final integration slice): chat + WhatsApp intents
// route to agent jobs. Drives the REAL Worker fetch handler — app
// chat via POST /api/chat (account sessions, integrationtest style)
// and WhatsApp via POST /webhook (wa107 style) — with in-memory KV
// and a stubbed network (Gemini brain, GitHub dispatch, Meta send).
//
// Covers:
//   App chat: a general task creates exactly ONE agent job (goal
//     text intact, TOK.COST.agent charged once via the spend
//     record); a second task while one runs -> busy, no new job;
//     a status question answers from the record (no invented %);
//     "stop" halts the job; terminal outcomes (done with the answer
//     / unverified / failed) surface in chat ONCE, truthfully, with
//     the refund claimed only when it landed; greetings, a setup
//     question, a setup-progress question, a video request and a
//     how question create NO agent job; insufficient balance -> the
//     standard tokMsg reply, no job.
//   WhatsApp: the same routing through handle() — task creates the
//     job, a second task is busy, status answers from the record,
//     "stop" halts it, a new task after the stop starts fresh, and
//     greetings / status questions create nothing.
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
let outbox = [];
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
    return new Response(null, { status: 204 });
  }
  if (u.includes("graph.facebook.com")) {
    let body = {}; try { body = JSON.parse((opts && opts.body) || "{}"); } catch {}
    if (body.type === "text" && body.text && body.text.body) outbox.push({ to: body.to, text: body.text.body });
    return Response.json({ messages: [{ id: "wamid.test" }] });
  }
  return new Response("stub-404", { status: 404 });
};

const OWNER = "910000000001";      // WhatsApp user (owner — handle() gate)
const NUM = "919876543210";        // app user: create / busy / status / stop
const NUM2 = "919876543211";       // app user: done outcome
const NUM3 = "919876543212";       // app user: unverified outcome
const NUM4 = "919876543213";       // app user: failed outcome
const NUM5 = "919876543214";       // app user: negative battery
const NUM6 = "919876543215";       // app user: insufficient balance
const TOKS = {};
function seedUser(num) {
  const uid = "u" + num.slice(-6);
  const tok = (num.slice(-6) + "abcdef").padEnd(48, "0"); // appAuth accepts hex tokens only
  TOKS[num] = tok;
  store.set(`acct:${uid}`, JSON.stringify({ uid, name: "Test", email: "", phone: num, pwv: 1, created: 1 }));
  store.set(`sess:${tok}`, `a:${uid}:1`);
}
[NUM, NUM2, NUM3, NUM4, NUM5, NUM6].forEach(seedUser);
const istWeek = () => { const d = new Date(Date.now() + 19800000); const day = (d.getUTCDay() + 6) % 7; d.setUTCDate(d.getUTCDate() - day); return d.toISOString().slice(0, 10); };
store.set(`tokw:${NUM6}:${istWeek()}`, "488000"); // 12,000 left: the 5,000 chat spend passes, the 10,000 agent spend cannot

const kek = Buffer.from(crypto.getRandomValues(new Uint8Array(32))).toString("base64");
const env = {
  KV, APP_KEK: kek, RUNNER_KEY: "test-runner", GH_TOKEN: "ghp_testtoken",
  GH_REPO: "owner/repo", OWNERS: OWNER, FRIENDS: "", GROQ_KEY: "",
  GEMINI_KEY: "test-gemini-key", WA_TOKEN: "wa-test", PHONE_ID: "1555000111",
};
const worker = (await import(pathToFileURL(path.join(HERE, "cfworker", "divya.js")).href)).default;

async function call(method, p, body, headers = {}) {
  const ctx = { waitUntil() {}, passThroughOnException() {} };
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
const chat = (num, text) => call("POST", "/api/chat", { text, lang: "te" }, { authorization: `Bearer ${TOKS[num]}` });
const runner = (method, p, body) => call(method, p, body, { "x-runner-key": "test-runner" });
const getRec = (k) => { try { return JSON.parse(store.get(k) || "null"); } catch { return null; } };
const agentJobsOf = (num) => [...store.keys()].filter(k => k.startsWith("setupjob:")).map(k => getRec(k)).filter(j => j && j.provider === "agent" && j.user === num);
const agentDispatches = () => dispatches.filter(d => d.url.includes("agent.yml/dispatches"));

let seq = 0;
async function waSend(text) {
  const before = outbox.length;
  const promises = [];
  const ctx = { waitUntil(p) { promises.push(Promise.resolve(p)); }, passThroughOnException() {} };
  const body = { entry: [{ changes: [{ field: "messages", value: { messages: [{ from: OWNER, id: "m" + (++seq), type: "text", text: { body: text } }] } }] }] };
  const req = new Request("https://divya.test/webhook", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
  await worker.fetch(req, env, ctx);
  for (let i = 0; i < 6; i++) { const ps = promises.splice(0); if (!ps.length) break; await Promise.all(ps); }
  return outbox.slice(before).filter(o => o.to === OWNER).map(o => o.text);
}

const TASK1 = "Write a short report on the water cycle and list the main stages";
const TASK2 = "Prepare a summary of photosynthesis and list the steps";

// =====================================================================
// App chat — create exactly one job, charged once, goal intact
// =====================================================================
let r = await chat(NUM, TASK1);
check(r.json && r.json.agent_started === true && typeof r.json.agent_job === "string",
  "A1 a general task in app chat starts an agent job");
const JOB = r.json.agent_job;
let rec = getRec(`setupjob:${JOB}`);
check(rec && rec.provider === "agent" && rec.user === NUM && rec.task === TASK1 && rec.state === "queued",
  "A2 the record is an agent job with the goal text intact");
check(agentJobsOf(NUM).length === 1 && agentDispatches().length === 1,
  "A3 exactly one agent job and one agent.yml dispatch");
const spend = getRec(`spend:${JOB}`);
check(spend && spend.cost === 10000 && spend.refunded === false,
  "A4 the spend record charges TOK.COST.agent (10,000) exactly once");
check(store.get(`tokw:${NUM}:${istWeek()}`) === "15000",
  "A5 the weekly bucket shows chat 5,000 + agent 10,000 — no double charge");

// =====================================================================
// App chat — busy rule, status from the record, stop
// =====================================================================
r = await chat(NUM, TASK2);
check(r.json && !r.json.agent_started && /already running|already nadusthundhi/.test(r.json.reply || "")
  && agentJobsOf(NUM).length === 1 && agentDispatches().length === 1,
  "A6 a second task while one runs -> busy line, no second job, no second charge");

r = await chat(NUM, "status enti");
check(r.json && /queue lo undhi/.test(r.json.reply || "") && (r.json.reply || "").includes("water cycle") && !/%/.test(r.json.reply || ""),
  "A7 a status question answers from the agent record (state + task, no invented %)");

r = await chat(NUM, "stop");
rec = getRec(`setupjob:${JOB}`);
check(rec && rec.state === "stopped" && r.json && /Agent job aapesanu/.test(r.json.reply || ""),
  "A8 'stop' in app chat halts the running agent job");

// =====================================================================
// App chat — terminal outcomes surface once, truthfully
// =====================================================================
r = await chat(NUM2, TASK1);
const JOB2 = r.json.agent_job;
check(!!JOB2, "A9 (setup) second user starts an agent job");
const ANSWER = "The water cycle has four main stages: evaporation, condensation, precipitation, collection.";
r = await runner("POST", `/api/setup/runner/result?job=${JOB2}`, { provider: "agent", status: "done", answer: ANSWER });
check(r.status === 200, "A10 (setup) the runner's done result posts");
r = await chat(NUM2, "Hi");
check(r.json && (r.json.reply || "").includes("four main stages") && /ayipoyindhi/.test(r.json.reply || ""),
  "A11 the done outcome + the answer surface in app chat");
r = await chat(NUM2, "Hi");
check(r.json && !(r.json.reply || "").includes("four main stages"),
  "A12 the outcome is told ONCE — the next chat does not repeat it");

r = await chat(NUM3, TASK1);
const JOB3 = r.json.agent_job;
r = await runner("POST", `/api/setup/runner/result?job=${JOB3}`, { provider: "agent", status: "unverified", error: "missing evidence: no recorded OK verify step" });
r = await chat(NUM3, "Hi");
check(r.json && /UNVERIFIED/.test(r.json.reply || "") && /venakki ichesa/.test(r.json.reply || ""),
  "A13 an unverified outcome surfaces honestly, with the refund line");
check(getRec(`spend:${JOB3}`) && getRec(`spend:${JOB3}`).refunded === true,
  "A14 the unverified job's spend is refunded on the durable record");

r = await chat(NUM4, TASK1);
const JOB4 = r.json.agent_job;
r = await runner("POST", `/api/setup/runner/result?job=${JOB4}`, { provider: "agent", status: "failed", error: "machine died at step 3" });
r = await chat(NUM4, "Hi");
check(r.json && /complete avvaledu/.test(r.json.reply || "") && /venakki ichesa/.test(r.json.reply || "")
  && getRec(`spend:${JOB4}`) && getRec(`spend:${JOB4}`).refunded === true,
  "A15 a failed outcome surfaces honestly and its spend is refunded");

// =====================================================================
// App chat — negatives: nothing else starts an agent job
// =====================================================================
const dispBefore = agentDispatches().length;
for (const [label, msg] of [
  ["a greeting", "Hi"],
  ["a setup-progress question", "Groq setup ayindha?"],
  ["a setup question", "enni api keys unnayi"],
  ["a video request", "Make a 30 second video about rain"],
  ["a how question", "topic isthe ela edit chesthav, detailed ga cheppu"],
  ["a status question with no job", "status enti"],
]) {
  r = await chat(NUM5, msg);
  check(r.json && !r.json.agent_started && !getRec(`agentcur:${NUM5}`) && agentDispatches().length === dispBefore,
    `A16 ${label} creates NO agent job`);
}

// =====================================================================
// App chat — insufficient balance: standard reply, no job
// =====================================================================
r = await chat(NUM6, TASK1);
check(r.json && !r.json.agent_started && /Tokens saripovu/.test(r.json.reply || "")
  && !getRec(`agentcur:${NUM6}`) && agentJobsOf(NUM6).length === 0,
  "A17 insufficient balance -> the standard tokMsg reply, no job created");

// =====================================================================
// WhatsApp — the same routing through handle()
// =====================================================================
let tells = await waSend("Water cycle meedha oka chinna report raayi, main stages list cheyu");
const waJobs = agentJobsOf(OWNER);
check(waJobs.length === 1 && waJobs[0].state === "queued" && /Agent task start chesa/.test(tells.join("\n")),
  "W1 a general task on WhatsApp creates an agent job and says so in chat");
const WJOB = waJobs[0] && waJobs[0].job;
check(waJobs[0] && waJobs[0].task.includes("report raayi"),
  "W2 the WhatsApp goal text rides the record");

tells = await waSend("Hi");
check(agentJobsOf(OWNER).length === 1 && agentDispatches().filter(d => (d.input.inputs || {}).job === WJOB).length === 1,
  "W3 a greeting on WhatsApp creates NO agent job");

tells = await waSend("Photosynthesis gurinchi summary raayi, steps list cheyu");
check(/already nadusthundhi/.test(tells.join("\n")) && agentJobsOf(OWNER).filter(j => ["queued", "running"].includes(j.state)).length === 1,
  "W4 a second task while one runs -> busy line, still one active job");

tells = await waSend("ayindha? status enti");
check(/queue lo undhi/.test(tells.join("\n")) && !/%/.test(tells.join("\n")),
  "W5 a WhatsApp status question answers from the agent record (no invented %)");

tells = await waSend("stop");
rec = getRec(`setupjob:${WJOB}`);
check(rec && rec.state === "stopped" && /agent job stop chesa/.test(tells.join("\n")),
  "W6 'stop' on WhatsApp halts the running agent job");

tells = await waSend("Water cycle meedha oka chinna report raayi, main stages list cheyu");
check(agentJobsOf(OWNER).filter(j => ["queued", "running"].includes(j.state)).length === 1
  && agentJobsOf(OWNER).length === 2 && /Agent task start chesa/.test(tells.join("\n")),
  "W7 after the stop, a new task starts a fresh agent job");

tells = await waSend("setup ayindha");
check(agentJobsOf(OWNER).length === 2,
  "W8 a setup-progress question creates NO agent job");

console.log(fails ? `\n${fails} FAILURES` : "\nALL PASS");
process.exit(fails ? 1 : 0);
