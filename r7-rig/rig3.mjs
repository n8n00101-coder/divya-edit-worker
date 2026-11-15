// Julie r7 rig3 — prefs round-trip through the app's own api() (authenticated).
import { spawn } from "node:child_process";
import { mkdirSync } from "node:fs";
const SHELL = "/home/hatch/.cache/ms-playwright/chromium_headless_shell-1255/chrome-headless-shell-linux64/chrome-headless-shell";
const PORT = 9900 + Math.floor(Math.random() * 90);
const APP = process.argv[2] || "http://127.0.0.1:8907/";
mkdirSync("/tmp/rig", { recursive: true });
const sleep = ms => new Promise(r => setTimeout(r, ms));
const log = (...a) => console.log("[r7c]", ...a);
const proc = spawn(SHELL, ["--remote-debugging-port=" + PORT, "--window-size=360,740", "--user-data-dir=/tmp/rig/profile-r7c-" + Date.now(), "--no-sandbox", "--disable-dev-shm-usage", "--mute-audio", "about:blank"], { stdio: ["ignore", "pipe", "pipe"] });
proc.stderr.on("data", () => {});
async function waitTarget() { for (let i = 0; i < 60; i++) { try { const r = await fetch(`http://127.0.0.1:${PORT}/json/list`); const list = await r.json(); const page = list.find(t => t.type === "page"); if (page) return page.webSocketDebuggerUrl; } catch {} await sleep(500); } throw new Error("no page target"); }
const ws = new WebSocket(await waitTarget());
await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
let seq = 0; const pending = new Map();
ws.onmessage = ev => { const m = JSON.parse(ev.data); if (m.id && pending.has(m.id)) { const { res, rej } = pending.get(m.id); pending.delete(m.id); m.error ? rej(new Error(JSON.stringify(m.error))) : res(m.result); } };
const cmd = (method, params = {}) => new Promise((res, rej) => { const id = ++seq; pending.set(id, { res, rej }); ws.send(JSON.stringify({ id, method, params })); });
const evl = async expr => { const r = await cmd("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true }); if (r.exceptionDetails) throw new Error("EVAL: " + (r.exceptionDetails.exception?.description || r.exceptionDetails.text)); return r.result.value; };
async function waitFor(expr, label, ms = 30000) { const t0 = Date.now(); while (Date.now() - t0 < ms) { if (await evl(expr).catch(() => false)) { log("ok:", label); return true; } await sleep(400); } log("TIMEOUT:", label); return false; }

await cmd("Page.enable"); await cmd("Runtime.enable"); await cmd("Network.enable");
await cmd("Emulation.setDeviceMetricsOverride", { width: 360, height: 740, deviceScaleFactor: 2, mobile: true });
await cmd("Page.navigate", { url: APP });
await sleep(3500);
const email = `r7c-${Date.now()}@example.com`;
await waitFor(`!!document.querySelector('#suForm') || !document.querySelector('#main')?.hidden`, "app booted", 20000);
await evl(`(() => { const b = document.querySelector('#tab-su') || [...document.querySelectorAll('#authTabs button')].find(x => x.dataset.v === 'su'); b && b.click(); })()`);
await sleep(600);
await evl(`(() => { const set = (s, v) => { const e = document.querySelector(s); e.value = v; e.dispatchEvent(new Event('input', { bubbles: true })); }; set('#suName', 'R7C Test'); set('#suEmail', ${JSON.stringify(email)}); set('#suPass', 'rigtest-pass-123'); })()`);
await evl(`document.querySelector('#suForm').requestSubmit()`);
await waitFor(`document.querySelector('#main') && !document.querySelector('#main').hidden`, "entered app", 25000);
await sleep(1500);
log("signup:", email);
log("identity:", await evl(`JSON.stringify({ n: S.number, acct: S.acct && (S.acct.email || S.acct.id || S.acct.name) })`));
log("POST lvMini=false ->", await evl(`api("prefs", { method: "POST", json: { lvMini: false } }).then(d => JSON.stringify(d)).catch(e => "ERR " + e.message)`));
log("GET            ->", await evl(`api("prefs").then(d => JSON.stringify(d)).catch(e => "ERR " + e.message)`));
log("POST lvMini=true ->", await evl(`api("prefs", { method: "POST", json: { lvMini: true } }).then(d => JSON.stringify(d)).catch(e => "ERR " + e.message)`));
log("GET            ->", await evl(`api("prefs").then(d => JSON.stringify(d)).catch(e => "ERR " + e.message)`));
proc.kill();
process.exit(0);
