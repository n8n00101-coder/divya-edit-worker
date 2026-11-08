"use strict";
const API = "https://divya.n8n00101.workers.dev/api";
const $ = s => document.querySelector(s), $$ = s => [...document.querySelectorAll(s)];
const store = { get: (k, d) => { try { const v = localStorage.getItem("dv_" + k); return v === null ? d : JSON.parse(v); } catch { return d; } }, set: (k, v) => localStorage.setItem("dv_" + k, JSON.stringify(v)), del: k => localStorage.removeItem("dv_" + k) };
const S = { token: store.get("token", ""), number: store.get("number", ""), lang: store.get("lang", "te"), voice: store.get("voice", true), theme: store.get("theme", "auto") };

const T = {
  te: { loginSub: "Nee WhatsApp number ivvu. Code WhatsApp ki vasthundi.", getCode: "Code pampu", verify: "Login", codeHint: "Code raakapothe WhatsApp lo Divya ki \"login\" ani pampu.", changeNum: "Number marchu", codeSentTo: n => `+${n} ki WhatsApp lo code pampa.`,
    online: "Online", thinking: "Typing…", listening: "Vintunna…", releaseToSend: "Vadilithe pamputha", typeMsg: "Message…", holdMic: "Mic ni press chesi pattuko, matladu, vadilai.",
    emptyTitle: "Hi, nenu Divya", emptySub: "Chat cheyyi, matladu, leda video create cheyyamanu.", s1: "Ee roju em cheddam?", s2: "Oka video idea cheppu", s3: "Nuvvu em cheyagalavu?",
    createTitle: "Create", topicPh: "Topic (khaali ga unte nene select chestha)", voiceLang: "Voice language", voice: "Voice", female: "Female", male: "Male", length: "Length", createBtn: "Video create cheyyi", createNote: "Video ready ayyaka WhatsApp ki vasthundi.",
    jobRun: "Video tayaru avuthondi", jobRunSub: "Konchem time paduthundi. Ready ayyaka WhatsApp lo pampistha.", jobDone: "Last video ready", jobDoneSub: "WhatsApp chudu.", jobFail: "Last video fail ayyindi", jobFailSub: "Malli try cheyyi.", started: "Start chesa! WhatsApp lo vasthundi.",
    connectTitle: "Connect", connectNote: "Login page browser lo open avuthundi. Connect ayyaka ikkadiki tirigi raa.", connect: "Connect", connectedP: "Connected", soon: "Tvaralo", reconnect: "Malli",
    settingsTitle: "Settings", language: "Language", voiceReplies: "Voice replies", voiceRepliesSub: "Mic lo adigithe Divya gattiga reply chestundi", theme: "Theme", auto: "Auto", light: "Light", dark: "Dark", connected: "Connected accounts", install: "App install cheyyi", logout: "Logout",
    tChat: "Chat", tCreate: "Create", tConnect: "Connect", tSettings: "Settings", netErr: "Network problem. Malli try cheyyi.", visionOff: "Image", micDenied: "Mic permission ivvu (browser settings lo).", noRec: "Ee browser lo voice record avvadu.", loggedIn: n => `+${n} tho login`, waitCode: "Code already pampa. WhatsApp chudu.",
    iosInstall: "iPhone/iPad: Safari lo Share (□↑) nokki \"Add to Home Screen\" select cheyyi.", genericInstall: "Browser menu (⋮) lo \"Install app\" leda \"Add to Home screen\" nokku." },
  en: { loginSub: "Enter your WhatsApp number. The code comes on WhatsApp.", getCode: "Send code", verify: "Log in", codeHint: "No code? Send \"login\" to Divya on WhatsApp.", changeNum: "Change number", codeSentTo: n => `Code sent on WhatsApp to +${n}.`,
    online: "Online", thinking: "Typing…", listening: "Listening…", releaseToSend: "Release to send", typeMsg: "Message…", holdMic: "Press and hold the mic, speak, then let go.",
    emptyTitle: "Hi, I'm Divya", emptySub: "Chat, talk, or ask me to make a video.", s1: "What should we do today?", s2: "Give me a video idea", s3: "What can you do?",
    createTitle: "Create", topicPh: "Topic (leave empty and I'll pick one)", voiceLang: "Voice language", voice: "Voice", female: "Female", male: "Male", length: "Length", createBtn: "Create video", createNote: "The video arrives on WhatsApp when it's ready.",
    jobRun: "Making your video", jobRunSub: "This takes a while. It'll arrive on WhatsApp.", jobDone: "Last video is ready", jobDoneSub: "Check WhatsApp.", jobFail: "Last video failed", jobFailSub: "Try again.", started: "Started! It'll arrive on WhatsApp.",
    connectTitle: "Connect", connectNote: "Sign-in opens in your browser. Come back here when done.", connect: "Connect", connectedP: "Connected", soon: "Soon", reconnect: "Again",
    settingsTitle: "Settings", language: "Language", voiceReplies: "Voice replies", voiceRepliesSub: "When you speak, Divya answers aloud", theme: "Theme", auto: "Auto", light: "Light", dark: "Dark", connected: "Connected accounts", install: "Install app", logout: "Log out",
    tChat: "Chat", tCreate: "Create", tConnect: "Connect", tSettings: "Settings", netErr: "Network problem. Try again.", visionOff: "Image", micDenied: "Allow microphone access in browser settings.", noRec: "Voice recording isn't supported in this browser.", loggedIn: n => `Logged in as +${n}`, waitCode: "Code already sent. Check WhatsApp.",
    iosInstall: "iPhone/iPad: in Safari tap Share (□↑), then \"Add to Home Screen\".", genericInstall: "Open the browser menu (⋮) and choose \"Install app\" or \"Add to Home screen\"." },
};
const t = (k, ...a) => { const v = (T[S.lang] || T.te)[k]; return typeof v === "function" ? v(...a) : v ?? k; };
function applyLang() {
  document.documentElement.lang = S.lang;
  $$("[data-t]").forEach(e => e.textContent = t(e.dataset.t));
  $$("[data-tp]").forEach(e => e.placeholder = t(e.dataset.tp));
  $$("#setLang button").forEach(b => b.classList.toggle("on", b.dataset.v === S.lang));
  if ($("#msgs .empty")) renderEmpty();
  if (S.number) $("#me").textContent = t("loggedIn", S.number);
}
function applyTheme() {
  document.documentElement.dataset.theme = S.theme;
  $$("#setTheme button").forEach(b => b.classList.toggle("on", b.dataset.v === S.theme));
  const dark = S.theme === "dark" || (S.theme === "auto" && matchMedia("(prefers-color-scheme: dark)").matches);
  $$('meta[name="theme-color"]').forEach(m => { m.removeAttribute("media"); m.content = dark ? "#0c0c12" : "#f6f6fa"; });
}
function toast(msg) { const e = $("#toast"); e.textContent = msg; e.classList.add("show"); clearTimeout(toast.t); toast.t = setTimeout(() => e.classList.remove("show"), 2600); }
function sheet(msg) { $("#sheetText").textContent = msg; $("#sheet").hidden = false; }
$("#sheetOk").onclick = () => $("#sheet").hidden = true;

