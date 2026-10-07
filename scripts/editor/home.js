/* ClipCut หน้าแรก — ลากวาง → เลือกแบบ → autopilot → editor */
"use strict";
const $ = (s) => document.querySelector(s);
const STEPS_FX = ["ถอดเสียง", "AI ดูคลิป แก้คำเพี้ยน เลือกสไตล์ซับ", "ตัด dead air", "AI วางเอฟเฟกต์ตามบท",
  "วาดไอคอน + ภาพประกอบ + กล้อง / ซูมอัจฉริยะ"];
const STEPS_EX = ["ถอดเสียง", "AI ดูคลิป แก้คำเพี้ยน เลือกสไตล์ซับ", "ตัด dead air", "AI กำกับฉาก + วาดไอคอนที่ยังไม่มี", "AI ดูภาพหาจุดที่ควรซูม"];
const KEYS = ["cut", "subs", "sfx", "gif", "broll", "fx", "cam", "music"];
const PRESETS = {
  full: { cut: 1, subs: 1, sfx: 1, emoji: 0, gif: 1, broll: 1, fx: 1, cam: 1, music: 1 },
  subs: { cut: 1, subs: 1, sfx: 0, emoji: 0, gif: 0, broll: 0, fx: 0, cam: 0, music: 0 },
  cut: { cut: 1, subs: 0, sfx: 0, emoji: 0, gif: 0, broll: 0, fx: 0, cam: 0, music: 0 },
};
const VIBE = { tech: "สอน / เทค", funny: "ฮา", vlog: "vlog / แกะกล่อง", hype: "มันส์" };
const DENS = { 1: "น้อย", 2: "พอดี", 3: "แน่นสาย TikTok" };
let opts = { ...PRESETS.full, mode: "fx", vibe: "tech", aspect: "9x16", density: 2, kind: "story", order: "ai" };
try { opts = { ...opts, ...JSON.parse(localStorage.getItem("clipcut.opts") || "{}") }; } catch (e) { /* ไม่มีก็ใช้ค่าเริ่มต้น */ }
if (opts.cam === undefined) opts.cam = 1;
if (opts.gif === undefined) opts.gif = 1;
opts.emoji = 0; // เลิกใช้อีโมจิแล้ว (เฉินสั่งเอาออก)
let staged = null;            // คลิปแรก (ใช้เช็คว่ามีคลิปรอทำไหม)
let clips = [];               // [{path, name, dur, ctime, vertical}] — หลายคลิป = รวมเป็นคลิปเดียว (multiclip.py)
// มือถือ (เข้าผ่าน tailscale) → editor แบบย่อ /m · ดูคลิปในเครื่องตัวเอง ไม่ใช่เปิดบนคอม
const MOBILE = matchMedia("(pointer: coarse)").matches && innerWidth < 900;
const EDITOR = MOBILE ? "/m" : "/edit";

function show(v) { ["vDrop", "vOpts", "vJob"].forEach((id) => $("#" + id).classList.toggle("hidden", id !== v)); }
function esc(s) { return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }
const post = (u, b) => fetch(u, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b || {}) }).then((r) => r.json());

