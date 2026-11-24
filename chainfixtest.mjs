// v104 chain-robustness Worker rig (in the acctcreatetest style:
// in-memory KV, stubbed fetch, real fetch handler).
//
// Proves the fixes from the 2026-11-16 live 22-provider run:
//  Fix 7 — a retried setup/start returns the SAME chain (startId, and
//          the same-provider-set dropped-response shape), never a
//          duplicate, never alreadyRunning.
//  Fix 2 — the watchdog respects real GitHub queue times: a run still
//          QUEUED is never declared stalled (the silence clock runs
//          from run START); a completed run still stalls normally.
//          setup/status reports queued:true for a queued run.
//  Fix 1 — a pause past its per-kind budget is SKIPPED (recorded in
//          chain.skipped + failReason) and the chain advances; a
//          fresh pause is not skipped; a pause whose user input WAS
//          delivered is not skipped.
//  Fix 3 — the profile POST refuses a stale job (409) and accepts the
//          live chain job / current browse job (200).
//  Fix 4 — runner/linkbad marks a fed link consumed; the Gmail feed
//          never re-feeds it and feeds the NEWER mail's link instead.
//  Fix 6 — setup/stop retains the chain's per-provider failReason in
//          setupdone instead of discarding it with the chain.
import path from "node:path";
import { pathToFileURL } from "node:url";

