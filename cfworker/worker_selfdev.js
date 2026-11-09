// ===== DIVYA SELFDEV (owner-only self-improvement) — start =====
// Owner (OWNERS var) only. "divya change: <what>" -> plan on a branch -> "ok <id>" deploy, "cancel <id>", "undo", "changes".
async function selfdevDispatch(env, job) {
  return fetch(`https://api.github.com/repos/${env.GH_REPO}/actions/workflows/selfdev.yml/dispatches`, {
    method: "POST",
    headers: { Authorization: `token ${env.GH_TOKEN}`, "User-Agent": "divya", Accept: "application/vnd.github+json" },
    body: JSON.stringify({ ref: "main", inputs: { job } }),
  });
}
async function selfdevStart(env, user, action, id, request) {
  const job = crypto.randomUUID().slice(0, 8);
  await env.KV.put(`job:${job}`, JSON.stringify({ mode: "selfdev", action, id, request: request || "", to: user, OWNERS: env.OWNERS || "" }), { expirationTtl: 86400 });
  const r = await selfdevDispatch(env, job);
  return r.status === 204;
}
async function selfdevHandle(env, user, text) {
  const t = text.trim();
  let m = t.match(/^(?:divya\s*,?\s*)?(?:change|update|improve|self\s*change|marchu)\s*[:\-]\s*([\s\S]{3,2000})$/i);
  if (m) {
    if (await env.KV.get("selfdev:busy")) { await say(env, user, "Okka self-change already jaruguthondi. Adi ayyaka next di cheppu."); return true; }
    const id = Math.random().toString(36).slice(2, 8);
    await env.KV.put(`selfdev:${id}`, JSON.stringify({ id, request: m[1].trim(), state: "queued", at: Date.now() }), { expirationTtl: 86400 * 14 });
    await env.KV.put("selfdev:busy", id, { expirationTtl: 1800 });
    const ok = await selfdevStart(env, user, "plan", id, m[1].trim());
    if (!ok) { await env.KV.delete("selfdev:busy"); await say(env, user, "Self-change machine start avvaledu (GitHub). Konchem sepu tarvatha malli cheppu."); }
    return true;
  }
  m = t.match(/^(ok|deploy|cancel)\s+([a-z0-9]{6})$/i);
  if (m) {
    const rec = JSON.parse((await env.KV.get(`selfdev:${m[2].toLowerCase()}`)) || "null");
    if (!rec) { await say(env, user, `Change ${m[2]} kanipinchaledu.`); return true; }
    if (/cancel/i.test(m[1])) { rec.state = "cancelled"; await env.KV.put(`selfdev:${rec.id}`, JSON.stringify(rec), { expirationTtl: 86400 * 14 }); await say(env, user, `❌ Change ${rec.id} cancel chesa. Emi marchaledu.`); return true; }
    if (rec.state !== "ready") { await say(env, user, `Change ${rec.id} inka ready ledu (state: ${rec.state}).`); return true; }
    const ok = await selfdevStart(env, user, "apply", rec.id, rec.request);
    await say(env, user, ok ? `🚀 Change ${rec.id} deploy chesthunna...` : "Deploy start avvaledu (GitHub). Malli 'ok " + rec.id + "' pampu.");
    return true;
  }
  if (/^(undo|rollback|venakki)\s*$/i.test(t)) {
    const ok = await selfdevStart(env, user, "undo", "", "");
    await say(env, user, ok ? "↩️ Last change undo chesthunna..." : "Undo start avvaledu (GitHub).");
    return true;
  }
  if (/^(changes|self\s*changes)\s*$/i.test(t)) {
    const l = await env.KV.list({ prefix: "selfdev:" });
    const recs = (await Promise.all(l.keys.filter(k => k.name !== "selfdev:busy").slice(-10).map(async k => JSON.parse((await env.KV.get(k.name)) || "null")))).filter(Boolean);
    await say(env, user, recs.length ? recs.sort((a, b) => b.at - a.at).map(r => `${r.id} · ${r.state} · ${r.request.slice(0, 60)}`).join("\n") : "Inka self-changes emi levu.");
    return true;
  }
  return false;
}
async function selfdevState(req, env) {
  if (req.headers.get("x-runner-key") !== env.RUNNER_KEY) return new Response("no", { status: 403 });
  const { id, state } = await req.json();
  if (id) {
    const rec = JSON.parse((await env.KV.get(`selfdev:${id}`)) || "null");
    if (rec) { rec.state = state; await env.KV.put(`selfdev:${id}`, JSON.stringify(rec), { expirationTtl: 86400 * 14 }); }
  }
  if (["ready", "failed", "live", "cancelled"].includes(state)) await env.KV.delete("selfdev:busy");
  return Response.json({ ok: true });
}
// ===== DIVYA SELFDEV — end =====
