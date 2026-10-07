/* clipcut editor — พรีวิว canvas + timeline
   สูตร anim/zoom ต้องตรงกับ scripts/ccfx.py (render จริงใช้ตัวนั้น) */
"use strict";
const $ = (s) => document.querySelector(s);
const BASE_TRACKS = [
  { id: "sub", name: "ซับ", col: "var(--c-sub)" },
  { id: "broll", name: "ภาพ", col: "var(--c-broll)" },
  { id: "emoji", name: "อีโมจิ", col: "var(--c-emoji)" },
  { id: "sfx", name: "เสียง", col: "var(--c-sfx)" },
  { id: "fx", name: "เอฟเฟกต์", col: "var(--c-fx)" },
  { id: "gif", name: "GIF", col: "var(--c-gif)" },
];
// โหมด Motion Explainer: แถบ "ฉาก" (E.scenes) แทนภาพ/อีโมจิ/เอฟเฟกต์ — ซับกับเสียงใช้เหมือนเดิม
const SCENE_TRACK = { id: "scene", name: "ฉาก", col: "#facc15" };
const isEx = () => !!(E && E.mode === "explainer");
const TR = (id) => BASE_TRACKS.find((t) => t.id === id);
// อีโมจิเลิกใช้แล้ว (เฉินสั่งเอาออก) — แถวโผล่เฉพาะโปรเจกต์เก่าที่ยังมีอีโมจิค้างอยู่
const trackList = () => (isEx() ? [SCENE_TRACK, TR("sub"), TR("sfx")]
  : BASE_TRACKS.filter((t) => t.id !== "emoji" || E.items.some((x) => x.track === "emoji")));
const FX_INFO = {
  punch: ["ซูมกระแทก", "ซูมเข้าเร็วแล้วเด้งกลับ — ตอนเน้นคำ"],
  zoomin: ["ซูมเข้าช้า", "ค่อยๆ ดันเข้า — บิ้วอารมณ์"],
  zoomout: ["ซูมออกช้า", "เริ่มใกล้แล้วถอยออก"],
  focus: ["ซูมไปที่ของ", "ซูมเข้าค้างไว้แล้วออก — โชว์ของที่ยก/ชี้"],
  shake: ["จอสั่น", "ตอนช็อค/ระเบิด"],
  flash: ["แฟลชขาว", "ตัดฉาก/พีค"],
};
const FX_RANGE = { punch: [1.02, 1.6, 0.01], zoomin: [1.02, 1.8, 0.01], zoomout: [1.02, 1.8, 0.01], focus: [1.05, 2.5, 0.01], shake: [2, 60, 1], flash: [0.1, 1, 0.05] };
const FONT_FILES = { Mali: "Mali-Bold.ttf", Kanit: "Kanit-Bold.ttf", Itim: "Itim-Regular.ttf" };
// libass: Fontsize = winAscent+winDescent → [em/size, descent/size] จาก OS/2 ของแต่ละฟอนต์
const FONT_METRIC = { Mali: [1000 / 2122, 599 / 2122], Kanit: [1000 / 1580, 400 / 1580], Itim: [1000 / 1200, 250 / 1200] };
const CLIENT = Math.random().toString(36).slice(2);

let E = null;            // edit.json ปัจจุบัน
let rev = 0, assets = null;
let sel = null;          // id ที่เลือก
let pps = 60;            // pixel ต่อวินาทีบน timeline
let dirty = new Set(), deleted = new Set(), saveTimer = null, saving = false;
let undoStack = [], redoStack = [];
const vid = $("#vid"), cv = $("#cv"), ctx = cv.getContext("2d");
const imgCache = {}, sfxBuf = {};
let W = 1080, H = 1920;
let actx = null, lastT = 0;

/* ---------- utils ---------- */
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const r3 = (v) => Math.round(v * 1000) / 1000;
function fmt(t, ms = true) {
  t = Math.max(0, t); const m = Math.floor(t / 60), s = t - m * 60;
  return ms ? `${m}:${s.toFixed(2).padStart(5, "0")}` : `${m}:${String(Math.floor(s)).padStart(2, "0")}`;
}
function toast(msg) { const el = $("#toast"); el.textContent = msg; el.classList.add("on"); clearTimeout(toast.t); toast.t = setTimeout(() => el.classList.remove("on"), 2600); }
function img(src) {
  if (!imgCache[src]) { const i = new Image(); i.src = src; i.onload = () => { drawFrame(); renderTimeline(); }; imgCache[src] = i; }
  return imgCache[src];
}
const emojiSrc = (e) => "/emoji/" + encodeURIComponent(e);
const mediaSrc = (p) => "/media/" + p.split("/").map(encodeURIComponent).join("/");
const byId = (id) => E.items.find((x) => x.id === id);
function newId(track) { const p = { sub: "s", broll: "b", gif: "g", emoji: "e", sfx: "a", fx: "z" }[track]; let i = 1; while (byId(p + i)) i++; return p + i; }

/* ---------- load / save / live sync ---------- */
/* ---------- GIF (คลังกลาง assets/gif — gif_lib.py) ---------- */
let GIFS = { lib: {}, cats: {} };
async function loadGifs() { try { GIFS = await fetch("/api/gifs").then((r) => r.json()); } catch (e) { /* ไม่มีคลัง */ } }
const gifSrc = (id) => (GIFS.lib[id] ? "/gif/" + GIFS.lib[id].file : null);
const gifVids = new Map();
function gifVid(id) { // <video> ต่อ GIF 1 ตัว (วนเล่น เงียบ) — วาดลง canvas
  if (!gifVids.has(id)) {
    const v = document.createElement("video"); v.muted = true; v.loop = true; v.playsInline = true; v.preload = "auto";
    v.src = gifSrc(id); v.addEventListener("loadeddata", () => drawFrame()); v.load(); gifVids.set(id, v);
  }
  return gifVids.get(id);
}
function preloadGifs() { // GIF ทุกตัวในงานโหลดไว้ก่อน — โหลดตอนถึงคิว = ช่วงตัดเข้าเห็นภาพคลิปค้างแทน GIF
  if (!E) return;
  for (const it of E.items) if (it.track === "gif" && it.gif && GIFS.lib[it.gif]) gifVid(it.gif);
}
function pauseIdleGifs(t) { // GIF ที่ไม่ได้อยู่บนจอ หยุดเล่น ไม่แย่งเครื่องถอดรหัสวิดีโอกับคลิปหลัก
  const on = new Set(E.items.filter((x) => x.track === "gif" && t >= x.start && t <= x.end).map((x) => x.gif));
  for (const [id, v] of gifVids) if (!on.has(id) && !v.paused) v.pause();
}
function gifFrame(it, t) { // เวลาใน GIF ตามหัวเล่น (เล่นวน) · เล่นอยู่ = ปล่อยเล่นเอง ห่างเกินค่อย seek
  const v = gifVid(it.gif); if (!v.duration) return v;
  const want = (t - it.start) % v.duration;
  if (vid.paused) { if (Math.abs(v.currentTime - want) > 0.04) v.currentTime = want; if (!v.paused) v.pause(); }
  else { if (Math.abs(v.currentTime - want) > 0.25) v.currentTime = want; if (v.paused) v.play().catch(() => {}); }
  return v;
}
function gifBox(it) {
  const g = GIFS.lib[it.gif] || { w: 4, h: 3 }, w = (it.w ?? 0.55) * W, h = w * g.h / g.w;
  return { x: (it.x ?? 0.5) * W - w / 2, y: (it.y ?? 0.3) * H - h / 2, w, h };
}
function drawCaption(it) {
  if (!(it.caption || "").trim()) return;
  const st = E.style, em = (FONT_METRIC[st.font] || [0.8])[0], fs = st.size * (W <= H ? 1.25 : 0.8) * em;
  const y = H * (it.mode === "overlay" ? Math.max(0.06, (it.y ?? 0.3) - 0.17) : 0.14);
  ctx.save(); ctx.font = `${fs}px "${st.font}"`;
  const tw = ctx.measureText(it.caption).width; if (tw > W * 0.9) ctx.font = `${fs * W * 0.9 / tw}px "${st.font}"`; // ยาว = ย่อให้พอดีจอ (= render_edit)
  ctx.textAlign = "center"; ctx.textBaseline = "top"; ctx.lineJoin = "round";
  ctx.lineWidth = st.outline_w * 2; ctx.strokeStyle = st.outline; ctx.strokeText(it.caption, W / 2, y);
  ctx.fillStyle = st.fill; ctx.fillText(it.caption, W / 2, y); ctx.restore();
}
function drawGif(it, t) { // = render_edit 4b (แปะทับ) / 5b (ตัดเข้าเต็มจอ)
  const SB = "#fcfaf4";
  if (it.mode === "freeze") return drawCaption(it);
  if (!GIFS.lib[it.gif]) return;
  const v = gifFrame(it, t); if (v.readyState < 2) return;
  if (it.mode === "cut") {
    // พื้น = GIF ขยายเต็ม + เบลอ + มืดลง · ย่อลงจิ๋วแล้วขยาย (ctx.filter blur ทั้งจอทุกเฟรม = หนัก ภาพกระตุก)
    const gs = drawGif.bg || (drawGif.bg = document.createElement("canvas")), gx = gs.getContext("2d");
    gs.width = W <= H ? 14 : 24; gs.height = W <= H ? 24 : 14; // จิ๋วมาก = เบลอหนักใกล้ boxblur 30 ตอนเรนเดอร์
    const sw = gs.width, sh = gs.height, kc = Math.max(sw / v.videoWidth, sh / v.videoHeight);
    gx.drawImage(v, (sw - v.videoWidth * kc) / 2, (sh - v.videoHeight * kc) / 2, v.videoWidth * kc, v.videoHeight * kc);
    ctx.imageSmoothingQuality = "high"; ctx.drawImage(gs, 0, 0, W, H);
    ctx.fillStyle = "rgba(0,0,0,.18)"; ctx.fillRect(0, 0, W, H);
    const fw = Math.min(W * 0.92, v.videoWidth * H * 0.62 / v.videoHeight), fh = fw * v.videoHeight / v.videoWidth, bd = Math.max(4, W * 0.012);
    ctx.fillStyle = SB; ctx.fillRect((W - fw) / 2 - bd, (H - fh) / 2 - bd, fw + bd * 2, fh + bd * 2);
    ctx.drawImage(v, (W - fw) / 2, (H - fh) / 2, fw, fh);
    return drawCaption(it);
  }
  const b = gifBox(it), bd = Math.max(4, b.w * 0.035), fd = 0.12;
  ctx.save(); ctx.globalAlpha = clamp(Math.min((t - it.start) / fd, (it.end - t) / fd), 0, 1);
  ctx.translate(b.x + b.w / 2, b.y + b.h / 2); ctx.rotate((it.rot ?? -3) * Math.PI / 180);
  ctx.fillStyle = SB; ctx.fillRect(-b.w / 2 - bd, -b.h / 2 - bd, b.w + bd * 2, b.h + bd * 2);
  ctx.drawImage(v, -b.w / 2, -b.h / 2, b.w, b.h); ctx.restore();
  drawCaption(it);
}
function paintTitle() {
  const nm = (E.title || ($("#projName").dataset.file || "")).replace(".edit.json", "");
  $("#projName").textContent = nm; document.title = "ClipCut — " + nm;
}
$("#projName").onclick = () => { const t = prompt("ตั้งชื่องาน", $("#projName").textContent); if (t == null) return; snapshot(); E.title = t.trim() || null; paintTitle(); touch([]); };
async function load() {
  const re = await fetch("/api/edit");
  if (!re.ok) { location.href = "/"; return; } // ยังไม่ได้เปิดโปรเจกต์ → หน้าแรก
  const [r, a] = await Promise.all([re.json(), fetch("/api/assets").then((x) => x.json())]);
  assets = a; rev = r.rev; E = r.edit; proxy = r.proxy; paintTitle();
  await loadGifs(); preloadGifs();
  $("#projName").dataset.file = r.name; paintTitle();
  await loadFont();
  applyAspect(); renderLib(isEx() ? "sfx" : "gif"); renderTimeline(); renderInspector(); setSave("ok");
  if (isEx()) setupExplainer();
  vid.addEventListener("loadedmetadata", () => {
    $("#tDur").textContent = fmt(vid.duration, false);
    const q = new URLSearchParams(location.search); // ?t=12.5&sel=e1 — เปิดตรงจุดที่จะให้ดู
    if (q.get("t")) seek(+q.get("t"));
    if (q.get("sel")) select(q.get("sel"));
    drawFrame();
  });
  vid.addEventListener("seeked", drawFrame);
  vid.src = mediaSrc(previewVideo());
  loadWave();
  const es = new EventSource("/api/events");
  es.addEventListener("edit", (ev) => onRemote(JSON.parse(ev.data)));
  es.addEventListener("render", (ev) => onRender(JSON.parse(ev.data)));
  es.addEventListener("proxy", (ev) => { // ไฟล์พรีวิวเบาทำเสร็จ → สลับไปใช้ (เวลาเดิม)
    proxy = JSON.parse(ev.data).proxy; const t = vid.currentTime, playing = !vid.paused;
    vid.src = mediaSrc(previewVideo()); vid.currentTime = t; if (playing) vid.play(); syncPlayerProps();
  });
}
let proxy = null;
const previewVideo = () => proxy || E.video; // editor ใช้ไฟล์เบา · เรนเดอร์ใช้ไฟล์เต็ม
async function loadFont() {
  for (const [fam, file] of Object.entries(FONT_FILES)) {
    try { const f = new FontFace(fam, `url(/fonts/${file})`); await f.load(); document.fonts.add(f); } catch (e) { /* ไม่มีไฟล์ก็ข้าม */ }
  }
}
function setSave(s) {
  const el = $("#saveState"); el.className = "status " + (s === "ok" ? "ok" : "dirty");
  el.textContent = s === "ok" ? "บันทึกแล้ว" : s === "saving" ? "กำลังบันทึก…" : "ยังไม่บันทึก";
}
function snapshot() { undoStack.push(JSON.stringify(E)); if (undoStack.length > 150) undoStack.shift(); redoStack = []; }
function touch(ids, opts = {}) {
  ids.forEach((id) => dirty.add(id));
  if (!opts.noTimeline) renderTimeline();
  if (!opts.noInspector) renderInspector();
  drawFrame(); syncPlayerProps(); setSave("dirty");
  clearTimeout(saveTimer); saveTimer = setTimeout(save, 350);
}
async function save() {
  if (saving) { clearTimeout(saveTimer); saveTimer = setTimeout(save, 200); return; }
  saving = true; setSave("saving");
  const sent = new Set(dirty), sentDel = new Set(deleted);
  try {
    const r = await fetch("/api/edit", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ edit: E, base_rev: rev, client: CLIENT, file: $("#projName").dataset.file }) });
    const j = await r.json();
    if (j.switched) return switched();
    if (j.conflict) { merge(j.edit); rev = j.rev; saving = false; return save(); }
    rev = j.rev; sent.forEach((x) => dirty.delete(x)); sentDel.forEach((x) => deleted.delete(x));
    setSave(dirty.size ? "dirty" : "ok");
  } catch (e) { setSave("dirty"); toast("บันทึกไม่ได้ — server ปิดอยู่?"); }
  saving = false;
}
/* ของจากไฟล์ (กุ้งแก้) + ของที่เฉินแก้ค้างอยู่ → รวมกัน (ของที่เฉินแตะชนะ) */
function merge(remote) {
  const local = new Map(E.items.map((x) => [x.id, x]));
  const items = remote.items.filter((x) => !deleted.has(x.id)).map((x) => (dirty.has(x.id) && local.has(x.id) ? local.get(x.id) : x));
  for (const id of dirty) if (local.has(id) && !items.some((x) => x.id === id)) items.push(local.get(id));
  let scenes = remote.scenes;
  if (dirty.has("__scenes") && E.scenes) { // เก็บฉากที่แก้ค้าง แต่ห้ามทิ้ง focus ที่ไฟล์มีแล้ว (ฉากเดียวกัน = เวลาเริ่มตรงกัน)
    scenes = E.scenes.map((sc) => (sc.focus ? sc : { ...sc, ...((remote.scenes || []).find((o) => Math.abs(o.start - sc.start) < 0.05 && o.focus) ? { focus: remote.scenes.find((o) => Math.abs(o.start - sc.start) < 0.05).focus } : {}) }));
  }
  E = { ...remote, items, scenes };
}
// server เปิดงานได้ทีละงาน — อีกเครื่อง (มือถือ/ไอแพด) เปิดงานอื่น = หน้านี้ต้องโหลดใหม่ ห้ามเซฟทับ/รวมของข้ามงาน
function switched() { saving = true; toast("อีกเครื่องเปิดงานอื่นอยู่ — กำลังโหลดงานนั้น"); setTimeout(() => location.reload(), 1500); }
function onRemote(d) {
  if (d.file && d.file !== $("#projName").dataset.file) return switched();
  if (d.by === CLIENT) return;
  if (E && d.edit.video !== E.video) {
    const t = Math.min(vid.currentTime, d.edit.duration);
    E.video = d.edit.video; proxy = null; vid.src = mediaSrc(E.video); vid.currentTime = t; loadWave();
  }
  const before = new Map(E.items.map((x) => [x.id, JSON.stringify(x)]));
  if (dirty.size || deleted.size) merge(d.edit); else E = d.edit;
  rev = d.rev;
  const changed = E.items.filter((x) => before.get(x.id) !== JSON.stringify(x)).map((x) => x.id);
  const removed = [...before.keys()].filter((id) => !byId(id)).length;
  if (sel && !byId(sel)) sel = null;
  preloadGifs(); applyAspect(); renderTimeline(changed); renderInspector(); drawFrame(); syncPlayerProps();
  if (changed.length || removed) {
    const cnt = {}; changed.forEach((id) => { const t = byId(id).track; cnt[t] = (cnt[t] || 0) + 1; });
    const parts = Object.entries(cnt).map(([t, n]) => `${(BASE_TRACKS.find((x) => x.id === t) || { name: t }).name} ${n}`);
    if (removed) parts.push(`ลบ ${removed}`);
    toast("กุ้งแก้มา: " + parts.join(" · "));
  }
}

