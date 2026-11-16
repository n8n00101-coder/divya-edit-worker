// PROOF-FIXES Worker harness — runs the REAL merged Worker
// (cfworker/divya.js from this branch) in Node with a Map-backed KV.
// Proves, against the shipped bytes:
//   fix 3: rescue thresholds (a live 40-min-old job is NOT rescued;
//          an 80-min-silent job IS) and late-result surfacing (a
//          result posted after rescue lands as done + late_result
//          + the honest late note; a normal result is untouched).
//   fix 4: extractTopic rejects greeting seeds ("Helo") and still
//          extracts real topics (the function is evaluated from the
//          shipped source — it is not exported by the Worker).
// Usage: node harness.mjs <worker-file.mjs>
import { copyFileSync, readFileSync } from "node:fs";

const srcPath = process.argv[2];
if (!srcPath) { console.error("usage: node harness.mjs <worker.mjs>"); process.exit(2); }
copyFileSync(srcPath, new URL("./worker.mjs", import.meta.url));
const worker = (await import("./worker.mjs")).default;
const srcText = readFileSync(srcPath, "utf8");

// ---------- KV stub ----------
const map = new Map();
const KV = {
  async get(k, type) { const v = map.has(k) ? map.get(k) : null; if (v === null) return null; if (type === "arrayBuffer") return v instanceof Uint8Array ? v.buffer.slice(v.byteOffset, v.byteOffset + v.byteLength) : new TextEncoder().encode(String(v)).buffer; return v instanceof Uint8Array ? new TextDecoder().decode(v) : v; },
  async put(k, v) { map.set(k, v instanceof Uint8Array ? v : String(v)); },
  async delete(k) { map.delete(k); },
  async list({ prefix } = {}) { return { keys: [...map.keys()].filter(k => !prefix || k.startsWith(prefix)).map(name => ({ name })) }; },
};
const env = { KV, RUNNER_KEY: "test-runner-key", APP_KEK: Buffer.alloc(32, 7).toString("base64"), GOOGLE_CLIENT_ID: "cid", GOOGLE_CLIENT_SECRET: "csecret", OWNERS: "", FRIENDS: "" };
globalThis.fetch = async (url) => new Response(JSON.stringify({ error: "unstubbed " + url }), { status: 404, headers: { "content-type": "application/json" } });

const ctx = { waitUntil(p) { this._p = p; } };
let pass = 0, fail = 0;
const T = (name, cond, extra = "") => { if (cond) { pass++; console.log("PASS", name); } else { fail++; console.log("FAIL", name, extra); } };
const hist = (n, num) => { const v = map.get(`hist:${n}:${num}`); return v ? JSON.parse(v) : null; };
function seedHist(n, num, e) {
  // a real hist entry's `n` field is its own NUMBER (histPut keys on it)
  map.set(`hist:${n}:${num}`, JSON.stringify({ ...e, n: num }));
  map.set(`histjob:${e.job}`, `${n}:${num}`);
  map.set(`histcount:${n}`, String(Math.max(parseInt(map.get(`histcount:${n}`) || "0", 10), num)));
}
async function runnerPost(path, { job, body, raw } = {}) {
  const req = new Request("https://divya.n8n00101.workers.dev/api/" + path + (job ? `?job=${job}` : ""), {
    method: "POST",
    headers: { "x-runner-key": "test-runner-key", ...(raw ? { "content-type": "video/mp4" } : { "content-type": "application/json" }) },
    body: raw ? raw : JSON.stringify(body || {}),
  });
  const res = await worker.fetch(req, env, ctx);
  return { status: res.status, text: await res.text() };
}

// ---------- fix 4: extractTopic from the shipped source ----------
{
  const start = srcText.indexOf("const GREETING_SEED_RX");
  const end = srcText.indexOf("\n}\n", srcText.indexOf("function extractTopic")) + 3;
  T("extractTopic source located", start > 0 && end > start);
  const extractTopic = new Function(srcText.slice(start, end) + "\nreturn extractTopic;")();
  T('"Helo" is not a topic', extractTopic("Helo") === null, String(extractTopic("Helo")));
  T('"hello" is not a topic', extractTopic("hello") === null);
  T('"hii" is not a topic', extractTopic("hii") === null);
  T('"good morning" is not a topic', extractTopic("good morning") === null);
  T('"ok" is not a topic', extractTopic("ok") === null);
  T("real topic via 'on X'",
    /silk road/i.test(extractTopic("make a video on the silk road") || ""),
    String(extractTopic("make a video on the silk road")));
  T("real topic via 'gurinchi'",
    /photosynthesis/i.test(extractTopic("photosynthesis gurinchi video cheyyi") || ""),
    String(extractTopic("photosynthesis gurinchi video cheyyi")));
  T("real topic survives a greeting prefix word in a sentence",
    /black holes/i.test(extractTopic("make a video on black holes") || ""));
}