async function api(path, { method = "GET", json, form } = {}) {
  const h = {}; if (S.token) h.authorization = "Bearer " + S.token;
  let body; if (json) { h["content-type"] = "application/json"; body = JSON.stringify({ lang: S.lang, ...json }); } else if (form) body = form;
  const sep = path.includes("?") ? "&" : "?";
  const r = await fetch(API + "/" + path + (method === "GET" ? `${sep}lang=${S.lang}` : ""), { method, headers: h, body });
  const d = await r.json().catch(() => ({ ok: false, error: "bad response" }));
  if (r.status === 401 && path !== "login/verify") { logout(true); throw new Error("login"); }
  return { status: r.status, ...d };
}

/* ---------- login ---------- */
function showLogin() { $("#main").hidden = true; $("#login").hidden = false; $("#numForm").hidden = false; $("#codeForm").hidden = true; $("#loginErr").textContent = ""; setTimeout(() => $("#num").focus(), 300); }
$("#numForm").onsubmit = async e => {
  e.preventDefault(); const n = $("#num").value.replace(/\D/g, "");
  if (n.length !== 10) { $("#loginErr").textContent = "10 digits"; return; }
  $("#numBtn").disabled = true; $("#loginErr").textContent = "";
  try {
    const d = await api("login/start", { method: "POST", json: { number: n } });
    if (!d.ok) { $("#loginErr").textContent = d.error || t("netErr"); return; }
    S.pendingNum = "91" + n; $("#codeSent").textContent = d.sent === false ? t("waitCode") : t("codeSentTo", "91" + n);
    $("#numForm").hidden = true; $("#codeForm").hidden = false; setTimeout(() => $("#code").focus(), 200);
  } catch { $("#loginErr").textContent = t("netErr"); } finally { $("#numBtn").disabled = false; }
};
$("#code").oninput = e => { e.target.value = e.target.value.replace(/\D/g, "").slice(0, 6); if (e.target.value.length === 6) $("#codeForm").requestSubmit(); };
$("#codeForm").onsubmit = async e => {
  e.preventDefault(); $("#codeBtn").disabled = true; $("#loginErr").textContent = "";
  try {
    const d = await api("login/verify", { method: "POST", json: { number: S.pendingNum, code: $("#code").value } });
    if (!d.ok) { $("#loginErr").textContent = d.error || t("netErr"); $("#code").value = ""; return; }
    S.token = d.token; S.number = d.number; store.set("token", d.token); store.set("number", d.number); enter();
  } catch { $("#loginErr").textContent = t("netErr"); } finally { $("#codeBtn").disabled = false; }
};
$("#changeNum").onclick = showLogin;
function logout(silent) {
  if (!silent && S.token) api("logout", { method: "POST", json: {} }).catch(() => {});
  S.token = ""; store.del("token"); store.del("chat"); $("#msgs").innerHTML = ""; showLogin();
}

