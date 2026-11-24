// directortest.mjs — Director Layer Worker-side proofs against
// the REAL Worker module: the agentdirector merge route, the
// agentpage publish route, and the public /p/<job> page route.
//   T1: plan -> check -> review POSTs merge onto rec.director in
//       order; the record read back holds all three.
//   T2: a check before any plan is refused (400) and stores
//       nothing.
//   T3: a wrong runner key is refused (403) and stores nothing.
//   T4: a sync POST replaces the director state wholesale
//       (terminal-sync shape), capped and cleaned.
//   T5: a malformed plan (step without acceptance) is refused.
//   T6: posts against a TERMINAL record are swallowed — the
//       record's director state is never rewritten after settle.
//   T7: agentpage stores the page and returns the /p/<job> URL;
//       GET /p/<job> serves the exact HTML as text/html; an
//       unknown job 404s.
import { readFileSync, writeFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

const SRC = readFileSync(new URL("./divya.js", import.meta.url), "utf8");
writeFileSync("/tmp/_divya_director_under_test.mjs", SRC);
const worker = (await import(pathToFileURL("/tmp/_divya_director_under_test.mjs").href)).default;

const m = new Map();
const kv = { async get(k, o) { const v = m.has(k) ? m.get(k) : null; if (v === null) return null; return o && o.type === "json" ? JSON.parse(v) : v; },
  async put(k, v) { m.set(k, String(v)); }, async delete(k) { m.delete(k); },
  async list(o = {}) { return { keys: [...m.keys()].filter(k => k.startsWith(o.prefix || "")).sort().map(name => ({ name })), list_complete: true }; } };
const env = { KV: kv, KEK: Buffer.alloc(32, 7).toString("base64"), GROQ_KEY: "gk", WA_TOKEN: "t", WA_PHONE_ID: "p", RUNNER_KEY: "rk-test", GH_TOKEN: "g" };
globalThis.fetch = async () => new Response("{}", { status: 500, headers: { "content-type": "application/json" } });

let pass = 0, fail = 0;
const ok = (name, cond, extra) => { if (cond) { pass++; console.log("PASS", name); } else { fail++; console.log("FAIL", name, extra !== undefined ? "— " + JSON.stringify(extra).slice(0, 300) : ""); } };
const ctx = { waitUntil(p) { this._p = Promise.resolve(p); }, passThroughOnException() {} };

const J = "dd100000000000000001";
const now = Date.now();
await kv.put(`setupjob:${J}`, JSON.stringify({ job: J, provider: "agent", flow: "agent", user: "directortest", task: "build a focus timer app", state: "running", step: "starting", note: "", at: now, upd: now, directorRequired: true }));

const post = (route, body, key = "rk-test") => worker.fetch(new Request(`https://w.test/api/setup/runner/${route}?job=${J}`, { method: "POST", headers: { "x-runner-key": key, "content-type": "application/json" }, body: JSON.stringify(body) }), env, ctx);
const rec = async () => JSON.parse(await kv.get(`setupjob:${J}`));

const PLAN = { vision: "A live focus-timer web app for anyone doing deep work; good = the page loads at a public URL and the timer counts down from 25:00.", steps: [{ title: "Write index.html", acceptance: "index.html exists with timer markup" }, { title: "Publish + verify", acceptance: "publish returns a URL and a fetch of it shows the timer" }], risks: ["publish route may reject the page"] };
const CHECK = { step: 1, verdict: "pass", evidence: "file_write ok; re-read shows the timer markup", at: now };
const REVIEW = { verdict: "deliver", summary: "Page fetched back live; matches the vision.", defects: [], at: now };

// T2 first (order matters): a check with no plan on record.
const early = await post("agentdirector", { kind: "check", data: CHECK });
ok("T2 check before plan refused, nothing stored", early.status === 400 && !(await rec()).director, { status: early.status });

// T1: the full sequence merges.
const r1 = await post("agentdirector", { kind: "plan", data: PLAN });
const r2 = await post("agentdirector", { kind: "check", data: CHECK });
const r3 = await post("agentdirector", { kind: "review", data: REVIEW });
const rec1 = await rec();
ok("T1 plan/check/review merged onto rec.director",
  r1.status === 200 && r2.status === 200 && r3.status === 200
  && rec1.director && rec1.director.plan.vision.startsWith("A live focus-timer")
  && rec1.director.plan.steps.length === 2
  && rec1.director.checks.length === 1 && rec1.director.checks[0].verdict === "pass"
  && rec1.director.reviews.length === 1 && rec1.director.reviews[0].verdict === "deliver",
  { director: rec1.director });

// T3: wrong key.
const before = JSON.stringify((await rec()).director);
const bad = await post("agentdirector", { kind: "check", data: { step: 2, verdict: "pass", evidence: "should never land" } }, "WRONG");
ok("T3 wrong runner key refused, nothing stored", bad.status === 403 && JSON.stringify((await rec()).director) === before, { status: bad.status });

// T4: sync replaces wholesale.
const sync = await post("agentdirector", { kind: "sync", data: { plan: PLAN, checks: [CHECK, { step: 2, verdict: "fail", evidence: "fetch showed a blank page", at: now }], reviews: [REVIEW] } });
const rec4 = await rec();
ok("T4 sync replaces the director state", sync.status === 200 && rec4.director.checks.length === 2 && rec4.director.checks[1].verdict === "fail" && rec4.director.reviews.length === 1, { director: rec4.director });

// T5: malformed plan refused.
const badPlan = await post("agentdirector", { kind: "plan", data: { vision: "x".repeat(20), steps: [{ title: "no acceptance here" }] } });
ok("T5 malformed plan refused", badPlan.status === 400, { status: badPlan.status });

// T7: publish + serve (before T6 settles the record).
const HTML = "<!doctype html><html><head><title>Focus Timer</title></head><body><div id=\"t\">25:00</div></body></html>";
const pub = await post("agentpage", { html: HTML });
const pubBody = await pub.json().catch(() => ({}));
const pageRes = await worker.fetch(new Request(`https://w.test/p/${J}`, { method: "GET" }), env, ctx);
const pageText = await pageRes.text();
const missRes = await worker.fetch(new Request("https://w.test/p/dd199999999999999999", { method: "GET" }), env, ctx);
ok("T7 publish returns URL; /p/<job> serves the exact HTML; unknown 404s",
  pub.status === 200 && typeof pubBody.url === "string" && pubBody.url.endsWith(`/p/${J}`)
  && pageRes.status === 200 && pageText === HTML
  && (pageRes.headers.get("content-type") || "").includes("text/html")
  && missRes.status === 404,
  { pub: pub.status, url: pubBody.url, page: pageRes.status, miss: missRes.status });

// T6: terminal records swallow director posts.
const settled = await rec();
settled.state = "done";
await kv.put(`setupjob:${J}`, JSON.stringify(settled));
const late = await post("agentdirector", { kind: "check", data: { step: 2, verdict: "pass", evidence: "too late" } });
const rec6 = await rec();
ok("T6 terminal record swallows director posts",
  late.status === 200 && rec6.director.checks.length === 2,
  { status: late.status, checks: (rec6.director.checks || []).length });

console.log(`\n${pass} passed, ${fail} failed`);
if (fail) process.exit(1);
console.log("DIRECTORTEST.MJS: ALL PASS");