/* ---------- ตัวเลือก ---------- */
function paintOpts() {
  const ex = opts.mode === "explainer";
  document.querySelectorAll("#toggles button").forEach((b) => b.classList.toggle("on", !!opts[b.dataset.k]));
  document.querySelectorAll("[data-g]").forEach((g) => g.querySelectorAll("[data-v]").forEach((b) => b.classList.toggle("on", String(opts[g.dataset.g]) === b.dataset.v)));
  // explainer = จัดฉากเอง (ไม่ใช้อีโมจิ/ภาพแปะ/ซูม) · แนวตั้งเท่านั้น · ซับเต็มเสมอ
  document.querySelectorAll(".fxOnly").forEach((el) => el.classList.toggle("hidden", ex));
  if ($("#orderRow")) $("#orderRow").classList.toggle("hidden", clips.length < 2 || opts.kind !== "funny");
  const on = KEYS.filter((k) => opts[k]);
  const names = { cut: "ตัด dead air", subs: "ซับ", sfx: "เสียง", gif: "GIF", broll: "ภาพพิกเซล", fx: "ซูมอัจฉริยะ", cam: "กล้องตามหน้า", music: "เพลง" };
  $("#sum").innerHTML = [
    ["แบบ", ex ? "Motion Explainer" : "แปะเอฟเฟกต์"],
    ["ใส่", ex ? "ฉาก · ซับ · เสียง · เพลง" : on.map((k) => names[k]).join(" · ") || "-"],
    ...(clips.length > 1 ? [["คลิป", `${clips.length} คลิป · ${opts.kind === "funny" ? "รวมฉากฮา (" + (opts.order === "random" ? "สุ่ม" : "AI จัดลำดับ") + ")" : "เล่าเรื่อง ตามลำดับที่เรียง"}`]] : []),
    ["อารมณ์", VIBE[opts.vibe]], ["ความแน่น", DENS[opts.density]], ["ขนาด", ex ? "9:16" : opts.aspect.replace("x", ":")],
  ].map(([a, b]) => `<li><span>${a}</span><span>${esc(b)}</span></li>`).join("");
  try { localStorage.setItem("clipcut.opts", JSON.stringify(opts)); } catch (e) { /* โหมดส่วนตัว */ }
}
$("#toggles").onclick = (e) => { const b = e.target.closest("[data-k]"); if (b) { opts[b.dataset.k] = opts[b.dataset.k] ? 0 : 1; paintOpts(); } };
document.querySelectorAll("[data-p]").forEach((a) => (a.onclick = () => { Object.assign(opts, PRESETS[a.dataset.p]); paintOpts(); }));
document.querySelectorAll("[data-g]").forEach((g) => (g.onclick = (e) => {
  const b = e.target.closest("[data-v]"); if (!b) return;
  opts[g.dataset.g] = g.dataset.g === "density" ? +b.dataset.v : b.dataset.v; paintOpts();
}));

