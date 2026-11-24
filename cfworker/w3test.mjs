// w3test.mjs — Wave 3 (consent / response discipline) proofs against
// the REAL Worker module, driven through the real WA webhook with a
// KV stub. Scenarios:
//   S1 C-05: setup question after a STOPPED chain -> the retry offer
//      owns the reply (no fresh pitch, no "setup complete", the armed
//      ask is the RETRY ask), and the reply set is exactly card+text.
//   S2 C-14: keys exist + last chain done WITH failures -> failures
//      named via the retry offer, never "setup complete".
//   S3 C-14 positive: keys exist + done + zero failures -> the
//      "setup complete" line is earned.
//   S4 C-13: the scheduled auto-check refuses to start a chain for a
//      user holding a stop record.
//   S9 C-13: a fresh manual Allow clears the stop record.
//   S5 C-15: "always allow cancel" deletes the standing grant; the
//      Don't-allow tap deletes it too.
//   S6 C-04 residual: a stale Allow-card tap with nothing armed
//      starts nothing; with an armed ask it grants.
//   S7 C-12: a status question during a field ask is answered as a
//      question (never consumed as the field value); a real value
//      is consumed.
//   S8 17:38 replay: "Groq kakunda verey models try cheyu" after a
//      stopped chain -> the run-the-rest router owns it (one line),
//      never the pitch, never the brain.
import { readFileSync, writeFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

const SRC = readFileSync(new URL("./divya.js", import.meta.url), "utf8");
writeFileSync("/tmp/_divya_w3_under_test.mjs", SRC);
const worker = (await import(pathToFileURL("/tmp/_divya_w3_under_test.mjs").href)).default;

function kvStub() {
  const m = new Map();
  return { m, async get(k, o) { const v = m.has(k) ? m.get(k) : null; if (v === null) return null; return o && o.type === "json" ? JSON.parse(v) : v; },
    async put(k, v) { m.set(k, String(v)); }, async delete(k) { m.delete(k); },
    async list(o = {}) { const keys = [...m.keys()].filter(k => k.startsWith(o.prefix || "")).sort().map(name => ({ name })); return { keys, list_complete: true }; } };
}
const kv = kvStub();
const env = { KV: kv, KEK: Buffer.alloc(32, 7).toString("base64"), GROQ_KEY: "gk-shared-dead", WA_TOKEN: "t", WA_PHONE_ID: "p", RUNNER_KEY: "rk-test", GH_TOKEN: "g" };
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
  return sent.slice(before);
}
async function tap(id) {
  const before = sent.length;
  const ps = [];
  const body = { entry: [{ changes: [{ value: { messages: [{ from: U, id: "m" + (++seq), type: "interactive", interactive: { type: "button_reply", button_reply: { id } } }] } }] }] };
  await worker.fetch(new Request("https://worker.test/webhook", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) }), env, { waitUntil(p) { ps.push(Promise.resolve(p)); }, passThroughOnException() {} });
  await drain(ps);
  return sent.slice(before);
}
const texts = ms => ms.filter(x => x.type === "text").map(x => x.text.body);
const cards = ms => ms.filter(x => x.type === "interactive");
const reset = () => { kv.m.clear(); sent = []; };

let pass = 0, fail = 0;
const ok = (name, cond, extra) => { if (cond) { pass++; console.log("PASS", name); } else { fail++; console.log("FAIL", name, extra !== undefined ? "— " + JSON.stringify(extra).slice(0, 300) : ""); } };

// S1 — C-05: stopped chain -> retry offer owns the setup question.
reset();
await kv.put(`setupdone:${U}`, JSON.stringify({ state: "stopped", done: [], failed: ["mistral"], failReason: { mistral: "signup rejected" }, at: Date.now() - 60000 }));
{ const out = await send("setup cheyu");
  const t = texts(out).join("\n");
  ok("S1 stopped chain -> retry offer, no fresh pitch, no complete-claim", /Fail ayinavi/.test(t) && !/setup complete/i.test(t) && !/Setup \+ API keys anni nene create chestha — Allow nokku/.test(t), t);
  const ask = JSON.parse((await kv.get(`wasetupask:${U}`)) || "{}");
  ok("S1b the armed ask is the RETRY ask; reply set is exactly card+text", ask.retry === true && out.length === 2 && cards(out).length === 1, { ask, n: out.length }); }

// S2 — C-14: keys + done-with-failures -> no "setup complete".
reset();
await kv.put(`ukey:${U}:openrouter`, JSON.stringify({ ok: true, at: Date.now(), source: "divya" }));
await kv.put(`setupdone:${U}`, JSON.stringify({ state: "done", done: ["openrouter"], failed: ["mistral"], failReason: { mistral: "signup rejected" }, at: Date.now() - 60000 }));
{ const out = await send("setup ayindha");
  const t = texts(out).join("\n");
  ok("S2 done-with-failures names the failure, never claims complete", /fail ayyayi|Fail ayinavi/.test(t) && /Mistral/.test(t) && /malli try/.test(t) && !/Setup complete ayyindhi/.test(t), t); }