/* ---------- tabs ---------- */
function tab(name) {
  $$(".tabbar button").forEach(b => b.classList.toggle("on", b.dataset.tab === name));
  $$(".screen.tab").forEach(s => s.classList.toggle("active", s.id === "tab-" + name));
  if (name === "connect" || name === "settings") loadConnect();
  if (name === "create") loadStatus();
  if (name === "chat") scrollDown();
}
$$(".tabbar button").forEach(b => b.onclick = () => tab(b.dataset.tab));

/* ---------- chat ---------- */
const esc = s => s.replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const linkify = s => esc(s).replace(/https?:\/\/[^\s<]+/g, u => `<a href="${u}" target="_blank" rel="noopener">${u}</a>`);
function scrollDown() { const m = $("#msgs"); requestAnimationFrame(() => m.scrollTop = m.scrollHeight); }
function bubble(role, text, extra = {}) {
  $("#msgs .empty")?.remove();
  const d = document.createElement("div"); d.className = "msg " + (role === "user" ? "me" : role === "sys" ? "sys" : "bot");
  if (extra.img) { const i = new Image(); i.src = extra.img; d.appendChild(i); if (text) { const p = document.createElement("div"); p.textContent = text; d.appendChild(p); } }
  else d.innerHTML = (extra.heard ? `<span class="heard">🎙️</span>` : "") + linkify(text);
  $("#msgs").appendChild(d); scrollDown(); return d;
}
function typing(on) {
  $("#msgs .typing")?.remove(); $("#status").textContent = on ? t(on === "listen" ? "listening" : "thinking") : t("online");
  if (on === true) { const d = document.createElement("div"); d.className = "msg bot typing"; d.innerHTML = "<i></i><i></i><i></i>"; $("#msgs").appendChild(d); scrollDown(); }
}
function renderEmpty() {
  const m = $("#msgs"); m.innerHTML = "";
  const e = document.createElement("div"); e.className = "empty";
  e.innerHTML = `<img src="/icon-192.png" alt=""><h3>${esc(t("emptyTitle"))}</h3><div class="muted">${esc(t("emptySub"))}</div><div class="chips">${["s1", "s2", "s3"].map(k => `<button class="chip">${esc(t(k))}</button>`).join("")}</div>`;
  e.querySelectorAll(".chip").forEach(c => c.onclick = () => send(c.textContent));
  m.appendChild(e);
}
function saveChat() { store.set("chat", $$("#msgs .msg:not(.typing):not(.sys)").slice(-40).map(e => ({ r: e.classList.contains("me") ? "user" : "assistant", c: e.querySelector("img") ? "[image]" : e.textContent }))); }
async function loadHistory() {
  const cached = store.get("chat", null);
  const draw = list => { if (!list.length) return renderEmpty(); $("#msgs").innerHTML = ""; list.forEach(x => bubble(x.r, x.c)); };
  if (cached) draw(cached);
  try {
    const d = await api("history");
    if (d.ok) { const list = d.messages.filter(m => m.content).map(m => ({ r: m.role, c: m.content.replace(/^\[screenshot\] /, "🖼️ ").replace(/^\[app\] /, "") })); if (!cached || list.length) { draw(list); saveChat(); } }
  } catch {}
}
let busy = false;
async function send(text) {
  text = (text || "").trim(); if (!text || busy) return;
  busy = true; bubble("user", text); $("#input").value = ""; autoGrow(); updateBtn(); typing(true);
  try { const d = await api("chat", { method: "POST", json: { text } }); typing(false); bubble("bot", d.ok ? d.reply : (d.error || t("netErr"))); if (d.video_started) toast(t("started")); }
  catch (e) { typing(false); if (e.message !== "login") bubble("sys", t("netErr")); }
  busy = false; saveChat();
}
const input = $("#input");
function autoGrow() { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 140) + "px"; }
function updateBtn() { const has = !!input.value.trim(); $("#micSend").classList.toggle("send", has); $("#micSend").classList.toggle("mic", !has); }
input.addEventListener("input", () => { autoGrow(); updateBtn(); });
input.addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey && matchMedia("(pointer:fine)").matches) { e.preventDefault(); send(input.value); } });
$("#composer").onsubmit = e => { e.preventDefault(); send(input.value); };