function stage(path, add) {
  if (!add) clips = [];
  if (!clips.some((c) => c.path === path)) clips.push({ path, name: path.split(/[\\/]/).pop(), dur: 0 });
  staged = clips[0].path;
  show("vOpts"); paintClips(); paintOpts();
  fetch("/api/clipinfo?" + clips.map((c) => "path=" + encodeURIComponent(c.path)).join("&")).then((r) => r.json()).then((info) => {
    for (const i of info) Object.assign(clips.find((c) => c.path.toLowerCase() === i.path.toLowerCase()) || {}, i);
    paintClips(); paintOpts();
  }).catch(() => {});
}
const mmssC = (d) => `${Math.floor(d / 60)}:${String(Math.round(d % 60)).padStart(2, "0")}`;
function paintClips() {
  const multi = clips.length > 1;
  $("#fname").textContent = multi ? `${clips.length} คลิป · รวม ${mmssC(clips.reduce((a, c) => a + (c.dur || 0), 0))}` : clips[0]?.name || "";
  document.querySelectorAll(".multiOnly").forEach((el) => el.classList.toggle("hidden", !multi));
  $("#orderRow").classList.toggle("hidden", !multi || opts.kind !== "funny");
  $("#clipList").innerHTML = clips.map((c, i) => `<div class="cl" draggable="true" data-i="${i}">
      <span class="grip" title="ลากเพื่อเรียง">${i + 1}</span><img src="/api/clipthumb?path=${encodeURIComponent(c.path)}" alt="">
      <div class="ci"><b title="${esc(c.path)}">${esc(c.name)}</b><small>${c.dur ? mmssC(c.dur) : "…"}${c.ctime ? " · ถ่าย " + new Date(c.ctime).toLocaleString("th-TH", { dateStyle: "short", timeStyle: "short" }) : ""}</small></div>
      <button class="ib" data-up="${i}" title="ขึ้น">▲</button><button class="ib" data-dn="${i}" title="ลง">▼</button><button class="ib" data-rm="${i}" title="เอาออก">×</button></div>`).join("");
}
function moveClip(i, j) { if (j < 0 || j >= clips.length) return; const [c] = clips.splice(i, 1); clips.splice(j, 0, c); staged = clips[0].path; paintClips(); }
$("#clipList").onclick = (e) => {
  const b = e.target.closest("button"); if (!b) return;
  if (b.dataset.up) moveClip(+b.dataset.up, +b.dataset.up - 1);
  if (b.dataset.dn) moveClip(+b.dataset.dn, +b.dataset.dn + 1);
  if (b.dataset.rm) { clips.splice(+b.dataset.rm, 1); if (!clips.length) return $("#changeFile").onclick(); staged = clips[0].path; paintClips(); paintOpts(); }
};
let dragI = null; // ลากเรียงในคอม (มือถือใช้ปุ่ม ▲▼)
$("#clipList").addEventListener("dragstart", (e) => { dragI = +e.target.closest(".cl").dataset.i; e.dataTransfer.effectAllowed = "move"; e.stopPropagation(); });
$("#clipList").addEventListener("dragover", (e) => { if (dragI != null) { e.preventDefault(); e.stopPropagation(); } });
$("#clipList").addEventListener("drop", (e) => {
  if (dragI == null) return; e.preventDefault(); e.stopPropagation();
  const t = e.target.closest(".cl"); if (t) moveClip(dragI, +t.dataset.i); dragI = null; drop.classList.remove("over");
});
$("#sortTime").onclick = () => { clips.sort((a, b) => (a.ctime || a.name).localeCompare(b.ctime || b.name)); staged = clips[0].path; paintClips(); };
$("#addClip").onclick = () => { adding = true; $("#pick").click(); };
let adding = false;
$("#changeFile").onclick = () => { staged = null; clips = []; post("/api/unstage"); show("vDrop"); };
$("#go").onclick = async () => {
  const ex = opts.mode === "explainer";
  if (!ex && !KEYS.some((k) => opts[k])) return alert("เลือกอย่างน้อย 1 อย่าง");
  const send = ex ? { ...opts, subs: 1, sfx: 0, emoji: 0, gif: 0, broll: 0, fx: 0, cam: 0, aspect: "9x16" } : opts;
  if (clips.length > 1 && opts.kind !== "funny") send.order = "manual";
  const r = await post("/api/job", { paths: clips.map((c) => c.path), opts: send });
  if (!r.ok) alert(r.error);
};

