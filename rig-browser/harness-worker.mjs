// v101 BROWSER-PARITY Worker harness — runs the REAL patched Worker in
// Node with a Map-backed KV and stubbed GitHub + LLM endpoints. Proves
// the whole browse protocol end to end: browse/start (record +
// browse.yml dispatch + busy guard), runner job fetch, brainstep
// (snapshot -> ONE parsed JSON action; garbage brain -> honest error),
// progress, result (answer stored), setup/status browse field, the
// chat report-once path, chat-started browse orders, and the
// pause/continue/stop/tc fallbacks acting on the browse job.
// Usage: node harness-worker.mjs <worker-file>
import { copyFileSync } from "node:fs";

const srcPath = process.argv[2];
if (!srcPath) { console.error("usage: node harness-worker.mjs <worker.mjs>"); process.exit(2); }
copyFileSync(srcPath, new URL("./worker-under-test.mjs", import.meta.url));
const worker = (await import("./worker-under-test.mjs")).default;

// ---------- KV stub ----------
const map = new Map();
const KV = {
  async get(k, type) { const v = map.has(k) ? map.get(k) : null; if (v === null) return null; if (type === "arrayBuffer") return v instanceof Uint8Array ? v.buffer.slice(v.byteOffset, v.byteOffset + v.byteLength) : new TextEncoder().encode(String(v)).buffer; return v instanceof Uint8Array ? new TextDecoder().decode(v) : v; },
  async put(k, v) { map.set(k, String(v)); },
  async delete(k) { map.delete(k); },
  async list({ prefix } = {}) { return { keys: [...map.keys()].filter(k => !prefix || k.startsWith(prefix)).map(name => ({ name })) }; },
};
const env = { KV, APP_KEK: Buffer.alloc(32, 7).toString("base64"), GOOGLE_CLIENT_ID: "cid", GOOGLE_CLIENT_SECRET: "csecret", OWNERS: "", FRIENDS: "", GH_TOKEN: "ghtest", GH_REPO: "o/r", RUNNER_KEY: "rk-test" };

// ---------- fetch stub ----------
const GSK = "gsk_GOODKEYaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
const GROQ_MODELS = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"];
let BRAIN = '{"action":"click","i":0}';
const dispatches = [];
globalThis.fetch = async (url, opts = {}) => {
  const u = String(url);
  const J = (o, st = 200) => new Response(JSON.stringify(o), { status: st, headers: { "content-type": "application/json" } });
  if (u.includes("api.github.com") && u.includes("/dispatches")) { dispatches.push({ u, body: JSON.parse(opts.body || "{}") }); return new Response(null, { status: 204 }); }
  if (u === "https://api.groq.com/openai/v1/models") return J({ data: GROQ_MODELS.map(id => ({ id })) });
  if (u === "https://api.groq.com/openai/v1/chat/completions") {
    let txt = "";
    try { txt = JSON.stringify(JSON.parse(opts.body || "{}").messages || []); } catch {}
    if (txt.includes("browser driver")) return J({ choices: [{ message: { content: BRAIN } }] });
    return J({ choices: [{ message: { content: "ok" } }] });
  }
  return J({ error: "unstubbed " + u }, 404);
};

