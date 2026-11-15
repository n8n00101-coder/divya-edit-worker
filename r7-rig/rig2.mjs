// Julie r7 rig2 — OFF->ON toggle path for the floating mini box.
// Seeds a stored OFF state (localStorage + server prefs), then walks Ajju's
// exact path: Settings -> tap toggle ON -> open live view -> inspect.
// Also probes the loadStatus prefs-race (GET overriding a just-toggled ON).
import { spawn } from "node:child_process";
import { writeFileSync, mkdirSync } from "node:fs";

const SHELL = "/home/hatch/.cache/ms-playwright/chromium_headless_shell-1255/chrome-headless-shell-linux64/chrome-headless-shell";
const PORT = 9800 + Math.floor(Math.random() * 200);
const APP = process.argv[2] || "http://127.0.0.1:8907/";
const OUT = "/tmp/rig/out-r7b-" + Date.now();
mkdirSync(OUT, { recursive: true });
const sleep = ms => new Promise(r => setTimeout(r, ms));
const log = (...a) => console.log("[r7b]", ...a);

const proc = spawn(SHELL, [
  "--remote-debugging-port=" + PORT, "--window-size=360,740",
  "--user-data-dir=/tmp/rig/profile-r7b-" + Date.now(),
  "--no-sandbox", "--disable-dev-shm-usage", "--mute-audio", "about:blank",
], { stdio: ["ignore", "pipe", "pipe"] });
proc.stderr.on("data", () => {});

