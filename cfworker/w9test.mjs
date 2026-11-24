// w9test.mjs — Wave 9 (doors) proofs against the REAL Worker
// module: the door log route + putSetupDone's door surface.
//   T1: a runner doorlog POST lands in doorfail:<user> with the
//       provider/step/reason the flow reported.
//   T2: when the supervisor's watchdog settles a stalled chain,
//       the outcome note carries the newest matching door failure
//       ("(door: groq @ … — …)") — the supervisor surfaces the log.
//   T3: control — a settle with NO door failure keeps its note
//       clean (no "(door:" appended).
//   T4: a doorlog POST with the wrong runner key stores nothing.
import { readFileSync, writeFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

const SRC = readFileSync(new URL("./divya.js", import.meta.url), "utf8");
writeFileSync("/tmp/_divya_w9_under_test.mjs", SRC);
const worker = (await import(pathToFileURL("/tmp/_divya_w9_under_test.mjs").href)).default;

const m = new Map();
const kv = { async get(k, o) { const v = m.has(k) ? m.get(k) : null; if (v === null) return null; return o && o.type === "json" ? JSON.parse(v) : v; },
  async put(k, v) { m.set(k, String(v)); }, async delete(k) { m.delete(k); },
  async list(o = {}) { return { keys: [...m.keys()].filter(k => k.startsWith(o.prefix || "")).sort().map(name => ({ name })), list_complete: true }; } };
const env = { KV: kv, KEK: Buffer.alloc(32, 7).toString("base64"), GROQ_KEY: "gk", WA_TOKEN: "t", WA_PHONE_ID: "p", RUNNER_KEY: "rk-test", GH_TOKEN: "g" };
globalThis.fetch = async () => new Response("{}", { status: 500, headers: { "content-type": "application/json" } });

let pass = 0, fail = 0;
const ok = (name, cond, extra) => { if (cond) { pass++; console.log("PASS", name); } else { fail++; console.log("FAIL", name, extra !== undefined ? "— " + JSON.stringify(extra).slice(0, 300) : ""); } };
const ctx = { waitUntil(p) { this._p = Promise.resolve(p); }, passThroughOnException() {} };
async function tick() { const ps = []; await worker.scheduled({}, env, { waitUntil(p) { ps.push(Promise.resolve(p)); }, passThroughOnException() {} }); while (ps.length) await Promise.all(ps.splice(0, ps.length)); }

const U = "919999999996"; // doorlog + stalled-chain owner
const C = "919999999995"; // control owner (no door failures)
const now = Date.now();

// T1: the runner's job + its door failure.
await kv.put(`setupjob:jobw9`, JSON.stringify({ job: "jobw9", provider: "openrouter", user: U, state: "running", at: now, upd: now }));
const doorRes = await worker.fetch(new Request("https://w.test/api/setup/runner/doorlog?job=jobw9", { method: "POST", headers: { "x-runner-key": "rk-test", "content-type": "application/json" }, body: JSON.stringify({ provider: "openrouter", step: "api-key", reason: "Key kanipinchaledu — site layout marindhi (step: key creation)." }) }), env, ctx);
const doors = JSON.parse((await kv.get(`doorfail:${U}`)) || "[]");
ok("T1 doorlog POST accepted + stored", doorRes.status === 200 && doors.length === 1 && doors[0].provider === "openrouter" && doors[0].step === "api-key" && /layout/.test(doors[0].reason || ""), { status: doorRes.status, doors });

// T4: wrong key stores nothing.
const badRes = await worker.fetch(new Request("https://w.test/api/setup/runner/doorlog?job=jobw9", { method: "POST", headers: { "x-runner-key": "WRONG", "content-type": "application/json" }, body: JSON.stringify({ provider: "groq", step: "x", reason: "y" }) }), env, ctx);
const doors2 = JSON.parse((await kv.get(`doorfail:${U}`)) || "[]");
ok("T4 wrong runner key stores nothing", badRes.status !== 200 && doors2.length === 1, { status: badRes.status, n: doors2.length });

// T2: U's chain stalled at groq (signin pause, 40 min old — past
// the watchdog limit) WITH a groq door failure on record.
await kv.put(`doorfail:${U}`, JSON.stringify([...doors, { provider: "groq", step: "signin", reason: "Groq security wall (just a moment) — bot check", job: "jobG9", at: now - 60000 }]));
await kv.put(`setupchain:${U}`, JSON.stringify({ providers: ["groq"], done: [], failed: [], current: "jobG9", email: "u@example.com", at: now - 3600000 }));
await kv.put(`setupjob:jobG9`, JSON.stringify({ job: "jobG9", provider: "groq", user: U, state: "paused", pauseReason: "signin", pausedAt: now - 40 * 60000, upd: now - 40 * 60000, at: now - 3600000 }));
// T3 control: C's identical stall, no door failures.
await kv.put(`setupchain:${C}`, JSON.stringify({ providers: ["groq"], done: [], failed: [], current: "jobC9", email: "c@example.com", at: now - 3600000 }));
await kv.put(`setupjob:jobC9`, JSON.stringify({ job: "jobC9", provider: "groq", user: C, state: "paused", pauseReason: "signin", pausedAt: now - 40 * 60000, upd: now - 40 * 60000, at: now - 3600000 }));

await tick();

const finU = JSON.parse((await kv.get(`setupdone:${U}`)) || "{}");
ok("T2 settled note surfaces the door failure", typeof finU.note === "string" && finU.note.includes("(door: groq @ signin"), finU);
const finC = JSON.parse((await kv.get(`setupdone:${C}`)) || "{}");
ok("T3 control settle keeps a clean note", typeof finC.note === "string" && !finC.note.includes("(door:"), finC);

console.log(`\nw9test: ${pass} pass, ${fail} fail`);
process.exit(fail ? 1 : 0);