// ---------- fix 3a: rescue thresholds ----------
{
  const n = "u_rescue1", now = Date.now();
  map.set(`jobown:polljob1`, n);
  map.set(`appedit:${n}`, JSON.stringify({ job: "polljob1", num: 1, state: "running" }));
  seedHist(n, 1, { job: "polljob1", state: "running", pct: 40, at: now - 5 * 60000, upd: now });
  seedHist(n, 2, { job: "stuckjb1", state: "editing", pct: 0, at: now - 40 * 60000 });
  // a runner poll for the live job triggers the rescue sweep
  let r = await runnerPost("runner/state", { job: "polljob1", body: { state: "running", note: "working", pct: 41 } });
  T("runner state post ok", r.status === 200, r.text.slice(0, 120));
  let e = hist(n, 2);
  T("40-min-old editing job NOT rescued (was rescued at 30 before)",
    e && e.state === "editing" && !e.rescued, JSON.stringify(e));
  // age it past the new threshold: 80 minutes
  seedHist(n, 2, { job: "stuckjb1", state: "editing", pct: 0, at: now - 80 * 60000 });
  r = await runnerPost("runner/state", { job: "polljob1", body: { state: "running", note: "working", pct: 42 } });
  e = hist(n, 2);
  T("80-min-silent editing job IS rescued",
    e && e.state === "failed" && e.rescued === true, JSON.stringify(e));
}

// ---------- fix 3b: late result surfaces ----------
{
  const n = "u_late01";
  map.set(`jobown:latejob1`, n);
  map.set(`appedit:${n}`, JSON.stringify({ job: "latejob1", num: 1, state: "failed" }));
  seedHist(n, 1, { job: "latejob1", state: "failed", rescued: true, note: "Video machine start ayyi madhyalo aagipoyindhi — response raledhu. Tokens refund chesa. Malli order cheyyi.", at: Date.now() - 70 * 60000, failedAt: Date.now() - 10 * 60000 });
  const bytes = new Uint8Array([0, 0, 0, 24, 102, 116, 121, 112]); // fake mp4 head
  const r = await runnerPost("runner/result", { job: "latejob1", raw: bytes });
  T("late result accepted", r.status === 200, r.text.slice(0, 120));
  const e = hist(n, 1);
  T("late result flips the entry to done", e && e.state === "done", JSON.stringify(e));
  T("late result is flagged late_result", e && e.late_result === true);
  T("late note is honest about the delay + refund",
    e && /late ga ready/.test(e.note) && /refund/.test(e.note), e && e.note);
  T("late result restores the app pointer",
    !!map.get(`appjob:${n}`) && map.get(`curjob:${n}`) === "latejob1");
  T("late result bytes are stored", map.has(`res:latejob1`));
}

// ---------- fix 3c: a normal result is untouched ----------
{
  const n = "u_ok0001";
  map.set(`jobown:okjob001`, n);
  map.set(`appedit:${n}`, JSON.stringify({ job: "okjob001", num: 1, state: "running" }));
  seedHist(n, 1, { job: "okjob001", state: "running", pct: 90, at: Date.now() - 600000, upd: Date.now() });
  const bytes = new Uint8Array([0, 0, 0, 24, 102, 116, 121, 112]);
  const req = new Request("https://divya.n8n00101.workers.dev/api/runner/result?job=okjob001&note=clean%20delivery", {
    method: "POST", headers: { "x-runner-key": "test-runner-key", "content-type": "video/mp4" }, body: bytes,
  });
  const res = await worker.fetch(req, env, ctx);
  T("normal result accepted", res.status === 200);
  const e = hist(n, 1);
  T("normal result: done, no late flag, runner note kept",
    e && e.state === "done" && !e.late_result && e.note === "clean delivery",
    JSON.stringify(e));
}

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
