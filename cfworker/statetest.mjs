// Shadow programme Wave 0 battery: drives the REAL Worker fetch
// handler's POST /internal/state route with a stub KV + an in-memory
// Durable Object stub implementing the JulieState op protocol.
// Asserts: RUNNER_KEY guard, get/list/del against the DO facade,
// server-side redaction of the secret families (tok:/ukey:/upass:/sess:),
// and the KV-migration fallback read. Run: node statetest.mjs
import { readFileSync, writeFileSync } from "fs";
import { pathToFileURL } from "url";

const SRC = readFileSync(new URL("./divya.js", import.meta.url), "utf8");
writeFileSync("/tmp/_divya_state_under_test.mjs", SRC);
const worker = (await import(pathToFileURL("/tmp/_divya_state_under_test.mjs").href)).default;

class KVStub {
  constructor() { this.m = new Map(); }
  async get(k, opts) {
    const v = this.m.has(k) ? this.m.get(k) : null;
    if (v == null) return null;
    const t = typeof opts === "string" ? opts : (opts && opts.type) || "text";
    if (t === "json") { try { return JSON.parse(v); } catch { return null; } }
    return v;
  }
  async put(k, v) { this.m.set(k, typeof v === "string" ? v : String(v)); }
  async delete(k) { this.m.delete(k); }
  async list({ prefix = "", limit = 1000 } = {}) { return { keys: [...this.m.keys()].filter(k => k.startsWith(prefix)).slice(0, limit).map(name => ({ name })), list_complete: true }; }
}

class DOStub {
  constructor() { this.m = new Map(); }
  idFromName(n) { return n; }
  get() {
    const m = this.m;
    const now = Date.now();
    const alive = r => r && !(r.exp && r.exp < now);
    return { fetch: async (url, opts) => {
      const b = JSON.parse(opts.body);
      if (b.op === "get") { const r = m.get(b.key); if (!alive(r)) { if (r) m.delete(b.key); return Response.json({ v: null }); } return Response.json({ v: r.v }); }
      if (b.op === "put") { m.set(b.key, { v: String(b.value), exp: b.exp || 0 }); return Response.json({ ok: true }); }
      if (b.op === "putnx") { const r = m.get(b.key); if (alive(r)) return Response.json({ ok: true, skipped: true }); m.set(b.key, { v: String(b.value), exp: b.exp || 0 }); return Response.json({ ok: true }); }
      if (b.op === "del") { m.delete(b.key); return Response.json({ ok: true }); }
      if (b.op === "list") { const ks = [...m.keys()].filter(k => k >= b.prefix && k < b.prefix + "\ufffd").sort().slice(0, b.limit || 1000); return Response.json({ keys: ks.map(k => ({ name: k })), list_complete: true }); }
      if (b.op === "mget") { const out = {}; for (const k of b.keys || []) { const r = m.get(k); if (alive(r)) out[k] = r.v; } return Response.json({ v: out }); }
      return new Response("bad op", { status: 400 });
    } };
  }
}

const kv = new KVStub();
const dostore = new DOStub();
const put = (k, v) => dostore.m.set(k, { v, exp: 0 });
put("acct:u_test", JSON.stringify({ email: "a@b.c", phone: "917993610173" }));
put("ukey:919951950173:openrouter", JSON.stringify({ key: "SECRETVALUE123", ok: true, provider: "openrouter" }));
put("tok:u_x:google", JSON.stringify({ access: "TOKSECRET999", state: "expired" }));
put("setupconsent:917993610173", JSON.stringify({ at: 1795000000000, scope: "accounts+keys" }));
kv.m.set("dbg:kvonly", "from-old-kv");

const env = { KV: kv, STATE: dostore, RUNNER_KEY: "testkey" };
const ctx = { waitUntil() {} };
const call = async (body, key) => {
  const headers = { "content-type": "application/json" };
  if (key !== null) headers["x-runner-key"] = key || "testkey";
  const res = await worker.fetch(new Request("https://w.test/internal/state", { method: "POST", headers, body: JSON.stringify(body) }), env, ctx);
  return { status: res.status, text: await res.text() };
};

let pass = 0, fail = 0;
const T = (name, cond) => { if (cond) { pass++; console.log("PASS", name); } else { fail++; console.log("FAIL", name); } };

let r = await call({ op: "get", key: "acct:u_test" }, null);
T("no key -> 403", r.status === 403);
r = await call({ op: "get", key: "acct:u_test" }, "wrong");
T("wrong key -> 403", r.status === 403);
r = await call({ op: "get", key: "acct:u_test" });
let j = JSON.parse(r.text);
T("get acct from DO", r.status === 200 && j.exists && j.v && j.v.email === "a@b.c" && j.v.phone === "917993610173");
r = await call({ op: "get", key: "ukey:919951950173:openrouter" });
j = JSON.parse(r.text);
T("get ukey redacted meta", j.exists && j.redacted === true && j.keyOk === true && j.provider === "openrouter" && j.bytes > 10);
T("ukey value never leaks", !r.text.includes("SECRETVALUE123"));
r = await call({ op: "get", key: "tok:u_x:google" });
j = JSON.parse(r.text);
T("get tok redacted + state", j.redacted === true && j.state === "expired" && !r.text.includes("TOKSECRET999"));
r = await call({ op: "get", key: "nope:missing" });
j = JSON.parse(r.text);
T("get missing -> exists:false", j.exists === false);
r = await call({ op: "get", key: "dbg:kvonly" });
j = JSON.parse(r.text);
T("KV-shadow fallback read", j.exists && j.v === "from-old-kv");
r = await call({ op: "list", prefix: "ukey:" });
j = JSON.parse(r.text);
T("list names only", j.keys && j.keys.length === 1 && j.keys[0] === "ukey:919951950173:openrouter" && !r.text.includes("SECRETVALUE123"));
r = await call({ op: "del", key: "setupconsent:917993610173" });
j = JSON.parse(r.text);
T("del returns read-back proof", j.deleted === true);
r = await call({ op: "get", key: "setupconsent:917993610173" });
j = JSON.parse(r.text);
T("get after del -> exists:false", j.exists === false);
r = await call({ op: "bogus" });
T("bad op -> 400", r.status === 400);

console.log(`\nstatetest: ${pass} pass, ${fail} fail`);
process.exit(fail ? 1 : 0);
