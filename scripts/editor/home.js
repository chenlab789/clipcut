/* ClipCut หน้าแรก — ลากวาง → เลือกแบบ → autopilot → editor */
"use strict";
const $ = (s) => document.querySelector(s);
const STEPS_FX = ["ถอดเสียง", "AI ดูคลิป แก้คำเพี้ยน เลือกสไตล์ซับ", "ตัด dead air", "AI วางเอฟเฟกต์ตามบท",
  "วาดไอคอน + ภาพประกอบ + กล้อง / ซูมอัจฉริยะ"];
const STEPS_EX = ["ถอดเสียง", "AI ดูคลิป แก้คำเพี้ยน เลือกสไตล์ซับ", "ตัด dead air", "AI กำกับฉาก + วาดไอคอนที่ยังไม่มี", "AI ดูภาพหาจุดที่ควรซูม"];
const KEYS = ["cut", "subs", "sfx", "gif", "broll", "fx", "cam", "music", "voice"];
const PRESETS = {
  full: { cut: 1, subs: 1, sfx: 1, emoji: 0, gif: 1, broll: 1, fx: 1, cam: 1, music: 1, voice: 1 },
  subs: { cut: 1, subs: 1, sfx: 0, emoji: 0, gif: 0, broll: 0, fx: 0, cam: 0, music: 0, voice: 1 },
  cut: { cut: 1, subs: 0, sfx: 0, emoji: 0, gif: 0, broll: 0, fx: 0, cam: 0, music: 0, voice: 1 },
};
const VIBE = { tech: "สอน / เทค", funny: "ฮา", vlog: "vlog / แกะกล่อง", hype: "มันส์" };
const DENS = { 1: "น้อย", 2: "พอดี", 3: "แน่นสาย TikTok" };
let opts = { ...PRESETS.full, mode: "fx", vibe: "tech", aspect: "9x16", density: 2, kind: "story", order: "ai" };
try { opts = { ...opts, ...JSON.parse(localStorage.getItem("clipcut.opts") || "{}") }; } catch (e) { /* ไม่มีก็ใช้ค่าเริ่มต้น */ }
if (opts.cam === undefined) opts.cam = 1;
if (opts.gif === undefined) opts.gif = 1;
if (opts.voice === undefined) opts.voice = 1;
opts.emoji = 0; // เลิกใช้อีโมจิแล้ว (เฉินสั่งเอาออก)
let staged = null;            // คลิปแรก (ใช้เช็คว่ามีคลิปรอทำไหม)
let clips = [];               // [{path, name, dur, ctime, vertical}] — หลายคลิป = รวมเป็นคลิปเดียว (multiclip.py)
// มือถือ (เข้าผ่าน tailscale) → editor แบบย่อ /m · ดูคลิปในเครื่องตัวเอง ไม่ใช่เปิดบนคอม
const MOBILE = CC.MOBILE;
const EDITOR = CC.EDITOR;

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
  $("#optClip").textContent = multi ? `${clips.length} คลิป` : (lib.find((x) => x.path === clips[0]?.path)?.title || clips[0]?.name || "");
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
$("#optBack").onclick = () => { $("#changeFile").onclick(); window.scrollTo({ top: 0 }); }; // คลิปยังอยู่ในคลัง เลือกใหม่ได้
$("#go").onclick = async () => {
  const ex = opts.mode === "explainer";
  if (!ex && !KEYS.some((k) => opts[k])) return alert("เลือกอย่างน้อย 1 อย่าง");
  const send = ex ? { ...opts, subs: 1, sfx: 0, emoji: 0, gif: 0, broll: 0, fx: 0, cam: 0, aspect: "9x16" } : opts;
  if (clips.length > 1 && opts.kind !== "funny") send.order = "manual";
  const b = $("#go"); if (b.disabled) return; b.disabled = true; jobAway(null); // กันกดซ้ำ (มือถือ SSE ช้า หน้ายังไม่เปลี่ยน → กดอีกที = "กำลังทำคลิปอื่นอยู่")
  const r = await post("/api/job", { paths: clips.map((c) => c.path), opts: send }).catch(() => ({ ok: false, error: "ส่งงานไม่ได้" }));
  b.disabled = false;
  // เริ่มแล้ว / มีงานวิ่งอยู่ → ไปหน้าความคืบหน้าเลย ไม่ต้องรอ event
  const h = await fetch("/api/home").then((x) => x.json()).catch(() => null);
  if (h && h.job && h.job.state === "running") return paintJob(h.job);
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
  const cards = files.map(upCard);
  for (let k = 0; k < files.length; k++) {
    const path = await upload(files[k], grp, `${k + 1}/${files.length} `, null, cards[k]).catch((e) => { upDone(cards[k]); alert(e); return null; });
    if (path) stage(path, add || k > 0);
    if (k < files.length - 1) show("vDrop");
  }
  if (back) show(back);
}
// ระหว่างอัป: ต้องอยู่หน้านี้ (มือถือสลับแอป/ล็อกจอ = Safari หยุดส่ง ไฟล์ไม่ครบ) → กันจอดับ + เตือนก่อนออก
let uploading = 0, wake = null;
const stayHere = (e) => { e.preventDefault(); e.returnValue = ""; };
async function holdScreen(on) {
  uploading += on ? 1 : -1;
  if (uploading > 0) {
    addEventListener("beforeunload", stayHere);
    try { wake = wake || await navigator.wakeLock?.request("screen"); } catch (err) { /* เครื่องไม่รองรับ */ }
  } else {
    removeEventListener("beforeunload", stayHere);
    try { await wake?.release(); } catch (err) { /* ปล่อยแล้ว */ }
    wake = null;
  }
}
document.addEventListener("visibilitychange", async () => { // กลับมาหน้านี้ระหว่างอัป → ขอกันจอดับใหม่ (ระบบปล่อยเองตอนสลับแอป)
  if (uploading > 0 && document.visibilityState === "visible") { try { wake = await navigator.wakeLock?.request("screen"); } catch (err) { /* */ } }
});
// การ์ดคลิปที่กำลังอัป → โผล่ในคลังทันที (ภาพจากไฟล์ในเครื่อง + วงแหวน %) · อัปเสร็จ = การ์ดจริงแทนที่
let ups = [], upSeq = 0;
function upCard(f) {
  const c = { id: "up" + ++upSeq, name: f.name, size: f.size, pct: 0, url: URL.createObjectURL(f) };
  ups.push(c); paintLib(); return c;
}
function upDone(c) { ups = ups.filter((x) => x !== c); try { URL.revokeObjectURL(c.url); } catch (e) { /* */ } paintLib(); }
function upPaint(c) {
  const el = document.getElementById(c.id); if (!el) return;
  el.querySelector(".upr div").style.setProperty("--p", c.pct); el.querySelector(".upr b").textContent = c.pct + "%";
}
function upload(f, grp, tag, say, card) {
  holdScreen(true);
  card = card || upCard(f);
  return new Promise((ok, bad) => {
    const x = new XMLHttpRequest(); x.open("POST", "/api/upload"); x.setRequestHeader("X-Filename", encodeURIComponent(f.name));
    if (grp) x.setRequestHeader("X-Group", grp);
    x.upload.onprogress = (e) => {
      card.pct = Math.min(99, Math.round(100 * e.loaded / e.total)); upPaint(card);
      (say || ((m) => ($("#upStat").textContent = m)))(`กำลังอัป ${tag || ""}${card.pct}% (${(e.total / 1048576).toFixed(0)} MB)${MOBILE ? " · อย่าเพิ่งออกจากหน้านี้" : ""}`);
    };
    x.onload = () => { let r; try { r = JSON.parse(x.responseText); } catch (err) { r = { ok: false, error: "อัปไม่สำเร็จ" }; } r.ok ? ok(r.path) : bad(r.error); };
    x.onerror = () => bad("อัปไม่สำเร็จ (การเชื่อมต่อหลุด) — อัปใหม่อีกที");
    x.send(f);
  }).then((path) => { upDone(card); loadLib(); return path; }).finally(() => holdScreen(false));
}

