// TTYSI kadastr sayti: binolar ro'yxati, etaj chizmasi (SVG), AT belgilarini qo'shish/o'zgartirish.
// Telefon: barmoq bilan surish, ikki barmoq bilan kattalashtirish, bosish - belgi qo'yish/tanlash.

const $ = (id) => document.getElementById(id);
const SVG = "http://www.w3.org/2000/svg";
const S = {
  info: null, tree: null, b: null, fi: 0, etag: null, tool: null, sel: null,
  view: { s: 1, tx: 0, ty: 0 }, bg: localGet("bg", "0") === "1", img: {},
};

function localGet(k, d) { try { return localStorage.getItem("ttysi." + k) ?? d; } catch { return d; } }
function localSet(k, v) { try { localStorage.setItem("ttysi." + k, v); } catch { /* yo'q */ } }
function el(tag, attrs = {}, ...kids) {
  const n = tag.startsWith("svg:") ? document.createElementNS(SVG, tag.slice(4)) : document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "text") n.textContent = v; else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v === true ? "" : v);
  }
  for (const k of kids) if (k) n.append(k);
  return n;
}
function toast(msg) {
  const t = $("toast"); t.textContent = msg; t.classList.add("show");
  clearTimeout(toast.h); toast.h = setTimeout(() => t.classList.remove("show"), 3000);
}
function type(code) { return S.info.equipment.find((t) => t.code === code) || S.info.equipment.at(-1); }
const pts = (p) => p.map(([x, y]) => `${x},${y}`).join(" ");

async function api(path, opts = {}) {
  const r = await fetch(path, { credentials: "same-origin", ...opts });
  if (r.status === 401) { showLogin(); throw new Error("login"); }
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).detail || msg; } catch { /* matn emas */ }
    const e = new Error(msg); e.status = r.status; throw e;
  }
  return r;
}

// ------------------------------------------------------------------ kirish
function showLogin() { $("login").hidden = false; $("pin").focus(); }
$("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const r = await fetch("/api/login", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pin: $("pin").value }) });
  if (r.ok) { $("login").hidden = true; route(); } else $("login-err").textContent = "Kod noto'g'ri";
});

// ------------------------------------------------------------------ bosh sahifa
async function showHome() {
  $("view-home").hidden = false; $("view-building").hidden = true;
  $("crumbs").textContent = "TTYSI Binolar kadastri";
  S.tree = await (await api("/api/workspace")).json();
  renderTree();
}

function card(b) {
  const chips = el("div", { class: "chips" });
  for (const t of S.info.equipment) {
    if (b.counts[t.code]) chips.append(el("span", { class: "chip", style: `background:${t.color}`, text: `${t.label} ${b.counts[t.code]}` }));
  }
  if (b.unknown) chips.append(el("span", { class: "chip warn", text: `${b.unknown} ta ? kutmoqda` }));
  if (!chips.childElementCount) chips.append(el("span", { class: "muted", text: "AT jihozlari hali belgilanmagan" }));
  return el("a", { class: "card", href: `#/b/${encodeURIComponent(b.id)}/0` },
    el("h3", { text: b.name }), el("span", { class: "muted", text: `${b.floors} etaj · tayyor ${b.ready}/${b.floors}` }), chips);
}

function renderTree() {
  const q = $("search").value.trim().toLowerCase();
  const match = (b, org = "") => !q || b.name.toLowerCase().includes(q) || org.toLowerCase().includes(q);
  const tree = $("tree"); tree.replaceChildren();
  for (const o of S.tree.orgs) {
    const bs = o.buildings.filter((b) => match(b, o.name));
    if (!bs.length && q) continue;
    const floors = o.buildings.reduce((a, b) => a + b.floors, 0);
    tree.append(el("section", {},
      el("div", { class: "org-head" }, el("b", { text: o.name }),
        el("span", { class: "muted", text: `Tashkilot · ${o.buildings.length} ta bino · ${floors} etaj` }),
        o.buildings.length ? el("a", { class: "link", href: `/api/report.xlsx?org=${encodeURIComponent(o.id)}`, text: "Excel hisobot" }) : null),
      bs.length ? el("div", { class: "cards" }, ...bs.map(card)) : el("div", { class: "muted", text: "Bo'sh tashkilot" })));
  }
  const own = S.tree.buildings.filter((b) => match(b));
  if (own.length) {
    tree.append(el("section", {}, S.tree.orgs.length ? el("h2", { class: "muted", text: "Tashkilotsiz binolar" }) : null,
      el("div", { class: "cards" }, ...own.map(card))));
  }
  if (!tree.childElementCount) tree.append(el("div", { class: "empty", text: q ? "Hech narsa topilmadi" : "Binolar papkasi bo'sh" }));
}
$("search").addEventListener("input", () => S.tree && renderTree());

