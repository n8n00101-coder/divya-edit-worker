"""Idempotently merge the selfdev block into the live divya Worker script. usage: patch_worker.py in.js out.js"""
import sys, re
src = open(sys.argv[1], encoding="utf-8").read()
blk = open(__file__.replace("patch_worker.py", "worker_selfdev.js"), encoding="utf-8").read()
if "DIVYA SELFDEV (owner-only" in src:
    src = re.sub(r"// ===== DIVYA SELFDEV \(owner-only[\s\S]*?// ===== DIVYA SELFDEV — end =====\n?", "", src)
# 1) block before export default
i = src.rindex("export default")
src = src[:i] + blk + "\n" + src[i:]
# 2) route
route = '    if (url.pathname === "/selfdev/state" && req.method === "POST") return selfdevState(req, env);\n'
if route not in src:
    a = 'if (url.pathname === "/done" && req.method === "POST") {'
    assert src.count(a) == 1, "done route anchor"
    src = src.replace(a, route.strip() + "\n    " + a)
# 3) owner hook inside handle() text branch
hook = '    if (isOwner && await selfdevHandle(env, user, text)) return;\n'
if hook not in src:
    a = '  if (m.type === "text") {\n    const text = m.text.body.trim();\n'
    assert src.count(a) == 1, "text anchor"
    src = src.replace(a, a + hook)
open(sys.argv[2], "w", encoding="utf-8").write(src)
print("patched", len(src))