/* ---------- ลากวาง / เลือกไฟล์ → อัปโหลดเข้าโฟลเดอร์โปรเจกต์ ---------- */
const drop = $("#drop");
drop.onclick = () => $("#pick").click();
$("#pick").onchange = (e) => { uploadAll([...e.target.files], adding); adding = false; e.target.value = ""; };
["dragenter", "dragover"].forEach((t) => document.addEventListener(t, (e) => { e.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach((t) => document.addEventListener(t, (e) => { e.preventDefault(); if (t === "drop" || e.target === document.documentElement) drop.classList.remove("over"); }));
document.addEventListener("drop", (e) => { if (e.dataTransfer.files.length) uploadAll([...e.target.files || e.dataTransfer.files], !$("#vOpts").classList.contains("hidden")); });
// หลายไฟล์ในครั้งเดียว = โฟลเดอร์กลุ่มเดียวกัน (ชื่อซ้ำ IMG_0001 คนละวันไม่ทับกัน) · อัปทีละไฟล์
async function uploadAll(files, add) {
  files = files.filter((f) => /\.(mp4|mov|mkv|m4v|webm|avi)$/i.test(f.name));
  if (!files.length) return alert("ไม่ใช่ไฟล์วิดีโอ");
  const grp = files.length > 1 || add ? "clips_" + new Date().toISOString().replace(/\D/g, "").slice(0, 14) : "";
  const back = add ? "vOpts" : null; show("vDrop");
  for (let k = 0; k < files.length; k++) {
    const path = await upload(files[k], grp, `${k + 1}/${files.length} `).catch((e) => { alert(e); return null; });
    if (path) stage(path, add || k > 0);
    if (k < files.length - 1) show("vDrop");
  }
  if (back) show(back);
}
function upload(f, grp, tag) {
  return new Promise((ok, bad) => {
    const x = new XMLHttpRequest(); x.open("POST", "/api/upload"); x.setRequestHeader("X-Filename", encodeURIComponent(f.name));
    if (grp) x.setRequestHeader("X-Group", grp);
    x.upload.onprogress = (e) => ($("#upStat").textContent = `กำลังนำเข้า ${tag || ""}${Math.round(100 * e.loaded / e.total)}% (${(e.total / 1048576).toFixed(0)} MB)`);
    x.onload = () => { const r = JSON.parse(x.responseText); r.ok ? ok(r.path) : bad(r.error); };
    x.onerror = () => bad("นำเข้าไม่ได้");
    x.send(f);
  });
}

/* ---------- ความคืบหน้า ---------- */
function paintJob(j) {
  if (!j || j.state === "idle") return;
  show("vJob");
  $("#jTitle").textContent = j.state === "done" ? "เสร็จแล้ว — กำลังเปิด editor" : j.state === "error" ? "พัง" : "กำลังทำ";
  $("#jSub").textContent = j.name || "";
  $("#jTitle").classList.toggle("err", j.state === "error");
  $("#jBar").style.width = (j.state === "done" ? 100 : j.prog || 0) + "%";
  const STEPS = /กำกับฉาก/.test((j.log || []).join(" ") + j.msg) ? STEPS_EX : STEPS_FX;
  $("#jSteps").innerHTML = STEPS.map((s, i) => {
    const n = i + 1, cls = j.state === "done" || n < j.step ? "ok" : n === j.step && j.state === "running" ? "now" : "";
    return `<li class="${cls}"><span class="dot"></span>${s}</li>`;
  }).join("");
  const log = $("#jLog"); log.textContent = (j.log || []).filter((l) => !/^\s*\d+\.\d+ speaker/.test(l)).join("\n"); log.scrollTop = log.scrollHeight;
  $("#jCancel").classList.toggle("hidden", j.state !== "running");
  $("#jBack").classList.toggle("hidden", j.state !== "error");
  if (j.state === "done") setTimeout(() => (location.href = EDITOR), 900);
}
$("#jCancel").onclick = () => post("/api/job/cancel");
$("#jBack").onclick = () => (staged ? show("vOpts") : show("vDrop"));

/* ---------- โปรเจกต์ล่าสุด ---------- */
const ICON = {
  play: '<path d="m8 5 11 7-11 7z"/>',
  dir: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  name: '<path d="M4 20h4L19 9l-4-4L4 16z"/>',
  hide: '<path d="M6 6l12 12M18 6 6 18"/>',
};
const svg = (k) => `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${ICON[k]}</svg>`;
function ago(t) {
  const s = Date.now() / 1000 - t;
  return s < 3600 ? Math.max(1, Math.round(s / 60)) + " นาทีก่อน" : s < 86400 ? Math.round(s / 3600) + " ชม.ก่อน" : new Date(t * 1000).toLocaleDateString("th-TH");
}
const mmss = (d) => `${Math.floor(d / 60)}:${String(Math.round(d % 60)).padStart(2, "0")}`;
function paintProjects(ps) {
  const el = $("#projects");
  $("#pCount").textContent = ps.length ? ps.length + " งาน" : "";
  if (!ps.length) { el.innerHTML = '<div class="empty" style="grid-column:1/-1">ยังไม่มีงาน — ลากคลิปแรกเข้ามาด้านบนได้เลย</div>'; return; }
  el.innerHTML = ps.map((p, i) => `<div class="pc">
      <div class="th" data-a="open" data-i="${i}">${p.thumb ? `<img src="/api/thumb?edit=${encodeURIComponent(p.edit)}" loading="lazy" alt="">` : ""}
        <span class="badge l">${mmss(p.duration)}</span>${p.outputs.length ? '<span class="badge r done">เรนเดอร์แล้ว</span>' : ""}</div>
      <div class="body"><div class="ttl" title="${esc(p.title)}">${esc(p.title)}</div>
        <small>${p.mode === "explainer" ? "Motion Explainer" : "แปะเอฟเฟกต์"} · ${p.aspect.replace("x", ":")} · ${ago(p.mtime)}</small>
        <div class="acts"><button class="primary" data-a="open" data-i="${i}">แก้ไข</button>
          ${p.outputs.length ? `<button class="ib" data-a="play" data-i="${i}" title="ดูคลิปที่เรนเดอร์">${svg("play")}</button>` : ""}
          <button class="ib" data-a="name" data-i="${i}" title="ตั้งชื่อ">${svg("name")}</button>
          <button class="ib" data-a="dir" data-i="${i}" title="เปิดโฟลเดอร์">${svg("dir")}</button>
          <button class="ib" data-a="forget" data-i="${i}" title="เอาออกจากรายการ (ไม่ลบไฟล์)">${svg("hide")}</button></div></div></div>`).join("");
  el.onclick = async (e) => {
    const b = e.target.closest("[data-a]"); if (!b) return;
    const a = b.dataset.a, p = ps[+b.dataset.i];
    if (a === "open") { await post("/api/open", { edit: p.edit }); location.href = EDITOR; }
    if (a === "play") { const o = p.outputs[p.outputs.length - 1]; MOBILE ? window.open("/api/video?path=" + encodeURIComponent(o)) : post("/api/play", { path: o }); }
    if (a === "dir") post("/api/reveal", { path: p.dir });
    if (a === "name") { const t = prompt("ตั้งชื่องาน", p.title); if (t != null) { await post("/api/rename", { edit: p.edit, title: t }); refresh(); } }
    if (a === "forget") { await post("/api/forget", { edit: p.edit }); refresh(); }
  };
}

let root = "";
async function refresh() {
  const h = await fetch("/api/home").then((r) => r.json());
  root = h.root; $("#root").textContent = "เก็บงานที่ " + h.root;
  $("#toEditor").style.display = h.current ? "" : "none";
  paintProjects(h.projects);
  if (h.job && h.job.state === "running") paintJob(h.job);
  else if (h.staged && !staged) stage(h.staged);
}
// สำรองให้ SSE: ผ่าน tailscale serve (มือถือ) event อาจค้างในตัวกลาง → หน้าความคืบหน้าค้างทั้งที่งานเสร็จแล้ว
setInterval(async () => {
  if ($("#vJob").classList.contains("hidden")) return;
  const h = await fetch("/api/home").then((r) => r.json()).catch(() => null);
  if (h && h.job) paintJob(h.job);
}, 3000);
$("#openRoot").onclick = () => post("/api/reveal", { path: root });
$("#toEditor").onclick = () => (location.href = EDITOR);
if (MOBILE) {
  document.body.classList.add("mobile");
  document.querySelector("#drop .big").textContent = "แตะเพื่อเลือกคลิปจากเครื่อง";
  $("#upStat").textContent = "คลิปจะถูกส่งไปทำที่คอม แล้วกลับมาดู/แก้/เรนเดอร์บนมือถือได้";
}
const es = new EventSource("/api/events");
es.addEventListener("job", (e) => paintJob(JSON.parse(e.data)));
es.addEventListener("stage", (e) => { const d = JSON.parse(e.data); if (d.path) stage(d.path); });
paintOpts(); refresh();