// ------------------------------------------------------------------ bino va etaj
async function showBuilding(id, fi) {
  $("view-home").hidden = true; $("view-building").hidden = false;
  if (!S.b || S.b.id !== id) {
    const r = await api(`/api/building?id=${encodeURIComponent(id)}`);
    setBuilding(await r.json(), r.headers.get("ETag"));
    S.fi = -1;
  }
  const changed = S.fi !== fi;
  S.fi = Math.min(Math.max(0, fi), Math.max(0, S.b.floors.length - 1));
  S.sel = null;
  renderBuilding(changed);
}

function setBuilding(b, etag) { S.b = b; S.etag = etag; }
function floor() { return S.b.floors[S.fi]; }

function renderBuilding(fit) {
  const b = S.b;
  $("crumbs").replaceChildren(el("a", { href: "#/", text: "Binolar" }), " › ",
    b.org ? `${b.org} › ` : "", b.name);
  $("floors").replaceChildren(...b.floors.map((f, i) => el("button", {
    "aria-current": i === S.fi ? "true" : "false", onclick: () => { location.hash = `#/b/${encodeURIComponent(b.id)}/${i}`; },
  }, f.name, f.unknown ? el("span", { class: "badge", text: f.unknown }) : null)));
  $("report").href = `/api/report.xlsx?id=${encodeURIComponent(b.id)}`;
  if (!b.floors.length) { $("plan").replaceChildren(); $("hint").textContent = "Bu binoda etaj yo'q"; return; }
  renderPalette(); renderPlan(); renderStats();
  if (fit) fitView();
}

function renderPalette() {
  $("palette").replaceChildren(...S.info.equipment.filter((t) => t.code !== "?").map((t) => el("button", {
    class: t.square ? "sq" : "", style: `background:${t.color}`, title: t.name, "aria-pressed": S.tool === t.code ? "true" : "false",
    text: t.label, onclick: () => { S.tool = S.tool === t.code ? null : t.code; renderPalette(); hint(); },
  })));
  const f = floor();
  $("next").hidden = !f.unknown; $("next").textContent = `Keyingi ?  (${f.unknown})`;
  hint();
}

function hint() {
  const t = S.tool && type(S.tool);
  $("hint").textContent = t ? `${t.name}: chizmada joyini bosing` : "";
}

function renderStats() {
  const f = floor();
  $("stats").replaceChildren(...S.info.equipment.filter((t) => t.code !== "?").map((t) =>
    el("div", { class: "stat" }, el("b", { text: f.counts[t.code] || 0 }),
      el("span", { text: t.name + (f.planned[t.code] ? ` · +${f.planned[t.code]} kerak` : "") }))));
}

