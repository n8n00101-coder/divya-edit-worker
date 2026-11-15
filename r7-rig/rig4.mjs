// Julie r7 rig4 — Ajju's exact path, run pre-fix (expect the trap) and
// post-fix (expect truth + persistence). Full journey:
//   seed local lvMini=false ("toggled off once") -> reload -> Settings
//   (record what the switch SHOWS vs what S holds) -> ONE tap on the switch
//   -> open live view -> inspect mini -> (post-fix also: send from mini,
//   toggle OFF, reload persistence checks).
import { spawn } from "node:child_process";
import { writeFileSync, mkdirSync } from "node:fs";
const SHELL = "/home/hatch/.cache/ms-playwright/chromium_headless_shell-1255/chrome-headless-shell-linux64/chrome-headless-shell";
const PORT = 9600 + Math.floor(Math.random() * 200);
const APP = process.argv[2] || "http://127.0.0.1:8907/";
const TAG = process.argv[3] || "run";
const OUT = "/tmp/rig/out-r7d-" + TAG + "-" + Date.now();
mkdirSync(OUT, { recursive: true });
const sleep = ms => new Promise(r => setTimeout(r, ms));
const log = (...a) => console.log("[r7d:" + TAG + "]", ...a);
const proc = spawn(SHELL, ["--remote-debugging-port=" + PORT, "--window-size=360,740", "--user-data-dir=/tmp/rig/profile-r7d-" + TAG + "-" + Date.now(), "--no-sandbox", "--disable-dev-shm-usage", "--mute-audio", "about:blank"], { stdio: ["ignore", "pipe", "pipe"] });
proc.stderr.on("data", () => {});
async function waitTarget() { for (let i = 0; i < 60; i++) { try { const r = await fetch(`http://127.0.0.1:${PORT}/json/list`); const list = await r.json(); const page = list.find(t => t.type === "page"); if (page) return page.webSocketDebuggerUrl; } catch {} await sleep(500); } throw new Error("no page target"); }
const ws = new WebSocket(await waitTarget());
await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
let seq = 0; const pending = new Map();
const events = { exceptions: [] };
ws.onmessage = ev => { const m = JSON.parse(ev.data); if (m.id && pending.has(m.id)) { const { res, rej } = pending.get(m.id); pending.delete(m.id); m.error ? rej(new Error(JSON.stringify(m.error))) : res(m.result); return; } if (m.method === "Runtime.exceptionThrown") events.exceptions.push(m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text); };
const cmd = (method, params = {}) => new Promise((res, rej) => { const id = ++seq; pending.set(id, { res, rej }); ws.send(JSON.stringify({ id, method, params })); });
const evl = async expr => { const r = await cmd("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true }); if (r.exceptionDetails) throw new Error("EVAL: " + (r.exceptionDetails.exception?.description || r.exceptionDetails.text)); return r.result.value; };
async function shot(name) { const r = await cmd("Page.captureScreenshot", { format: "png" }); writeFileSync(`${OUT}/${name}.png`, Buffer.from(r.data, "base64")); log("screenshot", name); }
async function clickPt(x, y) { await cmd("Input.dispatchMouseEvent", { type: "mousePressed", x, y, button: "left", clickCount: 1 }); await cmd("Input.dispatchMouseEvent", { type: "mouseReleased", x, y, button: "left", clickCount: 1 }); }
async function tapSwitch() { await evl(`document.querySelector('#setLvMini').closest('.switch').scrollIntoView({ block: 'center' })`); await sleep(500); const pt = await evl(`(() => { const sw = document.querySelector('#setLvMini').closest('.switch'); const r = sw.getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; })()`); await clickPt(pt.x, pt.y); await sleep(300); const after = await evl(`document.querySelector('#setLvMini').checked`); return after; }
async function waitFor(expr, label, ms = 30000) { const t0 = Date.now(); while (Date.now() - t0 < ms) { if (await evl(expr).catch(() => false)) { log("ok:", label); return true; } await sleep(400); } log("TIMEOUT:", label); return false; }
const stateExpr = `(() => ({ S_lvMini: S.lvMini, ls: localStorage.getItem("dv_lvMini"), cb: document.querySelector("#setLvMini") ? document.querySelector("#setLvMini").checked : "no-cb" }))()`;
const prefsExpr = `api("prefs").then(d => JSON.stringify(d.prefs)).catch(e => "ERR " + e.message)`;
const miniExpr = `(() => { const m = document.querySelector("[data-lv-mini]"); if (!m) return { exists: false }; const cs = getComputedStyle(m); const r = m.getBoundingClientRect(); return { exists: true, hiddenAttr: m.hidden, display: cs.display, bbox: { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) }, onScreen: r.width > 0 && r.height > 0 && r.top < innerHeight && r.bottom > 0, S_lvMini: S.lvMini }; })()`;
const stubFrame = `(() => { const c = document.createElement('canvas'); c.width = 412; c.height = 915; const g = c.getContext('2d'); g.fillStyle = '#fff'; g.fillRect(0, 0, 412, 915); g.fillStyle = '#202020'; g.font = '28px sans-serif'; g.fillText('YouTube (stub frame)', 30, 80); g.fillStyle = '#c00'; g.fillRect(30, 120, 200, 110); const img = document.querySelector('[data-lv-img]'); if (img) img.src = c.toDataURL('image/png'); const w = document.querySelector('[data-lv-wait]'); if (w) w.hidden = true; const st = document.querySelector('[data-lv-status]'); if (st) st.textContent = 'Working - youtube.com (stub)'; })()`;

await cmd("Page.enable"); await cmd("Runtime.enable"); await cmd("Network.enable"); await cmd("Log.enable");
await cmd("Emulation.setDeviceMetricsOverride", { width: 360, height: 740, deviceScaleFactor: 2, mobile: true });
await cmd("Emulation.setEmulatedMedia", { features: [{ name: "prefers-color-scheme", value: "light" }] });
await cmd("Page.navigate", { url: APP });
await sleep(3500);
const email = `r7d-${TAG}-${Date.now()}@example.com`;
await waitFor(`!!document.querySelector('#suForm') || !document.querySelector('#main')?.hidden`, "app booted", 20000);
await evl(`(() => { const b = document.querySelector('#tab-su') || [...document.querySelectorAll('#authTabs button')].find(x => x.dataset.v === 'su'); b && b.click(); })()`);
await sleep(600);
await evl(`(() => { const set = (s, v) => { const e = document.querySelector(s); e.value = v; e.dispatchEvent(new Event('input', { bubbles: true })); }; set('#suName', 'R7D Test'); set('#suEmail', ${JSON.stringify(email)}); set('#suPass', 'rigtest-pass-123'); })()`);
await evl(`document.querySelector('#suForm').requestSubmit()`);
await waitFor(`document.querySelector('#main') && !document.querySelector('#main').hidden`, "entered app", 25000);
await sleep(2000);
log("signup:", email);

// seed: "toggled off once in the past" (local store only — server can never hold it pre-fix)
await evl(`store.set("lvMini", false)`);
await cmd("Page.reload");
await waitFor(`document.querySelector('#main') && !document.querySelector('#main').hidden`, "re-entered (seeded OFF)", 25000);
await sleep(2000);
log("STATE seeded OFF after reload:", JSON.stringify(await evl(stateExpr)), "| server:", await evl(prefsExpr));

// Settings: what does the switch SHOW?
await evl(`location.hash = '#/settings'`);
await waitFor(`!!document.querySelector('#setLvMini')`, "settings rendered", 15000);
await sleep(600);
const st0 = await evl(stateExpr);
log("AT SETTINGS: S =", st0.S_lvMini, "| switch shows checked =", st0.cb, st0.cb !== st0.S_lvMini ? "<<< DESYNC (switch lies)" : "(in sync)");
await shot("01-settings-seeded-off");

// Ajju's ONE tap to "turn it ON"
await tapSwitch();
await sleep(1500);
const st1 = await evl(stateExpr);
log("AFTER ONE TAP: S =", st1.S_lvMini, "| switch checked =", st1.cb, "| server:", await evl(prefsExpr));
await shot("02-settings-after-one-tap");

// open live view
await evl(`openLive(false)`); await sleep(900); await evl(stubFrame); await sleep(300);
const m1 = await evl(miniExpr);
log("MINI after Ajju-path:", JSON.stringify(m1));
await shot("03-live-after-ajju-path");

if (TAG === "fixed") {
  // send a message from the mini box -> Julie should answer in chat
  await evl(`(() => { const i = document.querySelector('[data-lv-mini-text]'); i.focus(); i.value = 'Hi Julie, quick test from the floating box'; })()`);
  const sendPt = await evl(`(() => { const b = document.querySelector('[data-lv-mini-send]'); const r = b.getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; })()`);
  await clickPt(sendPt.x, sendPt.y);
  await sleep(800);
  log("mini status after send:", await evl(`document.querySelector('[data-lv-mini-status]')?.textContent || ""`));
  await shot("04-live-mini-sent");
  await evl(`closeLive()`);
  await evl(`location.hash = '#/chat'`);
  const gotReply = await waitFor(`(() => { const ms = document.querySelector('#msgs'); return ms && /floating box/i.test(ms.textContent || "") && [...ms.querySelectorAll('.msg')].length >= 2; })()`, "mini message + Julie reply in chat", 45000);
  log("chat has mini msg + reply:", gotReply);
  await shot("05-chat-after-mini-send");
  // toggle OFF -> box gone; reload -> persists (server)
  await evl(`location.hash = '#/settings'`);
  await waitFor(`!!document.querySelector('#setLvMini')`, "settings again", 15000);
  await sleep(500);
  for (let attempt = 1; attempt <= 3 && (await evl(stateExpr)).cb; attempt++) { const r = await tapSwitch(); log("toggle-OFF tap attempt", attempt, "-> checked:", r); await sleep(900); }
  log("STATE after toggle OFF:", JSON.stringify(await evl(stateExpr)), "| server:", await evl(prefsExpr));
  await evl(`openLive(false)`); await sleep(700);
  log("MINI after toggle OFF:", JSON.stringify(await evl(miniExpr)));
  await evl(`closeLive()`);
  await cmd("Page.reload");
  await waitFor(`document.querySelector('#main') && !document.querySelector('#main').hidden`, "re-entered (OFF persistence)", 25000);
  await sleep(2500);
  log("STATE after reload (expect OFF, server-held):", JSON.stringify(await evl(stateExpr)), "| server:", await evl(prefsExpr));
  // and back ON for a final visible proof + persistence
  await evl(`location.hash = '#/settings'`);
  await waitFor(`!!document.querySelector('#setLvMini')`, "settings final", 15000);
  await sleep(500);
  if (!(await evl(stateExpr)).cb) { await tapSwitch(); await sleep(1200); }
  log("STATE after toggle ON again:", JSON.stringify(await evl(stateExpr)), "| server:", await evl(prefsExpr));
  await cmd("Page.reload");
  await waitFor(`document.querySelector('#main') && !document.querySelector('#main').hidden`, "re-entered (ON persistence)", 25000);
  await sleep(2500);
  log("STATE after reload (expect ON, server-held):", JSON.stringify(await evl(stateExpr)), "| server:", await evl(prefsExpr));
  await evl(`openLive(false)`); await sleep(900); await evl(stubFrame); await sleep(300);
  log("MINI final (expect visible):", JSON.stringify(await evl(miniExpr)));
  await shot("06-live-final-on");
}
log("exceptions:", JSON.stringify(events.exceptions.slice(0, 6)));
log("OUT dir:", OUT);
proc.kill();
process.exit(0);
