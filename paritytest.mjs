// v106 Muse-parity rig: (A) a BROWSE job's in-chat ask (OTP) is
// answered from chat — before v106 the answer routing only ever looked
// at the setup chain, so a code typed for a browse task vanished;
// (B) chain precedence when both wait; (C) source pins for the UI
// element parity changes in app/app.js and the brainstep ask action.
// Style follows acctcreatetest.mjs (in-memory KV, stubbed fetch, real
// fetch handler). Run: node paritytest.mjs
import path from "node:path";
import { pathToFileURL } from "node:url";
import { readFileSync } from "node:fs";

const HERE = path.dirname(new URL(import.meta.url).pathname);
let fails = 0;
function check(cond, label) {
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

const worker = (await import(pathToFileURL(path.join(HERE, "cfworker", "divya.js")).href)).default;

async function call(method, p, body) {
  const req = new Request("https://divya.test" + p, {
    method,
    headers: { "content-type": "application/json", authorization: `Bearer ${TOKEN}` },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const r = await worker.fetch(req, env, ctx);
  const text = await r.text();
  let json = null;
  try { json = JSON.parse(text); } catch {}
  return { status: r.status, json, text };
}
async function runner(method, p, body) {
  const req = new Request("https://divya.test" + p, {
    method,
    headers: { "content-type": "application/json", "x-runner-key": "test-runner" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const r = await worker.fetch(req, env, ctx);
  const text = await r.text();
  let json = null;
  try { json = JSON.parse(text); } catch {}
  return { status: r.status, json, text };
}
const getRec = k => { try { return JSON.parse(store.get(k) || "null"); } catch { return null; } };
const histText = () => (getRec(`h:${NUM}`) || []).map(m => m.content || "").join("\n");
const countOcc = (hay, needle) => hay.split(needle).length - 1;

// ---------- (A) browse job ask: stored, asked once, answered from chat ----------
const PROMPT = "Site oka verification code aduguthundhi — nee phone ki vachina code cheppu, nenu enter chestha.";
store.set(`browsecur:${NUM}`, JSON.stringify({ job: "jobp1", at: Date.now() }));
store.set("setupjob:jobp1", JSON.stringify({ job: "jobp1", user: NUM, provider: "browse", flow: "browse", task: "open the site and verify", state: "running", step: "browsing", upd: Date.now() }));
const aw = { id: "browse-otp-111-1", provider: "browse", kind: "otp", prompt: PROMPT, at: Date.now(), expires: Date.now() + 10 * 60 * 1000, attempts: 1 };
let r = await runner("POST", "/api/setup/runner/progress?job=jobp1", { state: "paused", step: "await-otp", reason: "sms", awaiting: aw });
let job = getRec("setupjob:jobp1");
check(r.status === 200 && job && job.awaiting && job.awaiting.id === aw.id,
  "browse ask: progress post stores the structured ask on the browse job");
check(countOcc(histText(), PROMPT) === 1, "browse ask: the ask lands in chat history exactly once");
r = await runner("POST", "/api/setup/runner/progress?job=jobp1", { state: "paused", step: "await-otp", reason: "sms", awaiting: aw });
check(countOcc(histText(), PROMPT) === 1, "browse ask: heartbeat re-post does not duplicate the chat ask");

// a non-code message is NOT consumed by the ask
r = await call("POST", "/api/chat", { text: "weather ela undi?" });
job = getRec("setupjob:jobp1");
check(!job.userInput, "browse ask: a non-code chat message is not consumed as the code");

// the code IS delivered to the browse job (no setup chain exists at all)
check(!store.has(`setupchain:${NUM}`), "browse ask: test setup has no setup chain (fallback is what routes)");
r = await call("POST", "/api/chat", { text: "482916" });
job = getRec("setupjob:jobp1");
check(job.userInput && job.userInput.value === "482916" && job.userInput.askId === aw.id,
  "browse ask: code-shaped chat reply is delivered to the BROWSE job as userInput");
check(r.json && typeof r.json.reply === "string" && /entering it|enter chesi/.test(r.json.reply) && /the site/.test(r.json.reply) && !r.json.reply.includes("482916"),
  "browse ask: Julie confirms (naming the site) without echoing the code");

// a second delivery for the same ask is refused (one value per ask)
r = await call("POST", "/api/chat", { text: "999999" });
job = getRec("setupjob:jobp1");
check(job.userInput && job.userInput.value === "482916", "browse ask: the same ask accepts exactly one value");

// ---------- (B) chain precedence: the chain job wins over browse ----------
store.delete("setupjob:jobp1"); store.delete(`browsecur:${NUM}`);
store.set(`setupchain:${NUM}`, JSON.stringify({ providers: ["kaggle"], current: "jobc9", browser: "profile", at: Date.now(), upd: Date.now() }));
store.set("setupjob:jobc9", JSON.stringify({ job: "jobc9", user: NUM, provider: "kaggle", state: "paused", step: "await-otp", awaiting: { id: "kaggle-otp-1", provider: "kaggle", kind: "otp", prompt: "Kaggle code?", at: Date.now(), expires: Date.now() + 600000, attempts: 1 }, upd: Date.now() }));
store.set(`browsecur:${NUM}`, JSON.stringify({ job: "jobp2", at: Date.now() }));
store.set("setupjob:jobp2", JSON.stringify({ job: "jobp2", user: NUM, provider: "browse", state: "paused", step: "await-otp", awaiting: { id: "browse-otp-2", provider: "browse", kind: "otp", prompt: "Site code?", at: Date.now(), expires: Date.now() + 600000, attempts: 1 }, upd: Date.now() }));
r = await call("POST", "/api/chat", { text: "112233" });
check(getRec("setupjob:jobc9").userInput && getRec("setupjob:jobc9").userInput.value === "112233" && !getRec("setupjob:jobp2").userInput,
  "precedence: with both waiting, the code goes to the setup chain job first");

// ---------- (C) source pins: brainstep ask + UI element parity ----------
const wsrc = readFileSync(path.join(HERE, "cfworker", "divya.js"), "utf8");
check(wsrc.includes("awaitingJobFor(env, u.n)") && wsrc.includes("awaitingJobFor(env, n)"),
  "worker pin: both answer paths resolve through awaitingJobFor");
check(wsrc.includes("ALWAYS use ask for codes"),
  "worker pin: brainstep teaches ask for OTP codes");
const asrc = readFileSync(path.join(HERE, "app", "app.js"), "utf8");
check(!asrc.includes("data-lv-zoom"), "ui pin: no Zoom button in the live view (Muse has none)");
check(asrc.includes("<b data-lv-status></b>"), "ui pin: the live header IS the status line (no product title before it)");
check(asrc.includes("data-lv-url"), "ui pin: the live view carries a page-URL line");
const bar = asrc.slice(asrc.indexOf('class="lv-bar"'), asrc.indexOf('class="lv-bar"') + 400);
check(bar.indexOf("data-lv-stop") > -1 && bar.indexOf("data-lv-stop") < bar.indexOf("data-lv-done") && bar.indexOf("data-lv-done") < bar.indexOf("data-lv-take"),
  "ui pin: bottom bar order is Stop task | I did it ✓ | Take control (Take control bottom-right)");
check(asrc.includes('liveBtn: "Open browser"'), "ui pin: the card button is named Open browser");
check(asrc.includes('lvMini: store.get("lvMini", false)'), "ui pin: floating message box defaults OFF in the live view");
check(!asrc.includes("Please tick the permission box first."), "ui pin: the Allow popup no longer says 'tick the permission box'");
const rb = asrc.slice(asrc.indexOf("function renderBrowseBox"), asrc.indexOf("function renderSetupBox"));
check((rb.match(/<button class="pill" data-a=/g) || []).length === 1 && rb.includes('data-a="live"'),
  "ui pin: the browse card carries exactly ONE button (Open browser)");
check(!rb.includes("tc-panel"), "ui pin: the browse card has no in-card Take Control panel");
check(rb.includes("openLive(paused)"), "ui pin: a paused card opens the browser straight into control mode");
check(asrc.includes('state === "not-started" && !d.active && !d.current'),
  "sweep pin: pollSetup treats the Worker's not-started state as idle (no phantom Setup running box/pill)");
check(asrc.includes("if (d.active) return false;"),
  "sweep pin: the setup prompt never fires while a setup/browse is already active");
check(asrc.includes('tokens / ${free ? "week" : "month"}'),
  "sweep pin: the free plan card labels its grant per week, matching the token card");
const csrc = readFileSync(path.join(HERE, "app", "app.css"), "utf8");
check(/\.sheet-bg\{[^}]*z-index:90/.test(csrc),
  "sweep pin: the sheet sits above the floating composer (z-index 90 > 70)");
const bsrc = readFileSync(path.join(HERE, "browse.py"), "utf8");
check(bsrc.includes('kind == "ask"') && bsrc.includes("S.await_user_input"),
  "runner pin: browse.py handles the ask action via the in-chat awaiting protocol");
check(bsrc.includes("value hidden"), "runner pin: the ask result recorded in history hides the value");

console.log();
if (fails) { console.log("PARITY RIG: " + fails + " FAILURES"); process.exit(1); }
console.log("PARITY RIG: ALL PASS");