/* image */
$("#attach").onclick = () => $("#file").click();
$("#file").onchange = async e => {
  const f = e.target.files[0]; e.target.value = ""; if (!f || busy) return;
  const small = await shrink(f); const url = URL.createObjectURL(small);
  const q = input.value.trim(); input.value = ""; autoGrow(); updateBtn();
  busy = true; bubble("user", q, { img: url }); typing(true);
  const fd = new FormData(); fd.append("image", small, "image.jpg"); fd.append("lang", S.lang); if (q) fd.append("q", q);
  try { const d = await api("image", { method: "POST", form: fd }); typing(false); bubble("bot", d.reply || d.error || t("netErr")); }
  catch (er) { typing(false); if (er.message !== "login") bubble("sys", t("netErr")); }
  busy = false; saveChat();
};
function shrink(file) {
  return new Promise(res => {
    const img = new Image(); img.onload = () => {
      const m = 1600, k = Math.min(1, m / Math.max(img.width, img.height)); const c = document.createElement("canvas");
      c.width = Math.round(img.width * k); c.height = Math.round(img.height * k); c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
      c.toBlob(b => res(b || file), "image/jpeg", 0.85);
    }; img.onerror = () => res(file); img.src = URL.createObjectURL(file);
  });
}

/* voice: push-to-talk */
let rec, chunks = [], recStart = 0, recTimer, stream;
const micBtn = $("#micSend");
function pickMime() { for (const m of ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"]) if (window.MediaRecorder && MediaRecorder.isTypeSupported?.(m)) return m; return ""; }
async function startRec() {
  if (busy) return;
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) return toast(t("noRec"));
  try { stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } }); }
  catch { return toast(t("micDenied")); }
  if (!micBtn.pressed) { stream.getTracks().forEach(x => x.stop()); return; }
  speechSynthesis?.cancel();
  const mime = pickMime(); rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined); chunks = [];
  rec.ondataavailable = e => e.data.size && chunks.push(e.data);
  rec.onstop = onRecStop; rec.start(); recStart = Date.now();
  micBtn.classList.add("recording"); $("#recBar").hidden = false; typing("listen");
  navigator.vibrate?.(15);
  recTimer = setInterval(() => { const s = Math.floor((Date.now() - recStart) / 1000); $("#recTime").textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; if (s >= 120) stopRec(); }, 250);
}
function stopRec() {
  clearInterval(recTimer); micBtn.classList.remove("recording"); $("#recBar").hidden = true; $("#recTime").textContent = "0:00";
  if (rec && rec.state !== "inactive") rec.stop(); else typing(false);
}
async function onRecStop() {
  stream?.getTracks().forEach(x => x.stop());
  const dur = Date.now() - recStart; typing(false);
  if (dur < 600) { toast(t("holdMic")); return; }
  const type = rec.mimeType || "audio/webm"; const ext = type.includes("mp4") ? "m4a" : type.includes("ogg") ? "ogg" : "webm";
  const blob = new Blob(chunks, { type });
  busy = true; const me = bubble("user", "🎙️ …"); typing(true);
  const fd = new FormData(); fd.append("audio", blob, "voice." + ext); fd.append("lang", S.lang);
  try {
    const d = await api("voice", { method: "POST", form: fd }); typing(false);
    if (d.ok) { me.innerHTML = `<span class="heard">🎙️</span>` + linkify(d.heard); bubble("bot", d.reply); if (S.voice) speak(d.reply); if (d.video_started) toast(t("started")); }
    else { me.remove(); bubble("sys", d.error || t("netErr")); }
  } catch (e) { typing(false); me.remove(); if (e.message !== "login") bubble("sys", t("netErr")); }
  busy = false; saveChat();
}
micBtn.addEventListener("pointerdown", e => { if (micBtn.classList.contains("send")) return; e.preventDefault(); micBtn.pressed = true; micBtn.setPointerCapture?.(e.pointerId); startRec(); });
const up = () => { if (!micBtn.pressed) return; micBtn.pressed = false; if (rec && rec.state === "recording") stopRec(); else if (!rec || rec.state === "inactive") { toast(t("holdMic")); } };
micBtn.addEventListener("pointerup", up); micBtn.addEventListener("pointercancel", up);
micBtn.addEventListener("click", e => { if (micBtn.classList.contains("send")) send(input.value); });
micBtn.addEventListener("contextmenu", e => e.preventDefault());

