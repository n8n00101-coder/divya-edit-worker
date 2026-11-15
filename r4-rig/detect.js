// R4 visual audit v2 — clip-aware. An element's EFFECTIVE rect is its layout
// rect intersected with every overflow-clipping ancestor's box and the
// viewport: content scrolled out of a .scroll/#msgs container is clipped,
// not overlapping. Defects = text/interactive spill, glyph overflow,
// clipped badges/buttons, and true same-layer overlaps of effective rects.
(scopeSel) => {
  const vw = window.innerWidth, vh = window.innerHeight;
  const root = scopeSel ? document.querySelector(scopeSel) : document.body;
  if (!root) return { error: "no root " + scopeSel, defects: [], infos: [] };
  const defects = [], infos = [];
  const desc = el => {
    let s = el.tagName.toLowerCase();
    if (el.id) s += "#" + el.id;
    if (el.className && typeof el.className === "string") s += "." + el.className.trim().split(/\s+/).slice(0, 3).join(".");
    const t = (el.textContent || "").trim().replace(/\s+/g, " ").slice(0, 60);
    if (t) s += " «" + t + "»";
    return s;
  };
  const INTERACTIVE = "button, a, input, textarea, select";
  const STRUCT = ".card,.list,.row,.msg,.plan-card,.hist-item,.tab-item,.voice-row,.fld,.field,.tok-total,.setup-box,.browser-card";
  const directText = el => [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
  function effRect(el) {
    let r = el.getBoundingClientRect();
    let L = r.left, T = r.top, R = r.right, B = r.bottom, clippedBy = null;
    let a = el.parentElement;
    while (a && a !== document.body) {
      const cs = getComputedStyle(a);
      if (/(hidden|clip|auto|scroll)/.test(cs.overflowX) || /(hidden|clip|auto|scroll)/.test(cs.overflowY)) {
        const ar = a.getBoundingClientRect();
        if (/(hidden|clip|auto|scroll)/.test(cs.overflowX)) { if (ar.left > L) { L = ar.left; clippedBy = a; } if (ar.right < R) { R = ar.right; clippedBy = a; } }
        if (/(hidden|clip|auto|scroll)/.test(cs.overflowY)) { if (ar.top > T) { T = ar.top; clippedBy = a; } if (ar.bottom < B) { B = ar.bottom; clippedBy = a; } }
      }
      a = a.parentElement;
    }
    return { left: L, top: T, right: R, bottom: B, width: Math.max(0, R - L), height: Math.max(0, B - T), raw: r, clippedBy };
  }
  const baseVis = el => {
    const cs = getComputedStyle(el), r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && cs.display !== "none" && cs.visibility !== "hidden";
  };
  const SKIP = el =>
    (el.matches && el.matches(".tabbar a > span:not(.tv-orb)")) || // v50 X7: sr-only tab labels, 1x1 clipped BY DESIGN
    el.closest(".sr-only") || el.classList.contains("sr-only") ||
    el.classList.contains("skip") ||
    (el.closest(".drawer") && !el.closest(".drawer").classList.contains("open")) ||
    el.closest("#toast:not(.show)") ||
    el.closest(".orb") || el.closest(".switch");
  const els = [...root.querySelectorAll("*")].filter(el => baseVis(el) && !SKIP(el));
  const ER = new Map(); els.forEach(el => ER.set(el, effRect(el)));
  const vis = el => { const e = ER.get(el); return e && e.width > 0 && e.height > 0; };

  if (document.documentElement.scrollWidth > vw + 1)
    defects.push({ kind: "doc-hscroll", el: "document", sw: document.documentElement.scrollWidth, vw });
  for (const el of els) {
    if (!vis(el)) continue;
    const cs = getComputedStyle(el);
    const isScroller = /(auto|scroll)/.test(cs.overflowY) || /(auto|scroll)/.test(cs.overflowX);
    if (isScroller && el.scrollWidth > el.clientWidth + 2)
      defects.push({ kind: "container-hscroll", el: desc(el), sw: el.scrollWidth, cw: el.clientWidth, over: el.scrollWidth - el.clientWidth });
    const scrollableX = /(auto|scroll)/.test(cs.overflowX), scrollableY = /(auto|scroll)/.test(cs.overflowY);
    const ellipsis = cs.textOverflow === "ellipsis" && /(hidden|clip)/.test(cs.overflowX);
    const matters = directText(el) || el.matches(INTERACTIVE) || el.matches(STRUCT);
    if (matters && !scrollableX && el.scrollWidth > el.clientWidth + 2) {
      const hit = { kind: "overflow-x", el: desc(el), sw: el.scrollWidth, cw: el.clientWidth, over: el.scrollWidth - el.clientWidth };
      (ellipsis ? infos : defects).push(hit);
    }
    if (matters && !scrollableY && el.scrollHeight > el.clientHeight + 2 && el.children.length === 0 && directText(el)) {
      const hit = { kind: "overflow-y", el: desc(el), sh: el.scrollHeight, ch: el.clientHeight, over: el.scrollHeight - el.clientHeight };
      (ellipsis ? infos : defects).push(hit);
    }
    const e = ER.get(el), r = e.raw;
    if (e.right > vw + 2 || e.left < -2) {
      const layered = el.closest(".tab-switcher,.sheet-bg,.liveview,.drawer-bg,.ctxmenu,.upd-banner,.bubble");
      if (!layered)
        defects.push({ kind: "viewport-spill", el: desc(el), left: Math.round(e.left), right: Math.round(e.right), vw });
    }
    if (directText(el)) {
      const box = el.closest(".card,.list,.msg,.sheet,.tab-switcher-card,.login-card,.plan-card,.setup-box,.bubble-panel,.liveview");
      if (box && box !== el && ER.get(box)) {
        const br = ER.get(box);
        if (e.left < br.left - 2 || e.right > br.right + 2)
          defects.push({ kind: "container-spill", el: desc(el), left: Math.round(e.left), right: Math.round(e.right), boxLeft: Math.round(br.left), boxRight: Math.round(br.right), box: desc(box) });
      }
      try {
        const range = document.createRange(); range.selectNodeContents(el);
        const rr = range.getBoundingClientRect();
        if (rr.width > r.width + 3 && !ellipsis)
          defects.push({ kind: "glyph-overflow-x", el: desc(el), glyphW: Math.round(rr.width), boxW: Math.round(r.width) });
        if (rr.height > r.height + 5 && cs.overflowY === "hidden")
          defects.push({ kind: "glyph-clipped-y", el: desc(el), glyphH: Math.round(rr.height), boxH: Math.round(r.height) });
      } catch (err) {}
      // clipped by an overflow-hidden ancestor: badges/chips/buttons must
      // never lose >15% of their width; plain text spans go to INFO.
      if (e.clippedBy && r.width > 0 && e.width < r.width * 0.85 && r.width - e.width > 6) {
        const hit = { kind: "clipped-by-ancestor", el: desc(el), visW: Math.round(e.width), fullW: Math.round(r.width), by: desc(e.clippedBy) };
        if (el.matches(INTERACTIVE) || /house|pill|badge|chip/.test(el.className || "")) defects.push(hit); else infos.push(hit);
      }
    }
  }

  const CAND = "button, a, input, textarea, select, .pill, .row, .card, .msg, .plan-card, .tab-item, .voice-row, .hist-item, .chip, .seg, .fld, .field, .tok-total, h1, h2, h3, .pc-price, .tt-num, .q-num, .avatar, .tab-chip, .icon-btn, .send-btn, .hey, .quota, .greet, .brand-status, .lv-btn, .lv-x, .step, li";
  const cand = [...root.querySelectorAll(CAND)].filter(el => baseVis(el) && !SKIP(el) && vis(el) &&
    !el.closest(".orb") && !el.closest(".switch") && !el.closest("#toast") &&
    !(el.closest(".liveview") && scopeSel !== "#liveView"));
  const rects = cand.map(el => ({ el, r: ER.get(el) || effRect(el) }));
  for (let i = 0; i < rects.length; i++) {
    for (let j = i + 1; j < rects.length; j++) {
      const A = rects[i], B = rects[j];
      if (A.el.contains(B.el) || B.el.contains(A.el)) continue;
      // designed layering: the bottom sheet may sit under the composer
      // (composer z-70 always wins taps) — not a box-on-box mistake.
      const sheetPair = (A.el.closest("#sheet") && B.el.closest(".composer-wrap")) || (B.el.closest("#sheet") && A.el.closest(".composer-wrap"));
      if (sheetPair) continue;
      // the open sheet is a modal layer — it legitimately covers app chrome
      const sheetChrome = (A.el.closest("#sheet") && B.el.closest("header.appbar, nav.tabbar")) || (B.el.closest("#sheet") && A.el.closest("header.appbar, nav.tabbar"));
      if (sheetChrome) continue;
      // v50: the open sheet is a modal — it covers the screen's CONTENT too
      // (cards, rows), not just chrome. Sheet x non-sheet pairs are layering,
      // never a box-on-box defect.
      const sheetContent = (A.el.closest("#sheet") && !B.el.closest("#sheet")) || (B.el.closest("#sheet") && !A.el.closest("#sheet"));
      if (sheetContent) continue;
      const ix = Math.min(A.r.right, B.r.right) - Math.max(A.r.left, B.r.left);
      const iy = Math.min(A.r.bottom, B.r.bottom) - Math.max(A.r.top, B.r.top);
      if (ix <= 3 || iy <= 3) continue;
      const area = ix * iy, minArea = Math.min(A.r.width * A.r.height, B.r.width * B.r.height);
      if (minArea > 0 && area > 0.12 * minArea)
        defects.push({ kind: "overlap", a: desc(A.el), b: desc(B.el), ix: Math.round(ix), iy: Math.round(iy), pct: Math.round(100 * area / minArea) });
    }
  }
  return { defects, infos, n: els.length };
}