function renderPlan() {
  const f = floor(), svg = $("plan");
  const g = el("svg:g", { id: "vp" });
  if (S.bg && f.has_image) {
    const src = `/api/floor-image?id=${encodeURIComponent(S.b.id)}&floor=${S.fi}&v=${encodeURIComponent(S.etag || "")}`;
    const nat = S.img[src];
    if (nat) {
      const k = f.width / nat.w, cx = f.width / 2, cy = f.height / 2, bg = f.bg;
      g.append(el("svg:image", { href: src, width: nat.w, height: nat.h, opacity: 0.55, preserveAspectRatio: "none",
        transform: `translate(${cx + bg.dx},${cy + bg.dy}) rotate(${bg.rot}) scale(${bg.scale}) translate(${-cx},${-cy}) scale(${k})` }));
    } else {
      const im = new Image();
      im.onload = () => { S.img[src] = { w: im.naturalWidth, h: im.naturalHeight }; renderPlan(); };
      im.src = src;
    }
  } else {
    g.append(el("svg:rect", { x: 0, y: 0, width: f.width, height: f.height, fill: "#fff" }));
  }
  const ww = f.wall_width;
  for (const r of f.rooms) {
    g.append(el("svg:polygon", { points: pts(r.points), fill: S.bg ? "none" : r.fill, stroke: "#212121", "stroke-width": ww, "stroke-linejoin": "miter" }));
    for (const ln of r.stairs || []) g.append(el("svg:polyline", { points: pts(ln), fill: "none", stroke: "#616161", "stroke-width": Math.max(1, ww * 0.18) }));
    if (r.ring) g.append(el("svg:polygon", { points: pts(r.ring), fill: "none", stroke: "#5c6b7a", "stroke-width": Math.max(1, ww * 0.18), "stroke-dasharray": `${ww} ${ww * 0.6}` }));
  }
  for (const w of f.walls) g.append(el("svg:polyline", { points: pts(w.points), fill: "none", stroke: "#212121", "stroke-width": w.thickness, "stroke-linecap": "square" }));
  for (const d of f.doors) {
    g.append(el("svg:polygon", { points: pts(d.cut), fill: S.bg ? "rgba(255,255,255,.8)" : "#fff" }));
    for (const ln of d.lines) g.append(el("svg:polyline", { points: pts(ln), fill: "none", stroke: "#212121", "stroke-width": d.stroke }));
  }
  for (const r of f.rooms) {
    const lines = (r.label || "").split("\n").filter(Boolean);
    const lp = f.label_px;
    lines.forEach((t, i) => g.append(el("svg:text", { x: r.cx, y: r.cy + (i - (lines.length - 1) / 2) * lp * 1.15,
      "font-size": i ? lp * 0.75 : lp, "font-weight": i ? 400 : 600, fill: "#37474f", "text-anchor": "middle", "dominant-baseline": "middle",
      "pointer-events": "none", text: t })));
  }
  const R = f.symbol_r;
  for (const e of f.equipment) {
    const t = type(e.code), planned = e.status === "planned";
    const grp = el("svg:g", { class: "eq" + (S.sel === e.id ? " sel" : ""), "data-id": e.id, transform: `translate(${e.x},${e.y})` });
    const attrs = { fill: planned ? "#fff" : t.color, stroke: S.sel === e.id ? "#FFD54F" : (planned ? t.color : "#00000055"),
      "stroke-width": S.sel === e.id ? R * 0.35 : R * (planned ? 0.2 : 0.14), "stroke-dasharray": planned ? `${R * 0.5} ${R * 0.3}` : null };
    grp.append(t.square ? el("svg:rect", { x: -R, y: -R, width: 2 * R, height: 2 * R, ...attrs }) : el("svg:circle", { r: R, ...attrs }));
    grp.append(el("svg:text", { "font-size": R * (t.label.length <= 2 ? 0.95 : 0.7), "font-weight": 700, fill: planned ? t.color : "#fff",
      "text-anchor": "middle", "dominant-baseline": "central", "pointer-events": "none", text: t.label }));
    if (e.code === "?") grp.append(el("svg:circle", { r: R * 1.5, fill: "none", stroke: "#d32f2f", "stroke-width": R * 0.15, "stroke-dasharray": `${R * 0.4} ${R * 0.3}` }));
    g.append(grp);
  }
  svg.replaceChildren(g);
  applyView();
}

// ------------------------------------------------------------------ surish va kattalashtirish
function applyView() {
  const vp = $("vp"); if (vp) vp.setAttribute("transform", `translate(${S.view.tx},${S.view.ty}) scale(${S.view.s})`);
}
function fitView() {
  const f = floor(), r = $("plan").getBoundingClientRect(); if (!f || !r.width) return;
  let s = Math.min(r.width / f.width, r.height / f.height) * 0.94;
  // telefonda uzun (yo'lak) etaj juda mayda chiqmasin: balandlik bo'yicha, kengligi 3 ekrangacha
  if (r.width < 760) s = Math.max(s, Math.min(r.height / f.height, 3 * r.width / f.width) * 0.94);
  const tx = f.width * s > r.width ? r.width * 0.03 : (r.width - f.width * s) / 2;   // uzun bo'lsa - boshidan
  S.view = { s, tx, ty: (r.height - f.height * s) / 2 }; applyView();
}
function zoomAt(k, cx, cy) {
  const v = S.view, s = Math.min(Math.max(v.s * k, 0.02), 40);
  v.tx = cx - (cx - v.tx) * (s / v.s); v.ty = cy - (cy - v.ty) * (s / v.s); v.s = s; applyView();
}
function toPlan(cx, cy) { return [(cx - S.view.tx) / S.view.s, (cy - S.view.ty) / S.view.s]; }

