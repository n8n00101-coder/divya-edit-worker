// NEXT-ROUND (Fix 5b) Worker harness — runs the REAL Worker
// (cfworker/divya.js from this branch) in Node with a Map-backed
// KV and proves the /job payload's channel-pool wiring:
//   - an owner WITH a sealed second provider key (ukey:<n>:cerebras)
//     gets a payload carrying TWO providers, owner-first;
//   - an owner with NO sealed keys gets exactly the env pool
//     (one provider here) — nothing invented;
//   - the owner's sealed Add-Model record rides as CUSTOM_MODEL
//     (base + model + key present).
// Assertions are presence/counts only — key VALUES are never
// printed, here or anywhere.
// Usage: node harness.mjs <worker-file.mjs>
import { copyFileSync } from "node:fs";

const srcPath = process.argv[2];
if (!srcPath) { console.error("usage: node harness.mjs <worker.mjs>"); process.exit(2); }
copyFileSync(srcPath, new URL("./worker.mjs", import.meta.url));
const worker = (await import("./worker.mjs")).default;

// ---------- KV stub ----------
const map = new Map();
const KV = {
  async get(k, type) { const v = map.has(k) ? map.get(k) : null; if (v === null) return null; if (type === "arrayBuffer") return v instanceof Uint8Array ? v.buffer.slice(v.byteOffset, v.byteOffset + v.byteLength) : new TextEncoder().encode(String(v)).buffer; return v instanceof Uint8Array ? new TextDecoder().decode(v) : v; },
  async put(k, v) { map.set(k, v instanceof Uint8Array ? v : String(v)); },
  async delete(k) { map.delete(k); },
  async list({ prefix } = {}) { return { keys: [...map.keys()].filter(k => !prefix || k.startsWith(prefix)).map(name => ({ name })) }; },
};
// The production shape the second film ran with: exactly ONE
// provider key in the Worker env.
const env = { KV, RUNNER_KEY: "test-runner-key", APP_KEK: Buffer.alloc(32, 7).toString("base64"), GROQ_KEY: "env-groq-fixture", GOOGLE_CLIENT_ID: "cid", GOOGLE_CLIENT_SECRET: "csecret", OWNERS: "", FRIENDS: "" };
globalThis.fetch = async (url) => new Response(JSON.stringify({ error: "unstubbed " + url }), { status: 404, headers: { "content-type": "application/json" } });
const ctx = { waitUntil(p) { this._p = p; } };

let pass = 0, fail = 0;
const T = (name, cond, extra = "") => { if (cond) { pass++; console.log("PASS", name); } else { fail++; console.log("FAIL", name, extra); } };

// ---------- seal a key exactly as the Worker's storeKey does ----------
const kek = await crypto.subtle.importKey("raw", Buffer.from(env.APP_KEK, "base64"), { name: "AES-GCM" }, false, ["encrypt", "decrypt"]);
async function sealKey(n, prov, plain) {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ct = await crypto.subtle.encrypt({ name: "AES-GCM", iv, additionalData: new TextEncoder().encode(`${n}:${prov}`) }, kek, new TextEncoder().encode(plain));
  const b64 = (buf) => Buffer.from(new Uint8Array(buf)).toString("base64");
  map.set(`ukey:${n}:${prov}`, JSON.stringify({ ct: b64(iv) + "." + b64(ct), at: Date.now(), ok: true, source: "divya" }));
}

const CHAN_FIELDS = ["GROQ_KEY", "CEREBRAS_KEY", "GEMINI_KEY", "OPENROUTER_KEY", "SAMBANOVA_KEY", "NVIDIA_KEY", "ZAI_KEY", "MISTRAL_KEY", "COHERE_KEY"];
const providerCount = (p) => CHAN_FIELDS.filter(f => typeof p[f] === "string" && p[f].trim()).length;

async function fetchJob(job) {
  const req = new Request("https://divya.n8n00101.workers.dev/job", {
    method: "POST",
    headers: { "x-runner-key": "test-runner-key", "content-type": "application/json" },
    body: JSON.stringify({ job }),
  });
  const res = await worker.fetch(req, env, ctx);
  return { status: res.status, payload: JSON.parse(await res.text()) };
}

// ---------- owner WITH a sealed second key + an Add-Model record ----------
const OWNER = "u_chan1";
await sealKey(OWNER, "cerebras", "owner-cerebras-fixture");
await sealKey(OWNER, "custom", "owner-custom-fixture");
map.set(`umodel:${OWNER}`, JSON.stringify({ base: "https://api.cerebras.ai/v1", model: "gpt-oss-120b", also: [] }));
map.set("job:jobnr1", JSON.stringify({ to: OWNER, kind: "create", brief: "a long documentary" }));

{
  const { status, payload } = await fetchJob("jobnr1");
  T("/job answers 200 for the wired owner", status === 200, String(status));
  T("owner's sealed cerebras key reaches the payload", typeof payload.CEREBRAS_KEY === "string" && payload.CEREBRAS_KEY.length > 0);
  T("payload carries TWO providers for that owner (env groq + owner cerebras)", providerCount(payload) === 2, "count=" + providerCount(payload));
  T("env groq still present", typeof payload.GROQ_KEY === "string" && payload.GROQ_KEY.length > 0);
  T("CUSTOM_MODEL rides the payload with base + model", !!payload.CUSTOM_MODEL && payload.CUSTOM_MODEL.base === "https://api.cerebras.ai/v1" && payload.CUSTOM_MODEL.model === "gpt-oss-120b", JSON.stringify(payload.CUSTOM_MODEL || null).slice(0, 120));
  T("CUSTOM_MODEL carries a key (presence only)", !!payload.CUSTOM_MODEL && typeof payload.CUSTOM_MODEL.key === "string" && payload.CUSTOM_MODEL.key.length > 0);
}

// ---------- owner with NO sealed keys: exactly the env pool ----------
map.set("job:jobnr2", JSON.stringify({ to: "u_plain", kind: "create", brief: "a long documentary" }));
{
  const { status, payload } = await fetchJob("jobnr2");
  T("/job answers 200 for the plain owner", status === 200, String(status));
  T("no owner keys -> payload is exactly the one-provider env pool", providerCount(payload) === 1, "count=" + providerCount(payload));
  T("no CUSTOM_MODEL without a sealed record", payload.CUSTOM_MODEL === null || payload.CUSTOM_MODEL === undefined);
}

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
