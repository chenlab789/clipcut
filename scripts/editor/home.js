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
let opts = { ...PRESETS.full, mode: "fx", vibe: "tech", aspect: "9x16", density: 2 };
try { opts = { ...opts, ...JSON.parse(localStorage.getItem("clipcut.opts") || "{}") }; } catch (e) { /* ไม่มีก็ใช้ค่าเริ่มต้น */ }
if (opts.cam === undefined) opts.cam = 1;
if (opts.gif === undefined) opts.gif = 1;
opts.emoji = 0; // เลิกใช้อีโมจิแล้ว (เฉินสั่งเอาออก)
let staged = null;
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
  const on = KEYS.filter((k) => opts[k]);
  const names = { cut: "ตัด dead air", subs: "ซับ", sfx: "เสียง", gif: "GIF", broll: "ภาพพิกเซล", fx: "ซูมอัจฉริยะ", cam: "กล้องตามหน้า", music: "เพลง" };
  $("#sum").innerHTML = [
    ["แบบ", ex ? "Motion Explainer" : "แปะเอฟเฟกต์"],
    ["ใส่", ex ? "ฉาก · ซับ · เสียง · เพลง" : on.map((k) => names[k]).join(" · ") || "-"],
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

function stage(path) {
  staged = path; $("#fname").textContent = path.split(/[\\/]/).pop(); $("#fname").title = path;
  show("vOpts"); paintOpts();
}
$("#changeFile").onclick = () => { staged = null; post("/api/unstage"); show("vDrop"); };
$("#go").onclick = async () => {
  const ex = opts.mode === "explainer";
  if (!ex && !KEYS.some((k) => opts[k])) return alert("เลือกอย่างน้อย 1 อย่าง");
  const send = ex ? { ...opts, subs: 1, sfx: 0, emoji: 0, gif: 0, broll: 0, fx: 0, cam: 0, aspect: "9x16" } : opts;
  const r = await post("/api/job", { path: staged, opts: send });
  if (!r.ok) alert(r.error);
};

/* ---------- ลากวาง / เลือกไฟล์ → อัปโหลดเข้าโฟลเดอร์โปรเจกต์ ---------- */
const drop = $("#drop");
drop.onclick = () => $("#pick").click();
$("#pick").onchange = (e) => e.target.files[0] && upload(e.target.files[0]);
["dragenter", "dragover"].forEach((t) => document.addEventListener(t, (e) => { e.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach((t) => document.addEventListener(t, (e) => { e.preventDefault(); if (t === "drop" || e.target === document.documentElement) drop.classList.remove("over"); }));
document.addEventListener("drop", (e) => { const f = e.dataTransfer.files[0]; if (f) upload(f); });
function upload(f) {
  if (!/\.(mp4|mov|mkv|m4v|webm|avi)$/i.test(f.name)) return alert("ไม่ใช่ไฟล์วิดีโอ");
  show("vDrop");
  const x = new XMLHttpRequest(); x.open("POST", "/api/upload"); x.setRequestHeader("X-Filename", encodeURIComponent(f.name));
  x.upload.onprogress = (e) => ($("#upStat").textContent = `กำลังนำเข้า ${Math.round(100 * e.loaded / e.total)}% (${(e.total / 1048576).toFixed(0)} MB)`);
  x.onload = () => { const r = JSON.parse(x.responseText); r.ok ? stage(r.path) : alert(r.error); };
  x.onerror = () => alert("นำเข้าไม่ได้");
  x.send(f);
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
