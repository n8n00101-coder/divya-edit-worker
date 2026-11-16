// v97 MULTI-ACCOUNT harness — runs the REAL merged Worker (divya-merged.js)
// in Node with a Map-backed KV and a stubbed Google fetch. Proves:
// migration, add-account via the real OAuth callback, cap, remove/default,
// self-heal grant selection, per-account YouTube upload token.
import { readFileSync } from "node:fs";

const src = readFileSync(new URL("./worker.mjs", import.meta.url), "utf-8");
const worker = (await import("./worker.mjs")).default;

// ---------- KV stub ----------
const map = new Map();
const KV = {
  async get(k, type) { const v = map.has(k) ? map.get(k) : null; if (v === null) return null; if (type === "arrayBuffer") return v instanceof Uint8Array ? v.buffer.slice(v.byteOffset, v.byteOffset + v.byteLength) : new TextEncoder().encode(String(v)).buffer; return v instanceof Uint8Array ? new TextDecoder().decode(v) : v; },
  async put(k, v) { map.set(k, String(v)); },
  async delete(k) { map.delete(k); },
  async list({ prefix } = {}) { return { keys: [...map.keys()].filter(k => !prefix || k.startsWith(prefix)).map(name => ({ name })) }; },
};
const env = { KV, GOOGLE_CLIENT_ID: "cid", GOOGLE_CLIENT_SECRET: "csecret", OWNERS: "", FRIENDS: "" };

// ---------- Google fetch stub ----------
const EMAILS = { "code-a1": "first@example.com", "code-a2": "second@example.com", "code-a3": "third@example.com" };
const TOKENS = { "code-a1": "AT1", "code-a2": "AT2", "code-a3": "AT3" };
const MAILTOKEN = { AT1: false, AT2: true, AT3: false }; // the Groq mail sits in account #2's inbox only
let lastUploadAuth = "";
const b64url = s => Buffer.from(s).toString("base64").replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const groqMail = {
  id: "m1", internalDate: String(Date.now()),
  payload: { headers: [{ name: "From", value: "Groq <noreply@groq.com>" }, { name: "Subject", value: "Verify your email" }],
    parts: [{ mimeType: "text/html", body: { data: b64url('<p>Hi</p><a href="https://console.groq.com/verify-email?token=abc123">Verify</a>') } }] },
};
const realFetch = globalThis.fetch;
globalThis.fetch = async (url, opts = {}) => {
  const u = String(url);
  const auth = (opts.headers && (opts.headers.Authorization || opts.headers.authorization)) || "";
  const J = (o, st = 200, extra = {}) => new Response(JSON.stringify(o), { status: st, headers: { "content-type": "application/json", ...extra } });
  if (u.startsWith("https://oauth2.googleapis.com/token")) {
    const body = new URLSearchParams(opts.body ? String(opts.body) : "");
    if (body.get("grant_type") === "refresh_token") return J({ access_token: "REFRESHED-" + body.get("refresh_token"), expires_in: 3600 });
    const code = body.get("code"); return J({ access_token: TOKENS[code] || "ATX", refresh_token: "R" + (TOKENS[code] || "X"), expires_in: 3600 });
  }
  if (u.startsWith("https://openidconnect.googleapis.com/v1/userinfo")) {
    const em = { AT1: EMAILS["code-a1"], AT2: EMAILS["code-a2"], AT3: EMAILS["code-a3"] }[auth.replace("Bearer ", "")] || "";
    return J({ email: em, name: em.split("@")[0] });
  }
  if (u.startsWith("https://www.googleapis.com/youtube/v3/channels")) {
    const t = auth.replace("Bearer ", "");
    return J({ items: [{ snippet: { title: t === "AT2" ? "Second Channel" : t === "AT1" ? "First Channel" : "Third Channel" } }] });
  }
  if (u.includes("gmail.googleapis.com/gmail/v1/users/me/messages?")) {
    const t = auth.replace("Bearer ", "");
    return J(MAILTOKEN[t] ? { messages: [{ id: "m1" }] } : { messages: [] });
  }
  if (u.includes("gmail.googleapis.com/gmail/v1/users/me/messages/m1")) return J(groqMail);
  if (u.startsWith("https://www.googleapis.com/upload/youtube/v3/videos")) {
    lastUploadAuth = auth;
    return J({ id: "vid123", snippet: { title: "T" } });
  }
  if (u.startsWith("https://upload.example/")) return J({ id: "vid123", snippet: { title: "T" } });
  return J({ error: "unstubbed " + u }, 404);
};

