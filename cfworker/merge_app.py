#!/usr/bin/env python3
"""Merge the Divya app API block into the currently deployed divya.js.
usage: merge_app.py <deployed multipart or js> <app_api.js> <out.js>"""
import re, sys
src = open(sys.argv[1], encoding="utf-8").read()
if src.startswith("--"):  # multipart from /content/v2
    m = re.search(r'name="divya\.js"[^\n]*\n(?:[^\n]*\n)*?\r?\n(.*)\r?\n--[0-9a-f]+--', src, re.S)
    src = m.group(1)
block = open(sys.argv[2], encoding="utf-8").read().strip("\n")
S, E = "// ===== DIVYA APP API", "// ===== DIVYA APP API — end =====\n"
if S in src:  # replace previous block
    a = src.index(S); b = src.index(E) + len(E)
    src = src[:a] + block + "\n" + src[b:]
else:
    i = src.index("export default {")
    src = src[:i] + block + "\n\n" + src[i:]
route = '    if (url.pathname.startsWith("/api/")) return appApi(req, env, url);\n'
if route not in src:
    anchor = "    const url = new URL(req.url);\n"
    i = src.index(anchor, src.index("async fetch(req, env, ctx)")) + len(anchor)
    src = src[:i] + route + src[i:]
login = '  if (/^\\s*\\/?(login|app login|app code)\\s*$/.test(tx0)) { if (await env.KV.get(`otpcool:${user}`)) return; await env.KV.put(`otpcool:${user}`, "1", { expirationTtl: 60 }); return say(env, user, `🔐 Divya app login code: ${await appCode(env, user)}\\n10 min lo expire avuthundi.`); }\n'
if "app login|app code" not in src:
    anchor = re.search(r"  if \(/\^\\s\*\\/\?connect\\s\*\$/\.test\(tx0\)\)[^\n]*\n", src)
    src = src[:anchor.end()] + login + src[anchor.end():]
# WhatsApp create path: same daily video quota as the app (owners exempt)
wa_busy = '    if (go && await env.KV.get(`busy:${user}`)) { ans = "Okka video already tayaru avuthondi. Adi vachaka next di start chestha."; go = false; }\n'
wa_q = '    if (go && !(await vidQuota(env, user)).ok) { ans = quotaMsg("te"); go = false; }\n'
if wa_q not in src:
    i = src.index(wa_busy) + len(wa_busy); src = src[:i] + wa_q + src[i:]
wa_go = '    if (go) return startCreate(env, user, (mm[1] || "AUTO").trim() || "AUTO");\n'
if wa_go in src:
    src = src.replace(wa_go, '    if (go) { await vidCount(env, user); return startCreate(env, user, (mm[1] || "AUTO").trim() || "AUTO"); }\n')
open(sys.argv[3], "w", encoding="utf-8").write(src)
print("merged", len(src))