async function waitTarget() {
  for (let i = 0; i < 60; i++) {
    try { const r = await fetch(`http://127.0.0.1:${PORT}/json/list`); const list = await r.json(); const page = list.find(t => t.type === "page"); if (page) return page.webSocketDebuggerUrl; } catch {}
    await sleep(500);
  }
  throw new Error("no page target");
}
const ws = new WebSocket(await waitTarget());
await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
let seq = 0; const pending = new Map();
const events = { exceptions: [], prefsPosts: [] };
const reqUrls = new Map();
ws.onmessage = ev => {
  const m = JSON.parse(ev.data);
  if (m.id && pending.has(m.id)) { const { res, rej } = pending.get(m.id); pending.delete(m.id); m.error ? rej(new Error(JSON.stringify(m.error))) : res(m.result); return; }
  if (m.method === "Runtime.exceptionThrown") events.exceptions.push(m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text);
  if (m.method === "Network.requestWillBeSent") { reqUrls.set(m.params.requestId, m.params.request.method + " " + m.params.request.url); if (/\/api\/prefs/.test(m.params.request.url) && m.params.request.method === "POST") events.prefsPosts.push(m.params.request.postData || "(no body)"); }
};
const cmd = (method, params = {}) => new Promise((res, rej) => { const id = ++seq; pending.set(id, { res, rej }); ws.send(JSON.stringify({ id, method, params })); });
const evl = async expr => { const r = await cmd("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true }); if (r.exceptionDetails) throw new Error("EVAL: " + (r.exceptionDetails.exception?.description || r.exceptionDetails.text)); return r.result.value; };
async function shot(name) { const r = await cmd("Page.captureScreenshot", { format: "png" }); writeFileSync(`${OUT}/${name}.png`, Buffer.from(r.data, "base64")); log("screenshot", name); }
async function clickPt(x, y) { await cmd("Input.dispatchMouseEvent", { type: "mousePressed", x, y, button: "left", clickCount: 1 }); await cmd("Input.dispatchMouseEvent", { type: "mouseReleased", x, y, button: "left", clickCount: 1 }); }
async function tapEl(sel) { const pt = await evl(`(() => { const e = document.querySelector(${JSON.stringify(sel)}); if (!e) return null; const r = e.getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; })()`); if (!pt) throw new Error("no element " + sel); await clickPt(pt.x, pt.y); }
async function waitFor(expr, label, ms = 30000) { const t0 = Date.now(); while (Date.now() - t0 < ms) { if (await evl(expr).catch(() => false)) { log("ok:", label); return true; } await sleep(400); } log("TIMEOUT:", label); return false; }

const stateExpr = `(() => ({ S_lvMini: (typeof S !== "undefined") ? S.lvMini : "no-S", ls: localStorage.getItem("lvMini"), cb: document.querySelector("#setLvMini") ? document.querySelector("#setLvMini").checked : "no-cb" }))()`;
const prefsExpr = `api("prefs").then(d => JSON.stringify(d.prefs)).catch(e => "ERR " + e.message)`;
const miniExpr = `(() => { const m = document.querySelector("[data-lv-mini]"); if (!m) return { exists: false }; const cs = getComputedStyle(m); const r = m.getBoundingClientRect(); return { exists: true, hiddenAttr: m.hidden, display: cs.display, bbox: { y: Math.round(r.y), h: Math.round(r.height), w: Math.round(r.width) }, onScreen: r.height > 0 && r.top < innerHeight && r.bottom > 0, S_lvMini: S.lvMini }; })()`;
const stubFrame = `(() => { const c = document.createElement('canvas'); c.width = 412; c.height = 915; const g = c.getContext('2d'); g.fillStyle = '#fff'; g.fillRect(0, 0, 412, 915); g.fillStyle = '#202020'; g.font = '28px sans-serif'; g.fillText('YouTube (stub frame)', 30, 80); const img = document.querySelector('[data-lv-img]'); if (img) img.src = c.toDataURL('image/png'); const w = document.querySelector('[data-lv-wait]'); if (w) w.hidden = true; })()`;

await cmd("Page.enable"); await cmd("Runtime.enable"); await cmd("Network.enable"); await cmd("Log.enable");
await cmd("Emulation.setDeviceMetricsOverride", { width: 360, height: 740, deviceScaleFactor: 2, mobile: true });
await cmd("Emulation.setEmulatedMedia", { features: [{ name: "prefers-color-scheme", value: "light" }] });
await cmd("Page.navigate", { url: APP });
await sleep(3500);

const email = `r7b-${Date.now()}@example.com`;
await waitFor(`!!document.querySelector('#suForm') || !document.querySelector('#main')?.hidden`, "app booted", 20000);
await evl(`(() => { const b = document.querySelector('#tab-su') || [...document.querySelectorAll('#authTabs button')].find(x => x.dataset.v === 'su'); b && b.click(); })()`);
await sleep(600);
await evl(`(() => { const set = (s, v) => { const e = document.querySelector(s); e.value = v; e.dispatchEvent(new Event('input', { bubbles: true })); }; set('#suName', 'R7B Test'); set('#suEmail', ${JSON.stringify(email)}); set('#suPass', 'rigtest-pass-123'); })()`);
await evl(`document.querySelector('#suForm').requestSubmit()`);
await waitFor(`document.querySelector('#main') && !document.querySelector('#main').hidden`, "entered app", 25000);
await sleep(2000);
log("signup:", email);

// ---- seed stored OFF state through the app's own channels ----
await evl(`api("prefs", { method: "POST", json: { lvMini: false } }).then(() => "posted")`);
await evl(`S.lvMini = false; store.set("lvMini", false); applyLvMini();`);
await cmd("Page.reload");
await waitFor(`document.querySelector('#main') && !document.querySelector('#main').hidden`, "re-entered after seeding OFF", 25000);
await sleep(2500);
log("STATE seeded OFF, after reload:", JSON.stringify(await evl(stateExpr)), "| server:", await evl(prefsExpr));

// live view while OFF (sanity: box hidden)
await evl(`openLive(false)`); await sleep(800); await evl(stubFrame); await sleep(300);
log("MINI while OFF:", JSON.stringify(await evl(miniExpr)));
await shot("01-live-off");
await evl(`closeLive()`);

// ---- Ajju's path: Settings -> tap the switch ON ----
await evl(`location.hash = '#/settings'`);
await waitFor(`!!document.querySelector('#setLvMini')`, "settings rendered", 15000);
await sleep(600);
log("STATE at settings (expect OFF):", JSON.stringify(await evl(stateExpr)));
await shot("02-settings-off");
// tap the visible switch knob area (the .switch span wrapping the checkbox)
await tapEl('#s-settings .row .switch');
await sleep(1500);
log("STATE after tap ON:", JSON.stringify(await evl(stateExpr)), "| server:", await evl(prefsExpr));
log("prefs POST bodies seen:", JSON.stringify(events.prefsPosts));
await shot("03-settings-on");

// race probe: hammer loadStatus for 3s (it re-reads prefs and can override S)
await evl(`(async () => { for (let i = 0; i < 6; i++) { await loadStatus().catch(() => {}); await new Promise(r => setTimeout(r, 300)); } return "done"; })()`);
log("STATE after loadStatus hammer:", JSON.stringify(await evl(stateExpr)), "| server:", await evl(prefsExpr));

// ---- open live view: the moment of truth ----
await evl(`openLive(false)`); await sleep(800); await evl(stubFrame); await sleep(300);
log("MINI after toggle ON:", JSON.stringify(await evl(miniExpr)));
await shot("04-live-after-toggle-on");

log("exceptions:", JSON.stringify(events.exceptions.slice(0, 6)));
log("OUT dir:", OUT);
proc.kill();
process.exit(0);