/* ---------- undo ---------- */
function undo() { if (!undoStack.length) return; redoStack.push(JSON.stringify(E)); restore(undoStack.pop()); }
function redo() { if (!redoStack.length) return; undoStack.push(JSON.stringify(E)); restore(redoStack.pop()); }
function restore(s) {
  const old = new Set(E.items.map((x) => x.id)); E = JSON.parse(s);
  const now = new Set(E.items.map((x) => x.id));
  old.forEach((id) => { if (!now.has(id)) deleted.add(id); });
  now.forEach((id) => { dirty.add(id); deleted.delete(id); });
  applyAspect(); touch([]);
}

/* ---------- aspect / canvas ---------- */
function applyAspect() {
  [W, H] = E.aspect === "9x16" ? [1080, 1920] : [1920, 1080];
  if (cv.width !== W || cv.height !== H) { cv.width = W; cv.height = H; }
  document.querySelectorAll("#aspectSeg button").forEach((b) => b.classList.toggle("on", b.dataset.aspect === E.aspect));
}
const small = document.createElement("canvas"); small.width = 54; small.height = 96;
const sctx = small.getContext("2d");

function zoomAt(t) { // = ccfx.zoom_at
  let z = 1, sx = 0, sy = 0, fl = 0;
  for (const it of E.items) {
    if (it.track !== "fx" || t < it.start || t > it.end) continue;
    const a = it.amount ?? assets.fx_default[it.fx], s = it.start, e = it.end, d = Math.max(e - s, 1e-3), p = (t - s) / d;
    if (it.fx === "punch") z += (a - 1) * Math.min(1, (t - s) / 0.08, (e - t) / 0.15);
    else if (it.fx === "zoomin") z += (a - 1) * p;
    else if (it.fx === "zoomout") z += (a - 1) * (1 - p);
    else if (it.fx === "focus") z += (a - 1) * Math.min(1, (t - s) / 0.35, (e - t) / 0.35);
    else if (it.fx === "shake") { z += 0.06; sx += a * Math.sin(t * 47); sy += a * Math.sin(t * 61 + 1); }
    else if (it.fx === "flash") fl += a * Math.exp(-(t - s) * 4 / d);
  }
  return [z, sx, sy, fl];
}
function emojiAnim(anim, t, dur) { // = ccfx.emoji_anim
  const outT = Math.min(0.15, dur / 3);
  if (anim === "float") return [1, Math.sin(t * 6) * 6, Math.max(0, Math.min(1, t / 0.15) * Math.min(1, (dur - t) / 0.25)), -0.08 * t / Math.max(dur, 1e-3)];
  if (anim === "shake") return [Math.min(1, t / 0.08), Math.sin(t * 40) * 12, Math.max(0, Math.min(1, (dur - t) / outT)), 0];
  let s = t < 0.12 ? 1.25 * t / 0.12 : t < 0.24 ? 1.25 - 0.25 * (t - 0.12) / 0.12 : 1;
  if (t > dur - outT) s *= Math.max(0, (dur - t) / outT);
  return [s, Math.sin(t * 5) * 5, 1, 0];
}
// กล้องตามหน้า (smartcam.py) — มุมซ้ายบนกรอบครอปที่เวลา t = cam_at ใน smartcam / crop ใน render_edit
const camOn = () => !!(E.cam && E.cam.mode === "follow" && E.cam.path && E.cam.path.length);
function camAt(t) {
  const p = E.cam.path;
  if (t <= p[0][0]) return [p[0][1], p[0][2]];
  if (t >= p[p.length - 1][0]) return [p[p.length - 1][1], p[p.length - 1][2]];
  let lo = 0, hi = p.length - 1;
  while (hi - lo > 1) { const m = (lo + hi) >> 1; if (p[m][0] <= t) lo = m; else hi = m; }
  const a = p[lo], b = p[hi], f = b[0] > a[0] ? (t - a[0]) / (b[0] - a[0]) : 0;
  return [a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f];
}
function drawBase() {
  const vw = vid.videoWidth, vh = vid.videoHeight;
  ctx.fillStyle = "#060606"; ctx.fillRect(0, 0, W, H);
  if (!vw) return;
  if (camOn()) {
    const [x0, y0] = camAt(vid.currentTime);
    ctx.imageSmoothingQuality = "high";
    ctx.drawImage(vid, x0 * vw, y0 * vh, E.cam.w * vw, E.cam.h * vh, 0, 0, W, H);
    return;
  }
  if (E.aspect === "9x16" && vw > vh) {
    // พื้นหลัง = คลิป cover + เบลอ (ย่อเล็กแล้วขยาย ≈ boxblur ใน ffmpeg)
    const k = Math.max(54 / vw, 96 / vh), bw = vw * k, bh = vh * k;
    sctx.drawImage(vid, (54 - bw) / 2, (96 - bh) / 2, bw, bh);
    ctx.imageSmoothingQuality = "high"; ctx.drawImage(small, 0, 0, W, H);
    const fh = vh * W / vw; ctx.drawImage(vid, 0, (H - fh) / 2, W, fh);
  } else {
    const k = Math.min(W / vw, H / vh), dw = vw * k, dh = vh * k;
    ctx.drawImage(vid, (W - dw) / 2, (H - dh) / 2, dw, dh);
  }
}
function drawFrame() {
  if (!E || isEx()) return; // explainer = ตัวเล่น Remotion วาดเอง
  const t = vid.currentTime;
  const [z, sx, sy, fl] = zoomAt(t);
  ctx.save();
  // = zoompan ใน render_edit: มุมซ้ายบนของภาพที่เห็น = จุดโฟกัส - ครึ่งจอที่ซูม (ชนขอบ = หยุดที่ขอบ)
  const fit = E.items.find((x) => x.track === "fx" && x.fx !== "flash" && x.fx_x != null && t >= x.start && t <= x.end);
  const px = fit ? fit.fx_x * W : W / 2, py = fit ? fit.fx_y * H : H / 2;
  const x0 = clamp(px - W / z / 2, 0, W - W / z), y0 = clamp(py - H / z / 2, 0, H - H / z);
  ctx.translate(-(x0 + sx) * z, -(y0 + sy) * z); ctx.scale(z, z);
  drawBase(); ctx.restore();
  if (fl > 0) { ctx.fillStyle = `rgba(255,255,255,${Math.min(1, fl)})`; ctx.fillRect(0, 0, W, H); }
  const active = E.items.filter((x) => t >= x.start && t <= x.end);
  for (const it of active.filter((x) => x.track === "broll")) drawBroll(it, t);
  for (const it of active.filter((x) => x.track === "gif" && x.mode === "overlay")) drawGif(it, t);
  for (const it of active.filter((x) => x.track === "emoji")) drawEmoji(it, t);
  for (const it of active.filter((x) => x.track === "gif" && x.mode !== "overlay")) drawGif(it, t);
  for (const it of active.filter((x) => x.track === "sub")) drawSub(it, t);
  const s = sel && byId(sel);
  if (s && movable(s) && t >= s.start && t <= s.end) {
    const b = boxOf(s); ctx.strokeStyle = "#fde047"; ctx.lineWidth = 4; ctx.setLineDash([16, 10]);
    ctx.strokeRect(b.x, b.y, b.w, b.h); ctx.setLineDash([]);
  }
  if (s && s.track === "fx" && s.fx !== "flash") { // เป้าเล็ง = จุดที่ซูมเข้า (ลากย้ายได้)
    const fx = (s.fx_x ?? 0.5) * W, fy = (s.fx_y ?? 0.5) * H;
    ctx.strokeStyle = "#fde047"; ctx.lineWidth = 5; ctx.beginPath(); ctx.arc(fx, fy, 46, 0, 7); ctx.moveTo(fx - 80, fy); ctx.lineTo(fx + 80, fy); ctx.moveTo(fx, fy - 80); ctx.lineTo(fx, fy + 80); ctx.stroke();
  }
  if ($("#chkSafe").checked) {
    ctx.strokeStyle = "rgba(16,185,129,.7)"; ctx.lineWidth = 3; ctx.setLineDash([12, 12]);
    ctx.strokeRect(W * 0.06, H * 0.08, W * 0.88, H * 0.74); ctx.setLineDash([]);
  }
}
const movable = (i) => i.track === "emoji" || i.track === "broll" || (i.track === "gif" && i.mode === "overlay");
function boxOf(it) {
  if (it.track === "gif") return gifBox(it);
  if (it.track === "broll") {
    const im = img(mediaSrc(it.src)), w = (it.w ?? 0.8) * W, h = im.naturalWidth ? w * im.naturalHeight / im.naturalWidth : w * 0.6;
    return { x: it.x * W - w / 2, y: it.y * H - h / 2, w, h };
  }
  const sz = (it.size ?? 0.22) * W; return { x: it.x * W - sz / 2, y: it.y * H - sz / 2, w: sz, h: sz };
}
function drawBroll(it, t) {
  const im = img(mediaSrc(it.src)); if (!im.complete || !im.naturalWidth) return;
  const b = boxOf(it), fd = Math.min(0.15, (it.end - it.start) / 3);
  ctx.globalAlpha = clamp(Math.min((t - it.start) / fd, (it.end - t) / fd), 0, 1);
  ctx.drawImage(im, b.x, b.y, b.w, b.h); ctx.globalAlpha = 1;
}
function drawEmoji(it, t) {
  const im = img(emojiSrc(it.emoji)); if (!im.complete || !im.naturalWidth) return;
  const [s, rot, a, dy] = emojiAnim(it.anim || "pop", t - it.start, it.end - it.start);
  const sz = (it.size ?? 0.22) * W * s; if (sz < 1) return;
  ctx.save(); ctx.globalAlpha = a; ctx.translate(it.x * W, (it.y + dy) * H); ctx.rotate(rot * Math.PI / 180);
  ctx.drawImage(im, -sz / 2, -sz / 2, sz, sz); ctx.restore();
}
function subRuns(text, base) {
  const hl = E.style.highlights || {}; const keys = Object.keys(hl).sort((a, b) => b.length - a.length);
  if (!keys.length) return [[text, base]];
  const re = new RegExp(keys.map((k) => k.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|"), "gi");
  const out = []; let last = 0, m;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push([text.slice(last, m.index), base]);
    out.push([m[0], hl[keys.find((k) => k.toLowerCase() === m[0].toLowerCase())]]); last = m.index + m[0].length;
  }
  if (last < text.length) out.push([text.slice(last), base]);
  return out;
}
function drawSub(it, t) {
  const st = E.style, vertical = W <= H, k = vertical ? 1 : 0.62;
  const [emK, descK] = FONT_METRIC[st.font] || [0.8, 0.2];
  const assSize = st.size * k, size = assSize * emK;
  const ow = Math.max(2, Math.round(st.outline_w * k)), sh = Math.round(st.shadow * k);
  const mv = vertical ? st.margin_v : Math.max(50, Math.round(st.margin_v * 0.2));
  const base = (st.speakers || {})[it.speaker] || st.fill;
  const lt = (t - it.start) * 1000;
  let sc = lt < 120 ? 0.7 + 0.42 * lt / 120 : lt < 220 ? 1.12 - 0.12 * (lt - 120) / 100 : 1;
  const dur = (it.end - it.start) * 1000;
  const a = Math.min(1, lt / 80, (dur - lt) / 60);
  ctx.save(); ctx.font = `${st.font === "Itim" ? "" : "bold "}${size}px "${st.font}"`;
  ctx.textBaseline = "alphabetic"; ctx.lineJoin = "round"; ctx.globalAlpha = clamp(a, 0, 1);
  const runs = subRuns(it.text, base);
  const total = runs.reduce((s, r) => s + ctx.measureText(r[0]).width, 0);
  const y = H - mv - assSize * descK;
  ctx.translate(W / 2, y); ctx.scale(sc, sc);
  let x = -total / 2;
  const draw = (pass) => {
    let xx = x;
    for (const [txt, col] of runs) {
      if (pass === "sh") { ctx.fillStyle = st.shadow_color + "8f"; ctx.strokeStyle = st.shadow_color + "8f"; ctx.lineWidth = ow * 2; ctx.strokeText(txt, xx + sh, sh); ctx.fillText(txt, xx + sh, sh); }
      if (pass === "ol") { ctx.strokeStyle = st.outline; ctx.lineWidth = ow * 2; ctx.strokeText(txt, xx, 0); }
      if (pass === "fill") { ctx.fillStyle = col; ctx.fillText(txt, xx, 0); }
      xx += ctx.measureText(txt).width;
    }
  };
  if (sh) draw("sh"); draw("ol"); draw("fill");
  ctx.restore();
}

/* ---------- เสียง: ผ่าน WebAudio ให้ระดับตรงกับ render_edit.py ----------
   เสียงพูด × gain คงที่ไปที่ -16 LUFS · SFX × vol × mix.sfx · เพลง × vol แล้ว duck ตอนพูด · ทั้งหมดเข้า limiter */
const music = new Audio(); music.preload = "auto"; music.loop = true;
let bus = null, musicSrcId = null;
function audioInit() {
  if (bus) return;
  actx = actx || new AudioContext();
  const lim = actx.createDynamicsCompressor();
  lim.threshold.value = -2; lim.knee.value = 0; lim.ratio.value = 20; lim.attack.value = 0.002; lim.release.value = 0.1;
  lim.connect(actx.destination);
  const voice = actx.createGain(); actx.createMediaElementSource(vid).connect(voice).connect(lim);
  const mGain = actx.createGain(), duck = actx.createGain();
  actx.createMediaElementSource(music).connect(mGain).connect(duck).connect(lim);
  bus = { lim, voice, mGain, duck };
  levels();
}
function levels() { // ใส่ค่าจาก E ทุกครั้งที่เปลี่ยน
  if (!bus) return;
  bus.voice.gain.value = Math.pow(10, (assets.voice_lufs_target - (E.voice_lufs ?? assets.voice_lufs_target)) / 20);
  bus.mGain.gain.value = E.music ? (E.music.vol ?? assets.music_default.vol) : 0;
}
async function sfx(name) {
  actx = actx || new AudioContext();
  if (!sfxBuf[name]) sfxBuf[name] = fetch("/sfx/" + name + ".wav").then((r) => r.arrayBuffer()).then((b) => actx.decodeAudioData(b));
  return sfxBuf[name];
}
async function playSfx(name, vol = 0.8, offset = 0) {
  audioInit(); if (actx.state === "suspended") actx.resume();
  const b = await sfx(name); const src = actx.createBufferSource(), g = actx.createGain();
  src.buffer = b; g.gain.value = vol * (E.mix?.sfx ?? assets.mix_default.sfx); src.connect(g).connect(bus.lim); src.start(0, offset);
}
function syncMusic(force) {
  if (!E.music) { if (!music.paused) music.pause(); return; }
  if (musicSrcId !== E.music.src) {
    const m = assets.music.find((x) => x.id === E.music.src); if (!m) return;
    music.src = "/music/" + encodeURIComponent(m.file); musicSrcId = E.music.src; force = true;
  }
  if (vid.paused) { if (!music.paused) music.pause(); return; }
  const want = ((E.music.offset || 0) + vid.currentTime) % (music.duration || 1e9);
  if (force || Math.abs(music.currentTime - want) > 0.25) music.currentTime = want;
  if (music.paused) music.play().catch(() => {});
}
function togglePlay() {
  audioInit(); if (actx.state === "suspended") actx.resume();
  if (vid.paused) { vid.play(); E.items.filter((x) => x.track === "sfx").forEach((x) => sfx(x.sfx)); } else vid.pause();
}
vid.addEventListener("play", () => { $("#btnPlay").textContent = "หยุด"; $("#btnPlay").classList.add("on"); syncMusic(true); if (player) { player.seek(Math.round(vid.currentTime * 30)); player.play(); lastFix = performance.now() - 1600; } });
vid.addEventListener("pause", () => { $("#btnPlay").textContent = "เล่น"; $("#btnPlay").classList.remove("on"); music.pause(); if (player) player.pause(); lastSeekF = -1; });
vid.addEventListener("seeked", () => syncMusic(true));
function tick() {
  const t = vid.currentTime;
  if (!vid.paused && $("#chkSfx").checked && E) {
    for (const it of E.items) if (it.track === "sfx" && it.start > lastT && it.start <= t && t - lastT < 0.5) playSfx(it.sfx, it.vol ?? 0.8);
  }
  if (E && bus) {
    levels(); syncMusic(false);
    // ducking: เสียงพูดดัง (จาก waveform) → กดเพลงลง ~10 dB เหมือน sidechaincompress ตอน render
    const talking = E.music?.duck !== false && peaks && (peaks[Math.floor(t * 50)] || 0) > 0.12;
    bus.duck.gain.setTargetAtTime(talking ? 0.32 : 1, actx.currentTime, talking ? 0.04 : 0.5);
  }
  if (player) { // ตัวเล่น Remotion ตามนาฬิกาของวิดีโอ (เสียงมาจาก vid)
    const f = Math.round(t * 30);
    if (vid.paused) { if (f !== lastSeekF) { player.seek(f); lastSeekF = f; } }
    // ตอนเล่น: แก้เมื่อคลาดเกิน 4 เฟรม ไม่ถี่กว่าทุก 2 วิ (ตัวเล่นเริ่มช้ากว่าเสียง ~0.25 วิ ต้องไล่ตาม 1 ครั้ง)
    else if (performance.now() - lastFix > 1500) {
      // วัดจากเวลาของ <video> จริงในตัวเล่น (เฟรมของตัวเล่นถูกแต่วิดีโอข้างในโหลดไม่ทันได้) คลาดเกิน 0.1 วิ = จับใหม่
      const pv = [...document.querySelectorAll("#playerBox video")].pop();
      const lag = pv ? t - pv.currentTime : (f - player.frame()) / 30;
      if (Math.abs(lag) > 0.1) { player.seek(f + Math.round(Math.max(0, lag) * 15)); lastFix = performance.now(); }
    }
  }
  // คลิปหลักค้าง (เวลาไม่เดินทั้งที่กำลังเล่น ข้อมูลพร้อม) เกิน 0.4 วิ → seek ที่เดิมให้ตัวถอดรหัสเริ่มใหม่
  if (!vid.paused && !vid.seeking && vid.readyState >= 2 && t < (vid.duration || 1e9) - 0.1) {
    if (t !== tick.lastT) { tick.lastT = t; tick.since = performance.now(); }
    else if (performance.now() - tick.since > 400) { vid.currentTime = t + 0.001; tick.since = performance.now(); console.warn("unstick", t); }
  }
  if (E && !isEx()) pauseIdleGifs(t);
  lastT = t;
  if (E) {
    drawFrame(); $("#tCur").textContent = fmt(t);
    $("#playhead").style.left = t * pps + "px";
    if (!vid.paused) { // ตามหัวเล่น
      const sc = $("#tlScroll"), x = t * pps;
      if (x > sc.scrollLeft + sc.clientWidth - 80 || x < sc.scrollLeft) sc.scrollLeft = x - 120;
    }
  }
  requestAnimationFrame(tick);
}
function seek(t) {
  vid.currentTime = clamp(t, 0, vid.duration || E.duration); lastT = vid.currentTime;
  const sc = $("#tlScroll"), x = vid.currentTime * pps; // หัวเล่นหลุดจอ → เลื่อน timeline ตาม
  if (x < sc.scrollLeft || x > sc.scrollLeft + sc.clientWidth - 40) sc.scrollLeft = x - sc.clientWidth / 3;
}

/* ---------- timeline ---------- */
function itemLabel(it) {
  if (it.track === "sub") return document.createTextNode(it.text);
  if (it.track === "emoji") { const i = new Image(); i.src = emojiSrc(it.emoji); return i; }
  if (it.track === "broll") { const f = document.createDocumentFragment(); const i = new Image(); i.src = mediaSrc(it.src); f.append(i, it.src.split("/").pop()); return f; }
  if (it.track === "sfx") return document.createTextNode(it.sfx);
  if (it.track === "gif") return document.createTextNode({ overlay: "แปะ", cut: "ตัดเข้า", freeze: "หยุดภาพ" }[it.mode] + " · " + (it.caption || GIFS.lib[it.gif]?.desc || it.gif || ""));
  if (it.track === "scene") return document.createTextNode(`${it.idx + 1}. ${it.title || ""}`);
  return document.createTextNode(FX_INFO[it.fx]?.[0] || it.fx);
}
function renderTimeline(flashIds = []) {
  if (!E) return;
  const dur = E.duration, width = Math.ceil(dur * pps) + 200;
  $("#tlContent").style.width = width + "px";
  // timeline สูงพอดีจำนวนแถว (explainer 3 แถว / แปะเอฟเฟกต์ 5 แถว) → ที่เหลือให้จอพรีวิว
  document.documentElement.style.setProperty("--tl-h", Math.min(360, Math.max(190, 32 + 28 + trackList().length * 46 + 14)) + "px");
  $("#tlHeads").innerHTML = trackList().map((t) => `<div><i style="background:${t.col}"></i>${t.name}</div>`).join("");
  const ruler = $("#ruler"); ruler.querySelectorAll(".tick").forEach((x) => x.remove());
  const step = [0.5, 1, 2, 5, 10, 15, 30, 60].find((s) => s * pps >= 70) || 60;
  for (let s = 0; s <= dur; s += step) {
    const d = document.createElement("div"); d.className = "tick"; d.style.left = s * pps + "px"; d.textContent = fmt(s, false); ruler.appendChild(d);
  }
  drawWave();
  const tracks = $("#tracks"); tracks.innerHTML = "";
  for (const tr of trackList()) {
    const row = document.createElement("div"); row.className = "track"; row.dataset.track = tr.id;
    for (const it of tr.id === "scene" ? sceneProxies() : E.items.filter((x) => x.track === tr.id)) {
      const el = document.createElement("div");
      el.className = `item t-${it.track}` + (it.id === sel ? " sel" : "") + (flashIds.includes(it.id) ? " flash" : "");
      el.dataset.id = it.id; el.style.left = it.start * pps + "px"; el.style.width = Math.max(4, (it.end - it.start) * pps) + "px";
      el.title = `${fmt(it.start)} – ${fmt(it.end)}`;
      el.append(itemLabel(it));
      const hl = document.createElement("div"); hl.className = "h l"; const hr = document.createElement("div"); hr.className = "h r";
      if (it.track === "scene") { if (it.idx > 0) el.append(hl); } else el.append(hl, hr);
      row.appendChild(el);
    }
    tracks.appendChild(row);
  }
}
let drag = null;
$("#tracks").addEventListener("pointerdown", (ev) => {
  const el = ev.target.closest(".item"); if (!el) { select(null); return; }
  if (el.dataset.id.startsWith("sc")) {
    const i = +el.dataset.id.slice(2); select(el.dataset.id); seek(E.scenes[i].start + 0.01);
    if (i > 0 && ev.target.classList.contains("l")) { drag = { scene: i, x0: ev.clientX, s0: E.scenes[i].start, el, moved: false, snapshot: JSON.stringify(E) }; el.setPointerCapture(ev.pointerId); }
    return;
  }
  const it = byId(el.dataset.id); select(it.id);
  const mode = ev.target.classList.contains("l") ? "l" : ev.target.classList.contains("r") ? "r" : "m";
  drag = { it, mode, x0: ev.clientX, s0: it.start, e0: it.end, el, moved: false, snapshot: JSON.stringify(E) };
  el.setPointerCapture(ev.pointerId);
});
function snapT(t, it) {
  if (!$("#chkSnap").checked) return t;
  const cands = [vid.currentTime]; for (const x of E.items) if (x !== it) cands.push(x.start, x.end);
  let best = t, bd = 8 / pps; for (const c of cands) if (Math.abs(c - t) < bd) { bd = Math.abs(c - t); best = c; }
  return best;
}
window.addEventListener("pointermove", (ev) => {
  if (!drag) return;
  if (drag.scene != null) {
    const i = drag.scene, sc = E.scenes, lo = sc[i - 1].start + 0.8, hi = (sc[i + 1] ? sc[i + 1].start : E.duration) - 0.8;
    sc[i].start = r3(clamp(snapT(drag.s0 + (ev.clientX - drag.x0) / pps, null), lo, hi)); drag.moved = true;
    renderTimeline(); seek(sc[i].start + 0.01); syncPlayerProps(); return;
  }
  const dt = (ev.clientX - drag.x0) / pps; if (Math.abs(ev.clientX - drag.x0) > 2) drag.moved = true;
  const { it } = drag, len = drag.e0 - drag.s0, minLen = 0.05;
  if (drag.mode === "m") {
    let s = clamp(drag.s0 + dt, 0, E.duration - len); const ss = snapT(s, it), se = snapT(s + len, it);
    s = ss !== s ? ss : se !== s + len ? se - len : s; it.start = r3(s); it.end = r3(s + len);
  } else if (drag.mode === "l") it.start = r3(clamp(snapT(drag.s0 + dt, it), 0, it.end - minLen));
  else it.end = r3(clamp(snapT(drag.e0 + dt, it), it.start + minLen, E.duration));
  drag.el.style.left = it.start * pps + "px"; drag.el.style.width = (it.end - it.start) * pps + "px";
  if (it.track !== "sfx" && vid.paused) seek(drag.mode === "r" ? it.end - 0.01 : it.start);
  renderInspector(); drawFrame();
});
window.addEventListener("pointerup", () => {
  if (!drag) return;
  if (drag.moved) { undoStack.push(drag.snapshot); redoStack = []; touch([drag.scene != null ? "__scenes" : drag.it.id]); }
  drag = null;
});
let scrub = false;
$("#ruler").addEventListener("pointerdown", (ev) => { scrub = true; scrubTo(ev); $("#ruler").setPointerCapture(ev.pointerId); });
$("#ruler").addEventListener("pointermove", (ev) => scrub && scrubTo(ev));
$("#ruler").addEventListener("pointerup", () => (scrub = false));
function scrubTo(ev) { const r = $("#tlContent").getBoundingClientRect(); seek((ev.clientX - r.left) / pps); }
$("#tlScroll").addEventListener("wheel", (ev) => {
  if (ev.ctrlKey) { ev.preventDefault(); setZoom(pps * (ev.deltaY < 0 ? 1.2 : 1 / 1.2), ev.clientX); }
  else if (Math.abs(ev.deltaY) > Math.abs(ev.deltaX)) { ev.preventDefault(); $("#tlScroll").scrollLeft += ev.deltaY; }
}, { passive: false });
function setZoom(v, anchorX) {
  const sc = $("#tlScroll"), r = sc.getBoundingClientRect(), ax = anchorX ? anchorX - r.left : sc.clientWidth / 2;
  const tAt = (sc.scrollLeft + ax) / pps; pps = clamp(v, 8, 400); $("#tlZoom").value = pps;
  renderTimeline(); sc.scrollLeft = tAt * pps - ax;
}
$("#tlZoom").addEventListener("input", (e) => setZoom(+e.target.value));

/* waveform ของคลิป ไว้ดูจังหวะ */
let peaks = null;
async function loadWave() {
  try {
    const buf = await fetch(mediaSrc(previewVideo())).then((r) => r.arrayBuffer());
    const ac = new OfflineAudioContext(1, 1, 8000);
    const ab = await ac.decodeAudioData(buf);
    const ch = ab.getChannelData(0), n = Math.ceil(ab.duration * 50), per = Math.floor(ch.length / n);
    peaks = new Float32Array(n);
    for (let i = 0; i < n; i++) { let m = 0; for (let j = i * per, e = j + per; j < e; j += 4) { const v = Math.abs(ch[j]); if (v > m) m = v; } peaks[i] = m; }
    const mx = Math.max(...peaks) || 1; for (let i = 0; i < n; i++) peaks[i] /= mx;
    drawWave();
  } catch (e) { console.warn("wave", e); }
}
function drawWave() {
  const c = $("#wave"); if (!peaks || !E) return;
  const w = Math.min(32000, Math.ceil(E.duration * pps)); c.width = w; c.height = 28; c.style.width = w + "px";
  const g = c.getContext("2d"); g.fillStyle = "rgba(16,185,129,.35)";
  for (let x = 0; x < w; x++) { const v = peaks[Math.floor(x / pps * 50)] || 0; const h = v * 24; g.fillRect(x, 28 - h, 1, h); }
}

/* ---------- select / canvas drag ---------- */
function select(id) { sel = id; renderInspector(); document.querySelectorAll(".item").forEach((e) => e.classList.toggle("sel", e.dataset.id === id)); drawFrame(); }
function canvasPt(ev) { const r = cv.getBoundingClientRect(); return [(ev.clientX - r.left) * W / r.width, (ev.clientY - r.top) * H / r.height]; }
let cdrag = null;
cv.addEventListener("pointerdown", (ev) => {
  const [x, y] = canvasPt(ev), t = vid.currentTime;
  const sf = sel && byId(sel);
  if (sf && sf.track === "fx" && sf.fx !== "flash") { // ลากเป้าเล็งจุดซูม
    cdrag = { it: sf, focus: true, snapshot: JSON.stringify(E), moved: false };
    delete sf.fx_src; sf.fx_x = r3(x / W); sf.fx_y = r3(y / H); cdrag.moved = true; drawFrame(); cv.setPointerCapture(ev.pointerId); return;
  }
  const hits = E.items.filter((i) => movable(i) && t >= i.start && t <= i.end)
    .filter((i) => { const b = boxOf(i); return x >= b.x && x <= b.x + b.w && y >= b.y && y <= b.y + b.h; });
  const it = hits.find((h) => h.id === sel) || hits.reverse().find((h) => h.track === "emoji") || hits[0];
  if (!it) { if (!vid.paused) return; return togglePlay(); }
  select(it.id); cdrag = { it, x, y, x0: it.x, y0: it.y, snapshot: JSON.stringify(E), moved: false };
  cv.setPointerCapture(ev.pointerId);
});
cv.addEventListener("pointermove", (ev) => {
  const [x, y] = canvasPt(ev);
  if (!cdrag) {
    const t = vid.currentTime;
    const over = E && E.items.some((i) => movable(i) && t >= i.start && t <= i.end && (() => { const b = boxOf(i); return x >= b.x && x <= b.x + b.w && y >= b.y && y <= b.y + b.h; })());
    cv.classList.toggle("grab", !!over); return;
  }
  if (cdrag.focus) { cdrag.it.fx_x = r3(clamp(x / W, 0, 1)); cdrag.it.fx_y = r3(clamp(y / H, 0, 1)); drawFrame(); return; }
  cdrag.moved = true; cdrag.it.x = r3(clamp(cdrag.x0 + (x - cdrag.x) / W, 0, 1)); cdrag.it.y = r3(clamp(cdrag.y0 + (y - cdrag.y) / H, 0, 1));
  drawFrame(); renderInspector();
});
cv.addEventListener("pointerup", () => { if (cdrag?.moved) { undoStack.push(cdrag.snapshot); redoStack = []; touch([cdrag.it.id], { noTimeline: true }); } cdrag = null; });
cv.addEventListener("wheel", (ev) => { // หมุนล้อบนของที่เลือก = ย่อ/ขยาย
  const it = sel && byId(sel); if (!it || (it.track !== "emoji" && it.track !== "broll")) return;
  ev.preventDefault(); const key = it.track === "emoji" ? "size" : "w"; const v = it[key] ?? (key === "size" ? 0.22 : 0.8);
  it[key] = r3(clamp(v * (ev.deltaY < 0 ? 1.06 : 1 / 1.06), 0.04, 1.5)); touch([it.id], { noTimeline: true });
}, { passive: false });

/* ---------- inspector ---------- */
function field(label, html) { return `<div class="field"><label>${label}</label><div>${html}</div></div>`; }
function slider(key, v, min, max, step) { return `<div class="row"><input type="range" data-k="${key}" min="${min}" max="${max}" step="${step}" value="${v}"><span class="val">${(+v).toFixed(step < 0.1 ? 2 : step < 1 ? 1 : 0)}</span></div>`; }
function esc(s) { return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }
function renderInspector() {
  if (sel && sel.startsWith("sc") && isEx()) { $("#inspHead").textContent = "แก้ฉาก"; return renderSceneInspector(+sel.slice(2)); }
  const body = $("#inspBody"), it = sel && byId(sel);
  $("#inspHead").textContent = it ? "แก้ค่า" : "ภาพรวม";
  if (!it) {
    const cnt = (t) => E.items.filter((x) => x.track === t).length;
    const rows = isEx() ? [["ฉาก", (E.scenes || []).length], ["ซับ", cnt("sub")], ["เสียง", cnt("sfx")]]
      : trackList().map((t) => [t.name, cnt(t.id)]);
    const cam = !isEx() && E.cam ? (E.cam.mode === "follow" ? "ตามหน้าคนพูด" : "ภาพเต็ม") : null;
    body.innerHTML = `<div class="stats">${rows.map(([a, b]) => `<div><b>${b}</b><span>${a}</span></div>`).join("")}</div>
      <div class="kv"><span>ความยาว</span><span>${fmt(E.duration, false)}</span>${cam ? `<span>กล้อง</span><span>${cam}</span>` : ""}${E.music ? `<span>เพลง</span><span>${esc((assets.music.find((m) => m.id === E.music.src) || { title: E.music.src }).title)}</span>` : ""}</div>
      <p class="muted" style="margin:12px 0 8px">คลิกของบน timeline หรือบนจอเพื่อแก้</p>
      <div class="keys"><kbd>Space</kbd><span>เล่น / หยุด</span><kbd>← →</kbd><span>ทีละเฟรม</span><kbd>Delete</kbd><span>ลบของที่เลือก</span>
      <kbd>Ctrl D</kbd><span>ทำสำเนา</span><kbd>Ctrl Z</kbd><span>ย้อน</span><kbd>Ctrl ล้อเมาส์</kbd><span>ซูม timeline</span></div>`;
    return;
  }
  if (body.contains(document.activeElement) && document.activeElement.dataset.k && body.dataset.id === it.id) { // อย่าทับช่องที่กำลังพิมพ์
    body.querySelectorAll("[data-k]").forEach((el) => { if (el !== document.activeElement && el.type !== "range") el.value = it[el.dataset.k] ?? ""; });
    return;
  }
  body.dataset.id = it.id;
  const tr = BASE_TRACKS.find((x) => x.id === it.track);
  let h = `<div class="inspHead"><span class="tag" style="background:${tr.col}">${tr.name}</span><span class="muted">${it.id}</span></div>`;
  h += field("เริ่ม", `<input type="number" step="0.01" data-k="start" value="${it.start}">`);
  h += field("จบ", `<input type="number" step="0.01" data-k="end" value="${it.end}">`);
  if (it.track === "sub") {
    h += field("ข้อความ", `<textarea data-k="text">${esc(it.text)}</textarea>`);
    const sp = Object.keys(E.style.speakers || {});
    h += field("คนพูด", `<select data-k="speaker"><option value="">ค่าเริ่มต้น</option>${sp.map((s) => `<option ${s === it.speaker ? "selected" : ""}>${s}</option>`).join("")}</select>`);
  }
  if (it.track === "emoji") {
    h += field("อีโมจิ", `<div class="row"><img src="${emojiSrc(it.emoji)}" width="30"><input data-k="emoji" value="${esc(it.emoji)}" style="width:70px"></div>`);
    h += field("แอนิเมชัน", `<select data-k="anim">${["pop", "float", "shake"].map((a) => `<option ${a === (it.anim || "pop") ? "selected" : ""}>${a}</option>`).join("")}</select>`);
    h += field("ขนาด", slider("size", it.size ?? 0.22, 0.05, 0.8, 0.01));
    h += field("แนวนอน", slider("x", it.x, 0, 1, 0.01)) + field("แนวตั้ง", slider("y", it.y, 0, 1, 0.01));
  }
  if (it.track === "broll") {
    h += field("รูป", `<select data-k="src">${assets.images.map((s) => `<option ${s === it.src ? "selected" : ""}>${s}</option>`).join("")}</select>`);
    h += field("กว้าง", slider("w", it.w ?? 0.8, 0.1, 1.2, 0.01));
    h += field("แนวนอน", slider("x", it.x, 0, 1, 0.01)) + field("แนวตั้ง", slider("y", it.y, 0, 1, 0.01));
  }
  if (it.track === "gif") {
    const g = GIFS.lib[it.gif];
    h += `<p class="muted" style="margin:0 0 8px">${{ overlay: "แปะทับบนคลิป", cut: "ตัดเข้าเต็มจอ — คลิปหยุดรอช่วงนี้", freeze: "หยุดภาพ + ข้อความ — คลิปหยุดรอช่วงนี้" }[it.mode]}</p>`;
    if (g) h += `<div class="gifCur"><video src="${gifSrc(it.gif)}" autoplay loop muted playsinline></video><span>${esc(g.desc)}<br><small>${esc(GIFS.cats[g.cat] || g.cat)}</small></span></div>`;
    if (it.mode !== "freeze") h += `<div class="row" style="gap:6px;margin:6px 0 10px"><button id="gifPrev">ตัวก่อน</button><button id="gifNext">เปลี่ยนตัว (หมวดเดียวกัน)</button></div>`;
    h += field("ข้อความ", `<input data-k="caption" value="${esc(it.caption || "")}" placeholder="คำมุกสั้นๆ (เว้นว่างได้)">`);
    if (it.mode === "overlay") {
      h += field("กว้าง", slider("w", it.w ?? 0.55, 0.2, 1, 0.01)) + field("เอียง", slider("rot", it.rot ?? -3, -15, 15, 1));
      h += field("แนวนอน", slider("x", it.x ?? 0.5, 0, 1, 0.01)) + field("แนวตั้ง", slider("y", it.y ?? 0.3, 0, 1, 0.01));
    }
  }
  if (it.track === "sfx") {
    h += field("เสียง", `<div class="row"><select data-k="sfx">${assets.sfx.map((s) => `<option ${s === it.sfx ? "selected" : ""}>${s}</option>`).join("")}</select><button id="btnHear">ฟัง</button></div>`);
    h += field("ความดัง", slider("vol", it.vol ?? 0.8, 0, 1.5, 0.05));
  }
  if (it.track === "fx") {
    h += field("ชนิด", `<select data-k="fx">${assets.fx.map((s) => `<option value="${s}" ${s === it.fx ? "selected" : ""}>${FX_INFO[s][0]}</option>`).join("")}</select>`);
    const [mn, mx, st] = FX_RANGE[it.fx];
    h += field(it.fx === "shake" ? "แรงสั่น" : it.fx === "flash" ? "ความสว่าง" : "ซูม", slider("amount", it.amount ?? assets.fx_default[it.fx], mn, mx, st));
    if (it.fx !== "flash") h += field("ซูมเข้า", `<div class="row"><span class="muted" style="flex:1">${it.fx_x != null ? "จุดที่ AI/มึงเลือก" : "กลางจอ"} — คลิกบนจอเพื่อย้าย</span>${it.fx_x != null ? '<button id="fxCenter">กลางจอ</button>' : ""}</div>`);
  }
  h += `<div class="inspActions"><button id="btnGo">ไปที่จุดนี้</button><button id="btnDup">ทำสำเนา</button><div class="spacer"></div><button class="danger" id="btnDel">ลบ</button></div>`;
  body.innerHTML = h;
  body.querySelectorAll("[data-k]").forEach((el) => {
    const k = el.dataset.k; let snap = null;
    el.addEventListener("focus", () => (snap = JSON.stringify(E)));
    el.addEventListener("pointerdown", () => (snap = JSON.stringify(E)));
    el.addEventListener(el.type === "range" ? "input" : el.tagName === "SELECT" ? "change" : "input", () => {
      if (snap) { undoStack.push(snap); redoStack = []; snap = null; }
      let v = el.value; if (el.type === "range" || el.type === "number") v = r3(+v);
      if (k === "speaker" && !v) v = null;
      if (k === "start") v = clamp(v, 0, it.end - 0.05); if (k === "end") v = clamp(v, it.start + 0.05, E.duration);
      if (k === "fx") it.amount = assets.fx_default[v];
      it[k] = v; if (el.type === "range") el.nextElementSibling.textContent = (+v).toFixed(+el.step < 0.1 ? 2 : +el.step < 1 ? 1 : 0);
      if (k === "sfx") playSfx(v, it.vol ?? 0.8);
      touch([it.id], { noInspector: el.tagName !== "SELECT" || k === "src" ? true : false });
      if (k === "fx" || k === "emoji") renderInspector();
    });
  });
  $("#btnGo").onclick = () => seek(it.start + 0.001);
  const fc = $("#fxCenter"); if (fc) fc.onclick = () => { snapshot(); delete it.fx_x; delete it.fx_y; delete it.fx_src; touch([it.id]); };
  $("#btnDup").onclick = dup; $("#btnDel").onclick = del;
  const hear = $("#btnHear"); if (hear) hear.onclick = () => playSfx(it.sfx, it.vol ?? 0.8);
  const swap = (d) => { // ตัวถัดไปในหมวดเดียวกัน (ใช้น้อยก่อน)
    const cat = GIFS.lib[it.gif]?.cat, ids = Object.keys(GIFS.lib).filter((k) => GIFS.lib[k].cat === cat);
    if (ids.length < 2) return toast("หมวดนี้มีตัวเดียว");
    snapshot(); it.gif = ids[(ids.indexOf(it.gif) + d + ids.length) % ids.length]; touch([it.id]);
  };
  const gp = $("#gifPrev"), gn = $("#gifNext"); if (gp) gp.onclick = () => swap(-1); if (gn) gn.onclick = () => swap(1);
}
function del() {
  if (sel && sel.startsWith("sc") && isEx()) return delScene(+sel.slice(2));
  const it = sel && byId(sel); if (!it) return;
  if (it.gap) return gapReq({ op: "del", id: it.gap }, "ลบช่วงตัดเข้า แล้วต่อคลิปกลับ…");
  snapshot(); E.items = E.items.filter((x) => x !== it); deleted.add(it.id); dirty.delete(it.id); sel = null; touch([]); }
async function gapReq(body, msg) { // ใส่/ลบช่องหยุดคลิป = เวลาหลังจุดนั้นเลื่อนทั้งหมด → server ทำ (ต้องสร้างคลิปใหม่)
  if (dirty.size || deleted.size) await save();
  toast(msg); sel = null;
  const r = await post("/api/gap", body).catch(() => ({ ok: false }));
  toast(r.ok ? "เสร็จ — คลิปยาว " + fmt(E.duration, false) : r.error || "ทำไม่ได้");
}
function dup() {
  const it = sel && byId(sel); if (!it) return; snapshot();
  const len = it.end - it.start, c = { ...it, id: newId(it.track), start: r3(Math.min(it.end + 0.1, E.duration - len)) }; c.end = r3(c.start + len);
  E.items.push(c); sel = c.id; touch([c.id]);
}

/* ---------- library ---------- */
const DEF = { gif: 1.8, emoji: 1.2, broll: 2.5, sfx: 0.6, fx: 0.45, sub: 1.5 };
function add(track, props) {
  snapshot();
  const t = r3(vid.currentTime), len = props._len ?? DEF[track]; delete props._len;
  const it = { id: newId(track), track, start: t, end: r3(Math.min(E.duration, t + len)), ...props };
  E.items.push(it); sel = it.id; touch([it.id]);
  if (track === "sfx") playSfx(it.sfx, it.vol);
}
function renderLib(tab) {
  document.querySelectorAll("#libTabs button").forEach((b) => b.classList.toggle("on", b.dataset.tab === tab));
  const body = $("#libBody"); const vy = E.aspect === "9x16" ? 0.3 : 0.25;
  if (tab === "emoji") {
    body.innerHTML = `<div class="emojiGrid">${assets.emoji.map((e) => `<button data-e="${e}" title="${e}"><img src="${emojiSrc(e)}" loading="lazy"></button>`).join("")}</div>
      <div class="custom"><input id="emojiCustom" placeholder="อีโมจิอื่น เช่น 🍜"><button id="emojiAdd">วาง</button></div>`;
    body.querySelectorAll("[data-e]").forEach((b) => (b.onclick = () => add("emoji", { emoji: b.dataset.e, x: 0.72, y: vy, size: 0.22, anim: "pop" })));
    $("#emojiAdd").onclick = () => { const v = $("#emojiCustom").value.trim(); if (v) add("emoji", { emoji: v, x: 0.72, y: vy, size: 0.22, anim: "pop" }); };
  } else if (tab === "sfx") {
    body.innerHTML = `<div class="list">${assets.sfx.map((s) => `<div class="it"><span class="nm" data-play="${s}" title="คลิกฟัง">${s}</span><button data-add="${s}">วาง</button></div>`).join("")}</div>`;
    body.querySelectorAll("[data-play]").forEach((b) => (b.onclick = () => playSfx(b.dataset.play, 0.8)));
    body.querySelectorAll("[data-add]").forEach((b) => (b.onclick = () => sfx(b.dataset.add).then((buf) => add("sfx", { sfx: b.dataset.add, vol: 0.8, _len: r3(buf.duration) }))));
  } else if (tab === "broll") {
    body.innerHTML = assets.images.length
      ? `<div class="imgGrid">${assets.images.map((s) => `<button data-src="${esc(s)}"><img src="${mediaSrc(s)}" loading="lazy"><span>${esc(s)}</span></button>`).join("")}</div>`
      : `<p class="muted">ยังไม่มีรูป — ใส่ไฟล์ .png/.jpg ไว้ในโฟลเดอร์ของคลิป (หรือ broll/) แล้วกด F5</p>`;
    const by = E.aspect === "9x16" ? 0.17 : 0.3;
    body.querySelectorAll("[data-src]").forEach((b) => (b.onclick = () => add("broll", { src: b.dataset.src, x: 0.5, y: by, w: E.aspect === "9x16" ? 0.86 : 0.4 })));
  } else if (tab === "fx") {
    const tr = (E.faces?.tracks || []).length, cam = E.cam || {};
    const camH = `<div class="musicCur"><b>กล้อง</b>` + (tr
      ? `<label class="chk"><input type="checkbox" id="camFollow" ${cam.mode === "follow" ? "checked" : ""}> ตามหน้าคนพูด (เจอ ${tr} คน)</label>` +
        (cam.mode === "follow" ? field("ซูมพื้นฐาน", slider("camzoom", cam.zoom ?? 1, 1, 2, 0.05)) : "")
      : `<p class="muted">ยังไม่ได้ตามหน้า (โปรเจกต์เก่า) — กดเพื่อให้หาหน้าคนในคลิป</p><button id="camScan">หาหน้าคน</button>`) + `</div>`;
    body.innerHTML = camH + `<div class="fxList">${assets.fx.map((f) => `<button data-fx="${f}"><b>${FX_INFO[f][0]}</b><small>${FX_INFO[f][1]}</small></button>`).join("")}</div>`;
    const camReq = (o) => post("/api/cam", o).then((r) => { toast(r.ok ? r.msg || "อัปเดตกล้องแล้ว" : r.error || "ทำไม่ได้"); setTimeout(() => renderLib("fx"), 700); });
    const cf = $("#camFollow"); if (cf) cf.onchange = () => camReq({ mode: cf.checked ? "follow" : "fit" });
    const cz = body.querySelector('[data-k="camzoom"]'); if (cz) cz.onchange = () => camReq({ zoom: +cz.value });
    const cs = $("#camScan"); if (cs) cs.onclick = () => { cs.disabled = true; cs.textContent = "กำลังหาหน้า…"; camReq({ scan: true }); };
    body.querySelectorAll("[data-fx]").forEach((b) => (b.onclick = () => { const f = b.dataset.fx; add("fx", { fx: f, amount: assets.fx_default[f], _len: { punch: 0.45, zoomin: 2.5, zoomout: 2.5, focus: 2.5, shake: 0.5, flash: 0.35 }[f] }); }));
  } else if (tab === "gif") {
    const cats = Object.keys(GIFS.cats).filter((c) => Object.values(GIFS.lib).some((g) => g.cat === c));
    Object.values(GIFS.lib).forEach((g) => { if (!cats.includes(g.cat)) cats.push(g.cat); });
    renderLib.gcat = cats.includes(renderLib.gcat) ? renderLib.gcat : cats[0];
    const ids = Object.keys(GIFS.lib).filter((k) => GIFS.lib[k].cat === renderLib.gcat);
    body.innerHTML = cats.length ? `<div class="chipRow">${cats.map((c) => `<button class="${c === renderLib.gcat ? "on" : ""}" data-gc="${c}">${esc(GIFS.cats[c] || c)}</button>`).join("")}</div>
      <button id="freezeAdd" style="width:100%;margin:8px 0">หยุดภาพ + ข้อความ ที่หัวเล่น</button>
      <div class="gifGrid">${ids.map((k) => `<div class="gt"><video src="${gifSrc(k)}" muted loop playsinline preload="metadata" title="${esc(GIFS.lib[k].desc)}"></video>
        <div class="ga"><button data-ov="${k}" title="แปะทับบนคลิป">แปะ</button><button data-cut="${k}" title="คลิปหยุด ตัดไป GIF เต็มจอ">ตัดเข้า</button><button class="ib" data-ban="${k}" title="ลบออกจากคลัง (ไม่ใช้อีก)">×</button></div></div>`).join("")}</div>`
      : `<p class="muted">คลัง GIF ว่าง — รัน gif_lib.py build</p>`;
    body.querySelectorAll("[data-gc]").forEach((b) => (b.onclick = () => { renderLib.gcat = b.dataset.gc; renderLib("gif"); }));
    body.querySelectorAll(".gt video").forEach((v) => { v.onmouseenter = () => v.play(); v.onmouseleave = () => v.pause(); });
    body.querySelectorAll("[data-ov]").forEach((b) => (b.onclick = () => { const g = GIFS.lib[b.dataset.ov];
      add("gif", { mode: "overlay", gif: b.dataset.ov, x: 0.5, y: 0.3, w: E.aspect === "9x16" ? 0.55 : 0.32, rot: -3, caption: "", _len: Math.min(2.5, Math.max(1.2, g.dur)) }); }));
    body.querySelectorAll("[data-cut]").forEach((b) => (b.onclick = () => { const g = GIFS.lib[b.dataset.cut];
      gapReq({ op: "add", t: vid.currentTime, dur: Math.min(2, Math.max(0.9, g.dur)), mode: "cut", gif: b.dataset.cut }, "เว้นช่องตัดเข้า GIF…"); }));
    body.querySelectorAll("[data-ban]").forEach((b) => (b.onclick = async () => {
      if (!confirm("ลบ GIF ตัวนี้ออกจากคลัง? (ไม่ถูกเลือกอีก)")) return;
      await post("/api/gif/ban", { gif: b.dataset.ban }); await loadGifs(); renderLib("gif"); }));
    const fz = $("#freezeAdd"); if (fz) fz.onclick = () => { const c = prompt("ข้อความตอนหยุดภาพ", "เดี๋ยวนะ..."); if (c == null) return;
      gapReq({ op: "add", t: vid.currentTime, dur: 1.3, mode: "freeze", caption: c }, "เว้นช่องหยุดภาพ…"); };
  } else if (tab === "music") {
    renderMusicTab(body);
  } else if (tab === "sub") {
    body.innerHTML = `<p class="muted">เพิ่มซับใหม่ที่หัวเล่น แล้วพิมพ์ข้อความในช่องแก้ค่า</p><button id="subAdd" class="primary">เพิ่มซับ</button>`;
    $("#subAdd").onclick = () => add("sub", { text: "ข้อความ", speaker: null });
  }
}
$("#libTabs").addEventListener("click", (e) => e.target.dataset.tab && renderLib(e.target.dataset.tab));

function renderMusicTab(body) {
  const cur = E.music, mx = E.mix?.sfx ?? assets.mix_default.sfx;
  let h = field("SFX รวม", slider("mixsfx", mx, 0, 1.5, 0.05));
  if (cur) {
    const m = assets.music.find((x) => x.id === cur.src) || { title: cur.src, credit: "" };
    h += `<div class="musicCur"><b>${esc(m.title)}</b>` +
      field("ความดัง", slider("mvol", cur.vol ?? assets.music_default.vol, 0, 1, 0.01)) +
      field("เริ่มที่วิ", `<input type="number" step="1" min="0" data-m="offset" value="${cur.offset || 0}">`) +
      `<label class="chk"><input type="checkbox" data-m="duck" ${cur.duck !== false ? "checked" : ""}> เบาลงเองตอนพูด</label>` +
      (m.credit ? `<textarea readonly class="credit">${esc(m.credit)}</textarea><button id="copyCredit">ก๊อปเครดิต (ต้องใส่ใต้คลิป)</button> ` : "") +
      `<button id="musicOff">ไม่ใช้เพลง</button></div>`;
  }
  h += `<div class="list" style="margin-top:10px">` + assets.music.map((m) =>
    `<div class="it${cur && cur.src === m.id ? " on" : ""}"><span class="nm" data-hear="${m.id}" title="คลิกฟังตัวอย่าง"><b>${esc(m.title)}</b><small>${esc(m.mood)}</small></span><button data-use="${m.id}">ใช้</button></div>`).join("") + `</div>`;
  if (!assets.music.length) h += `<p class="muted">ยังไม่มีเพลง — รัน scripts/fetch_music.py หรือวาง .mp3 ใน assets/music/</p>`;
  body.innerHTML = h;
  const setMix = (fn) => { snapshot(); fn(); touch([], { noInspector: true }); levels(); };
  const sl = (k, fn) => { const el = body.querySelector(`[data-k="${k}"]`); if (el) el.addEventListener("input", () => { setMix(() => fn(+el.value)); el.nextElementSibling.textContent = (+el.value).toFixed(2); }); };
  sl("mixsfx", (v) => (E.mix = { ...(E.mix || {}), sfx: v }));
  sl("mvol", (v) => (E.music.vol = v));
  body.querySelectorAll("[data-m]").forEach((el) => el.addEventListener("change", () => {
    setMix(() => (E.music[el.dataset.m] = el.type === "checkbox" ? el.checked : +el.value)); syncMusic(true);
  }));
  body.querySelectorAll("[data-use]").forEach((b) => (b.onclick = () => {
    stopHear();
    setMix(() => (E.music = { src: b.dataset.use, vol: E.music?.vol ?? assets.music_default.vol, duck: E.music?.duck ?? true, offset: 0 }));
    syncMusic(true); renderLib("music");
  }));
  body.querySelectorAll("[data-hear]").forEach((b) => (b.onclick = () => hear(b.dataset.hear)));
  const off = $("#musicOff"); if (off) off.onclick = () => { setMix(() => (E.music = null)); syncMusic(); renderLib("music"); };
  const cp = $("#copyCredit"); if (cp) cp.onclick = () => { navigator.clipboard.writeText(body.querySelector(".credit").value); toast("ก๊อปเครดิตแล้ว"); };
}
const hearEl = new Audio(); let hearing = null;
function hear(id) {
  if (hearing === id) return stopHear();
  const m = assets.music.find((x) => x.id === id);
  hearEl.src = "/music/" + encodeURIComponent(m.file); hearEl.volume = 0.6; hearEl.play(); hearing = id;
  toast("ฟังตัวอย่าง: " + m.title + " (คลิกอีกทีเพื่อหยุด)");
}
function stopHear() { hearEl.pause(); hearing = null; }

/* ---------- Motion Explainer: ตัวเล่น + แก้ฉาก ---------- */
let player = null, lastSeekF = -1, pixLib = null, lastFix = 0;
const CAMS = { full: "เต็มจอ", polaroid: "กรอบรูปครึ่งล่าง", corner: "รูปเล็กมุมขวาบน", circle: "วงกลมซ้ายบน", none: "ซ่อนคนพูด" };
const BGS = { grid: "กระดาษตาราง", paper: "กระดาษ", lined: "กระดาษเส้น", kraft: "กระดาษคราฟต์", navy: "กรมท่า", mint: "เขียวมิ้นต์", pink: "ชมพู", yellow: "เหลือง" };
const TCOL = { "#ef4444": "แดง", "#facc15": "เหลือง", "#10b981": "เขียว", "#3b82f6": "น้ำเงิน" };
const TRANS = { slide: "สไลด์", slap: "ตบ", drop: "หล่น", punch: "กระแทก", cut: "ตัดตรง" };
// ช่องวางของ = explainer.py SLOTS (แก้คู่กัน)
const SLOTS = {
  full: [[[0.8, 0.62, 0.22]], [[0.2, 0.6, 0.2], [0.8, 0.64, 0.22]], [[0.18, 0.58, 0.18], [0.82, 0.6, 0.2], [0.8, 0.3, 0.16]]],
  polaroid: [[[0.5, 0.3, 0.4]], [[0.3, 0.3, 0.34], [0.72, 0.28, 0.3]], [[0.24, 0.31, 0.3], [0.58, 0.27, 0.26], [0.84, 0.37, 0.17]]],
  corner: [[[0.36, 0.55, 0.5]], [[0.3, 0.52, 0.36], [0.72, 0.64, 0.32]], [[0.26, 0.48, 0.32], [0.7, 0.6, 0.3], [0.32, 0.72, 0.22]]],
  circle: [[[0.55, 0.62, 0.42]], [[0.78, 0.3, 0.24], [0.5, 0.63, 0.4]], [[0.78, 0.28, 0.22], [0.3, 0.63, 0.32], [0.72, 0.64, 0.3]]],
  none: [[[0.5, 0.46, 0.56]], [[0.3, 0.43, 0.4], [0.7, 0.53, 0.4]], [[0.28, 0.37, 0.34], [0.72, 0.43, 0.32], [0.5, 0.66, 0.34]]],
};
function layout(sc) { const sl = SLOTS[sc.cam] || SLOTS.polaroid; (sc.items || []).forEach((it, i) => { const [x, y, s] = sl[sc.items.length - 1][i]; Object.assign(it, { x, y, size: s }); }); }
function sceneProxies() {
  return (E.scenes || []).map((s, i) => ({ id: "sc" + i, idx: i, track: "scene", start: s.start, end: (E.scenes[i + 1] ? E.scenes[i + 1].start : E.duration), title: s.title }));
}
const pixUrl = (src) => (src.startsWith("pixel/") ? "/pixel/" + src.slice(6) : mediaSrc(src));
function explainerProps() { // = explainer.py props_for(url=True)
  const [sw, sh] = E.source_wh || [1080, 1920];
  return {
    video: mediaSrc(previewVideo()), srcW: sw, srcH: sh, face: E.face || null, faces: E.faces || null,
    fontName: ["Kanit", "Mali"].includes(E.style.font) ? E.style.font : "Kanit", total: Math.round(E.duration * 30),
    subs: E.items.filter((x) => x.track === "sub").map((x) => ({ start: x.start, end: x.end, text: x.text, speaker: x.speaker })),
    scenes: (E.scenes || []).map((sc) => ({ ...sc, items: (sc.items || []).map((it) => ({ ...it, src: pixUrl(it.src) })) })),
  };
}
function syncPlayerProps() { if (player) player.setProps(explainerProps()); }
function setupExplainer() {
  cv.style.display = "none"; $("#aspectSeg").style.display = "none"; $("#inspector").style.maxHeight = "72%"; $("#chkSafe").parentElement.style.display = "none";
  ["gif", "broll", "fx"].forEach((t) => (document.querySelector(`#libTabs [data-tab="${t}"]`).style.display = "none"));
  const box = document.createElement("div"); box.id = "playerBox";
  box.style.cssText = "height:100%;aspect-ratio:9/16;max-width:100%;background:#000;box-shadow:0 0 0 1px var(--line)";
  $("#canvasWrap").appendChild(box);
  const sc = document.createElement("script"); sc.src = "/player.js";
  sc.onload = () => { player = window.ClipcutPlayer.mount(box, explainerProps(), { fps: 30 }); };
  document.body.appendChild(sc);
  fetch("/api/pixel").then((r) => r.json()).then((j) => (pixLib = j));
}
function sceneEdit(fn, relayout) { const i = +sel.slice(2); snapshot(); fn(E.scenes[i]); if (relayout) layout(E.scenes[i]); touch(["__scenes"]); }
function renderSceneInspector(i) {
  const body = $("#inspBody"), sc = E.scenes[i]; if (!sc) { sel = null; return renderInspector(); }
  if (body.contains(document.activeElement) && document.activeElement.dataset.s && body.dataset.id === "sc" + i) return; // กำลังพิมพ์
  body.dataset.id = "sc" + i;
  const opt = (m, v) => Object.entries(m).map(([k, n]) => `<option value="${k}" ${k === v ? "selected" : ""}>${n}</option>`).join("");
  let h = `<div class="inspHead"><span class="tag" style="background:#facc15">ฉาก ${i + 1}/${E.scenes.length}</span><span class="muted">${fmt(sc.start)}</span></div>`;
  h += field("หัวข้อ", `<input data-s="title" value="${esc(sc.title || "")}">`);
  h += field("สีหัวข้อ", `<select data-s="title_color">${opt(TCOL, sc.title_color)}</select>`);
  h += field("กล้อง", `<select data-s="cam">${opt(CAMS, sc.cam)}</select>`);
  h += field("พื้น", `<select data-s="bg">${opt(BGS, sc.bg)}</select>`);
  h += field("เปลี่ยนฉาก", `<select data-s="transition">${opt(TRANS, sc.transition)}</select>`);
  const FM = { speaker: "หน้าคนที่พูด", box: "กรอบที่เลือก", wide: "ภาพกว้าง" };
  const fs = sc.focus && sc.focus.length ? sc.focus : [{ at: 0, mode: "speaker" }];
  h += `<div class="sect2"><b>กล้องมองที่</b> <span class="muted">(เปลี่ยนกลางฉากได้ · +วินาที)</span></div><div class="list">` + fs.map((f, k) => `<div class="it">
      <input type="number" step="0.1" min="0" data-fa="${k}" value="${f.at || 0}" style="width:58px" ${k === 0 ? "disabled" : ""}>
      <select data-fm="${k}">${opt(FM, f.mode)}</select>${f.mode === "box" ? `<button data-fb="${k}">ลากกรอบ</button>` : ""}${k > 0 ? `<button data-fr="${k}">ลบ</button>` : ""}</div>`).join("") + `</div>
    <div class="row" style="gap:6px;margin-top:6px"><button id="addFocus">+ เปลี่ยนจุดที่หัวเล่น</button>${(E.faces?.tracks || []).length > 1 ? '<button id="swapSpk" title="AI จับคู่ใครพูดผิด">สลับคนพูด</button>' : ""}</div>`;
  h += `<div class="sect2"><b>ภาพ</b> <span class="muted">(สูงสุด 3 · โผล่ที่ +วินาทีหลังเริ่มฉาก)</span></div><div class="list">` +
    (sc.items || []).map((it, k) => `<div class="it"><img src="${pixUrl(it.src)}" style="height:34px;image-rendering:pixelated"><span class="nm">${esc(it.src.split("/").pop().replace(/\.png$/, ""))}</span>
      <input type="number" step="0.1" min="0" data-it="${k}" value="${it.at || 0}" style="width:58px"><button data-rm="${k}">ลบ</button></div>`).join("") + `</div>`;
  if ((sc.items || []).length < 3) h += `<button id="addPix" style="margin-top:6px">+ เพิ่มภาพ</button><div id="pixPick" class="hidden2"></div>`;
  h += `<div class="sect2"><b>ป้ายคำ</b></div><div class="list">` + (sc.tags || []).map((t, k) => `<div class="it"><input data-tg="${k}" value="${esc(t.text)}" style="flex:1">
      <input type="number" step="0.1" min="0" data-ta="${k}" value="${t.at || 0}" style="width:58px"><button data-tr="${k}">ลบ</button></div>`).join("") + `</div>`;
  if ((sc.tags || []).length < 3) h += `<button id="addTag" style="margin-top:6px">+ เพิ่มป้าย</button>`;
  h += `<div class="inspActions"><button id="scGo">ไปที่ฉากนี้</button><button id="scSplit" title="แบ่งฉากที่ตำแหน่งหัวเล่น">แบ่งฉากที่หัวเล่น</button><div class="spacer"></div>${i > 0 ? '<button class="danger" id="scDel">รวมกับฉากก่อน</button>' : ""}</div>`;
  body.innerHTML = h;
  body.querySelectorAll("[data-s]").forEach((el) => el.addEventListener(el.tagName === "SELECT" ? "change" : "input", () => sceneEdit((s) => (s[el.dataset.s] = el.value), el.dataset.s === "cam")));
  body.querySelectorAll("[data-it]").forEach((el) => el.addEventListener("input", () => sceneEdit((s) => (s.items[+el.dataset.it].at = r3(+el.value)))));
  body.querySelectorAll("[data-rm]").forEach((el) => (el.onclick = () => { sceneEdit((s) => s.items.splice(+el.dataset.rm, 1), true); renderInspector(); }));
  body.querySelectorAll("[data-tg]").forEach((el) => el.addEventListener("input", () => sceneEdit((s) => (s.tags[+el.dataset.tg].text = el.value))));
  body.querySelectorAll("[data-ta]").forEach((el) => el.addEventListener("input", () => sceneEdit((s) => (s.tags[+el.dataset.ta].at = r3(+el.value)))));
  body.querySelectorAll("[data-tr]").forEach((el) => (el.onclick = () => { sceneEdit((s) => s.tags.splice(+el.dataset.tr, 1)); renderInspector(); }));
  const setF = (fn) => sceneEdit((s) => { s.focus = (s.focus && s.focus.length ? s.focus : [{ at: 0, mode: "speaker" }]).map((f) => ({ ...f })); fn(s.focus); s.focus.sort((a, b) => a.at - b.at); });
  body.querySelectorAll("[data-fa]").forEach((el) => el.addEventListener("change", () => setF((f) => (f[+el.dataset.fa].at = r3(+el.value)))));
  body.querySelectorAll("[data-fm]").forEach((el) => el.addEventListener("change", () => {
    const k = +el.dataset.fm;
    if (el.value === "box") return pickBox(sc.start + (fs[k].at || 0) + 0.3, fs[k].box, (box) => { setF((f) => Object.assign(f[k], { mode: "box", box })); renderInspector(); }, () => renderInspector());
    setF((f) => { f[k].mode = el.value; delete f[k].box; }); renderInspector();
  }));
  body.querySelectorAll("[data-fb]").forEach((el) => (el.onclick = () => { const k = +el.dataset.fb; pickBox(sc.start + (fs[k].at || 0) + 0.3, fs[k].box, (box) => { setF((f) => (f[k].box = box)); renderInspector(); }); }));
  body.querySelectorAll("[data-fr]").forEach((el) => (el.onclick = () => { setF((f) => f.splice(+el.dataset.fr, 1)); renderInspector(); }));
  $("#addFocus").onclick = () => { const a = r3(Math.max(0.1, vid.currentTime - sc.start)); setF((f) => f.push({ at: a, mode: "wide" })); renderInspector(); };
  const sw = $("#swapSpk"); if (sw) sw.onclick = () => { // สลับป้ายคนพูดของคนที่หาหน้าเจอ (ทั้งคลิป)
    snapshot(); const tr = E.faces.tracks, sp = tr.map((x) => x.speaker); tr.forEach((x, i) => (x.speaker = sp[(i + 1) % sp.length])); touch(["__scenes"]); toast("สลับคนพูดแล้ว");
  };
  const at = $("#addTag"); if (at) at.onclick = () => { sceneEdit((s) => (s.tags = [...(s.tags || []), { text: "คำ", at: r3(Math.max(0, vid.currentTime - s.start)) }])); renderInspector(); };
  const ap = $("#addPix"); if (ap) ap.onclick = () => showPicker(i);
  $("#scGo").onclick = () => seek(sc.start + 0.01);
  $("#scSplit").onclick = () => splitScene();
  const sd = $("#scDel"); if (sd) sd.onclick = () => delScene(i);
}
function showPicker(i) {
  const box = $("#pixPick"); if (!box || !pixLib) return;
  const all = [...pixLib.icons.map((x) => ({ src: `pixel/icon_${x.name}.png`, name: x.name, desc: x.desc })), ...pixLib.sprites.map((n) => ({ src: `pixel/${n}.png`, name: n, desc: "" }))];
  box.className = "";
  box.innerHTML = `<input id="pixQ" placeholder="ค้นหา เช่น laptop, think" style="width:100%;margin:6px 0">
    <div class="emojiGrid small" id="pixGrid"></div>
    <div class="custom"><input id="newName" placeholder="ไม่มี? ชื่ออังกฤษ เช่น cloud" style="width:40%"><input id="newDesc" placeholder="อธิบาย เช่น ก้อนเมฆ"><button id="newDraw">ให้ AI วาด</button></div>`;
  const paint = (q) => ($("#pixGrid").innerHTML = all.filter((x) => !q || (x.name + x.desc).toLowerCase().includes(q.toLowerCase()))
    .map((x) => `<button data-src="${x.src}" title="${esc(x.name + (x.desc ? " — " + x.desc : ""))}"><img src="${pixUrl(x.src)}" loading="lazy" style="image-rendering:pixelated"></button>`).join(""));
  paint("");
  $("#pixQ").oninput = (e) => paint(e.target.value);
  $("#pixGrid").onclick = (e) => { const b = e.target.closest("[data-src]"); if (!b) return;
    sceneEdit((s) => (s.items = [...(s.items || []), { src: b.dataset.src, at: r3(Math.max(0, vid.currentTime - s.start)) }]), true); renderInspector(); };
  $("#newDraw").onclick = async () => {
    const name = $("#newName").value.trim(), desc = $("#newDesc").value.trim(); if (!name) return;
    $("#newDraw").disabled = true; $("#newDraw").textContent = "กำลังวาด…";
    const r = await post("/api/pixel/new", { name, desc });
    if (!r.ok) { toast(r.error || "วาดไม่สำเร็จ"); $("#newDraw").disabled = false; $("#newDraw").textContent = "ให้ AI วาด"; return; }
    pixLib = await fetch("/api/pixel").then((x) => x.json());
    sceneEdit((s) => (s.items = [...(s.items || []), { src: r.src, at: r3(Math.max(0, vid.currentTime - s.start)) }]), true);
    toast("วาดเสร็จ: " + r.name); renderInspector();
  };
}
// ลากกรอบบนภาพต้นฉบับ (เวลา t) → [x0,y0,x1,y1] สัดส่วน 0-1
function pickBox(t, box, onOk, onCancel) {
  const ov = document.createElement("div");
  ov.style.cssText = "position:fixed;inset:0;background:rgba(0,0,0,.82);z-index:80;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px";
  ov.innerHTML = `<div style="color:#fff">ลากกรอบครอบสิ่งที่อยากให้กล้องซูมเข้า</div>
    <div style="position:relative;max-height:78vh"><video muted playsinline style="max-height:78vh;max-width:80vw;display:block"></video><canvas style="position:absolute;inset:0;width:100%;height:100%;cursor:crosshair"></canvas></div>
    <div style="display:flex;gap:8px"><button class="ghost" id="pbC">ยกเลิก</button><button class="primary" id="pbOk">ตกลง</button></div>`;
  document.body.appendChild(ov);
  const v = ov.querySelector("video"), c = ov.querySelector("canvas"), g = c.getContext("2d");
  let b = box ? [...box] : null, d0 = null;
  const paint = () => { c.width = c.clientWidth; c.height = c.clientHeight; g.clearRect(0, 0, c.width, c.height); if (!b) return;
    g.strokeStyle = "#fde047"; g.lineWidth = 3; g.setLineDash([10, 6]); g.strokeRect(b[0] * c.width, b[1] * c.height, (b[2] - b[0]) * c.width, (b[3] - b[1]) * c.height); };
  v.onloadeddata = () => { v.currentTime = Math.max(0, t); }; v.onseeked = paint; v.src = mediaSrc(previewVideo());
  const pt = (e) => { const r = c.getBoundingClientRect(); return [clamp((e.clientX - r.left) / r.width, 0, 1), clamp((e.clientY - r.top) / r.height, 0, 1)]; };
  c.onpointerdown = (e) => { d0 = pt(e); c.setPointerCapture(e.pointerId); };
  c.onpointermove = (e) => { if (!d0) return; const p = pt(e); b = [Math.min(d0[0], p[0]), Math.min(d0[1], p[1]), Math.max(d0[0], p[0]), Math.max(d0[1], p[1])].map(r3); paint(); };
  c.onpointerup = () => (d0 = null);
  const close = () => ov.remove();
  ov.querySelector("#pbC").onclick = () => { close(); onCancel && onCancel(); };
  ov.querySelector("#pbOk").onclick = () => { if (!b || b[2] - b[0] < 0.03 || b[3] - b[1] < 0.03) return toast("ลากกรอบก่อน"); close(); onOk(b); };
}
function splitScene() {
  const t = r3(vid.currentTime), sc = E.scenes; let i = 0;
  for (let k = 0; k < sc.length; k++) if (sc[k].start <= t) i = k;
  if (t - sc[i].start < 0.8 || (sc[i + 1] && sc[i + 1].start - t < 0.8)) return toast("ฉากสั้นเกิน — เลื่อนหัวเล่นออกห่างขอบฉาก");
  snapshot();
  sc.splice(i + 1, 0, { ...sc[i], start: t, title: "", items: [], tags: [], transition: "slap", cam: sc[i].cam === "polaroid" ? "corner" : "polaroid" });
  sel = "sc" + (i + 1); touch(["__scenes"]);
}
function delScene(i) { if (i <= 0) return; snapshot(); E.scenes.splice(i, 1); sel = "sc" + (i - 1); touch(["__scenes"]); }
const post = (u, b) => fetch(u, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b || {}) }).then((r) => r.json());

