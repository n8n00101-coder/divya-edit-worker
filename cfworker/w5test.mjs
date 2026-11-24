// w5test.mjs — Wave 5 (reporter truth: C-11 / C-18) proofs against
// the REAL Worker module via the real WA webhook + scheduled entry.
//   R1: mixed grants (one healthy, one expired) — the connections
//       reply claims Gmail reading for the healthy one AND names
//       the expired one as expired + reconnect.
//   R2: ONLY an expired Gmail grant — the reply must NOT carry the
//       old unconditional "Gmail kuda chadhavagalanu" claim; it
//       names the expiry + the remedy.
//   R3: legacy-only keyspace (tok: slots, no gaccts: index) — the
//       derived entry is "unknown", so no Gmail health claim; the
//       reply says the state is unconfirmed (C-18).
//   R4: mail feed over an expired grant — the job's mailFetch
//       becomes "gmail-expired" (not "no-gmail-token") and the
//       dead-outcome counter increments (fail-fast class kept).
import { readFileSync, writeFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

const SRC = readFileSync(new URL("./divya.js", import.meta.url), "utf8");
writeFileSync("/tmp/_divya_w5_under_test.mjs", SRC);
const worker = (await import(pathToFileURL("/tmp/_divya_w5_under_test.mjs").href)).default;

function kvStub() {
  const m = new Map();
  return { m, async get(k, o) { const v = m.has(k) ? m.get(k) : null; if (v === null) return null; return o && o.type === "json" ? JSON.parse(v) : v; },
    async put(k, v) { m.set(k, String(v)); }, async delete(k) { m.delete(k); },
    async list(o = {}) { return { keys: [...m.keys()].filter(k => k.startsWith(o.prefix || "")).sort().map(name => ({ name })), list_complete: true }; } };
}
const kv = kvStub();
const env = { KV: kv, KEK: Buffer.alloc(32, 7).toString("base64"), GROQ_KEY: "gk", WA_TOKEN: "t", WA_PHONE_ID: "p", RUNNER_KEY: "rk-test", GH_TOKEN: "g" };
let sent = [];
globalThis.fetch = async (url, opts = {}) => {
  const u = String(url);
  if (u.includes("graph.facebook.com")) { sent.push(JSON.parse(opts.body || "{}")); return Response.json({ messages: [{ id: "w" }] }); }
  return new Response("{}", { status: 500, headers: { "content-type": "application/json" } });
};
const U = "917993610173";
let seq = 0;
async function drain(ps) { while (ps.length) await Promise.all(ps.splice(0, ps.length)); }
async function send(text) {
  const before = sent.length;
  const ps = [];
  const body = { entry: [{ changes: [{ value: { messages: [{ from: U, id: "m" + (++seq), type: "text", text: { body: text } }] } }] }] };
  await worker.fetch(new Request("https://worker.test/webhook", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) }), env, { waitUntil(p) { ps.push(Promise.resolve(p)); }, passThroughOnException() {} });
  await drain(ps);
  return sent.slice(before).filter(x => x.type === "text").map(x => x.text.body).join("\n");
}
const reset = () => { kv.m.clear(); sent = []; };
let pass = 0, fail = 0;
const ok = (name, cond, extra) => { if (cond) { pass++; console.log("PASS", name); } else { fail++; console.log("FAIL", name, extra !== undefined ? "— " + JSON.stringify(extra).slice(0, 300) : ""); } };

// R1 — mixed healthy + expired.
reset();
await kv.put(`gaccts:${U}`, JSON.stringify({ def: "a1", list: [
  { id: "a1", email: "healthy@example.com", gmail: true, yt: false, state: "ok" },
  { id: "a2", email: "stale@example.com", gmail: true, yt: false, state: "expired" },
] }));
{ const t = await send("google connect ayindha");
  ok("R1 healthy grant earns the Gmail claim; expired is named + remedy", /Gmail kuda chadhavagalanu/.test(t) && /expire ayyindhi/.test(t) && /stale@example\.com/.test(t) && /reconnect kavali/.test(t), t); }

// R2 — only expired.
reset();
await kv.put(`gaccts:${U}`, JSON.stringify({ def: "a2", list: [
  { id: "a2", email: "stale@example.com", gmail: true, yt: false, state: "expired" },
] }));
{ const t = await send("google connect ayindha");
  ok("R2 expired-only: no unconditional Gmail claim, expiry named", !/— Gmail kuda chadhavagalanu\./.test(t) && !/connect ayyayi \(stale@example\.com\) —/.test(t) && /expire ayyindhi/.test(t) && /reconnect kavali/.test(t), t); }

// R3 — legacy-only keyspace derives "unknown".
reset();
await kv.put(`tok:${U}:google`, JSON.stringify({ refresh_token: "x", who: "legacy@example.com", at: Date.now() }));
{ const t = await send("google connect ayindha");
  ok("R3 legacy-derived grant earns NO health claim (state unknown)", !/Gmail kuda chadhavagalanu/.test(t) && /confirm avvaledu/.test(t), t); }

// R4 — feed over an expired grant records gmail-expired.
reset();
const U2 = "919999999996";
await kv.put(`gaccts:${U2}`, JSON.stringify({ def: "a2", list: [
  { id: "a2", email: "stale@example.com", gmail: true, yt: false, state: "expired" },
] }));
await kv.put(`tok:${U2}:google`, JSON.stringify({ refresh_token: "dead", who: "stale@example.com", at: Date.now() }));
await kv.put("verify:awaiting", "1");
await kv.put(`setupchain:${U2}`, JSON.stringify({ providers: ["groq"], done: [], failed: [], current: "jobM1", email: "stale@example.com", at: Date.now() - 600000 }));
await kv.put(`setupjob:jobM1`, JSON.stringify({ job: "jobM1", provider: "groq", user: U2, state: "paused", pauseReason: "email", verifyWait: true, email: "stale@example.com", pausedAt: Date.now() - 300000, upd: Date.now() - 300000, at: Date.now() - 600000 }));
{ const ps = []; await worker.scheduled({}, env, { waitUntil(p) { ps.push(Promise.resolve(p)); }, passThroughOnException() {} }); await drain(ps);
  const j = JSON.parse((await kv.get("setupjob:jobM1")) || "{}");
  ok("R4 feed records gmail-expired (not no-gmail-token) + dead-count", j.mailFetch === "gmail-expired" && (j.mailDead || 0) >= 1, j); }

console.log(`\nw5test: ${pass} pass, ${fail} fail`);
process.exit(fail ? 1 : 0);
