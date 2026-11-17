// v105 Take Control rig tests (app side). Extracts the SHIPPED
// tcMapPoint from app/app.js and exercises the exact math, plus source
// pins for the v105 wiring (streamed typing, one-tap hand-back, scroll
// keys, adaptive poll). Run: node tctest.mjs
import { readFileSync } from "fs";

const src = readFileSync(new URL("./app/app.js", import.meta.url), "utf8");
let fails = 0;
const check = (name, cond, extra = "") => {
  console.log((cond ? "PASS " : "FAIL ") + name + (!cond && extra ? " — " + extra : ""));
  if (!cond) fails++;
};

// Extract and eval the shipped pure mapping function.
const m = src.match(/function tcMapPoint[\s\S]*?\n\}/);
check("tcMapPoint present in app.js", !!m);
const tcMapPoint = eval("(" + m[0] + ")");

// Runner viewport is 1280x800 (1.6:1).
// Case 1: exact-fit element (in-chat panel, width 100%, height auto).
let r = { left: 0, top: 0, width: 1280, height: 800 };
let p = tcMapPoint(1280, 800, r, 640, 400);
check("exact-fit: centre maps to centre", p && p.x === 640 && p.y === 400, JSON.stringify(p));

// Case 2: portrait phone stage 390x700, object-fit:contain — content is
// 390x243.75 centred, bars of 228.125 top/bottom. A tap at the content's
// top-left corner (0, 228.125) must map to page (0,0) — the OLD math
// mapped it to ~(0, 260).
r = { left: 0, top: 0, width: 390, height: 700 };
p = tcMapPoint(1280, 800, r, 0, 228.125);
check("letterboxed: content top-left maps to (0,0)", p && p.x === 0 && p.y === 0, JSON.stringify(p));
p = tcMapPoint(1280, 800, r, 195, 228.125 + 121.875);
check("letterboxed: content centre maps to (640,400)", p && p.x === 640 && p.y === 400, JSON.stringify(p));
p = tcMapPoint(1280, 800, r, 389, 228.125 + 243);
check("letterboxed: content bottom-right maps near (1277,797)", p && p.x >= 1270 && p.y >= 790, JSON.stringify(p));
p = tcMapPoint(1280, 800, r, 195, 100); // in the top black bar
check("letterboxed: tap on the black bar is rejected (null)", p === null, JSON.stringify(p));

// Case 3: landscape stage wider than 1.6 (side bars).
r = { left: 10, top: 20, width: 1000, height: 500 }; // content 800x500, bars 100 each side +left offset
p = tcMapPoint(1280, 800, r, 110, 20);
check("side-letterbox: content top-left maps to (0,0)", p && p.x === 0 && p.y === 0, JSON.stringify(p));
p = tcMapPoint(1280, 800, r, 60, 270);
check("side-letterbox: tap on the side bar is rejected", p === null, JSON.stringify(p));

// Case 4: zoom box (element 200% wide, height auto — content fills it).
r = { left: -200, top: 0, width: 2560, height: 1600 };
p = tcMapPoint(1280, 800, r, -200 + 1280, 800);
check("zoom box: centre of the (scrolled) element maps to (640,400)", p && p.x === 640 && p.y === 400, JSON.stringify(p));

// Case 5: degenerate inputs never throw / never map.
check("degenerate rect rejected", tcMapPoint(1280, 800, { left: 0, top: 0, width: 0, height: 0 }, 5, 5) === null);
check("no natural size rejected", tcMapPoint(0, 0, r, 5, 5) === null);

// ---- wiring pins -----------------------------------------------------
check("streamed typing wired in both surfaces (tcWireTypeBox defined + used >=3x)",
  (src.match(/tcWireTypeBox/g) || []).length >= 3);
check("one-tap hand-back posts setup/continue from the Take toggle",
  /Handing back/.test(src) && /liveCtl = false; syncLiveCtl\(v\); await api\("setup\/continue"/.test(src));
check("scroll + special keys wired (tcWireKeys, scroll inputs)",
  /tcWireKeys\(v, "lv"\)/.test(src) && /tcWireKeys\(box, "tc"\)/.test(src) && /type: "scroll"/.test(src));
check("live poll is adaptive (700ms controlling / 1200ms watching)",
  /liveCtl \? 700 : 1200/.test(src));
check("in-chat TC poll at 800ms", /setTimeout\(fetchFrame, 800\)/.test(src));
check("Take button label flips to Hand back while controlling",
  /handBack/.test(src) && /tc\.textContent = liveCtl/.test(src) || /tk\.textContent = liveCtl/.test(src));
check("key-button rows injected into both TC panels + live view",
  (src.match(/TC_KEY_BTNS\("/g) || []).length >= 3);

console.log();
if (fails) { console.log("TC APP RIG: " + fails + " FAILURES"); process.exit(1); }
console.log("TC APP RIG: ALL PASS");