/* ---------- render ---------- */
async function startRender(preview) {
  if (dirty.size || deleted.size) await save();
  $("#log").textContent = ""; $("#drawer").classList.add("on"); $("#drawerTitle").textContent = preview ? "เรนเดอร์ทดสอบ" : "Render";
  const r = await fetch("/api/render", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ preview }) }).then((x) => x.json());
  if (!r.ok) logLine(r.error);
}
function logLine(s) { const l = $("#log"); l.append(s + "\n"); l.scrollTop = l.scrollHeight; }
function onRender(d) {
  $("#drawer").classList.add("on");
  if (d.line) logLine(d.line);
  const busy = d.state === "running"; $("#btnRender").disabled = busy; $("#btnPreviewRender").disabled = busy;
  if (d.state === "done") {
    logLine("\nเสร็จแล้ว"); if (d.output) { const a = document.createElement("a"); a.textContent = "เปิดโฟลเดอร์ → " + d.output; a.onclick = () => fetch("/api/reveal", { method: "POST", body: JSON.stringify({ path: d.output }) }); $("#log").append(a); }
    toast("เรนเดอร์เสร็จ");
  } else if (d.state === "error") logLine(`\nพัง (code ${d.code}) — ดู log ด้านบน`);
}
$("#btnRender").onclick = () => startRender(false);
$("#btnPreviewRender").onclick = () => startRender(true);
$("#btnCancelRender").onclick = () => fetch("/api/render/cancel", { method: "POST", body: "{}" });
$("#btnCloseDrawer").onclick = () => $("#drawer").classList.remove("on");

