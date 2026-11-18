// v116 Nod Phase 1 rig: VISIBLE MEMORY endpoints (GET /api/memory,
// POST /api/memory/edit, POST /api/memory/forget) over the existing
// umem:/hmem: KV stores, plus source pins for the Memory screen UI in
// app/app.js + app/index.html. Style follows paritytest.mjs (in-memory
// KV, stubbed fetch, real fetch handler). Run: node nodparitytest.mjs
import path from "node:path";
import { pathToFileURL } from "node:url";
import { readFileSync } from "node:fs";

const HERE = path.dirname(new URL(import.meta.url).pathname);
let fails = 0, total = 0;
function check(cond, label) {
  total++;
  console.log((cond ? "PASS " : "FAIL ") + label);
  if (!cond) fails++;
}

const store = new Map();
const KV = {
  async get(k) { return store.has(k) ? store.get(k) : null; },
  async put(k, v) { store.set(k, String(v)); },
  async delete(k) { store.delete(k); },
  async list() { return { keys: [...store.keys()].map(name => ({ name })) }; },
};
globalThis.fetch = async (url) => {
  const u = String(url);
  if (u.includes("api.github.com")) return new Response(null, { status: 204 });
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
store.set(`umem:${NUM}`, JSON.stringify({
  name: "Test User", voice: "female", lang: "Telugu",
  notes: ["Likes morning videos", "Client Ravi — invoices on Fridays"],
}));
store.set(`hmem:${NUM}`, JSON.stringify([
  "Discussed a documentary about rivers; user wants sources shown.",
  "User rejected a boring draft; wants faster cuts.",
]));

const worker = (await import(pathToFileURL(path.join(HERE, "cfworker", "divya.js")).href)).default;

async function call(method, p, body, token = TOKEN) {
  const req = new Request("https://divya.test" + p, {
    method,
    headers: { "content-type": "application/json", ...(token ? { authorization: `Bearer ${token}` } : {}) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const r = await worker.fetch(req, env, ctx);
  const text = await r.text();
  let json = null;
  try { json = JSON.parse(text); } catch {}
  return { status: r.status, json, text };
}
const umem = () => JSON.parse(store.get(`umem:${NUM}`) || "null") || {};
const hmem = () => JSON.parse(store.get(`hmem:${NUM}`) || "[]");

// --- auth gate ---
let r = await call("GET", "/api/memory", undefined, null);
check(r.status === 401, "memory: unauthenticated is 401");

// --- GET shape + sources ---
r = await call("GET", "/api/memory");
check(r.json && r.json.ok === true, "memory GET ok");
check(Array.isArray(r.json.facts) && r.json.facts.length === 3, "memory GET: 3 facts (name/voice/lang)");
check(r.json.facts.every(f => f.source && f.value), "memory GET: every fact carries value + source");
check(Array.isArray(r.json.notes) && r.json.notes.length === 2 && r.json.notes[0].source.includes("remember"), "memory GET: 2 notes with remember-source");
check(Array.isArray(r.json.summaries) && r.json.summaries.length === 2 && r.json.summaries[0].source.includes("earlier conversation"), "memory GET: 2 summaries with conversation-source");

// --- edit note ---
r = await call("POST", "/api/memory/edit", { kind: "note", idx: 0, text: "Likes evening videos" });
check(r.json.ok === true && umem().notes[0] === "Likes evening videos", "memory edit note idx0 persists to umem");

// --- edit summary ---
r = await call("POST", "/api/memory/edit", { kind: "summary", idx: 1, text: "User wants faster cuts and louder music." });
check(r.json.ok === true && hmem()[1].includes("louder music"), "memory edit summary idx1 persists to hmem");

// --- edit fact ---
r = await call("POST", "/api/memory/edit", { kind: "fact", field: "lang", text: "Hindi" });
check(r.json.ok === true && umem().lang === "Hindi", "memory edit fact lang persists");
r = await call("POST", "/api/memory/edit", { kind: "fact", field: "voice", text: "robot" });
check(r.status === 400, "memory edit fact voice rejects non female/male");

// --- edit guards ---
r = await call("POST", "/api/memory/edit", { kind: "note", idx: 9, text: "x" });
check(r.status === 400, "memory edit out-of-range idx is 400");
r = await call("POST", "/api/memory/edit", { kind: "note", idx: 0, text: "  " });
check(r.status === 400, "memory edit empty text is 400");

// --- forget note / fact / summary ---
r = await call("POST", "/api/memory/forget", { kind: "note", idx: 0 });
check(r.json.ok === true && umem().notes.length === 1 && umem().notes[0].includes("Ravi"), "memory forget note removes the right one");
r = await call("POST", "/api/memory/forget", { kind: "fact", field: "voice" });
check(r.json.ok === true && !("voice" in umem()), "memory forget fact removes the field only");
check(umem().name === "Test User" && umem().lang === "Hindi", "memory forget fact leaves other facts intact");
r = await call("POST", "/api/memory/forget", { kind: "summary", idx: 0 });
check(r.json.ok === true && hmem().length === 1, "memory forget summary removes it");
r = await call("POST", "/api/memory/forget", { kind: "bogus" });
check(r.status === 400, "memory forget bad kind is 400");

// --- GET reflects mutations (what the screen will render) ---
r = await call("GET", "/api/memory");
check(r.json.notes.length === 1 && r.json.summaries.length === 1 && r.json.facts.length === 2, "memory GET after edits: 1 note, 1 summary, 2 facts");

// --- empty state (the 0-notes screenshot state must be a clean 200) ---
store.delete(`umem:${NUM}`); store.delete(`hmem:${NUM}`);
r = await call("GET", "/api/memory");
check(r.json && r.json.ok === true && r.json.facts.length === 0 && r.json.notes.length === 0 && r.json.summaries.length === 0, "memory GET empty state: clean empty lists");

// --- UI source pins ---
const appJs = readFileSync(path.join(HERE, "app", "app.js"), "utf8");
const indexHtml = readFileSync(path.join(HERE, "app", "index.html"), "utf8");
const swJs = readFileSync(path.join(HERE, "app", "sw.js"), "utf8");
check(appJs.includes("loadMemory"), "pin: app.js has loadMemory");
check(appJs.includes('"memory/forget"') || appJs.includes("memory/forget"), "pin: app.js calls memory/forget");
check(appJs.includes("memory/edit"), "pin: app.js calls memory/edit");
check(indexHtml.includes('id="s-memory"'), "pin: index.html has s-memory screen");
check(indexHtml.includes('data-r="memory"'), "pin: drawer links to memory");
check(/"memory"/.test(appJs.slice(appJs.indexOf("const ROUTES"), appJs.indexOf("const ROUTES") + 200)), "pin: ROUTES includes memory");
check(!swJs.includes('const V = "julie-v63"'), "pin: sw.js version bumped past julie-v63");

console.log(`\n${total - fails}/${total} checks passed`);
process.exit(fails ? 1 : 0);