const HERE = path.dirname(new URL(import.meta.url).pathname);
let fails = 0;
function check(cond, label) {
  console.log((cond ? "PASS " : "FAIL ") + label);
  if (!cond) fails++;
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const store = new Map();
const KV = {
  async get(k) { return store.has(k) ? store.get(k) : null; },
  async put(k, v) { store.set(k, String(v)); },
  async delete(k) { store.delete(k); },
  async list() { return { keys: [...store.keys()].map(name => ({ name })) }; },
  async mget(keys) { const arr = Array.isArray(keys) ? keys : [keys]; const o = {}; for (const k of arr) o[k] = store.has(k) ? store.get(k) : null; return o; },
};

// --- stubbed network: GitHub Actions + Gmail -------------------------
let runSeq = 1000;
const ghRunsById = new Map();
let gmailMsgs = [];
function gmailFetch(u) {
  if (/\/messages\?/.test(u)) return Response.json({ messages: gmailMsgs.map((x) => ({ id: x.id })) });
  const m = u.match(/\/messages\/([\w-]+)/);
  if (m) {
    const g = gmailMsgs.find((x) => x.id === m[1]);
    if (!g) return new Response("nf", { status: 404 });
    const data = Buffer.from(g.body, "utf8").toString("base64url");
    return Response.json({ id: g.id, internalDate: String(g.internalDate), payload: { mimeType: "text/plain", headers: [{ name: "From", value: g.from }, { name: "Subject", value: g.subject }], body: { data } } });
  }
  return new Response("nf", { status: 404 });
}
globalThis.fetch = async (url) => {
  const u = String(url);
  if (u.includes("/dispatches")) {
    const id = ++runSeq;
    const nowIso = new Date().toISOString();
    ghRunsById.set(id, { status: "queued", conclusion: "", created_at: nowIso, run_started_at: nowIso });
    return new Response(null, { status: 204 });
  }
  if (u.includes("/actions/workflows/setup.yml/runs")) {
    const runs = [...ghRunsById.entries()].map(([id, r]) => ({ id, created_at: r.created_at, status: r.status })).sort((a, b) => b.id - a.id);
    return Response.json({ workflow_runs: runs });
  }
  const m = u.match(/\/actions\/runs\/(\d+)/);
  if (m) {
    const r = ghRunsById.get(+m[1]);
    if (r) return Response.json({ status: r.status, conclusion: r.conclusion, run_started_at: r.run_started_at, created_at: r.created_at });
    return new Response("nf", { status: 404 });
  }
  if (u.includes("gmail.googleapis.com")) return gmailFetch(u);
  return new Response("stub-404", { status: 404 });
};

const NUM = "919876543210";
const TOKEN = "a".repeat(48);
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
const getRec = (k) => { try { return JSON.parse(store.get(k) || "null"); } catch { return null; } };
const putRec = (k, v) => store.set(k, JSON.stringify(v));
const CHAIN = `setupchain:${NUM}`;
const DONE = `setupdone:${NUM}`;

// =====================================================================
// GROUP A — Fix 7: startSetup idempotency + Fix 2 run capture
// =====================================================================
let r = await call("POST", "/api/setup/start", { email: "a@b.co", providers: ["groq", "together"], startId: "tap-1" });
check(r.json && r.json.ok === true && !!r.json.job, "A1 first start ok with a job");
const J1 = r.json.job;
let chain = getRec(CHAIN);
check(chain && chain.startId === "tap-1" && chain.current === J1, "A2 chain carries the startId and the current job");
const j1 = getRec(`setupjob:${J1}`);
check(j1 && j1.ghRun && ghRunsById.has(j1.ghRun.id), "A3 dispatched GitHub run captured on the job (ghRun)");

r = await call("POST", "/api/setup/start", { email: "a@b.co", providers: ["groq", "together"], startId: "tap-1" });
check(r.json && r.json.ok === true && r.json.idempotent === true && r.json.job === J1, "A4 retried start (same startId) returns the SAME chain/job");
chain = getRec(CHAIN);
check(chain && chain.current === J1 && (chain.providers || []).length === 2, "A5 no duplicate chain was created");

r = await call("POST", "/api/setup/start", { email: "a@b.co", providers: ["groq", "together"] });
check(r.json && r.json.ok === true && r.json.idempotent === true && r.json.job === J1, "A6 dropped-response retry (same providers, no startId) is idempotent too");

r = await call("POST", "/api/setup/start", { email: "a@b.co", providers: ["groq"], startId: "tap-9" });
check(r.json && r.json.alreadyRunning === true, "A7 a genuinely different start still gets alreadyRunning");

r = await call("POST", "/api/setup/stop", {});
check(r.json && r.json.ok === true && !getRec(CHAIN), "A8 stop clears the chain");

// =====================================================================
// GROUP B — Fix 2: watchdog respects queue times
// =====================================================================
r = await call("POST", "/api/setup/start", { email: "a@b.co", providers: ["groq"], startId: "tap-2" });
const J2 = r.json.job;
const j2 = getRec(`setupjob:${J2}`);
const R2 = j2.ghRun.id;
j2.state = "queued"; j2.upd = Date.now() - 36 * 60 * 1000; // dispatched 36 min ago, silent since
putRec(`setupjob:${J2}`, j2);
ghRunsById.get(R2).status = "queued";

r = await call("GET", "/api/setup/status");
check(r.json && r.json.state === "running" && r.json.queued === true, "B1 queued run (36 min) reported running + queued, NOT stalled");
check(!!getRec(CHAIN), "B2 chain survives while its run is queued");

ghRunsById.get(R2).status = "in_progress";
ghRunsById.get(R2).run_started_at = new Date(Date.now() - 2 * 60 * 1000).toISOString();
r = await call("GET", "/api/setup/status");
check(r.json && r.json.state === "running" && !!getRec(CHAIN), "B3 in-progress run: silence clock runs from run start — not stalled");

ghRunsById.get(R2).status = "completed";
ghRunsById.get(R2).conclusion = "failure";
r = await call("GET", "/api/setup/status");
check(r.json && r.json.finished && r.json.finished.state === "stalled", "B4 completed run + silent runner still stalls (control)");
check(!getRec(CHAIN), "B5 stalled chain is cleared as before");

// =====================================================================
// GROUP C — Fix 1: pause-skip advances the chain
// =====================================================================
r = await call("POST", "/api/setup/start", { email: "a@b.co", providers: ["groq", "together"], startId: "tap-3" });
const J3 = r.json.job;
r = await runner("POST", `/api/setup/runner/progress?job=${J3}`, { state: "paused", step: "captcha", reason: "captcha", note: "Paused: IMAGE CAPTCHA" });
check(r.json && r.json.ok === true, "C1 captcha pause recorded");
const j3 = getRec(`setupjob:${J3}`);
j3.pausedAt = Date.now() - 26 * 60 * 1000; // captcha budget is 25 min
putRec(`setupjob:${J3}`, j3);

r = await call("GET", "/api/setup/status");
chain = getRec(CHAIN);
check(chain && (chain.failed || []).includes("groq"), "C2 over-budget captcha pause: provider marked failed");
check(chain && chain.skipped && chain.skipped.groq && chain.skipped.groq.kind === "captcha", "C3 skip recorded with its pause kind (chain.skipped)");
check(chain && chain.current && chain.current !== J3, "C4 chain ADVANCED to the next provider");
check(getRec(`setupjob:${J3}`).state === "stopped" && getRec(`setupjob:${J3}`).step === "paused-skipped", "C5 skipped job is stopped so its runner exits");
const J4 = chain.current;

r = await runner("POST", `/api/setup/runner/progress?job=${J4}`, { state: "paused", step: "google-signin", reason: "signin", note: "Paused: Google sign-in" });
r = await call("GET", "/api/setup/status");
chain = getRec(CHAIN);
check(chain && chain.current === J4 && !(chain.failed || []).includes("together"), "C6 a FRESH pause is not skipped");

const j4 = getRec(`setupjob:${J4}`);
j4.pausedAt = Date.now() - 20 * 60 * 1000; // beyond the sms budget (10 min)
j4.pauseReason = "sms";
j4.awaiting = { id: "askX", kind: "otp", provider: "together", prompt: "code?", at: Date.now(), expires: Date.now() + 600000, attempts: 1 };
j4.userInput = { askId: "askX", value: "123456", at: Date.now() };
putRec(`setupjob:${J4}`, j4);
r = await call("GET", "/api/setup/status");
chain = getRec(CHAIN);
check(chain && chain.current === J4, "C7 a pause whose user input WAS delivered is not skipped");

const j4b = getRec(`setupjob:${J4}`);
delete j4b.userInput;
putRec(`setupjob:${J4}`, j4b);
r = await call("GET", "/api/setup/status");
const chainAfterC = getRec(CHAIN);
check(!chainAfterC || chainAfterC.startId !== "tap-3", "C8 with no input delivered the skip fires and the tap-3 chain ENDS (a later chain, if any, is the pre-existing 6h-throttled auto-provision, not this one)");
const finC = getRec(DONE);
check(finC && finC.skipped && finC.skipped.groq && finC.skipped.together && finC.skipped.together.kind === "sms", "C9 setupdone retains both skips with kinds");
check(finC && finC.failReason && /paused-sms/.test(finC.failReason.together || ""), "C10 setupdone failReason names the paused-sms skip");
if (chainAfterC) await call("POST", "/api/setup/stop", {}); // clear any auto-provision chain for group D (AFTER reading finC — a stop rewrites setupdone)

// =====================================================================
// GROUP D — Fix 3: profile POST zombie backstop
// =====================================================================
putRec(`browsecur:${NUM}`, { job: "browsejob1" });
putRec(`setupjob:browsejob1`, { job: "browsejob1", user: NUM, provider: "browse", state: "running", at: Date.now(), upd: Date.now() });
putRec(`setupjob:stalejob`, { job: "stalejob", user: NUM, provider: "browse", state: "running", at: Date.now(), upd: Date.now() });
const PROF = { profile: { cookies: [], origins: [] } };
r = await runner("POST", "/api/setup/runner/profile?job=browsejob1", PROF);
check(r.status === 200 && r.json && r.json.stored === true, "D1 current browse job may save the profile");
r = await runner("POST", "/api/setup/runner/profile?job=stalejob", PROF);
check(r.status === 409, "D2 a stale job's profile push is refused (409)");

// The seeded browse job must not be "running" here: the v103 guard
// (correctly) refuses a profile-mode chain start over a live browse.
putRec(`setupjob:browsejob1`, { job: "browsejob1", user: NUM, provider: "browse", state: "done", at: Date.now(), upd: Date.now() });
r = await call("POST", "/api/setup/start", { email: "a@b.co", providers: ["groq"], startId: "tap-4" });
const J5 = r.json.job;
r = await runner("POST", `/api/setup/runner/profile?job=${J5}`, PROF);
check(r.status === 200, "D3 the live chain job may save the profile");
r = await runner("POST", "/api/setup/runner/profile?job=browsejob1", PROF);
check(r.status === 409, "D4 while a chain runs, a non-current job is refused (409)");
r = await call("POST", "/api/setup/stop", {});

// =====================================================================
// GROUP E — Fix 4: a rejected fed link is never re-fed
// =====================================================================
putRec(`tok:${NUM}:google`, { access_token: "ya29.test", at: Date.now(), expires_in: 3600, who: "a@b.co" });
const BAD = "https://auth.stytch.com/verify?token=deadbeef189";
const GOOD = "https://auth.stytch.com/verify?token=fresh234";
putRec(`setupjob:job6`, { job: "job6", user: NUM, provider: "groq", state: "running", verifyLink: BAD, at: Date.now(), upd: Date.now() });
r = await runner("POST", "/api/setup/runner/linkbad?job=job6", { kind: "link" });
check(r.json && r.json.ok === true && r.json.consumed === true, "E1 linkbad accepts the rejection report");
const j6 = getRec(`setupjob:job6`);
check(j6 && (j6.fedBad || []).includes(BAD) && !j6.verifyLink && j6.state === "paused" && j6.pauseReason === "email", "E2 link marked consumed, job back on its email pause");

gmailMsgs = [{ id: "m1", from: "Groq <noreply@groq.com>", subject: "Your login request to Groq", internalDate: Date.now(), body: "Sign in here: " + BAD }];
r = await runner("GET", "/api/setup/runner/job?job=job6");
const j6b = getRec(`setupjob:job6`);
check(j6b && !j6b.verifyLink, "E3 the feed does NOT re-feed the rejected link");

gmailMsgs = [{ id: "m2", from: "Groq <noreply@groq.com>", subject: "Your login request to Groq", internalDate: Date.now(), body: "Sign in here: " + GOOD }];
j6b.mailFetchAt = 0; // the 45 s feed throttle, elapsed
putRec(`setupjob:job6`, j6b);
r = await runner("GET", "/api/setup/runner/job?job=job6");
const j6c = getRec(`setupjob:job6`);
check(j6c && j6c.verifyLink === GOOD && j6c.state === "running", "E4 the feed delivers the NEWER mail's link instead");

// =====================================================================
// GROUP F — Fix 6: stop retains per-provider terminal reasons
// =====================================================================
r = await call("POST", "/api/setup/start", { email: "a@b.co", providers: ["groq", "together"], startId: "tap-5" });
const J7 = r.json.job;
r = await runner("POST", `/api/setup/runner/progress?job=${J7}`, { state: "failed", step: "error", note: "Exa-class silent death reason" });
await sleep(150); // deferAdvance settles
chain = getRec(CHAIN);
check(chain && chain.failReason && /silent death/.test(chain.failReason.groq || ""), "F1 terminal reason recorded on the chain at failure time");
check(chain && chain.current && chain.current !== J7, "F2 the failure advanced the chain");
r = await call("POST", "/api/setup/stop", {});
const finF = getRec(DONE);
check(finF && finF.state === "stopped" && finF.failReason && /silent death/.test(finF.failReason.groq || ""), "F3 setup/stop RETAINS failReason in setupdone (was discarded with the chain)");
check(!getRec(CHAIN), "F4 chain deleted on stop as before");

// =====================================================================
// GROUP G — Shadow W1 / census C-02: object-shaped chain.skipped must
// never break the failure paths (pre-fix: (chain.skipped || [])
// .includes(p) threw a TypeError inside the progress handler's failed
// branch and chainFailAdvance, and the count reporters printed NaN).
// =====================================================================
r = await call("POST", "/api/setup/start", { email: "a@b.co", providers: ["groq", "together", "cohere"], startId: "tap-g" });
const JG1 = r.json.job;
r = await runner("POST", `/api/setup/runner/progress?job=${JG1}`, { state: "paused", step: "captcha", reason: "captcha", note: "Paused: IMAGE CAPTCHA" });
const jg1 = getRec(`setupjob:${JG1}`);
jg1.pausedAt = Date.now() - 26 * 60 * 1000; // captcha budget is 25 min
putRec(`setupjob:${JG1}`, jg1);
r = await call("GET", "/api/setup/status");
chain = getRec(CHAIN);
check(chain && chain.skipped && !Array.isArray(chain.skipped) && chain.skipped.groq && chain.skipped.groq.kind === "captcha", "G1 pause-skip wrote the OBJECT skipped shape");
const JG2 = chain.current;
check(!!JG2 && JG2 !== JG1, "G2 chain advanced past the skip");
r = await runner("POST", `/api/setup/runner/progress?job=${JG2}`, { state: "failed", step: "error", note: "door exploded" });
check(r.json && r.json.ok === true, "G3 failed progress post accepted with object skipped on the chain (no TypeError)");
await sleep(150); // deferAdvance settles
chain = getRec(CHAIN);
check(chain && (chain.failed || []).includes("together"), "G4 the failure was recorded (the failed branch completed)");
check(chain && chain.current && chain.current !== JG2, "G5 the chain advanced past the failure");
check(chain && chain.skipped && chain.skipped.groq && chain.skipped.groq.kind === "captcha", "G6 the skip record survived the failure intact");
const JG3 = chain.current;
r = await runner("POST", `/api/setup/runner/progress?job=${JG3}`, { state: "failed", step: "error", note: "door exploded too" });
await sleep(150);
const finG = getRec(DONE);
check(finG && finG.state === "failed" && finG.skipped && finG.skipped.groq && finG.skipped.groq.kind === "captcha", "G7 finalize preserved the object skipped shape + kind");
check(!getRec(CHAIN), "G8 chain cleared at finalize");

console.log(fails === 0 ? "\nALL PASS" : `\n${fails} FAILURES`);
process.exit(fails === 0 ? 0 : 1);
