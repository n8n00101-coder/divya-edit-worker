// Julie r7 rig — floating mini message box (Y3) reproduction/proof.
// Raw CDP driver for chrome-headless-shell (no deps), modelled on r6-rig.
// Usage: node rig.mjs [appUrl] [mode]   mode = repro | fixed (default repro; same flow)
import { spawn } from "node:child_process";
import { writeFileSync, mkdirSync } from "node:fs";

const SHELL = "/home/hatch/.cache/ms-playwright/chromium_headless_shell-1255/chrome-headless-shell-linux64/chrome-headless-shell";
const PORT = 9500 + Math.floor(Math.random() * 300);
const APP = process.argv[2] || "http://127.0.0.1:8907/";
const OUT = "/tmp/rig/out-r7-" + Date.now();
mkdirSync(OUT, { recursive: true });

const sleep = ms => new Promise(r => setTimeout(r, ms));
const log = (...a) => console.log("[r7]", ...a);

const proc = spawn(SHELL, [
  "--remote-debugging-port=" + PORT, "--window-size=360,740",
  "--user-data-dir=/tmp/rig/profile-r7-" + Date.now(),
  "--no-sandbox", "--disable-dev-shm-usage", "--mute-audio", "about:blank",
], { stdio: ["ignore", "pipe", "pipe"] });
proc.stderr.on("data", () => {});

async function waitTarget() {
  for (let i = 0; i < 60; i++) {
    try {
      const r = await fetch(`http://127.0.0.1:${PORT}/json/list`);
      const list = await r.json();
      const page = list.find(t => t.type === "page");
      if (page) return page.webSocketDebuggerUrl;
    } catch {}
    await sleep(500);
  }
  throw new Error("no page target");
}

