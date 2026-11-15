// Round-4 X3/X4 unit tests: extract the REAL functions from cfworker/app_api.js
// and exercise them with stubbed fetch/KV. No code is copied — the harness
// slices the function bodies out of the production source.
import fs from "fs";
const src = fs.readFileSync(new URL("../cfworker/app_api.js", import.meta.url), "utf8");

function extract(name) {
  const sig = ["async function " + name + "(", "function " + name + "(", "const " + name + " ="];
  let i = -1;
  for (const s of sig) { i = src.indexOf(s); if (i >= 0) break; }
  if (i < 0) throw new Error("not found: " + name);
  let k = src.indexOf("{", i), depth = 0, j = k;
  for (; j < src.length; j++) { if (src[j] === "{") depth++; else if (src[j] === "}") { depth--; if (!depth) break; } }
  return src.slice(i, j + 1);
}
const names = ["digitsNum", "waOpenSendIntent", "ruleIntent", "gmailHeader", "b64urlDecode", "qpDecode", "gmailWalkParts", "gmailBodyText", "gmailPickLink", "gmailPickCode", "isApiDisabled", "fetchVerifyLink"];
let code = extract("VERIFY_PROVIDERS") + "\n";
for (const n of names) code += extract(n) + "\n";
code += "globalThis.__x = { digitsNum, waOpenSendIntent, ruleIntent, gmailBodyText, gmailPickLink, fetchVerifyLink };";
eval(code);
const X = globalThis.__x;

let pass = 0, fail = 0;
const eq = (label, got, want) => { const ok = JSON.stringify(got) === JSON.stringify(want); console.log((ok ? "PASS" : "FAIL") + " " + label + (ok ? "" : ` — got ${JSON.stringify(got)} want ${JSON.stringify(want)}`)); ok ? pass++ : fail++; };

// ---------- X3: Ajju's two EXACT phrasings ----------
const P1 = 'Open whatsapp business and ,open chat of 7993610173 contact chat and type msg that " i love ?"';
const P2 = 'Open whatsapp and open 7993610173 contact chat and type msg that " I love ? "';
const r1 = X.ruleIntent(P1), r2 = X.ruleIntent(P2);
eq("P1 intent", r1 && r1.intent, "whatsapp");
eq("P1 number", r1 && r1.number, "917993610173");
eq("P1 message", r1 && r1.message, "i love ?");
eq("P2 intent", r2 && r2.intent, "whatsapp");
eq("P2 number", r2 && r2.number, "917993610173");
eq("P2 message", r2 && r2.message, "I love ?");
// negatives: plain open must stay open; contact-name send must stay the contact path (null here)
eq("open whatsapp alone -> not send-intent", X.waOpenSendIntent("open whatsapp"), null);
eq("open youtube stays open", (X.ruleIntent("open youtube") || {}).intent, "open");
eq("call rule intact", (X.ruleIntent("call 7993610173") || {}).intent, "call");

// ---------- X4: mail chain ----------
const b64 = s => Buffer.from(s, "utf8").toString("base64").replace(/\+/g, "-").replace(/\//g, "_");
const LINK = "https://auth.stytch.com/v1/magic_links/authenticate?token=abc123XYZ";
function msg({ from, subject, date, plain, html }) {
  const parts = [];
  if (plain != null) parts.push({ mimeType: "text/plain", body: { data: b64(plain) } });
  if (html != null) parts.push({ mimeType: "text/html", body: { data: b64(html) } });
  return { internalDate: String(date), payload: { headers: [{ name: "From", value: from }, { name: "Subject", value: subject }], parts: parts.map(p => ({ mimeType: p.mimeType, body: p.body })) } };
}
const NOW = Date.now();
const job = { at: NOW - 5 * 60 * 1000, user: "u_test" };
// googleToken stub via globalThis: fetchVerifyLink calls googleToken(env, n) — inject by shadowing:
globalThis.googleToken = async () => ({ access_token: "tok" });
// re-eval fetchVerifyLink with the stub in scope is not possible post-hoc; instead the harness
// relies on env-driven googleToken in source reading KV. We stub env.KV below to satisfy it.
const store = new Map();
const env = { KV: { get: async k => store.get(k) ?? null, put: async (k, v) => store.set(k, v) } };
// tok:<n>:google record shape: inspect googleToken in source — it parses a JSON record.
store.set("tok:u_test:google", JSON.stringify({ access_token: "tok", at: Date.now(), expires_in: 3600 }));

let inbox = [];
globalThis.fetch = async (url) => {
  const u = String(url);
  if (u.includes("/messages?")) return { ok: true, json: async () => ({ messages: inbox.map((_, i) => ({ id: "m" + i })) }) };
  const m = u.match(/messages\/(m\d+)/); if (m) return { ok: true, json: async () => inbox[Number(m[1].slice(1))] };
  throw new Error("unexpected fetch " + u);
};

// case 1: HTML-only mail, link ONLY in href (the pre-v50 silent failure)
inbox = [msg({ from: "Groq <noreply@groq.com>", subject: "Your login request to Groq", date: NOW - 60000, plain: "", html: `<html><body><p>Click to sign in</p><a href="${LINK}">Sign in to Groq</a></body></html>` })];
let r = await X.fetchVerifyLink(env, "u_test", "groq", job, 0);
eq("html-only href mail -> link found", r.ok && r.link, LINK);

// case 2: plain-text mail with the link as text
inbox = [msg({ from: "noreply@groq.com", subject: "Your login request to Groq", date: NOW - 60000, plain: "Sign in: " + LINK, html: null })];
r = await X.fetchVerifyLink(env, "u_test", "groq", job, 0);
eq("plain mail -> link found", r.ok && r.link, LINK);

// case 3: only an OLD mail (previous run) -> no-mail-yet, never the stale link
inbox = [msg({ from: "noreply@groq.com", subject: "Your login request to Groq", date: NOW - 30 * 60 * 1000, plain: "Sign in: " + LINK, html: null })];
r = await X.fetchVerifyLink(env, "u_test", "groq", job, 0);
eq("old mail skipped -> no-mail-yet", r, { ok: false, reason: "no-mail-yet" });

// case 4: matching fresh mail but NO link/code anywhere -> honest mail-no-link
inbox = [msg({ from: "noreply@groq.com", subject: "Your login request to Groq", date: NOW - 60000, plain: "We sent you a sign-in request. Open the Groq app to continue.", html: null })];
r = await X.fetchVerifyLink(env, "u_test", "groq", job, 0);
eq("matching mail without link -> mail-no-link", r, { ok: false, reason: "mail-no-link" });

// case 5: empty inbox -> no-mail-yet
inbox = [];
r = await X.fetchVerifyLink(env, "u_test", "groq", job, 0);
eq("empty inbox -> no-mail-yet", r, { ok: false, reason: "no-mail-yet" });

// case 6: gmailBodyText surfaces hrefs
const bt = X.gmailBodyText(inbox[0] || msg({ from: "noreply@groq.com", subject: "x", date: NOW, plain: "", html: `<a href="${LINK}">go</a>` }));
eq("gmailBodyText includes href", bt.includes(LINK), true);

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
