// Julie chat rig — raw CDP driver for chrome-headless-shell (no deps).
// Usage: node rig.mjs <scenario> [appUrl]
// Scenarios: video-send | text-send | image-send | queue
import { spawn } from "node:child_process";
import { writeFileSync, mkdirSync } from "node:fs";

const SHELL = "/home/hatch/.cache/ms-playwright/chromium_headless_shell-1255/chrome-headless-shell-linux64/chrome-headless-shell";
const PORT = 9400 + Math.floor(Math.random() * 400);
const scenario = process.argv[2] || "video-send";
const APP = process.argv[3] || "http://127.0.0.1:8901/";
const OUT = "/tmp/rig/out-" + scenario;
mkdirSync(OUT, { recursive: true });

const sleep = ms => new Promise(r => setTimeout(r, ms));
const log = (...a) => console.log("[rig]", ...a);

const proc = spawn(SHELL, [
  "--remote-debugging-port=" + PORT, "--window-size=360,740",
  "--user-data-dir=/tmp/rig/profile-" + scenario + "-" + Date.now(),
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
const events = { console: [], exceptions: [], requests: [], responses: [] };
ws.onmessage = ev => {
  const m = JSON.parse(ev.data);
  if (m.id && pending.has(m.id)) { const { res, rej } = pending.get(m.id); pending.delete(m.id); m.error ? rej(new Error(JSON.stringify(m.error))) : res(m.result); return; }
  if (m.method === "Runtime.consoleAPICalled") events.console.push(m.params.args.map(a => a.value ?? a.description ?? "").join(" "));
  if (m.method === "Runtime.exceptionThrown") events.exceptions.push(m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text);
  if (m.method === "Log.entryAdded" && m.params.entry.level === "error") events.console.push("LOG-ERR: " + m.params.entry.text);
  if (m.method === "Network.requestWillBeSent") events.requests.push(m.params.request.method + " " + m.params.request.url);
  if (m.method === "Network.responseReceived") events.responses.push(m.params.response.status + " " + m.params.response.url);
};
const cmd = (method, params = {}) => new Promise((res, rej) => { const id = ++seq; pending.set(id, { res, rej }); ws.send(JSON.stringify({ id, method, params })); });
const evl = async expr => { const r = await cmd("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true }); if (r.exceptionDetails) throw new Error("EVAL: " + (r.exceptionDetails.exception?.description || r.exceptionDetails.text)); return r.result.value; };
async function shot(name) { const r = await cmd("Page.captureScreenshot", { format: "png" }); writeFileSync(`${OUT}/${name}.png`, Buffer.from(r.data, "base64")); log("screenshot", name); }
async function click(sel) { const pt = await evl(`(() => { const e = document.querySelector(${JSON.stringify(sel)}); if (!e) return null; const r = e.getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; })()`); if (!pt) throw new Error("no element " + sel); await cmd("Input.dispatchMouseEvent", { type: "mousePressed", x: pt.x, y: pt.y, button: "left", clickCount: 1 }); await cmd("Input.dispatchMouseEvent", { type: "mouseReleased", x: pt.x, y: pt.y, button: "left", clickCount: 1 }); }
async function waitFor(expr, label, ms = 30000) { const t0 = Date.now(); while (Date.now() - t0 < ms) { if (await evl(expr).catch(() => false)) { log("ok:", label); return true; } await sleep(400); } log("TIMEOUT:", label); return false; }

await cmd("Page.enable"); await cmd("Runtime.enable"); await cmd("Network.enable"); await cmd("Log.enable"); await cmd("DOM.enable");
await cmd("Emulation.setDeviceMetricsOverride", { width: 360, height: 740, deviceScaleFactor: 2, mobile: true });
await cmd("Page.navigate", { url: APP });
await sleep(3500);

// ---- signup (throwaway) ----
const email = `rigtest-${Date.now()}@example.com`;
await waitFor(`!!document.querySelector('#suForm') || !document.querySelector('#main')?.hidden`, "app booted", 20000);
await evl(`(() => { const b = document.querySelector('#tab-su') || [...document.querySelectorAll('#authTabs button')].find(x => x.dataset.v === 'su'); b && b.click(); })()`);
await sleep(600);
await evl(`(() => { const set = (s, v) => { const e = document.querySelector(s); e.value = v; e.dispatchEvent(new Event('input', { bubbles: true })); }; set('#suName', 'Rig Test'); set('#suEmail', ${JSON.stringify(email)}); set('#suPass', 'rigtest-pass-123'); })()`);
await evl(`document.querySelector('#suForm').requestSubmit()`);
const inApp = await waitFor(`document.querySelector('#main') && !document.querySelector('#main').hidden`, "entered app", 25000);
log("signup email:", email, "| entered:", inApp);
await sleep(1500);
// go to the CHAT screen (post-signup landing is Home; the user flow is in Chat)
await evl(`location.hash = '#/chat'`);
await waitFor(`(() => { const b = document.querySelector('#chatSend'); const r = b && b.getBoundingClientRect(); return r && r.width > 0; })()`, "chat screen visible", 15000);
await sleep(800);
await shot("01-after-signup");

// dismiss any setup sheet if present (tap a decline/close if visible) — record only
const sheetInfo = await evl(`(() => { const s = [...document.querySelectorAll('body *')].filter(e => e.offsetParent && /setup cheyala|Set up|setup/i.test(e.textContent || '') && e.children.length < 6).map(e => e.className + ':' + (e.textContent || '').slice(0, 60)); return s.slice(0, 4); })()`);
log("setup-ish elements:", JSON.stringify(sheetInfo));

const msgsDump = () => evl(`(() => [...document.querySelectorAll('#msgs .msg')].map(e => { const v = e.querySelector('video'); return { cls: e.className, text: (e.textContent || '').slice(0, 120), hasVideo: !!v, vidDur: v ? v.duration : null, vidReady: v ? v.readyState : null, vidSrc: v ? String(v.src).slice(0, 30) : null, vidJob: e.dataset.vidjob || null, hasImg: !!e.querySelector('img'), html: e.innerHTML.slice(0, 300) }; }))()`);

if (scenario === "video-send" || scenario === "queue") {
  // attach the test video through the real file input
  const doc = await cmd("DOM.getDocument", { depth: 1 });
  const node = await cmd("DOM.querySelector", { nodeId: doc.root.nodeId, selector: "#file" });
  await cmd("DOM.setFileInputFiles", { nodeId: node.nodeId, files: ["/tmp/test2s.mp4"] });
  log("file set on #file");
  for (let i = 0; i < 10; i++) {
    await sleep(2000);
    const st = await evl(`JSON.stringify({ chipHidden: document.querySelector('#attachChip')?.hidden, chipTxt: document.querySelector('#attachChipTxt')?.textContent || '', pending: typeof pendingVideo !== 'undefined' && pendingVideo ? pendingVideo.job : null, busy: typeof busy !== 'undefined' ? busy : '?', api: typeof API !== 'undefined' ? API : '?', toast: document.querySelector('#toast')?.textContent || '', sendDis: document.querySelector('#chatSend')?.disabled })`).catch(e => "EVALFAIL " + e.message);
    log("stage-poll", i, st);
    if (/"chipHidden":false/.test(st)) break;
  }
  const chipTxt = await evl(`document.querySelector('#attachChipTxt')?.textContent || ''`);
  const sendDisabled = await evl(`document.querySelector('#chatSend').disabled`);
  log("chip text:", chipTxt, "| send disabled:", sendDisabled);
  await shot("02-video-staged");
  await click("#chatSend");
  log("send tapped");
  await sleep(9000);
  const msgs = await msgsDump();
  log("MSGS after send:", JSON.stringify(msgs, null, 1));
  await shot("03-after-send");
  // reload → history render
  await cmd("Page.reload", {});
  await sleep(5000);
  const msgs2 = await msgsDump();
  log("MSGS after reload:", JSON.stringify(msgs2, null, 1));
  await shot("04-after-reload");
  if (scenario === "queue") {
    // send two quick texts while a turn may be in flight
    await evl(`(() => { const i = document.querySelector('#input'); i.value = 'queue test one'; i.dispatchEvent(new Event('input', { bubbles: true })); })()`);
    await evl(`document.querySelector('#chatSend').click()`);
    await evl(`(() => { const i = document.querySelector('#input'); i.value = 'queue test two'; i.dispatchEvent(new Event('input', { bubbles: true })); })()`);
    await evl(`document.querySelector('#chatSend').click()`);
    await sleep(12000);
    log("MSGS queue:", JSON.stringify(await msgsDump(), null, 1));
    await shot("05-queue");
  }
}

if (scenario === "text-send") {
  await evl(`(() => { window.__mlog = []; const t0 = Date.now(); const mo = new MutationObserver(rs => { for (const r of rs) { for (const n of r.removedNodes) if (n.nodeType === 1) window.__mlog.push({ t: Date.now() - t0, ev: 'REMOVED', cls: n.className, txt: (n.textContent || '').slice(0, 50) }); for (const n of r.addedNodes) if (n.nodeType === 1) window.__mlog.push({ t: Date.now() - t0, ev: 'ADDED', cls: n.className, txt: (n.textContent || '').slice(0, 50) }); } }); mo.observe(document.querySelector('#msgs'), { childList: true }); })()`);
  await evl(`(() => { const i = document.querySelector('#input'); i.value = 'Hello Julie, test message'; i.dispatchEvent(new Event('input', { bubbles: true })); })()`);
  await evl(`document.querySelector('#chatSend').click()`);
  await sleep(9000);
  log("MSGS text:", JSON.stringify(await msgsDump(), null, 1));
  log("MLOG:", await evl(`JSON.stringify(window.__mlog || [])`));
  await shot("02-text-sent");
}

if (scenario === "image-send") {
  const doc = await cmd("DOM.getDocument", { depth: 1 });
  const node = await cmd("DOM.querySelector", { nodeId: doc.root.nodeId, selector: "#file" });
  await cmd("DOM.setFileInputFiles", { nodeId: node.nodeId, files: ["/tmp/testimg.png"] });
  log("image set on #file");
  await sleep(12000);
  log("MSGS image:", JSON.stringify(await msgsDump(), null, 1));
  await shot("02-image-sent");
}

log("REQUESTS:", JSON.stringify(events.requests.filter(u => /edit|assist|image|videos/.test(u)), null, 1));
log("RESPONSES:", JSON.stringify(events.responses.filter(u => /edit|assist|image|videos/.test(u)), null, 1));
log("CONSOLE:", JSON.stringify(events.console.slice(0, 20)));
log("EXCEPTIONS:", JSON.stringify(events.exceptions.slice(0, 10)));
writeFileSync(`${OUT}/events.json`, JSON.stringify(events, null, 1));
proc.kill("SIGKILL");
process.exit(0);
