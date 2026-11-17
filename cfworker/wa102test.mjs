// v102 incident-replay rig: extracts the pure gate/fallback functions
// from divya.js and replays the 2026-11-16 22:12-22:23 WhatsApp
// incident transcript against them. Run: node wa102test.mjs
import { readFileSync } from "fs";
const src = readFileSync(new URL("./divya.js", import.meta.url), "utf8");

function extract(name) {
  let i = src.indexOf(`function ${name}(`);
  if (i < 0) throw new Error("missing function " + name);
  if (src.slice(Math.max(0, i - 6), i) === "async ") i -= 6;
  let j = src.indexOf("{", i), depth = 0, k = j;
  for (; k < src.length; k++) {
    if (src[k] === "{") depth++;
    else if (src[k] === "}") { depth--; if (!depth) break; }
  }
  return src.slice(i, k + 1);
}
const rx = src.match(/const STOP_PROD_RX = .*;/)[0];
let chatImpl = async () => "";
const chatWithFallback = (...a) => chatImpl(...a);
const code = [rx,
  extract("isStopIntent"), extract("isBareStop"), extract("isCreateOrder"),
  extract("isNoVideoEditOrder"), extract("isNewTopicOrder"), extract("isHowQuestion"),
  extract("howProcessReply"), extract("setupGuideReply"), extract("brainDownReply"),
  extract("isRefusalText"), extract("waChatAnswer"),
  "return { isStopIntent, isBareStop, isCreateOrder, isNoVideoEditOrder, isNewTopicOrder, isHowQuestion, howProcessReply, setupGuideReply, brainDownReply, isRefusalText, waChatAnswer };"
].join("\n");
const F = new Function("chatWithFallback", code)(chatWithFallback);

let pass = 0, fail = 0;
const T = (name, cond) => { if (cond) { pass++; console.log("PASS", name); } else { fail++; console.log("FAIL", name); } };

// --- The incident transcript ---
const Q = "Nenu oka topic isthe ela edits chesthav first starting nundi last output ready aye varaku ela edits chesthav motham detailed ga chepu";
// 1. The how-question must NEVER start a job: no order gate may fire.
T("how-question detected", F.isHowQuestion(Q) === true);
T("how-question: isCreateOrder false", F.isCreateOrder(Q) === false);
T("how-question: isNewTopicOrder false", F.isNewTopicOrder(Q) === false);
T("how-question: isNoVideoEditOrder false", F.isNoVideoEditOrder(Q) === false);
// ...and it gets a real detailed answer that states nothing started.
const hp = F.howProcessReply();
T("process answer is detailed (6 steps)", (hp.match(/^\d\./gm) || []).length === 6);
T("process answer states nothing started", /emi start cheyyaledu/.test(hp));
// 2. "Cheyaku" is a stop — with or without a job found.
T('"Cheyaku" isStopIntent', F.isStopIntent("Cheyaku") === true);
T('"Cheyaku" isBareStop', F.isBareStop("Cheyaku") === true);
T('"Stop" isStopIntent', F.isStopIntent("Stop") === true);
T('"video aapu" isStopIntent', F.isStopIntent("video aapu") === true);
T('"music aapu" stays an amendment', F.isStopIntent("music aapu") === false);
// 3. Real orders still start (no over-blocking).
T("self-do order still an order", F.isCreateOrder("starting nundi last varaku nuvve chey") === true);
T("topic order still an order", F.isNewTopicOrder("topic: space") === true);
T("plain order still an order", F.isCreateOrder("oka video cheyu") === true);
// 4. No user-facing fallback may claim a limit or an unverified state.
for (const [nm, s] of [["setupGuideReply te", F.setupGuideReply("te")], ["setupGuideReply en", F.setupGuideReply("en")], ["brainDownReply te", F.brainDownReply("te")], ["brainDownReply en", F.brainDownReply("en")]]) {
  T(nm + ": no limit claim", !/limit full|free limit/i.test(s));
  T(nm + ": no unverified nothing-started claim", !/start cheyyaledu|haven't started/i.test(s));
}
// 5. Failover: brain 1 refuses, brain 2 answers; total failure -> "".
let calls = 0;
chatImpl = async () => (++calls === 1 ? "Sorry, I can't help with that." : "Process answer from backup brain.");
T("refusal fails over to backup brain", await F.waChatAnswer({}, "u", []) === "Process answer from backup brain.");
chatImpl = async () => "";
T("total pool failure returns empty (caller uses brainDownReply)", await F.waChatAnswer({}, "u", []) === "");
chatImpl = async () => "Sorry, I can't help with that.";
T("refusal from every brain returns empty, never the refusal", await F.waChatAnswer({}, "u", []) === "");

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