const P = new Map(); let gesture = null;
const plan = $("plan");
plan.addEventListener("pointerdown", (e) => {
  plan.setPointerCapture(e.pointerId);
  const r = plan.getBoundingClientRect();
  P.set(e.pointerId, { x: e.clientX - r.left, y: e.clientY - r.top });
  if (P.size === 1) gesture = { type: "tap", x0: e.clientX - r.left, y0: e.clientY - r.top, tx: S.view.tx, ty: S.view.ty, target: e.target };
  else if (P.size === 2) {
    const [a, b] = [...P.values()];
    gesture = { type: "pinch", d: Math.hypot(a.x - b.x, a.y - b.y), s: S.view.s, mx: (a.x + b.x) / 2, my: (a.y + b.y) / 2, tx: S.view.tx, ty: S.view.ty };
  }
});
plan.addEventListener("pointermove", (e) => {
  if (!P.has(e.pointerId) || !gesture) return;
  const r = plan.getBoundingClientRect(), x = e.clientX - r.left, y = e.clientY - r.top;
  P.set(e.pointerId, { x, y });
  if (gesture.type === "pinch" && P.size === 2) {
    const [a, b] = [...P.values()], d = Math.hypot(a.x - b.x, a.y - b.y), mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
    const s = Math.min(Math.max(gesture.s * d / Math.max(1, gesture.d), 0.02), 40);
    S.view.s = s;
    S.view.tx = mx - (gesture.mx - gesture.tx) * (s / gesture.s);
    S.view.ty = my - (gesture.my - gesture.ty) * (s / gesture.s);
    applyView();
  } else if (gesture.type !== "pinch") {
    if (gesture.type === "tap" && Math.hypot(x - gesture.x0, y - gesture.y0) > 8) gesture.type = "pan";
    if (gesture.type === "pan") { S.view.tx = gesture.tx + x - gesture.x0; S.view.ty = gesture.ty + y - gesture.y0; applyView(); }
  }
});
function endPointer(e) {
  if (!P.has(e.pointerId)) return;
  P.delete(e.pointerId);
  if (gesture && gesture.type === "tap" && P.size === 0) onTap(gesture);
  if (P.size === 0) gesture = null;
  else if (gesture && gesture.type === "pinch") gesture = { type: "done" };
}
plan.addEventListener("pointerup", endPointer);
plan.addEventListener("pointercancel", (e) => { P.delete(e.pointerId); gesture = null; });
plan.addEventListener("wheel", (e) => {
  e.preventDefault();
  const r = plan.getBoundingClientRect();
  zoomAt(Math.pow(1.0015, -e.deltaY), e.clientX - r.left, e.clientY - r.top);
}, { passive: false });
$("fit").onclick = fitView;
$("zin").onclick = () => { const r = plan.getBoundingClientRect(); zoomAt(1.4, r.width / 2, r.height / 2); };
$("zout").onclick = () => { const r = plan.getBoundingClientRect(); zoomAt(1 / 1.4, r.width / 2, r.height / 2); };
$("bg").checked = S.bg;
$("bg").onchange = () => { S.bg = $("bg").checked; localSet("bg", S.bg ? "1" : "0"); renderPlan(); };
window.addEventListener("resize", () => { if (!$("view-building").hidden && S.b) fitView(); });

function onTap(g) {
  const hit = g.target.closest && g.target.closest(".eq");
  if (hit) { openSheet(hit.dataset.id); return; }
  if (!S.tool) { toast("Avval jihoz turini tanlang (pastdagi/yondagi rangli tugmalar)"); return; }
  const [x, y] = toPlan(g.x0, g.y0), f = floor();
  if (x < 0 || y < 0 || x > f.width || y > f.height) return;
  send({ action: "add", code: S.tool, x, y, status: $("planned").checked ? "planned" : "existing" }, `${type(S.tool).name} qo'shildi`);
}

