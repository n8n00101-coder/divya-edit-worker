// w4test.mjs — Wave 4 (supervisor cron) proofs against the REAL
// Worker module, driven through the real scheduled() entry with a
// KV stub. Scenarios:
//   T1 C-10: a chain whose runner died mid-pause (signin pause,
//      20 min old — past the 15-min budget, inside the 30-min
//      watchdog limit) is advanced by the cron tick ALONE: the
//      provider is recorded skipped, the dead job is stopped, and
//      the chain moves on / settles — no user poll anywhere.
//   T2 C-21: verify:awaiting reads "0" (desynced) while another
//      chain's job sits paused on an email wait — after one tick
//      the marker is recomputed from live job state: "1".
//   T3 C-16: structural — exactly one bare setupdone: put exists in
//      the module, inside putSetupDone; every terminal writer
//      routes through the verified-write helper.
import { readFileSync, writeFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

const SRC = readFileSync(new URL("./divya.js", import.meta.url), "utf8");
writeFileSync("/tmp/_divya_w4_under_test.mjs", SRC);
const worker = (await import(pathToFileURL("/tmp/_divya_w4_under_test.mjs").href)).default;

const m = new Map();
const kv = { async get(k, o) { const v = m.has(k) ? m.get(k) : null; if (v === null) return null; return o && o.type === "json" ? JSON.parse(v) : v; },
  async put(k, v) { m.set(k, String(v)); }, async delete(k) { m.delete(k); },
  async list(o = {}) { return { keys: [...m.keys()].filter(k => k.startsWith(o.prefix || "")).sort().map(name => ({ name })), list_complete: true }; } };
const env = { KV: kv, KEK: Buffer.alloc(32, 7).toString("base64"), GROQ_KEY: "gk", WA_TOKEN: "t", WA_PHONE_ID: "p", RUNNER_KEY: "rk-test", GH_TOKEN: "g" };
globalThis.fetch = async () => new Response("{}", { status: 500, headers: { "content-type": "application/json" } });

let pass = 0, fail = 0;
const ok = (name, cond, extra) => { if (cond) { pass++; console.log("PASS", name); } else { fail++; console.log("FAIL", name, extra !== undefined ? "— " + JSON.stringify(extra).slice(0, 300) : ""); } };
async function tick() { const ps = []; await worker.scheduled({}, env, { waitUntil(p) { ps.push(Promise.resolve(p)); }, passThroughOnException() {} }); while (ps.length) await Promise.all(ps.splice(0, ps.length)); }

const T = "919999999998"; // dead-runner chain owner (test identity)
const E = "919999999997"; // email-wait chain owner (test identity)
const now = Date.now();
// T1: groq paused on signin 20 min ago; the runner is dead (it will
// never post again). cohere remains after groq.
await kv.put(`setupchain:${T}`, JSON.stringify({ providers: ["groq", "cohere"], done: [], failed: [], current: "jobD1", email: "t@example.com", at: now - 3600000 }));
await kv.put(`setupjob:jobD1`, JSON.stringify({ job: "jobD1", provider: "groq", user: T, state: "paused", pauseReason: "signin", pausedAt: now - 20 * 60000, upd: now - 20 * 60000, at: now - 3600000 }));
// T2: marker desynced to "0"; E's job is paused on an email wait.
await kv.put("verify:awaiting", "0");
await kv.put(`setupchain:${E}`, JSON.stringify({ providers: ["gemini"], done: [], failed: [], current: "jobE1", email: "e@example.com", at: now - 3600000 }));
await kv.put(`setupjob:jobE1`, JSON.stringify({ job: "jobE1", provider: "gemini", user: E, state: "paused", pauseReason: "email", verifyWait: true, pausedAt: now - 5 * 60000, upd: now - 5 * 60000, at: now - 3600000 }));

await tick();

const j1 = JSON.parse((await kv.get("setupjob:jobD1")) || "{}");
const chainT = await kv.get(`setupchain:${T}`);
const chainTObj = chainT ? JSON.parse(chainT) : null;
const finT = await kv.get(`setupdone:${T}`);
ok("T1 dead job stopped by the tick alone", j1.state === "stopped" && j1.step === "paused-skipped", j1);
ok("T1b chain advanced past groq (skip recorded) or settled with an outcome", (!!chainTObj && !!(chainTObj.skipped || {}).groq && chainTObj.current !== "jobD1") || !!finT, { chain: chainTObj, fin: !!finT });
ok("T2 verify:awaiting recomputed from live state", (await kv.get("verify:awaiting")) === "1", await kv.get("verify:awaiting"));

const puts = (SRC.match(/KV\.put\(`setupdone:/g) || []).length;
ok("T3 exactly one bare setupdone: put (inside putSetupDone)", puts === 1 && SRC.includes("async function putSetupDone"), { puts });

console.log(`\nw4test: ${pass} pass, ${fail} fail`);
process.exit(fail ? 1 : 0);
