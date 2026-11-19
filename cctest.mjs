// CC-mode rig (Claude Code mode on Julie's WhatsApp, 2026-11-19):
// drives the REAL Worker fetch handler — WhatsApp via POST /webhook
// (routingtest style) and the runner bridge endpoints via
// /api/setup/runner/ccpull + ccreply with x-runner-key — against
// in-memory KV and a stubbed network (Meta send captured, GitHub
// dispatch recorded, Gemini brain queued).
//
// Covers:
//   OFF (default): a normal message behaves exactly as before —
//     Julie answers, nothing is queued.
//   Toggle ON ("cc on"): flag set + exactly one ON line.
//   While ON: a general task message AND a "stop" message are
//     QUEUED as ccmsg records — Julie stays silent, NO agent job,
//     NO dispatch, NO spend/charge.
//   ccpull: wrong key -> 403; right key -> oldest pending first,
//     each marked "picked"; a second pull never re-hands a picked
//     message; an empty queue pulls empty.
//   Picked recovery: a fresh pick is NOT re-served; a stale pick
//     (>10 min, bridge died/restarted) IS re-served once and
//     re-marked with a fresh pickedAt; a done record is NEVER
//     re-served.
//   ccreply: the reply is sent on WhatsApp to the message's user
//     and the record lands "done" with the reply stored; a repeat
//     post is a no-op ({already:true}, no second send); an unknown
//     id -> 404.
//   Toggle OFF ("cc off" + the "claude code on" / "cc mode off"
//     spellings): flag cleared + one OFF line; Julie answers again.
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
  async list(opts) {
    const prefix = (opts && opts.prefix) || "";
    return { keys: [...store.keys()].filter(k => k.startsWith(prefix)).map(name => ({ name })), list_complete: true };
  },
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
const kek = Buffer.from(crypto.getRandomValues(new Uint8Array(32))).toString("base64");
const env = {
  KV, APP_KEK: kek, RUNNER_KEY: "test-runner", CC_BRIDGE_KEY: "test-bridge", GH_TOKEN: "ghp_testtoken",
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
const runner = (p, body, key = "test-runner") => call("POST", p, body, { "x-runner-key": key });
const getRec = (k) => { try { return JSON.parse(store.get(k) || "null"); } catch { return null; } };
const ccMsgs = () => [...store.keys()].filter(k => k.startsWith("ccmsg:")).map(k => getRec(k)).filter(Boolean);
const agentJobs = () => [...store.keys()].filter(k => k.startsWith("setupjob:")).map(k => getRec(k)).filter(j => j && j.provider === "agent");
const spends = () => [...store.keys()].filter(k => k.startsWith("spend:"));

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

// =====================================================================
// OFF by default: Julie answers, nothing queued
// =====================================================================
let tells = await waSend("Hi");
check(tells.length >= 1 && ccMsgs().length === 0 && store.get(`ccmode:${OWNER}`) !== "1",
  "C1 with CC mode off, a greeting gets Julie's normal answer and queues nothing");

// =====================================================================
// Toggle ON
// =====================================================================
tells = await waSend("cc on");
check(tells.length === 1 && /Claude Code mode ON/.test(tells[0]) && /cc off/.test(tells[0])
  && store.get(`ccmode:${OWNER}`) === "1",
  "C2 'cc on' sets the flag and replies exactly one ON line");

// =====================================================================
// While ON: messages queue silently — no brain, no job, no charge
// =====================================================================
const TASK = "Write a short report on the water cycle and list the main stages";
tells = await waSend(TASK);
check(tells.length === 0 && ccMsgs().length === 1 && ccMsgs()[0].state === "pending" && ccMsgs()[0].text === TASK && ccMsgs()[0].user === OWNER,
  "C3 a task message while ON is queued as a pending ccmsg, Julie silent");
check(agentJobs().length === 0 && dispatches.length === 0 && spends().length === 0,
  "C4 the queued message created NO agent job, NO dispatch, NO spend");

tells = await waSend("stop");
check(tells.length === 0 && ccMsgs().length === 2 && ccMsgs().some(m => m.text === "stop"),
  "C5 'stop' while ON is queued too — no stop flow fires, Julie stays silent");

// =====================================================================
// Bridge pull: auth, oldest-first, picked marking
// =====================================================================
let r = await runner("/api/setup/runner/ccpull", {}, "wrong-key");
check(r.status === 403, "C6 ccpull with a wrong runner key -> 403");

r = await runner("/api/setup/runner/ccpull", {});
check(r.json && r.json.ok && Array.isArray(r.json.messages) && r.json.messages.length === 2
  && r.json.messages[0].text === TASK && r.json.messages[1].text === "stop",
  "C7 ccpull returns both pending messages, oldest first");
const ID1 = r.json.messages[0].id, ID2 = r.json.messages[1].id;
check(getRec(`ccmsg:${ID1}`).state === "picked" && getRec(`ccmsg:${ID2}`).state === "picked",
  "C8 pulled messages are marked picked on their records");

r = await runner("/api/setup/runner/ccpull", {});
check(r.json && r.json.ok && r.json.messages.length === 0,
  "C9 a second pull is empty — picked messages are never handed out twice");

// =====================================================================
// Bridge reply: sent on WhatsApp, record done, repeat is a no-op
// =====================================================================
const outBefore = outbox.length;
r = await runner("/api/setup/runner/ccreply", { id: ID1, text: "CC ANSWER ONE" });
check(r.json && r.json.ok === true && outbox.length === outBefore + 1
  && outbox[outbox.length - 1].to === OWNER && outbox[outbox.length - 1].text === "CC ANSWER ONE",
  "C10 ccreply sends the answer on WhatsApp to the message's user");
check(getRec(`ccmsg:${ID1}`).state === "done" && getRec(`ccmsg:${ID1}`).reply === "CC ANSWER ONE",
  "C11 the record lands done with the reply stored");

r = await runner("/api/setup/runner/ccreply", { id: ID1, text: "CC ANSWER ONE" });
check(r.json && r.json.already === true && outbox.length === outBefore + 1,
  "C12 a repeat ccreply is a no-op — the answer is never sent twice");

r = await runner("/api/setup/runner/ccreply", { id: "deadbeefdeadbeefdeadbeef", text: "x" });
check(r.status === 404, "C13 ccreply for an unknown id -> 404");

r = await runner("/api/setup/runner/ccreply", { id: ID2, text: "" });
check(r.json && r.json.ok === false && getRec(`ccmsg:${ID2}`).state === "picked",
  "C14 an empty reply is refused and the record stays picked (retryable)");

// =====================================================================
// Toggle OFF (alternate spellings) — Julie answers again
// =====================================================================
tells = await waSend("cc off");
check(tells.length === 1 && /Claude Code mode OFF/.test(tells[0]) && store.get(`ccmode:${OWNER}`) !== "1",
  "C15 'cc off' clears the flag and replies exactly one OFF line");

tells = await waSend("Hi");
check(tells.length >= 1 && ccMsgs().length === 2,
  "C16 after OFF, Julie answers again and nothing new is queued");

tells = await waSend("Claude Code ON");
check(store.get(`ccmode:${OWNER}`) === "1" && tells.length === 1 && /mode ON/.test(tells[0]),
  "C17 'Claude Code ON' (mixed case, long spelling) also toggles on");
tells = await waSend("cc mode off");
check(store.get(`ccmode:${OWNER}`) !== "1" && tells.length === 1 && /mode OFF/.test(tells[0]),
  "C18 'cc mode off' toggles back off");

// =====================================================================
// Bridge key (CC_BRIDGE_KEY): accepted on ccpull/ccreply ONLY
// =====================================================================
tells = await waSend("cc on");
check(tells.length === 1 && store.get(`ccmode:${OWNER}`) === "1", "C19 cc on again for the bridge-key section");
tells = await waSend("Bridge key task");
check(tells.length === 0 && ccMsgs().some(m => m.text === "Bridge key task" && m.state === "pending"),
  "C20 a third message queues pending for the bridge-key pull");

let rb = await runner("/api/setup/runner/ccpull", {}, "test-bridge");
check(rb.json && rb.json.ok && rb.json.messages.length === 1 && rb.json.messages[0].text === "Bridge key task",
  "C21 ccpull with the BRIDGE key succeeds and returns the pending message");
const IDB = rb.json.messages[0].id;
check(getRec(`ccmsg:${IDB}`).state === "picked", "C22 the bridge-key pull marks the message picked");

rb = await runner("/api/setup/runner/ccreply", { id: IDB, text: "BRIDGE KEY ANSWER" }, "test-bridge");
check(rb.json && rb.json.ok === true && getRec(`ccmsg:${IDB}`).state === "done" && getRec(`ccmsg:${IDB}`).reply === "BRIDGE KEY ANSWER",
  "C23 ccreply with the BRIDGE key posts the answer and lands the record done");

rb = await runner("/api/setup/runner/agentstep", {}, "test-bridge");
check(rb.status === 403, "C24 the bridge key on agentstep (non-cc runner endpoint) -> 403");

rb = await runner("/api/setup/runner/ccreply", { id: IDB, text: "x" }, "wrong-key");
check(rb.status === 403, "C25 ccreply with a wrong key -> 403");

rb = await call("POST", "/api/setup/runner/ccpull", {}, {});
check(rb.status === 403, "C26 ccpull with NO key -> 403");

delete env.CC_BRIDGE_KEY;
rb = await runner("/api/setup/runner/ccpull", {}, "test-bridge");
check(rb.status === 403, "C27 with CC_BRIDGE_KEY unset, the bridge key is rejected (behavior unchanged)");
env.CC_BRIDGE_KEY = "test-bridge";

// =====================================================================
// Picked-message recovery: stale picks (>10 min) are re-served
// ID2 is still "picked" (empty reply was refused in C14, never
// completed). ID1 and IDB are "done".
// =====================================================================
const setRec = (id, patch) => { const cur = getRec(`ccmsg:${id}`); store.set(`ccmsg:${id}`, JSON.stringify({ ...cur, ...patch })); };

// (1) Freshly picked is NOT re-served
setRec(ID2, { pickedAt: Date.now() });
r = await runner("/api/setup/runner/ccpull", {});
check(r.json && r.json.ok && r.json.messages.length === 0,
  "C29 a freshly picked record is NOT re-served");

// (2) Stale pick (>10 min) IS re-served once and re-marked fresh
const staleAt = Date.now() - 11 * 60 * 1000;
setRec(ID2, { pickedAt: staleAt });
r = await runner("/api/setup/runner/ccpull", {});
check(r.json && r.json.ok && r.json.messages.length === 1 && r.json.messages[0].id === ID2 && r.json.messages[0].text === "stop",
  "C30 a stale pick (>10 min) IS re-served");
const reRec = getRec(`ccmsg:${ID2}`);
check(reRec.state === "picked" && reRec.pickedAt > staleAt && (Date.now() - reRec.pickedAt) < 10000,
  "C31 the re-served record is re-marked picked with a fresh pickedAt");
r = await runner("/api/setup/runner/ccpull", {});
check(r.json && r.json.ok && r.json.messages.length === 0,
  "C32 the re-served record is NOT handed out again on the next pull (re-served once)");

// (3) Done is NEVER re-served, even with a very old pick time
setRec(ID1, { pickedAt: Date.now() - 60 * 60 * 1000 });
setRec(IDB, { pickedAt: Date.now() - 60 * 60 * 1000 });
setRec(ID2, { pickedAt: Date.now() });
r = await runner("/api/setup/runner/ccpull", {});
check(r.json && r.json.ok && r.json.messages.length === 0
  && getRec(`ccmsg:${ID1}`).state === "done" && getRec(`ccmsg:${IDB}`).state === "done",
  "C33 done records are NEVER re-served, even when their pick time is stale");

tells = await waSend("cc off");
check(store.get(`ccmode:${OWNER}`) !== "1", "C28 cleanup: cc mode off again");

console.log(fails ? `\n${fails} FAILURES` : "\nALL PASS");
process.exit(fails ? 1 : 0);