/* ---------- ความคืบหน้า ---------- */
// "ไปทำอย่างอื่นก่อน" = จำว่างานนี้ (t0) ไม่ต้องเด้งหน้ารอ · ดูต่อได้จากแถบล่างจอ
const jobAway = (t0) => { try { t0 == null ? sessionStorage.removeItem("cc.away") : sessionStorage.setItem("cc.away", String(t0)); } catch (e) { /* */ } };
const isAway = (j) => { try { return sessionStorage.getItem("cc.away") === String(j.t0); } catch (e) { return false; } };
let lastJob = null, autoOpen = null;
CC.pill.hideWhen(() => !$("#vJob").classList.contains("hidden"));
function paintJob(j) {
  if (!j || j.state === "idle") return;
  lastJob = j; CC.pill.update(j);
  if ($("#vJob").classList.contains("hidden")) {
    if (j.state !== "running" || isAway(j)) return CC.pill.repaint();
    show("vJob"); CC.pill.repaint();
  }
  const run = j.state === "running", done = j.state === "done", err = j.state === "error", cancel = j.state === "cancel";
  $("#vJob").classList.toggle("run", run);
  $("#jTitle").textContent = done ? "เสร็จแล้ว" : err ? "ตัดไม่สำเร็จ" : cancel ? "ยกเลิกแล้ว" : CC.jobTitle(j);
  $("#jTitle").classList.toggle("err", err);
  const srcs = j.srcs || [j.src];
  $("#jSub").textContent = done || err || cancel ? CC.jobTitle(j) : `${srcs.length > 1 ? srcs.length + " คลิป · " : ""}ยาว ${CC.mmss(j.dur || 0)}`;
  if (j.src && $("#jCover").dataset.src !== j.src) { $("#jCover").dataset.src = j.src; $("#jCover").src = "/api/clipthumb?path=" + encodeURIComponent(j.src); }
  const pct = done ? 100 : Math.round(j.prog || 0);
  $("#jBar").style.width = pct + "%"; $("#jPct").textContent = pct + "%";
  $("#jEta").textContent = run ? CC.etaText(j) : done && j.now ? `ใช้เวลา ${CC.mmss(j.now - j.t0)}` : "";
  const steps = j.steps && j.steps.length ? j.steps : /กำกับฉาก/.test((j.log || []).join(" ")) ? STEPS_EX : STEPS_FX;
  $("#jSteps").innerHTML = steps.map((s, i) => {
    const n = i + 1, now = n === j.step && run, cls = done || n < j.step ? "ok" : now ? "now" : "";
    return `<li class="${cls}"><span class="dot"></span><span>${esc(s)}</span>${now && j.doing ? `<small>${esc(j.doing)}…</small>` : ""}</li>`;
  }).join("");
  paintFeed(j);
  const log = $("#jLog"); log.textContent = (j.log || []).filter((l) => !/^\s*\d+\.\d+ speaker/.test(l)).join("\n"); log.scrollTop = log.scrollHeight;
  if (err) $("#jDet").open = true;
  $("#jCancel").classList.toggle("hidden", !run);
  $("#jAway").classList.toggle("hidden", !run);
  $("#jBack").classList.toggle("hidden", run || done);
  $("#jOpen").classList.toggle("hidden", !done);
  paintBell();
  if (done && !j.seen && !autoOpen) autoOpen = setTimeout(() => CC.openJob(j), 1200); // ยืนดูหน้ารออยู่ = เปิด editor ให้เลย
}
// ของที่ได้ระหว่างทาง (การ์ดละอย่าง) — วาดเฉพาะการ์ดที่เปลี่ยน (GIF ไม่กระพริบ)
const feedHtml = {};
function paintFeed(j) {
  const n = j.notes || {}, out = [];
  const media = (u) => /\.(mp4|webm)$/i.test(u) ? `<video src="/api/jobimg?path=${encodeURIComponent(u)}" muted autoplay loop playsinline></video>`
    : `<img src="/api/jobimg?path=${encodeURIComponent(u)}" alt="">`;
  if (n.talk) out.push(["talk", `<div class="k">ถอดเสียง</div>ได้ ${n.talk.n} ประโยค`]);
  if (n.title) out.push(["title", `<div class="k">AI ตั้งชื่องาน</div><div class="big">${esc(n.title.text)}</div>`]);
  if (n.cmds) out.push(["cmds", `<div class="k">คำสั่งเสียงในคลิป</div>${n.cmds.items.length ? `<div class="tags">${n.cmds.items.map((x) => `<span>${esc(x)}</span>`).join("")}</div>` : '<span class="muted">ไม่ได้สั่งอะไร</span>'}`]);
  if (n.cut) out.push(["cut", `<div class="k">ตัดช่วงเงียบ</div><b>${CC.mmss(n.cut.a)} → ${CC.mmss(n.cut.b)}</b> <span class="muted">· ตัดออก ${Math.round(n.cut.a - n.cut.b)} วิ</span>
    <div class="cutbar"><i style="width:${Math.round(100 * n.cut.b / Math.max(n.cut.a, 1))}%"></i></div>`]);
  if (n.photos) out.push(["photos", `<div class="k">รูปจริงตามที่สั่ง</div><div class="imgs">${n.photos.imgs.map(media).join("")}</div>`]);
  if (n.gifs) out.push(["gifs", `<div class="k">GIF / meme ${n.gifs.n} จุด</div><div class="imgs">${n.gifs.imgs.map(media).join("")}</div>`]);
  if (n.count) {
    const c = n.count, L = [["ซับ", c.sub], ["ภาพ", c.broll], ["GIF", c.gif], ["เสียง", c.sfx], ["ซูม/เอฟเฟกต์", c.fx]].filter((x) => x[1]);
    out.push(["count", `<div class="k">ลง timeline แล้ว</div><div class="tags">${L.map(([a, b]) => `<span class="n">${a} ${b}</span>`).join("")}</div>`]);
  }
  if (j.state === "running") out.push(["wait", `<i></i>${esc(j.doing || j.msg || "กำลังเริ่ม")}…`]);
  const feed = $("#jFeed"), keys = out.map((x) => x[0]);
  [...feed.children].forEach((el) => { if (!keys.includes(el.dataset.k)) { el.remove(); delete feedHtml[el.dataset.k]; } });
  out.forEach(([k, h], i) => {
    let el = feed.querySelector(`[data-k="${k}"]`);
    if (!el) { el = document.createElement("div"); el.dataset.k = k; el.className = "fi" + (k === "wait" ? " wait" : ""); }
    if (feedHtml[k] !== h) { el.innerHTML = h; feedHtml[k] = h; }
    if (feed.children[i] !== el) feed.insertBefore(el, feed.children[i] || null);
  });
}
setInterval(() => { if (lastJob && lastJob.state === "running" && !$("#vJob").classList.contains("hidden")) $("#jEta").textContent = CC.etaText(lastJob); }, 5000);
$("#jCancel").onclick = () => { if (confirm("ยกเลิกงานนี้?")) post("/api/job/cancel"); };
$("#jBack").onclick = () => { if (lastJob && lastJob.state !== "running") post("/api/job/seen"); staged ? show("vOpts") : show("vDrop"); CC.pill.repaint(); };
$("#jOpen").onclick = () => CC.openJob(lastJob);
$("#jAway").onclick = () => { jobAway(lastJob && lastJob.t0); show(staged ? "vOpts" : "vDrop"); CC.pill.update(lastJob); window.scrollTo({ top: 0 }); };
$("#jBell").onclick = async () => { if (CC.push.state() === "on") return; await CC.push.enable(); paintBell(); };
function paintBell() {
  const st = CC.push.state(), on = st === "on";
  $("#btnBell").classList.toggle("on", on); $("#bellTx").textContent = on ? "แจ้งเตือนเปิดอยู่" : "แจ้งเตือน";
  $("#jBell").textContent = on ? "เสร็จแล้วจะเด้งแจ้งเตือน" : "แจ้งเตือนเมื่อเสร็จ"; $("#jBell").disabled = on;
  $("#jBell").classList.toggle("hidden", st === "no" || !lastJob || lastJob.state !== "running");
}
$("#btnBell").onclick = async () => {
  if (CC.push.state() === "on") { if (confirm("ปิดแจ้งเตือนบนเครื่องนี้?")) await CC.push.disable(); }
  else await CC.push.enable();
  paintBell();
};

