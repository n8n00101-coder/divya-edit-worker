// Round-5 (v51) server tests: F2 busy-wall guard, F3 edit hint/intent/
// anti-repeat. Extracts the REAL functions from cfworker/app_api.js —
// no copies; a source change breaks this test.
import { readFileSync } from "fs";
const SRC = readFileSync(new URL("../cfworker/app_api.js", import.meta.url), "utf8");

function extract(name) {
  for (const sig of [`async function ${name}(`, `function ${name}(`]) {
    const i = SRC.indexOf(sig);
    if (i < 0) continue;
    let depth = 0, started = false;
    for (let k = SRC.indexOf("{", i); k < SRC.length; k++) {
      if (SRC[k] === "{") { depth++; started = true; }
      else if (SRC[k] === "}") { depth--; if (started && depth === 0) return SRC.slice(i, k + 1); }
    }
  }
  const i = SRC.indexOf(`const ${name} =`);
  if (i >= 0) {
    let p = 0, b = 0, c = 0;
    for (let k = i; k < SRC.length; k++) {
      const ch = SRC[k];
      if (ch === "(") p++; else if (ch === ")") p--;
      else if (ch === "[") b++; else if (ch === "]") b--;
      else if (ch === "{") c++; else if (ch === "}") c--;
      else if (ch === ";" && p === 0 && b === 0 && c === 0) return SRC.slice(i, k + 1);
    }
  }
  throw new Error("not found: " + name);
}

const code = ["setupGuideReply", "busyWallGuard", "antiRepeatLine", "editHintRoute", "editHint"]
  .map(extract).join("\n") + "\nglobalThis.__x = { setupGuideReply, busyWallGuard, antiRepeatLine, editHintRoute, editHint };";
eval(code);
const X = globalThis.__x;

let pass = 0, fail = 0;
const eq = (label, got, want) => { const ok = JSON.stringify(got) === JSON.stringify(want); console.log((ok ? "PASS " : "FAIL ") + label + (ok ? "" : ` — got ${JSON.stringify(got)} want ${JSON.stringify(want)}`)); ok ? pass++ : fail++; };
const ok = (label, cond, extra = "") => { console.log((cond ? "PASS " : "FAIL ") + label + (cond ? "" : " " + extra)); cond ? pass++ : fail++; };

// ---- F2: the EXACT wall from Ajju's screenshot collapses to one short line ----
const WALL = "The shared AI is busy right now — its free limit is full, so it can't answer at the moment. It clears on its own in a bit, and you can try again. For no more limits, give one allow in Setup (#/setup) — Julie does everything: accounts, API keys, server setup, all in the background. You don't have to do anything. Only if needed: tap the verification link in your email once, and I'll do the rest. If an SMS code arrives on your phone, type that code once, and I'll do the rest. Your keys stay encrypted and are never shown to anyone.";
eq("F2 wall -> short line (en)", X.busyWallGuard(WALL, "en"), X.setupGuideReply("en"));
eq("F2 wall -> short line (te)", X.busyWallGuard(WALL, "te"), X.setupGuideReply("te"));
ok("F2 short line is one line <=180 chars", !X.setupGuideReply("en").includes("\n") && X.setupGuideReply("en").length <= 180, X.setupGuideReply("en").length);
eq("F2 normal reply untouched", X.busyWallGuard("Your video is ready — nice work!", "en"), "Your video is ready — nice work!");
eq("F2 short busy line itself untouched", X.busyWallGuard(X.setupGuideReply("en"), "en"), X.setupGuideReply("en"));

// ---- F3: edit hint is ONE short line, asks for the video / offers to make one ----
for (const lg of ["en", "te"]) {
  const h = X.editHint(lg);
  ok(`F3 hint ${lg} one line`, !h.includes("\n"));
  ok(`F3 hint ${lg} short (<170)`, h.length < 170, String(h.length));
  ok(`F3 hint ${lg} no old paragraph`, !/attach it yourself|Julie makes videos herself/.test(h), h);
}
ok("F3 hint en offers to make one", /make one/.test(X.editHint("en")));

// ---- F3: Romanized-Telugu + typo intent routes like English ----
eq("F3 route: Ajju exact phrase", X.editHintRoute("Short videps okati edits chesi ivvu"), true);
eq("F3 route: english edit", X.editHintRoute("edit this short video"), true);
eq("F3 route: plain video mention", X.editHintRoute("video"), true);
eq("F3 route: song excluded", X.editHintRoute("play a song"), false);
eq("F3 route: paata excluded", X.editHintRoute("video paata play cheyyi"), false);
eq("F3 route: unrelated", X.editHintRoute("what is the time"), false);

// ---- F3: anti-repeat lines ----
ok("F3 anti-repeat greeting differs + short", X.antiRepeatLine("Hello", "en").length < 80 && !/Need a video/.test(X.antiRepeatLine("Hello", "en")));
ok("F3 anti-repeat te greeting", /start chestha/.test(X.antiRepeatLine("Helo", "te")));
ok("F3 anti-repeat generic", X.antiRepeatLine("status?", "en").length < 100);

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