async function send(change, okMsg) {
  try {
    const r = await api(`/api/equipment?id=${encodeURIComponent(S.b.id)}`, { method: "POST",
      headers: { "Content-Type": "application/json", ...(S.etag ? { "If-Match": S.etag } : {}) },
      body: JSON.stringify({ floor: S.fi, ...change }) });
    setBuilding(await r.json(), r.headers.get("ETag"));
    renderBuilding(false);
    if (okMsg) toast(okMsg + " ✓");
    return true;
  } catch (e) {
    if (e.message === "login") return false;
    if (e.status === 409) {
      toast("Bino boshqa joyda o'zgartirilgan — yangilandi, qaytadan bajaring");
      const r = await api(`/api/building?id=${encodeURIComponent(S.b.id)}`);
      setBuilding(await r.json(), r.headers.get("ETag")); renderBuilding(false);
    } else toast("Saqlanmadi: " + e.message);
    return false;
  }
}

// ------------------------------------------------------------------ belgi varag'i
let sheetCode = null;
function openSheet(id) {
  const e = floor().equipment.find((q) => q.id === id); if (!e) return;
  S.sel = id; renderPlan();
  sheetCode = e.code;
  $("sheet-title").textContent = type(e.code).name;
  $("sheet-room").textContent = e.room ? `Xona: ${e.room}` : "Xonadan tashqarida";
  const types = $("sheet-types");
  const draw = () => types.replaceChildren(...S.info.equipment.filter((t) => t.code !== "?").map((t) => el("button", {
    class: t.square ? "sq" : "", style: `background:${t.color}`, "aria-pressed": sheetCode === t.code ? "true" : "false",
    title: t.name, text: t.label, onclick: () => { sheetCode = t.code; $("sheet-title").textContent = t.name; draw(); },
  })));
  draw();
  for (const r of document.querySelectorAll('input[name="st"]')) r.checked = r.value === e.status;
  $("sheet-note").value = e.note || "";
  $("sheet").hidden = false;
}
function closeSheet() { $("sheet").hidden = true; S.sel = null; if (S.b) renderPlan(); }
$("sheet-close").onclick = closeSheet;
$("sheet").addEventListener("click", (e) => { if (e.target === $("sheet")) closeSheet(); });
$("sheet-save").onclick = async () => {
  const status = document.querySelector('input[name="st"]:checked')?.value;
  const id = S.sel;
  $("sheet").hidden = true;
  await send({ action: "update", id, code: sheetCode, status, note: $("sheet-note").value }, "Saqlandi");
  S.sel = null; renderPlan();
  if (floor().unknown) nextUnknown();
};
$("sheet-del").onclick = async () => {
  const id = S.sel; $("sheet").hidden = true;
  await send({ action: "delete", id }, "O'chirildi"); S.sel = null; renderPlan();
};
function nextUnknown() {
  const u = floor().equipment.filter((e) => e.code === "?").sort((a, b) => a.y - b.y || a.x - b.x)[0];
  if (!u) return;
  const r = plan.getBoundingClientRect(), s = Math.max(S.view.s, 0.6 * r.width / Math.max(1, floor().meter_px * 12));
  S.view = { s, tx: r.width / 2 - u.x * s, ty: r.height / 2 - u.y * s };
  openSheet(u.id);
}
$("next").onclick = nextUnknown;
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") { if (!$("sheet").hidden) closeSheet(); else { S.tool = null; renderPalette(); } }
  if ($("view-building").hidden || !$("sheet").hidden || e.target.tagName === "INPUT") return;
  const t = S.info.equipment.find((q) => q.key === e.key && q.code !== "?");
  if (t) { S.tool = S.tool === t.code ? null : t.code; renderPalette(); }
});

// ------------------------------------------------------------------ yo'naltirish
async function route() {
  try {
    const m = location.hash.match(/^#\/b\/([^/]+)\/(\d+)/);
    if (m) await showBuilding(decodeURIComponent(m[1]), +m[2]); else { S.b = null; await showHome(); }
  } catch (e) {
    if (e.message !== "login") { toast(e.message); if (location.hash) location.hash = "#/"; }
  }
}
$("home").onclick = () => { location.hash = "#/"; };
window.addEventListener("hashchange", route);

(async () => {
  S.info = await (await fetch("/api/info")).json();
  $("ver").textContent = "v" + S.info.version;
  route();
})();