// ---------- helpers ----------
const ctx = { waitUntil(p) { this._p = p; } };
async function call(method, path, { token, body } = {}) {
  const req = new Request("https://divya-app.n8n00101.workers.dev" + path, {
    method, headers: { "content-type": "application/json", ...(token ? { authorization: "Bearer " + token } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  const res = await worker.fetch(req, env, ctx);
  const text = await res.text();
  let json = null; try { json = JSON.parse(text); } catch {}
  return { status: res.status, json, text, headers: res.headers };
}
let pass = 0, fail = 0;
const T = (name, cond, extra = "") => { if (cond) { pass++; console.log("PASS", name); } else { fail++; console.log("FAIL", name, extra); } };
async function signup(email) {
  const r = await call("POST", "/api/auth/signup", { body: { name: "T User", email, password: "Test!2345" } });
  if (!r.json?.token) throw new Error("signup failed " + r.text);
  const uid = map.get(`em:${email}`);
  return { token: r.json.token, n: "u_" + uid };
}
async function oauthCallback(token, prov, code, acctIntent) {
  const link = await call("POST", "/api/connect/link", { token, body: { provider: prov, ...(acctIntent ? { account: acctIntent } : {}) } });
  if (!link.json?.url) return { link, cb: null };
  const state = link.json.url.split("/c/")[1];
  const cb = await call("GET", `/oauth/google?state=${state}&code=${code}`);
  return { link, cb };
}

// ---------- (a) migration: legacy single grant -> account #1 ----------
{
  const u = await signup("mig@example.com");
  map.set(`tok:${u.n}:google`, JSON.stringify({ access_token: "AT1", refresh_token: "RT1", who: "first@example.com", at: Date.now(), expires_in: 3600 }));
  map.set(`tok:${u.n}:youtube`, JSON.stringify({ access_token: "AT1", refresh_token: "RT1", who: 'channel "First Channel"', at: Date.now(), expires_in: 3600 }));
  const c = await call("GET", "/api/connect", { token: u.token });
  T("a1 migration lists 1 account", c.json.accounts?.length === 1, JSON.stringify(c.json.accounts));
  T("a2 migrated email", c.json.accounts?.[0]?.email === "first@example.com");
  T("a3 migrated channel title normalized", c.json.accounts?.[0]?.ytChannel === "First Channel", c.json.accounts?.[0]?.ytChannel);
  T("a4 migrated account is default + gmail+yt", c.json.accounts?.[0]?.def === true && c.json.accounts?.[0]?.gmail && c.json.accounts?.[0]?.yt);
  const v = await call("GET", "/api/gmail/verify?provider=groq", { token: u.token });
  T("a5 legacy token still read (no-mail-yet 404)", v.status === 404, v.status + " " + v.text.slice(0, 120));
}

// ---------- (b) add accounts through the real OAuth callback ----------
const U = await signup("multi@example.com");
{
  const r1 = await oauthCallback(U.token, "google", "code-a1");
  T("b1 first connect link app-origin", r1.link.json.url.startsWith("https://divya-app.n8n00101.workers.dev/c/"), r1.link.json.url);
  T("b2 first callback redirects into app", r1.cb.status === 302 && (r1.cb.headers.get("location") || "").includes("connected=google"), r1.cb.status + " " + (r1.cb.headers.get("location") || ""));
  const r2 = await oauthCallback(U.token, "google", "code-a2", "new");
  T("b3 add-account callback ok", r2.cb.status === 302, r2.cb.status + " " + r2.cb.text.slice(0, 100));
  const r3 = await oauthCallback(U.token, "youtube", "code-a2");
  T("b4 youtube connect for acct2 ok", r3.cb.status === 302, r3.cb.status + "");
  const c = await call("GET", "/api/connect", { token: U.token });
  T("b5 two accounts listed", c.json.accounts?.length === 2, JSON.stringify(c.json.accounts));
  const a1 = c.json.accounts.find(a => a.email === "first@example.com");
  const a2 = c.json.accounts.find(a => a.email === "second@example.com");
  T("b6 acct1 default, gmail only", !!a1 && a1.def && a1.gmail && !a1.yt);
  T("b7 acct2 gmail+yt + channel", !!a2 && a2.gmail && a2.yt && a2.ytChannel === "Second Channel", JSON.stringify(a2));
  T("b8 acct2 grant under #-key, legacy = acct1", (map.get(`tok:${U.n}:google`) || "").includes('"AT1"') && [...map.keys()].some(k => k.startsWith(`tok:${U.n}:google#`) && (map.get(k) || "").includes('"AT2"')), [...map.keys()].filter(k => k.includes("tok:")).join(","));
  U.a1 = a1; U.a2 = a2;
}

// ---------- (e) self-heal: sweep feeds the job from acct #2's inbox ----------
{
  const jobId = "jobX1";
  map.set("setupchain:t1", JSON.stringify({ current: jobId, at: Date.now() }));
  map.set(`setupjob:${jobId}`, JSON.stringify({ job: jobId, user: U.n, state: "paused", pauseReason: "email", provider: "groq", email: "second@example.com", at: Date.now() }));
  await worker.scheduled({}, env, ctx); if (ctx._p) await ctx._p.catch(() => {});
  const job = JSON.parse(map.get(`setupjob:${jobId}`));
  T("e1 sweep fed verify link from acct2 inbox", !!job.verifyLink && job.verifyLink.includes("console.groq.com"), JSON.stringify(job).slice(0, 200));
  // job.email = acct1 (mail NOT there) — sweep must still find it in acct2
  const jobId2 = "jobX2";
  map.set("setupchain:t2", JSON.stringify({ current: jobId2, at: Date.now() }));
  map.set(`setupjob:${jobId2}`, JSON.stringify({ job: jobId2, user: U.n, state: "paused", pauseReason: "email", provider: "groq", email: "first@example.com", at: Date.now() }));
  map.set("verify:awaiting", "1");
  await worker.scheduled({}, env, ctx); if (ctx._p) await ctx._p.catch(() => {});
  const job2 = JSON.parse(map.get(`setupjob:${jobId2}`));
  T("e2 sweep checks ALL grants when job.email inbox misses", !!job2.verifyLink, JSON.stringify(job2).slice(0, 200));
}

// ---------- (f) YouTube upload uses the chosen account's token ----------
{
  map.set("res:jobup1", new TextEncoder().encode("fakevideo"));
  const r = await call("POST", "/api/post/youtube", { token: U.token, body: { job: "jobup1", title: "T", account: "second@example.com", confirm: true } });
  T("f1 upload ok via acct2", r.json?.ok === true, r.text.slice(0, 200));
  T("f2 upload carried acct2 token", lastUploadAuth === "Bearer AT2", lastUploadAuth);
  const r2 = await call("POST", "/api/post/youtube", { token: U.token, body: { job: "jobup1", title: "T", confirm: true } });
  T("f3 unnamed upload falls back to the yt-grant account (acct2)", r2.json?.ok === true && lastUploadAuth === "Bearer AT2", lastUploadAuth + " " + r2.text.slice(0, 120));
  const r3 = await call("POST", "/api/post/youtube", { token: U.token, body: { job: "jobup1", title: "T", confirm: true, account: "first@example.com" } });
  T("f4 explicit account without yt grant fails honestly", r3.json?.ok === false && /connect/i.test(r3.json?.error || ""), r3.text.slice(0, 120));
}

// ---------- (d) set-default + remove ----------
{
  const sd = await call("POST", "/api/connect/default", { token: U.token, body: { account: U.a2.id } });
  T("d1 set-default ok", sd.json?.ok === true && sd.json.acctDef === U.a2.id, JSON.stringify(sd.json).slice(0, 160));
  T("d2 legacy slot now acct2 grant", (map.get(`tok:${U.n}:google`) || "").includes('"AT2"'));
  const rm = await call("POST", "/api/connect/remove", { token: U.token, body: { account: U.a2.id } });
  T("d3 remove default ok, acct1 promoted", rm.json?.ok === true && rm.json.accounts?.length === 1 && rm.json.accounts[0].email === "first@example.com" && rm.json.acctDef === U.a1.id, JSON.stringify(rm.json).slice(0, 200));
  T("d4 legacy slot restored to acct1", (map.get(`tok:${U.n}:google`) || "").includes('"AT1"'));
  T("d5 acct2 #-grants deleted", ![...map.keys()].some(k => k.includes("#") && (map.get(k) || "").includes('"AT2"')), [...map.keys()].filter(k => k.includes("tok:")).join(","));
}

// ---------- (c) cap at 10 ----------
{
  const u = await signup("cap@example.com");
  const list = Array.from({ length: 10 }, (_, i) => ({ id: "ax" + i, email: `u${i}@example.com`, ytChannel: "", ytNoChannel: false, gmail: true, yt: false, state: "ok", at: Date.now() }));
  map.set(`gaccts:${u.n}`, JSON.stringify({ list, def: "ax0" }));
  map.set(`tok:${u.n}:google`, JSON.stringify({ access_token: "AT1", who: "u0@example.com", at: Date.now() }));
  const link = await call("POST", "/api/connect/link", { token: u.token, body: { provider: "google", account: "new" } });
  T("c1 link refused at cap with cap flag", link.json?.ok === false && link.json?.cap === true, JSON.stringify(link.json));
  const link2 = await call("POST", "/api/connect/link", { token: u.token, body: { provider: "google" } });
  const state = link2.json.url.split("/c/")[1];
  const cb = await call("GET", `/oauth/google?state=${state}&code=code-a3`);
  T("c2 callback refuses 11th account, stores nothing", cb.text.includes("Account limit reached") && JSON.parse(map.get(`gaccts:${u.n}`)).list.length === 10, cb.text.slice(0, 120));
}

console.log(`\n== harness: ${pass} PASS, ${fail} FAIL ==`);
process.exit(fail ? 1 : 0);