// S3 — C-14 positive: keys + clean done -> complete is earned.
reset();
await kv.put(`ukey:${U}:openrouter`, JSON.stringify({ ok: true, at: Date.now(), source: "divya" }));
await kv.put(`setupdone:${U}`, JSON.stringify({ state: "done", done: ["openrouter"], failed: [], at: Date.now() - 60000 }));
{ const out = await send("setup ayindha");
  const t = texts(out).join("\n");
  ok("S3 clean done -> setup complete line", /setup complete/i.test(t), t); }

// S4 — C-13: scheduled auto-check refuses after a stop.
reset();
await kv.put(`setupconsent:${U}`, JSON.stringify({ at: Date.now(), scope: "accounts+keys+captchas+server", email: "mike0123l098@gmail.com" }));
await kv.put(`setupstop:${U}`, JSON.stringify({ at: Date.now() }));
{ const ps = []; await worker.scheduled({}, env, { waitUntil(p) { ps.push(Promise.resolve(p)); }, passThroughOnException() {} }); await drain(ps); }
ok("S4 auto-check starts no chain for a stopped user", !(await kv.get(`setupchain:${U}`)), await kv.get(`setupchain:${U}`));

// S9 — C-13: a fresh manual Allow clears the stop record.
await kv.put(`wasetupask:${U}`, JSON.stringify({ at: Date.now() }));
{ await send("sare");
  ok("S9 manual Allow clears setupstop:", !(await kv.get(`setupstop:${U}`))); }

// S5 — C-15: phrase revoke + Don't-allow revoke.
reset();
await kv.put(`setupalways:${U}`, JSON.stringify({ at: Date.now(), scope: "accounts+keys+captchas+server", via: "wa" }));
{ const out = await send("always allow cancel");
  ok("S5 'always allow cancel' deletes the grant + confirms", !(await kv.get(`setupalways:${U}`)) && /cancel chesa/.test(texts(out).join("\n")), texts(out));
  await kv.put(`setupalways:${U}`, JSON.stringify({ at: Date.now(), scope: "accounts+keys+captchas+server", via: "wa" }));
  await tap("waallow:no");
  ok("S5b Don't-allow tap deletes the grant too", !(await kv.get(`setupalways:${U}`))); }

// S6 — C-04 residual: stale card tap vs armed tap.
reset();
{ const out = await tap("waallow:yes");
  ok("S6 stale Allow tap starts nothing", /pathadhi/.test(texts(out).join("\n")) && !(await kv.get(`setupchain:${U}`)) && !(await kv.get(`wasetupmail:${U}`)), texts(out));
  await kv.put(`wasetupask:${U}`, JSON.stringify({ at: Date.now() }));
  const out2 = await tap("waallow:yes");
  ok("S6b armed Allow tap grants (asks the one missing fact)", /email/.test(texts(out2).join("\n")), texts(out2)); }

// S7 — C-12: field ask ownership.
reset();
await kv.put(`setupchain:${U}`, JSON.stringify({ providers: ["kaggle"], done: [], failed: [], current: "jobF1", email: "mike0123l098@gmail.com", at: Date.now() }));
await kv.put(`setupjob:jobF1`, JSON.stringify({ job: "jobF1", provider: "kaggle", user: U, state: "paused", awaiting: { id: "a1", kind: "field", field: "name", provider: "kaggle", expires: Date.now() + 600000 } }));
{ const out = await send("setup ela undhi");
  const j = JSON.parse(await kv.get("setupjob:jobF1"));
  ok("S7 status question NOT consumed as the field value", !j.userInput, { userInput: j.userInput, replies: texts(out) });
  const out2 = await send("Ajju");
  const j2 = JSON.parse(await kv.get("setupjob:jobF1"));
  ok("S7b a real value IS consumed", !!(j2.userInput && j2.userInput.value === "Ajju") && /Theeskunna/.test(texts(out2).join("\n")), { userInput: j2.userInput, replies: texts(out2) }); }

// S8 — the 17:38 replay: run-the-rest owns the instruction.
reset();
await kv.put(`setupdone:${U}`, JSON.stringify({ state: "stopped", done: [], failed: ["groq"], failReason: { groq: "email verification failed" }, at: Date.now() - 60000 }));
{ const out = await send("Groq kakunda verey models try cheyu");
  const t = texts(out).join("\n");
  ok("S8 run-the-rest owns it — one line, no pitch, no brain line", out.length >= 1 && /migilinavi em levu|start chestha|try/.test(t) && !/Setup \+ API keys anni nene create chestha/.test(t) && !/brain/.test(t), t); }

console.log(`\nw3test: ${pass} pass, ${fail} fail`);
process.exit(fail ? 1 : 0);