/* ---------- โปรเจกต์ล่าสุด ---------- */
const ICON = {
  play: '<path d="m8 5 11 7-11 7z"/>',
  dl: '<path d="M12 4v11m-5-5 5 5 5-5M5 20h14"/>',
  trash: '<path d="M4 7h16M10 11v6m4-6v6M6 7l1 13h10l1-13M9 7V4h6v3"/>',
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
          ${p.outputs.length && MOBILE ? `<a class="ib" href="/api/video?path=${encodeURIComponent(p.outputs[p.outputs.length - 1])}&dl=1" download title="โหลดคลิปล่าสุดลงเครื่อง">${svg("dl")}</a>` : ""}
          <button class="ib" data-a="name" data-i="${i}" title="ตั้งชื่อ">${svg("name")}</button>
          <button class="ib" data-a="dir" data-i="${i}" title="เปิดโฟลเดอร์">${svg("dir")}</button>
          <button class="ib" data-a="del" data-i="${i}" title="ลบ (ไปถังขยะ กู้คืนได้ 30 วัน)">${svg("trash")}</button></div></div></div>`).join("");
  el.onclick = async (e) => {
    const b = e.target.closest("[data-a]"); if (!b) return;
    const a = b.dataset.a, p = ps[+b.dataset.i];
    if (a === "open") { await post("/api/open", { edit: p.edit }); location.href = EDITOR; }
    if (a === "play") { const o = p.outputs[p.outputs.length - 1]; MOBILE ? window.open("/api/video?path=" + encodeURIComponent(o)) : post("/api/play", { path: o }); }
    if (a === "dir") post("/api/reveal", { path: p.dir });
    if (a === "name") { const t = prompt("ตั้งชื่องาน", p.title); if (t != null) { await post("/api/rename", { edit: p.edit, title: t }); refresh(); } }
    if (a === "del") toTrash("project", p.edit, p.title);
  };
}

let root = "";
/* ---------- คลังคลิป: อัปเก็บไว้ก่อน → เลือกแล้วค่อยตัด (ตัดซ้ำได้) ---------- */
let lib = [], libSel = [], libAll = false, libNaming = false;
async function loadLib() {
  const r = await fetch("/api/library").then((x) => x.json()).catch(() => null);
  if (!r) return;
  lib = r.clips; libNaming = r.naming; libSel = libSel.filter((p) => lib.some((c) => c.path === p)); paintLib();
  // AI ยังตั้งชื่อไม่เสร็จ (อัปไม่ถึง 3 นาที) / กำลังสแกนคลิปเก่า → ถามใหม่อีกที
  clearTimeout(loadLib.t);
  if (r.naming || r.scanning) loadLib.t = setTimeout(loadLib, 5000);
}
function paintLib() {
  $("#lCount").textContent = lib.length ? lib.length + " คลิป" : "";
  const shown = libAll ? lib : lib.slice(0, MOBILE ? 6 : 12);
  $("#library").innerHTML = ups.map((c) => `<div class="lc up" id="${c.id}">
      <div class="th"><video src="${c.url}#t=0.5" muted playsinline preload="metadata"></video><div class="upr"><div style="--p:${c.pct}"><b>${c.pct}%</b></div></div></div>
      <div class="body"><div class="ttl" title="${esc(c.name)}">${esc(c.name)}</div><small><span>กำลังอัป · ${(c.size / 1048576).toFixed(0)} MB</span></small></div></div>`).join("")
    + shown.map((c) => { const k = libSel.indexOf(c.path), t = c.ctime ? new Date(c.ctime) : new Date(c.added * 1000);
    const fresh = !c.by && libNaming;
    return `<div class="lc${k >= 0 ? " on" : ""}" data-p="${esc(c.path)}">
      <div class="th"><img src="/api/clipthumb?path=${encodeURIComponent(c.path)}" loading="lazy" alt=""><span class="chk">${k >= 0 ? k + 1 : ""}</span>
        <span class="badge l">${c.dur ? mmss(c.dur) : "…"}</span>${c.uses.length ? `<span class="badge r">ตัดแล้ว ${c.uses.length}</span>` : ""}</div>
      <div class="body"><div class="ttl${fresh ? " wait" : ""}" title="${esc(c.name)}">${esc(fresh ? "AI กำลังตั้งชื่อ…" : c.title)}</div>
        <small><span>${t.toLocaleDateString("th-TH", { day: "numeric", month: "short" })} ${t.toLocaleTimeString("th-TH", { hour: "2-digit", minute: "2-digit" })}</span>
        <button class="ib" data-ren title="ตั้งชื่อ">${svg("name")}</button><button class="ib" data-del title="ลบ (ไปถังขยะ กู้คืนได้ 30 วัน)">${svg("trash")}</button></small></div></div>`; }).join("")
    || '<div class="empty" style="grid-column:1/-1">ยังไม่มีคลิป — กด "+ อัปเก็บไว้ก่อน" หรือลากคลิปมาวางด้านบน</div>';
  $("#libMore")?.remove();
  if (lib.length > shown.length) {
    $("#library").insertAdjacentHTML("afterend", `<button class="ghost more" id="libMore" type="button">ดูทั้งหมด ${lib.length} คลิป</button>`);
    $("#libMore").onclick = () => { libAll = true; paintLib(); };
  }
  $("#lbar").classList.toggle("hidden", !libSel.length);
  $("#lSel").textContent = libSel.length > 1 ? `เลือก ${libSel.length} คลิป · รวมเป็นคลิปเดียวตามลำดับที่เลือก` : "เลือก 1 คลิป";
}
$("#library").onclick = async (e) => {
  const card = e.target.closest(".lc"); if (!card) return;
  const c = lib.find((x) => x.path === card.dataset.p); if (!c) return;
  if (e.target.closest("[data-ren]")) {
    const t = prompt("ตั้งชื่อคลิป", c.title); if (t == null) return;
    await post("/api/library/rename", { path: c.path, title: t }); return loadLib();
  }
  if (e.target.closest("[data-del]")) { libSel = libSel.filter((x) => x !== c.path); return toTrash("clip", c.path, c.title); }
  const k = libSel.indexOf(c.path);
  k >= 0 ? libSel.splice(k, 1) : libSel.push(c.path); paintLib();
};
$("#lClear").onclick = () => { libSel = []; paintLib(); };
$("#lCut").onclick = () => {
  if (!libSel.length) return;
  libSel.forEach((p, i) => stage(p, i > 0)); libSel = []; paintLib();
  window.scrollTo({ top: 0, behavior: "smooth" });
};
$("#libAdd").onclick = () => $("#pickLib").click();
$("#pickLib").onchange = async (e) => {
  const files = [...e.target.files].filter((f) => /\.(mp4|mov|mkv|m4v|webm|avi)$/i.test(f.name)); e.target.value = "";
  const cards = files.map(upCard);
  for (let k = 0; k < files.length; k++) {
    await upload(files[k], "", `${k + 1}/${files.length} `, () => {}, cards[k]).catch((err) => { upDone(cards[k]); alert(err); });
  }
};

/* ---------- ถังขยะ: ลบในแอป = ย้ายมาที่นี่ (ไฟล์ไม่ขยับ) · ครบ 30 วันลบเอง · ลบถาวร = ไฟล์ไปถังขยะ Windows ---------- */
let undoT = null;
async function toTrash(kind, path, title) {
  await post("/api/trash/add", { kind, path });
  kind === "clip" ? loadLib() : refresh(); loadTrashCount();
  $("#undoTx").textContent = `ย้าย "${title}" ไปถังขยะแล้ว`;
  $("#undo").classList.remove("hidden");
  $("#undoBtn").onclick = async () => {
    clearTimeout(undoT); $("#undo").classList.add("hidden");
    await post("/api/trash/restore", { kind, path }); kind === "clip" ? loadLib() : refresh(); loadTrashCount();
  };
  clearTimeout(undoT); undoT = setTimeout(() => $("#undo").classList.add("hidden"), 5000);
}
let T = { clips: [], projects: [], days: 30 };
async function loadTrashCount() {
  T = await fetch("/api/trash").then((r) => r.json()).catch(() => T);
  const n = T.clips.length + T.projects.length;
  $("#tCnt").textContent = n || "";
  if (!$("#trash").classList.contains("hidden")) paintTrash();
}
function paintTrash() {
  const n = T.clips.length + T.projects.length;
  $("#tInfo").textContent = n ? `${n} รายการ · ลบถาวรเองเมื่อครบ ${T.days} วัน` : "";
  $("#tEmpty").classList.toggle("hidden", !n);
  const card = (kind, path, title, img, left) => `<div class="tc">
      <div class="th"><img src="${img}" loading="lazy" alt=""><span class="left${left <= 3 ? " soon" : ""}">${left ? `เหลือ ${left} วัน` : "ลบวันนี้"}</span></div>
      <div class="body"><div class="ttl" title="${esc(title)}">${esc(title)}</div>
        <div class="row"><button data-res="${kind}" data-p="${esc(path)}">กู้คืน</button><button class="danger" data-pur="${kind}" data-p="${esc(path)}" data-t="${esc(title)}">ลบถาวร</button></div></div></div>`;
  $("#tBody").innerHTML = n ? (T.projects.length ? `<h4>โปรเจกต์ ${T.projects.length}</h4><div class="tgrid">${T.projects.map((p) =>
      card("project", p.edit, p.title, "/api/thumb?edit=" + encodeURIComponent(p.edit), p.left)).join("")}</div>` : "")
    + (T.clips.length ? `<h4>คลิปในคลัง ${T.clips.length}</h4><div class="tgrid">${T.clips.map((c) =>
      card("clip", c.path, c.title, "/api/clipthumb?path=" + encodeURIComponent(c.path), c.left)).join("")}</div>` : "")
    : '<div class="empty">ถังขยะว่าง</div>';
}
$("#tBody").onclick = async (e) => {
  const r = e.target.closest("[data-res]"), d = e.target.closest("[data-pur]");
  if (r) { r.disabled = true; await post("/api/trash/restore", { kind: r.dataset.res, path: r.dataset.p }); }
  if (d) {
    if (!confirm(`ลบ "${d.dataset.t}" ถาวร?\nไฟล์จะไปอยู่ในถังขยะของ Windows บนคอม (กู้จากตรงนั้นได้)`)) return;
    d.disabled = true; const x = await post("/api/trash/purge", { items: [{ kind: d.dataset.pur, path: d.dataset.p }] });
    if (!x.n) alert("ลบไม่ได้ — งานนี้อาจกำลังตัดอยู่");
  }
  if (r || d) { loadTrashCount(); loadLib(); refresh(); }
};
$("#tEmpty").onclick = async () => {
  if (!confirm(`ลบทั้งหมด ${T.clips.length + T.projects.length} รายการถาวร?\nไฟล์จะไปอยู่ในถังขยะของ Windows บนคอม`)) return;
  await post("/api/trash/purge", {}); loadTrashCount(); loadLib(); refresh();
};
$("#btnTrash").onclick = () => { $("#trash").classList.remove("hidden"); paintTrash(); loadTrashCount(); };
$("#tClose").onclick = () => $("#trash").classList.add("hidden");
$("#trash").onclick = (e) => { if (e.target.id === "trash") $("#trash").classList.add("hidden"); };
addEventListener("keydown", (e) => { if (e.key === "Escape") $("#trash").classList.add("hidden"); });

async function refresh() {
  const h = await fetch("/api/home").then((r) => r.json());
  root = h.root; $("#root").textContent = "เก็บงานที่ " + h.root;
  $("#toEditor").style.display = h.current ? "" : "none";
  paintProjects(h.projects);
  if (h.job && h.job.state !== "idle") paintJob(h.job);
  else if (h.staged && !staged) stage(h.staged);
}
// สำรองให้ SSE: ผ่าน tailscale serve (มือถือ) event อาจค้างในตัวกลาง → หน้าความคืบหน้าค้างทั้งที่งานเสร็จแล้ว
setInterval(async () => {
  if ($("#vJob").classList.contains("hidden") && !(lastJob && lastJob.state === "running")) return;
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
es.addEventListener("library", () => { loadLib(); loadTrashCount(); });
es.addEventListener("projects", () => { refresh(); loadTrashCount(); });
es.addEventListener("stage", (e) => { const d = JSON.parse(e.data); if (d.path) stage(d.path); });
// มาจากแจ้งเตือน/แถบงาน: ?job=1 ดูหน้ารอ · ?open=1 เปิดงานที่เพิ่งตัดเสร็จ · ?go=editor ไป editor
const Q = new URLSearchParams(location.search);
if (Q.get("go") === "editor") location.replace(EDITOR);
if (Q.has("job") || Q.has("open")) { jobAway(null); history.replaceState(null, "", "/"); }
if (Q.has("open")) fetch("/api/job").then((r) => r.json()).then((j) => { if (j.state === "done" && j.edit) CC.openJob(j); });
if (Q.has("job")) fetch("/api/job").then((r) => r.json()).then((j) => { if (j.state !== "idle") { show("vJob"); paintJob(j); } });
paintOpts(); refresh(); loadLib(); loadTrashCount(); paintBell();