// ---------- helpers ----------
const ctx = { waitUntil(p) { this._p = p; } };
async function call(method, path, { token, body, runner } = {}) {
  const req = new Request("https://divya-app.n8n00101.workers.dev" + path, {
    method, headers: { "content-type": "application/json", ...(token ? { authorization: "Bearer " + token } : {}), ...(runner ? { "x-runner-key": "rk-test" } : {}) },
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
async function withModel(u) {
  const r = await call("POST", "/api/model/save", { token: u.token, body: { name: "groq", key: GSK, consent: true } });
  if (!r.json?.ok) throw new Error("model save failed " + r.text);
}
const jobRec = job => { const v = map.get(`setupjob:${job}`); return v ? JSON.parse(v) : null; };

// ---------- 1. browse/start: record + dispatch + busy guard ----------
const u1 = await signup("browse1@example.com"); await withModel(u1);
const s1 = await call("POST", "/api/setup/browse/start", { token: u1.token, body: { task: "Open example.com and tell me the headline", url: "https://example.com" } });
T("1a browse/start ok", s1.json?.ok === true && !!s1.json?.job, s1.text.slice(0, 200));
const JOB = s1.json?.job;
const rec1 = jobRec(JOB);
T("1b record is a browse job, queued", !!rec1 && rec1.provider === "browse" && rec1.state === "queued" && rec1.startUrl === "https://example.com", JSON.stringify(rec1));
T("1c browse.yml dispatched with the job id", dispatches.some(d => d.u.includes("browse.yml") && d.body.inputs?.job === JOB), JSON.stringify(dispatches));
T("1d browsecur pointer set", (() => { try { return JSON.parse(map.get(`browsecur:${u1.n}`) || "{}").job === JOB; } catch { return false; } })());
const s2 = await call("POST", "/api/setup/browse/start", { token: u1.token, body: { task: "another task" } });
T("1e second start while busy -> honest busy error", s2.json?.ok === false && s2.json?.busy === true, s2.text.slice(0, 200));

// ---------- 2. runner protocol: job / progress / brainstep / result ----------
const gj = await call("GET", `/api/setup/runner/job?job=${JOB}`, { runner: true });
T("2a runner fetches the job", gj.json?.job?.provider === "browse" && gj.json?.job?.task?.includes("headline"), gj.text.slice(0, 200));
const pg = await call("POST", `/api/setup/runner/progress?job=${JOB}`, { runner: true, body: { job: JOB, state: "running", step: "Opening the site" } });
T("2b progress accepted", pg.json?.ok === true, pg.text.slice(0, 200));
const st1 = await call("GET", "/api/setup/status", { token: u1.token });
T("2c status carries browse (active, step)", st1.json?.browse?.active === true && /Opening/.test(st1.json?.browse?.note || st1.json?.browse?.step || "") && st1.json?.active === true, JSON.stringify(st1.json?.browse));
BRAIN = '{"action":"click","i":0}';
const bs = await call("POST", `/api/setup/runner/brainstep?job=${JOB}`, { runner: true, body: { job: JOB, goal: "tell me the headline", snapshot: { url: "https://example.com/", title: "Example Domain", text: "Example Domain This domain is for use in documentation examples.", elements: [{ i: 0, tag: "a", label: "Learn more", href: "https://www.iana.org/" }] }, history: [] } });
T("2d brainstep returns the parsed action", bs.json?.ok === true && bs.json?.action?.action === "click" && bs.json?.action?.i === 0, bs.text.slice(0, 300));
BRAIN = "Sorry, I cannot do that.";
const bs2 = await call("POST", `/api/setup/runner/brainstep?job=${JOB}`, { runner: true, body: { job: JOB, goal: "x", snapshot: { url: "https://example.com/", title: "", text: "", elements: [] }, history: [] } });
T("2e garbage brain reply -> honest brain error (runner will retry, not guess)", bs2.json?.ok === false && bs2.json?.error === "brain", bs2.text.slice(0, 200));
const rs = await call("POST", `/api/setup/runner/result?job=${JOB}`, { runner: true, body: { job: JOB, status: "done", answer: "The headline is: Example Domain" } });
T("2f result accepted", rs.json?.ok === true, rs.text.slice(0, 200));
const rec2 = jobRec(JOB);
T("2g answer + terminal state stored on the job", rec2?.answer === "The headline is: Example Domain" && rec2?.state === "done", JSON.stringify(rec2));
const st2 = await call("GET", "/api/setup/status", { token: u1.token });
T("2h status shows the finished browse with its answer", st2.json?.browse?.active === false && /Example Domain/.test(st2.json?.browse?.answer || ""), JSON.stringify(st2.json?.browse));

// ---------- 3. chat reports the result exactly once ----------
const t1 = await call("POST", "/api/assist", { token: u1.token, body: { text: "hi" } });
T("3a next chat message reports the browse answer", /Example Domain/.test(t1.json?.reply || ""), (t1.json?.reply || "").slice(0, 200));
T("3b job marked reported", jobRec(JOB)?.reported === true);
const t2 = await call("POST", "/api/assist", { token: u1.token, body: { text: "hi again" } });
T("3c not repeated on the following message", !/Example Domain/.test(t2.json?.reply || ""), (t2.json?.reply || "").slice(0, 200));

// ---------- 4. chat-started browse + pause/tc/continue/stop fallbacks ----------
const u2 = await signup("browse2@example.com"); await withModel(u2);
const c1 = await call("POST", "/api/assist", { token: u2.token, body: { text: "open https://en.wikipedia.org and find the capital of Norway" } });
T("4a chat order starts a browse", c1.json?.browse_started === true && !!c1.json?.browse_job, JSON.stringify(c1.json).slice(0, 300));
const JOB2 = c1.json?.browse_job;
T("4b reply says the browser started (no false done claim)", /browser/i.test(c1.json?.reply || ""), (c1.json?.reply || "").slice(0, 200));
const pz = await call("POST", "/api/setup/pause", { token: u2.token, body: { reason: "signin" } });
T("4c pause falls back to the browse job", pz.json?.ok === true && jobRec(JOB2)?.state === "paused", pz.text.slice(0, 200) + " " + JSON.stringify(jobRec(JOB2)?.state));
const fr = await call("POST", `/api/setup/runner/tcframe?job=${JOB2}`, { runner: true, body: { job: JOB2, img: "AAAA", url: "https://en.wikipedia.org/" } });
T("4d runner frame accepted", fr.json?.ok === true, fr.text.slice(0, 200));
const tc = await call("GET", "/api/setup/tc", { token: u2.token });
T("4e live view serves the browse job's frame", tc.json?.active === true && tc.json?.img === "AAAA", JSON.stringify(tc.json).slice(0, 200));
const ti = await call("POST", "/api/setup/tc/input", { token: u2.token, body: { type: "click", x: 10, y: 20 } });
T("4f tc input accepted for the browse job", ti.json?.ok === true, ti.text.slice(0, 200));
const gj2 = await call("GET", `/api/setup/runner/job?job=${JOB2}`, { runner: true });
T("4g runner receives the queued input", Array.isArray(gj2.json?.job?.tcInputs) && gj2.json.job.tcInputs.length === 1 && gj2.json.job.tcInputs[0].type === "click", JSON.stringify(gj2.json?.job?.tcInputs));
const ct = await call("POST", "/api/setup/continue", { token: u2.token, body: {} });
T("4h continue resumes the browse job", ct.json?.ok === true && jobRec(JOB2)?.state === "running", JSON.stringify(jobRec(JOB2)?.state));
const sp = await call("POST", "/api/setup/stop", { token: u2.token, body: {} });
T("4i stop halts the browse job", sp.json?.ok === true && jobRec(JOB2)?.state === "stopped", JSON.stringify(jobRec(JOB2)?.state));

// ---------- 5. chat stop word + non-browse chat unaffected ----------
const u3 = await signup("browse3@example.com"); await withModel(u3);
const c2 = await call("POST", "/api/assist", { token: u3.token, body: { text: "go to example.com and read the headline" } });
const JOB3 = c2.json?.browse_job;
T("5a domain + read verb also starts a browse", c2.json?.browse_started === true && !!JOB3, JSON.stringify(c2.json).slice(0, 300));
const c3 = await call("POST", "/api/assist", { token: u3.token, body: { text: "stop" } });
T("5b bare 'stop' stops the browse and says so", jobRec(JOB3)?.state === "stopped" && /🌐/.test(c3.json?.reply || ""), JSON.stringify(jobRec(JOB3)?.state) + " / " + (c3.json?.reply || "").slice(0, 120));
const c4 = await call("POST", "/api/assist", { token: u3.token, body: { text: "what is 2 plus 2?" } });
T("5c ordinary chat is not hijacked into a browse", c4.json?.browse_started !== true, JSON.stringify(c4.json).slice(0, 200));

console.log(`\n== ${pass} passed, ${fail} failed ==`);
process.exit(fail ? 1 : 0);
