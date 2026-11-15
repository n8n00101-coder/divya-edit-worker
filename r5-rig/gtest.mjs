// v51 G1–G3 regression: extracts the REAL routing functions from the
// Worker sources and runs appTalk's busy-state gate order over the
// decision table — including Ajju's exact 2026-11-15 sentence.
import { readFileSync } from "fs";
const api = readFileSync(new URL("../cfworker/app_api.js", import.meta.url), "utf8");
const div = readFileSync(new URL("../cfworker/divya.js", import.meta.url), "utf8");
function grab(src, name) {
  const i = src.indexOf(`function ${name}(`);
  if (i < 0) throw new Error("not found: " + name);
  let d = 0, j = src.indexOf("{", i);
  for (let k = j; k < src.length; k++) { if (src[k] === "{") d++; else if (src[k] === "}") { d--; if (!d) return src.slice(i, k + 1); } }
  throw new Error("unbalanced: " + name);
}
const isCreateOrder = new Function(`${grab(api, "isCreateOrder")}; return isCreateOrder;`)();
const isNewTopicOrder = new Function(`${grab(api, "isNewTopicOrder")}; return isNewTopicOrder;`)();
const isAmendment = new Function(`${grab(api, "isCreateOrder")}\n${grab(div, "isAmendment")}; return isAmendment;`)();
const VOICE = /(voice|male|female|telugu|hindi|english|language|sound)/i;
// appTalk's busy-state gate order (v51): amendment → nextpref → create.
function routeBusy(text) {
  const newOrder = isNewTopicOrder(text);
  if (!newOrder && isAmendment(text)) return "AMENDMENT (this video)";
  if (!newOrder && !isCreateOrder(text) && VOICE.test(text)) return "VOICE-CHANGE (this video + kept)";
  return "CREATE (starts now)";
}
let pass = 0, fail = 0;
function t(name, got, want) { const ok = got === want; console.log(`${ok ? "PASS" : "FAIL"}  ${name}  -> ${got}${ok ? "" : ` (want ${want})`}`); ok ? pass++ : fail++; }

const AJJU = "Nee own ga chesi motham a to z chesi ivvu, topic loneliness, video motham voice over julie voice over motham anni nve cheyu";
t("G1 Ajju exact loneliness order while busy", routeBusy(AJJU), "CREATE (starts now)");
t("G1 'topic: space' order while busy", routeBusy("topic: space, oka video cheyu"), "CREATE (starts now)");
t("G1 a-to-z self-do order, no 'topic' word", routeBusy("motham a to z nve cheyu, oka video cheyu"), "CREATE (starts now)");
t("G1 in-flight reference stays amendment", routeBusy("ee video lo music change cheyu"), "AMENDMENT (this video)");
t("G1 in-flight captions change stays amendment", routeBusy("ee video lo captions marchu"), "AMENDMENT (this video)");
t("G2 pure voice change while busy", routeBusy("voice female cheyu"), "VOICE-CHANGE (this video + kept)");
t("G2 explicit NEXT-video voice ask stays preference", routeBusy("next video ki female voice pettu"), "VOICE-CHANGE (this video + kept)");

// Source guards — the deferral class must be GONE from the app path.
const talk = api.slice(api.indexOf("async function appTalk("), api.indexOf("async function appTalk(") + 30000);
for (const bad of ["cancel and redo", "NEXT video will use it", "When it arrives, tell me and I'll start the next one", "cancel chesi malli chey"]) {
  t(`G2 banned string absent: "${bad.slice(0, 34)}…"`, api.includes(bad), false);
}
t("G1 amendment gate has !newOrder", talk.includes("!newOrder && isAmendment(cleanText)"), true);
t("G1 nextpref gate has !newOrder", /busyNow && !newOrder && !isCreateOrder\(cleanText\)/.test(talk), true);
t("G1 create fallback includes newOrder", talk.includes("forceCreate || newOrder || isNoVideoEditOrder"), true);
t("G1 busy refusal removed", talk.includes("One video is already being made"), false);
t("G2 voice reply acts on THIS video", api.includes("added to THIS video"), true);
t("G1 started-alongside line present", api.includes("both will land here"), true);
t("G3 AMEND_RULE new-topic carve-out", div.includes("KOTHA TOPIC matram ASALU amendment"), true);
t("G3 appSys never-defer clause", api.includes("NEVER defer work"), true);
console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
