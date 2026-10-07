/* ClipCut — แถบงานที่กำลังตัด (มุมจอ ทุกหน้า) + เวลาที่เหลือ + เปิดแจ้งเตือนมือถือ
   หน้าแรกเรียก CC.pill.update() เอง (window.CC_PILL_SELF = true) · หน้าอื่นฟัง SSE เอง */
"use strict";
(function () {
  const CC = (window.CC = window.CC || {});
  const MOBILE = matchMedia("(pointer: coarse)").matches && innerWidth < 900;
  CC.MOBILE = MOBILE;
  CC.EDITOR = MOBILE ? "/m" : "/edit";
  const post = (u, b) => fetch(u, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b || {}) }).then((r) => r.json());
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  /* ---------- เวลาเหลือ: ช่วงแรกเดาจากงานที่ผ่านมา (server) · พอเดินไปได้สักพักผสมกับความเร็วจริง ---------- */
  let skew = 0; // นาฬิกา server - เครื่องนี้ (มือถือเวลาไม่ตรงคอม)
  CC.jobClock = (j) => { if (j && j.now) skew = j.now - Date.now() / 1000; };
  CC.elapsed = (j) => Math.max(0, Date.now() / 1000 + skew - (j.t0 || 0));
  CC.eta = (j) => {
    const el = CC.elapsed(j), p = j.prog || 0;
    let est = j.eta || 180;
    if (p >= 15) { const w = Math.min(1, (p - 15) / 50); est = (1 - w) * est + w * (el / (p / 100)); }
    return Math.max(0, est - el);
  };
  CC.etaText = (j) => {
    if (!j || j.state !== "running") return "";
    const r = CC.eta(j);
    return r < 25 ? "อีกแป๊บเดียว" : r < 60 ? "เหลือไม่ถึงนาที" : `เหลืออีก ~${Math.ceil(r / 60)} นาที`;
  };
  CC.mmss = (d) => `${Math.floor(d / 60)}:${String(Math.round(d % 60)).padStart(2, "0")}`;
  CC.jobTitle = (j) => (j.notes && j.notes.title && j.notes.title.text) || j.name || "คลิป";
  CC.openJob = async (j) => { if (j && j.edit) { await post("/api/open", { edit: j.edit }); location.href = CC.EDITOR; } };

  if (document.documentElement.classList.contains("embed")) return; // จอพรีวิวที่ฝังในหน้ามือถือ — หน้าแม่มีแถบแล้ว
  /* ---------- แถบงาน ---------- */
  const css = document.createElement("style");
  css.textContent = `
  .jpill { position: fixed; left: 50%; transform: translateX(-50%); bottom: calc(16px + env(safe-area-inset-bottom)); z-index: 60;
    display: flex; align-items: center; gap: 10px; max-width: calc(100vw - 24px); padding: 8px 8px 8px 14px; border-radius: 999px;
    background: var(--panel2); border: 1px solid var(--line); box-shadow: 0 10px 34px rgba(0,0,0,.45); cursor: pointer;
    font: 13px/1.3 "Segoe UI", "Leelawadee UI", system-ui, sans-serif; color: var(--text); transition: opacity .2s, transform .2s; }
  .jpill.top { bottom: auto; top: 54px; }
  .jpill.hide { opacity: 0; pointer-events: none; transform: translate(-50%, 12px); }
  .jpill .ring { width: 28px; height: 28px; border-radius: 50%; flex: 0 0 28px; display: grid; place-items: center;
    background: conic-gradient(var(--accent) calc(var(--p) * 1%), var(--line) 0); }
  .jpill .ring::after { content: ""; width: 20px; height: 20px; border-radius: 50%; background: var(--panel2); }
  .jpill.done .ring { background: var(--accent); } .jpill.done .ring::after { content: "✓"; background: none; color: #031a12; font-weight: 800; width: auto; height: auto; }
  .jpill.err .ring { background: #ef4444; } .jpill.err .ring::after { content: "!"; background: none; color: #fff; font-weight: 800; width: auto; height: auto; }
  .jpill .tx { min-width: 0; display: flex; flex-direction: column; }
  .jpill b { font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 52vw; }
  .jpill small { color: var(--muted); font-size: 11.5px; white-space: nowrap; }
  .jpill .go { background: var(--accent); color: #031a12; border: 0; border-radius: 999px; padding: 6px 12px; font-weight: 600; white-space: nowrap; }
  .jpill .x { background: transparent; border: 0; color: var(--muted); width: 28px; height: 28px; padding: 0; border-radius: 50%; font-size: 16px; }`;
  document.head.appendChild(css);
  const el = document.createElement("div");
  el.className = "jpill hide" + (window.CC_PILL_TOP ? " top" : "");
  let J = null, away = false, hidden = () => false;
  function paint() {
    const j = J;
    const show = j && !hidden() && (j.state === "running" || ((j.state === "done" || j.state === "error") && !j.seen));
    el.classList.toggle("hide", !show || away);
    if (!show) return;
    if (!el.parentNode) document.body.appendChild(el);
    el.classList.toggle("done", j.state === "done"); el.classList.toggle("err", j.state === "error");
    const p = j.state === "done" ? 100 : j.prog || 0;
    el.innerHTML = `<span class="ring" style="--p:${p}"></span><span class="tx"><b>${esc(j.state === "done" ? "ตัดเสร็จแล้ว · " + CC.jobTitle(j) : j.state === "error" ? "ตัดพัง · " + CC.jobTitle(j) : CC.jobTitle(j))}</b>
      <small>${j.state === "running" ? `${Math.round(p)}% · ${esc(j.doing || (j.steps && j.steps[j.step - 1]) || j.msg || "")} · ${CC.etaText(j)}` : j.state === "done" ? "แตะเพื่อเปิด editor" : "แตะเพื่อดูรายละเอียด"}</small></span>
      ${j.state === "done" ? '<button class="go">เปิด</button>' : ""}<button class="x" title="ซ่อน">×</button>`;
  }
  el.onclick = (e) => {
    if (e.target.closest(".x")) {
      e.stopPropagation();
      if (J && J.state !== "running") post("/api/job/seen"); else away = true;
      return paint();
    }
    if (J && J.state === "done") return CC.openJob(J);
    location.href = "/?job=1";
  };
  CC.pill = {
    update(j) { if (!j) return; if (J && j.state !== J.state) away = false; J = j; CC.jobClock(j); paint(); },
    hideWhen(fn) { hidden = fn; paint(); },
    repaint: paint,
  };
  setInterval(() => J && J.state === "running" && paint(), 5000);
  if (!window.CC_PILL_SELF) {
    fetch("/api/job").then((r) => r.json()).then(CC.pill.update).catch(() => {});
    const es = new EventSource("/api/events");
    es.addEventListener("job", (e) => CC.pill.update(JSON.parse(e.data)));
    setInterval(() => J && J.state === "running" && fetch("/api/job").then((r) => r.json()).then(CC.pill.update).catch(() => {}), 8000);
  }

  /* ---------- แจ้งเตือน (Web Push) ---------- */
  const IOS = /iP(hone|ad|od)/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  const STANDALONE = matchMedia("(display-mode: standalone)").matches || navigator.standalone;
  const ok = "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
  if (ok) navigator.serviceWorker.register("/sw.js").catch(() => {});
  const u8 = (b64) => { const s = atob((b64 + "===".slice((b64.length + 3) % 4)).replace(/-/g, "+").replace(/_/g, "/")); return Uint8Array.from(s, (c) => c.charCodeAt(0)); };
  CC.push = {
    // on = เปิดแล้ว · off = กดเปิดได้ · ios-home = iPhone ต้องเพิ่มลงหน้าจอโฮมก่อน · no = เบราว์เซอร์ไม่รองรับ · denied = เคยกดไม่อนุญาต
    state() {
      if (!ok) return IOS && !STANDALONE ? "ios-home" : "no";
      if (Notification.permission === "denied") return "denied";
      return Notification.permission === "granted" && localStorage.getItem("cc.push") === "1" ? "on" : "off";
    },
    async enable() {
      const st = CC.push.state();
      if (st === "ios-home") { alert('บน iPhone ต้องเพิ่มเป็นแอปก่อน:\n1. กดปุ่มแชร์ (สี่เหลี่ยมลูกศรขึ้น) ใน Safari\n2. เลือก "เพิ่มลงหน้าจอโฮม"\n3. เปิด ClipCut จากไอคอนนั้น แล้วกดเปิดแจ้งเตือนอีกที'); return false; }
      if (st === "no") { alert("เบราว์เซอร์นี้ไม่รองรับการแจ้งเตือน"); return false; }
      if (st === "denied") { alert("เคยกดไม่อนุญาตไว้ — เปิดใหม่ได้ที่ ตั้งค่า → การแจ้งเตือน → ClipCut"); return false; }
      const perm = await Notification.requestPermission(); // ต้องเรียกทันทีหลังแตะ (iOS)
      if (perm !== "granted") return false;
      try {
        const reg = await navigator.serviceWorker.register("/sw.js"); await navigator.serviceWorker.ready;
        const k = await fetch("/api/push/key").then((r) => r.json());
        if (!k.ok) throw new Error(k.error);
        let sub = await reg.pushManager.getSubscription();
        if (!sub) sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: u8(k.key) });
        await post("/api/push/sub", { sub: sub.toJSON(), test: true });
        localStorage.setItem("cc.push", "1");
        return true;
      } catch (err) { alert("เปิดแจ้งเตือนไม่ได้: " + err.message); return false; }
    },
    async disable() {
      try {
        const reg = await navigator.serviceWorker.getRegistration(); const sub = reg && await reg.pushManager.getSubscription();
        if (sub) { await post("/api/push/unsub", { endpoint: sub.endpoint }); await sub.unsubscribe(); }
      } catch (err) { /* ไม่เป็นไร */ }
      localStorage.removeItem("cc.push");
    },
  };
})();