/* ---------- misc controls ---------- */
$("#btnPlay").onclick = togglePlay;
$("#btnStart").onclick = () => seek(0);
$("#btnPrevF").onclick = () => seek(Math.max(0, vid.currentTime - 1 / 30));
$("#btnNextF").onclick = () => seek(Math.min(E.duration, vid.currentTime + 1 / 30));
$("#btnUndo").onclick = undo; $("#btnRedo").onclick = redo;
$("#chkSafe").onchange = drawFrame;
$("#aspectSeg").addEventListener("click", (e) => { const a = e.target.dataset.aspect; if (!a || a === E.aspect) return; snapshot(); E.aspect = a; applyAspect(); renderLib("gif"); touch([]); });
window.addEventListener("keydown", (ev) => {
  const typing = /INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName) && document.activeElement.type !== "range" && document.activeElement.type !== "checkbox";
  if (ev.ctrlKey && ev.key.toLowerCase() === "z" && !typing) { ev.preventDefault(); ev.shiftKey ? redo() : undo(); return; }
  if (ev.ctrlKey && ev.key.toLowerCase() === "y" && !typing) { ev.preventDefault(); redo(); return; }
  if (ev.ctrlKey && ev.key.toLowerCase() === "s") { ev.preventDefault(); save(); return; }
  if (typing) return;
  if (ev.code === "Space") { ev.preventDefault(); document.activeElement.blur(); togglePlay(); }
  else if (ev.key === "Delete" || ev.key === "Backspace") del();
  else if (ev.ctrlKey && ev.key.toLowerCase() === "d") { ev.preventDefault(); dup(); }
  else if (ev.key === "ArrowLeft") seek(vid.currentTime - (ev.shiftKey ? 1 : 1 / 30));
  else if (ev.key === "ArrowRight") seek(vid.currentTime + (ev.shiftKey ? 1 : 1 / 30));
  else if (ev.key === "Home") seek(0);
  else if (ev.key === "End") seek(E.duration);
  else if (ev.key === "Escape") select(null);
});
window.addEventListener("beforeunload", (e) => { if (dirty.size || deleted.size) { save(); e.preventDefault(); } });

load().then(() => requestAnimationFrame(tick));