/* speech out */
let voices = []; const loadVoices = () => voices = speechSynthesis?.getVoices() || [];
if ("speechSynthesis" in window) { loadVoices(); speechSynthesis.onvoiceschanged = loadVoices; }
function speak(text) {
  if (!("speechSynthesis" in window)) return;
  const clean = text.replace(/https?:\/\/\S+/g, "").replace(/[\u{1F300}-\u{1FAFF}\u2600-\u27BF]/gu, "").trim(); if (!clean) return;
  const u = new SpeechSynthesisUtterance(clean); const telugu = /[\u0C00-\u0C7F]/.test(clean);
  const want = telugu ? ["te-IN"] : ["en-IN", "hi-IN", "en-GB", "en-US"];
  const fem = /female|heera|veena|neerja|swara|kalpana|zira|samantha|google/i;
  let v = null; for (const l of want) { const c = voices.filter(x => x.lang.replace("_", "-") === l); v = c.find(x => fem.test(x.name)) || c[0]; if (v) break; }
  if (v) { u.voice = v; u.lang = v.lang; } else u.lang = telugu ? "te-IN" : "en-IN";
  u.rate = 1; u.pitch = 1.1; speechSynthesis.cancel(); speechSynthesis.speak(u);
}

/* ---------- create ---------- */
$$(".seg[data-name] button").forEach(b => b.onclick = () => { b.parentElement.querySelectorAll("button").forEach(x => x.classList.toggle("on", x === b)); });
$("#createBtn").onclick = async () => {
  const pick = n => $(`.seg[data-name=${n}] .on`).dataset.v;
  $("#createBtn").disabled = true;
  try {
    const d = await api("create", { method: "POST", json: { topic: $("#topic").value.trim(), language: pick("language"), voice: pick("voice"), length: pick("length") } });
    if (d.ok) { toast(t("started")); $("#topic").value = ""; setJob("run"); setTimeout(loadStatus, 4000); } else { toast(d.error || t("netErr")); if (d.busy) setJob("run"); }
  } catch (e) { if (e.message !== "login") toast(t("netErr")); }
  $("#createBtn").disabled = false;
};
function setJob(kind, when) {
  if (!kind) return $("#jobCard").hidden = true;
  $("#jobCard").hidden = false; $("#jobDot").className = "pulse" + (kind === "done" ? " done" : kind === "fail" ? " fail" : "");
  $("#jobTitle").textContent = t(kind === "run" ? "jobRun" : kind === "done" ? "jobDone" : "jobFail");
  $("#jobSub").textContent = t(kind === "run" ? "jobRunSub" : kind === "done" ? "jobDoneSub" : "jobFailSub") + (when ? " · " + when : "");
}
let statusTimer;
async function loadStatus() {
  clearTimeout(statusTimer);
  try {
    const d = await api("status"); if (!d.ok) return;
    const r = d.runs?.[0]; const ago = ts => { const m = Math.round((Date.now() - new Date(ts)) / 60000); return m < 60 ? `${m} min` : `${Math.round(m / 60)} h`; };
    if (d.busy || (r && r.status !== "completed")) setJob("run", r ? ago(r.created_at) : "");
    else if (r) setJob(r.conclusion === "success" ? "done" : "fail", ago(r.updated_at));
    else if (d.last) setJob("done"); else setJob(null);
    if ($("#tab-create").classList.contains("active") && (d.busy || (r && r.status !== "completed"))) statusTimer = setTimeout(loadStatus, 15000);
  } catch {}
}