const ws = new WebSocket(await waitTarget());
await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
let seq = 0; const pending = new Map();
const events = { console: [], exceptions: [], prefs: [] };
const reqUrls = new Map();
ws.onmessage = ev => {
  const m = JSON.parse(ev.data);
  if (m.id && pending.has(m.id)) { const { res, rej } = pending.get(m.id); pending.delete(m.id); m.error ? rej(new Error(JSON.stringify(m.error))) : res(m.result); return; }
  if (m.method === "Runtime.consoleAPICalled") events.console.push(m.params.args.map(a => a.value ?? a.description ?? "").join(" "));
  if (m.method === "Runtime.exceptionThrown") events.exceptions.push(m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text);
  if (m.method === "Log.entryAdded" && m.params.entry.level === "error") events.console.push("LOG-ERR: " + m.params.entry.text);
  if (m.method === "Network.requestWillBeSent") reqUrls.set(m.params.requestId, m.params.request.method + " " + m.params.request.url);
  if (m.method === "Network.responseReceived" && /\/api\/prefs/.test(m.params.response.url)) {
    const id = m.params.requestId;
    cmd("Network.getResponseBody", { requestId: id }).then(r => events.prefs.push((reqUrls.get(id) || "?") + " -> " + m.params.response.status + " " + (r.body || "").slice(0, 200))).catch(() => {});
  }
};
const cmd = (method, params = {}) => new Promise((res, rej) => { const id = ++seq; pending.set(id, { res, rej }); ws.send(JSON.stringify({ id, method, params })); });
const evl = async expr => { const r = await cmd("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true }); if (r.exceptionDetails) throw new Error("EVAL: " + (r.exceptionDetails.exception?.description || r.exceptionDetails.text)); return r.result.value; };
async function shot(name) { const r = await cmd("Page.captureScreenshot", { format: "png" }); writeFileSync(`${OUT}/${name}.png`, Buffer.from(r.data, "base64")); log("screenshot", name); }
async function clickPt(x, y) { await cmd("Input.dispatchMouseEvent", { type: "mousePressed", x, y, button: "left", clickCount: 1 }); await cmd("Input.dispatchMouseEvent", { type: "mouseReleased", x, y, button: "left", clickCount: 1 }); }
async function clickCenter(sel) { const pt = await evl(`(() => { const e = document.querySelector(${JSON.stringify(sel)}); if (!e) return null; const r = e.getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; })()`); if (!pt) throw new Error("no element " + sel); await clickPt(pt.x, pt.y); }
async function waitFor(expr, label, ms = 30000) { const t0 = Date.now(); while (Date.now() - t0 < ms) { if (await evl(expr).catch(() => false)) { log("ok:", label); return true; } await sleep(400); } log("TIMEOUT:", label); return false; }

const stateExpr = `(() => ({
  S_lvMini: (typeof S !== "undefined") ? S.lvMini : "no-S",
  ls_lvMini: localStorage.getItem("lvMini"),
  themeAttr: document.documentElement.getAttribute("data-theme") || document.body.getAttribute("data-theme"),
  cbChecked: document.querySelector("#setLvMini") ? document.querySelector("#setLvMini").checked : "no-cb",
}))()`;
const prefsExpr = `api("prefs").then(d => JSON.stringify(d)).catch(e => "ERR " + e.message)`;

const miniInspect = `(() => {
  const m = document.querySelector("[data-lv-mini]");
  const lv = document.querySelector("#liveView");
  if (!m) return { exists: false, liveViewExists: !!lv };
  const cs = getComputedStyle(m);
  const r = m.getBoundingClientRect();
  const inp = m.querySelector("input");
  const ics = inp ? getComputedStyle(inp) : null;
  const cx = r.x + r.width / 2, cy = r.y + r.height / 2;
  const atPoint = document.elementFromPoint(cx, cy);
  const kids = lv ? [...lv.children].map(c => { const b = c.getBoundingClientRect(); return c.className + " y=" + Math.round(b.y) + " h=" + Math.round(b.height) + " hidden=" + c.hidden; }) : [];
  return {
    exists: true, hiddenAttr: m.hidden, display: cs.display, visibility: cs.visibility, opacity: cs.opacity,
    bg: cs.backgroundColor, bbox: { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) },
    viewport: { w: innerWidth, h: innerHeight }, onScreen: r.width > 0 && r.height > 0 && r.bottom > 0 && r.top < innerHeight && r.right > 0 && r.left < innerWidth,
    inputColor: ics ? ics.color : null, inputPlaceholder: inp ? inp.placeholder : null,
    atPoint: atPoint ? (atPoint.className || atPoint.tagName) : null,
    lvHidden: lv ? lv.hidden : null, lvKids: kids,
    S_lvMini: (typeof S !== "undefined") ? S.lvMini : "no-S",
  };
})()`;

await cmd("Page.enable"); await cmd("Runtime.enable"); await cmd("Network.enable"); await cmd("Log.enable"); await cmd("DOM.enable");
await cmd("Emulation.setDeviceMetricsOverride", { width: 360, height: 740, deviceScaleFactor: 2, mobile: true });
// Ajju's phone: light system scheme + theme Auto (app default)
await cmd("Emulation.setEmulatedMedia", { features: [{ name: "prefers-color-scheme", value: "light" }] });
await cmd("Page.navigate", { url: APP });
await sleep(3500);

// ---- signup (throwaway) ----
const email = `r7test-${Date.now()}@example.com`;
await waitFor(`!!document.querySelector('#suForm') || !document.querySelector('#main')?.hidden`, "app booted", 20000);
await evl(`(() => { const b = document.querySelector('#tab-su') || [...document.querySelectorAll('#authTabs button')].find(x => x.dataset.v === 'su'); b && b.click(); })()`);
await sleep(600);
await evl(`(() => { const set = (s, v) => { const e = document.querySelector(s); e.value = v; e.dispatchEvent(new Event('input', { bubbles: true })); }; set('#suName', 'R7 Test'); set('#suEmail', ${JSON.stringify(email)}); set('#suPass', 'rigtest-pass-123'); })()`);
await evl(`document.querySelector('#suForm').requestSubmit()`);
const inApp = await waitFor(`document.querySelector('#main') && !document.querySelector('#main').hidden`, "entered app", 25000);
log("signup:", email, "| entered:", inApp);
await sleep(2500);
log("STATE after boot:", JSON.stringify(await evl(stateExpr)));
log("SERVER prefs after boot:", await evl(prefsExpr));

// ---- Settings: toggle ON (Ajju's path) ----
await evl(`location.hash = '#/settings'`);
await waitFor(`!!document.querySelector('#setLvMini')`, "settings rendered", 15000);
await sleep(800);
log("STATE at settings:", JSON.stringify(await evl(stateExpr)));
await shot("01-settings-toggle");
const wasChecked = await evl(`document.querySelector('#setLvMini').checked`);
if (!wasChecked) {
  await clickCenter('#setLvMini'); // the checkbox itself (switch wraps it)
  await sleep(1200);
  log("toggled ON via UI click");
} else log("toggle already ON");
log("STATE after toggle:", JSON.stringify(await evl(stateExpr)));
log("SERVER prefs after toggle:", await evl(prefsExpr));
await shot("02-settings-after-toggle");

// ---- reload: persistence ----
await cmd("Page.reload");
await waitFor(`document.querySelector('#main') && !document.querySelector('#main').hidden`, "re-entered app after reload", 25000);
await sleep(2500);
await evl(`location.hash = '#/settings'`);
await waitFor(`!!document.querySelector('#setLvMini')`, "settings rendered after reload", 15000);
await sleep(600);
log("STATE after reload:", JSON.stringify(await evl(stateExpr)));
log("SERVER prefs after reload:", await evl(prefsExpr));

// ---- open live view (shell) + stub frame ----
await evl(`openLive(false)`);
await sleep(1200);
// STUB STREAM: no real setup session can run in this rig; inject a synthetic
// frame so the stage looks like a live session (visibility of the mini box
// does not depend on the frame source).
await evl(`(() => {
  const c = document.createElement('canvas'); c.width = 412; c.height = 915;
  const g = c.getContext('2d'); g.fillStyle = '#fff'; g.fillRect(0, 0, 412, 915);
  g.fillStyle = '#202020'; g.font = '28px sans-serif'; g.fillText('YouTube (stub frame)', 30, 80);
  g.fillStyle = '#c00'; g.fillRect(30, 120, 200, 110);
  const img = document.querySelector('[data-lv-img]'); if (img) img.src = c.toDataURL('image/png');
  const w = document.querySelector('[data-lv-wait]'); if (w) w.hidden = true;
  const st = document.querySelector('[data-lv-status]'); if (st) st.textContent = 'Working · youtube.com (stub)';
})()`);
await sleep(600);
const insp1 = await evl(miniInspect);
log("MINI INSPECT (light, toggle ON):", JSON.stringify(insp1, null, 1));
await shot("03-live-light-toggle-on");

// ---- force-on isolation: if hidden, flip S + apply and re-inspect ----
if (insp1.exists && (insp1.hiddenAttr || insp1.display === "none")) {
  await evl(`S.lvMini = true; applyLvMini();`);
  await sleep(400);
  log("MINI INSPECT after force applyLvMini:", JSON.stringify(await evl(miniInspect), null, 1));
  await shot("04-live-light-forced-on");
}

// ---- toggle OFF from live state: applyLvMini path ----
await evl(`closeLive()`).catch(() => {});
log("prefs net events:", JSON.stringify(events.prefs));
log("console:", JSON.stringify(events.console.slice(0, 10)));
log("exceptions:", JSON.stringify(events.exceptions.slice(0, 10)));
log("OUT dir:", OUT);
proc.kill();
process.exit(0);