/* ---------- connect ---------- */
const PDESC = { te: { youtube: "Videos upload cheyadaniki", google: "Gmail, Drive", instagram: "Reels post cheyadaniki", facebook: "Page lo post cheyadaniki", telegram: "Telegram lo kuda Divya" }, en: { youtube: "Upload videos", google: "Gmail, Drive", instagram: "Post Reels", facebook: "Post to your Page", telegram: "Divya on Telegram too" } };
const PCOL = { youtube: "#ff0033", google: "#4285f4", instagram: "linear-gradient(45deg,#f9a825,#e91e63,#7b1fa2)", facebook: "#1877f2", telegram: "#29a9eb" };
async function loadConnect() {
  try {
    const d = await api("connect"); if (!d.ok) return;
    $("#connCount").textContent = `${d.providers.filter(p => p.connected).length}/${d.providers.length}`;
    $("#provList").innerHTML = d.providers.map(p => `<div class="row"><div class="prov"><div class="pi" style="background:${PCOL[p.id]}">${p.name[0]}</div><div class="pt"><b>${esc(p.name)}</b><span class="muted small">${esc(p.connected ? (p.who || t("connectedP")) : (PDESC[S.lang]?.[p.id] || p.desc))}</span></div></div>
      ${p.connected ? `<span class="pill ok">✓ ${t("connectedP")}</span>` : p.ready ? `<button class="pill go" data-p="${p.id}">${t("connect")}</button>` : `<span class="pill wait">${t("soon")}</span>`}</div>`).join("");
    $$("#provList [data-p]").forEach(b => b.onclick = async () => {
      const w = window.open("about:blank", "_blank");
      const r = await api("connect/link", { method: "POST", json: { provider: b.dataset.p } }).catch(() => ({}));
      if (r.ok && r.url) { if (w) w.location = r.url; else location.href = r.url; } else { w?.close(); toast(r.error || t("netErr")); }
    });
  } catch {}
}
document.addEventListener("visibilitychange", () => { if (!document.hidden && S.token && $("#tab-connect").classList.contains("active")) loadConnect(); });

/* ---------- settings ---------- */
$$("#setLang button").forEach(b => b.onclick = () => { S.lang = b.dataset.v; store.set("lang", S.lang); applyLang(); loadConnect(); });
$$("#setTheme button").forEach(b => b.onclick = () => { S.theme = b.dataset.v; store.set("theme", S.theme); applyTheme(); });
$("#setVoice").onchange = e => { S.voice = e.target.checked; store.set("voice", S.voice); };
$("#goConnect").onclick = () => tab("connect");
$("#logout").onclick = () => logout(false);
matchMedia("(prefers-color-scheme: dark)").addEventListener?.("change", applyTheme);

/* install */
let deferred; const standalone = matchMedia("(display-mode: standalone)").matches || navigator.standalone;
window.addEventListener("beforeinstallprompt", e => { e.preventDefault(); deferred = e; $("#installRow").hidden = false; });
if (!standalone && /iphone|ipad|ipod/i.test(navigator.userAgent)) $("#installRow").hidden = false;
$("#installRow").onclick = async () => { if (deferred) { deferred.prompt(); await deferred.userChoice; deferred = null; $("#installRow").hidden = true; } else sheet(/iphone|ipad|ipod/i.test(navigator.userAgent) ? t("iosInstall") : t("genericInstall")); };
window.addEventListener("appinstalled", () => $("#installRow").hidden = true);

/* ---------- boot ---------- */
function enter() {
  $("#login").hidden = true; $("#main").hidden = false; $("#me").textContent = t("loggedIn", S.number);
  loadHistory(); loadConnect(); tab("chat");
}
applyTheme(); applyLang(); $("#setVoice").checked = S.voice; updateBtn();
if (S.token) enter(); else showLogin();
if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
