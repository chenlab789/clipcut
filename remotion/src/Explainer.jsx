// ClipCut — Motion Explainer: คลิปคนพูด + จัดฉากใหม่ทุกประโยค (พื้นกระดาษ ป้ายหัวข้อ ภาพพิกเซล ป้ายคำ ซับเต็มล่าง)
// ส่วนพื้นกระดาษ/ดาว/ท่าเด้ง/transition มาจาก animclip/remotion/src/Main.jsx (stop-motion ทีละ 2 เฟรม)
// วิดีโอคนพูดเป็นชั้นเดียวต่อเนื่องทั้งคลิป ย้ายตำแหน่งตามฉาก (เต็มจอ / โพลารอยด์ / มุม / วงกลม / ซ่อน)
import React from 'react';
import {AbsoluteFill, Sequence, Img, OffthreadVideo, staticFile, useCurrentFrame, useVideoConfig, random, interpolate, Easing} from 'remotion';
import {loadFont as kanit} from '@remotion/google-fonts/Kanit';
import {loadFont as mali} from '@remotion/google-fonts/Mali';

const FONTS = {
  Kanit: kanit('normal', {weights: ['600', '800'], subsets: ['thai', 'latin']}).fontFamily,
  Mali: mali('normal', {weights: ['600', '700'], subsets: ['thai', 'latin']}).fontFamily,
};
const STEP = 2;
const W = 1080;
const H = 1920;
const OVER = 6;
const INK = '#1a161c';

const BG = {
  grid: {base: '#eef3f8', ink: '#9fb4c8', grid: '#9fc3e6'},
  paper: {base: '#f3ecdc', ink: '#b9a77f'},
  lined: {base: '#f6f0e1', ink: '#b9a77f', lined: true},
  kraft: {base: '#c9a77c', ink: '#8a6a45'},
  navy: {base: '#1c2440', ink: '#3b4670', grid: '#3b4a7a'},
  mint: {base: '#e3f1e6', ink: '#8fb39a', grid: '#9cc7a8'},
  pink: {base: '#f6e3e6', ink: '#c99aa3', grid: '#e0b3bc'},
  yellow: {base: '#f7eecb', ink: '#c9b26a', lined: true},
  black: {base: '#171717', ink: '#3a3a3a'},
};
const DARK = new Set(['navy', 'black']);
const PILL = [['#ef4444', '#fff'], ['#10b981', '#fff'], ['#facc15', INK], ['#3b82f6', '#fff'], [INK, '#fff'], ['#fcfaf4', INK]];

const ENTER = {
  pop: [[0.2, 0, 0, 0], [1.25, 0, 0, 0], [0.92, 0, 0, 0]],
  slap: [[1.7, 0, 0, -8], [0.9, 0, 0, 3], [1.04, 0, 0, 0]],
  drop: [[1, 0, -1100, 0], [1, 0, -380, 0], [1, 0, 30, 0], [1, 0, -12, 0]],
  slide_left: [[1, -1300, 0, -12], [1, -350, 0, -4], [1, 30, 0, 2]],
  slide_right: [[1, 1300, 0, 12], [1, 350, 0, 4], [1, -30, 0, -2]],
  rise: [[1, 0, 900, 0], [1, 0, 250, 0], [1, 0, -20, 0]],
};
const TRANS = {
  slap: [[1.18, 0, 0, 4], [0.97, 0, 0, -1], [1, 0, 0, 0]],
  slide: [[1, 1150, 0, 9], [1, 380, 0, 3], [1, -25, 0, -1]],
  drop: [[1, 0, -2000, -4], [1, 0, -520, -2], [1, 0, 30, 0]],
  punch: [[1.16, 0, 0, 0], [1.06, 0, 0, 0], [1.02, 0, 0, 0]],
  cut: [],
};
// path ในพร็อพ: 'pixel/..' หรือ 'jobs/..' = ไฟล์ใน public (ตอนเรนเดอร์) · '/..' หรือ http = URL ตรง (ตอนพรีวิวใน editor)
const asset = (p) => (/^(\/|https?:)/.test(p) ? p : staticFile(p));
const jit = (key, step, amt) => (random(`${key}-${step}`) - 0.5) * amt;

// ---------- พื้นกระดาษ ----------
const PaperBg = ({bg = 'paper', step, seedKey}) => {
  const b = BG[bg] || BG.paper;
  const boil = Math.floor(step / 2) % 3;
  return (
    <AbsoluteFill style={{background: b.base}}>
      {b.grid && <AbsoluteFill style={{backgroundImage: `repeating-linear-gradient(0deg, ${b.grid}66 0 2px, transparent 2px 54px), repeating-linear-gradient(90deg, ${b.grid}66 0 2px, transparent 2px 54px)`}} />}
      {b.lined && <AbsoluteFill style={{backgroundImage: 'linear-gradient(90deg, transparent 120px, #ef444466 120px 124px, transparent 124px), repeating-linear-gradient(0deg, #60a5fa55 0 3px, transparent 3px 64px)'}} />}
      <svg width={W} height={H} style={{position: 'absolute', mixBlendMode: DARK.has(bg) ? 'screen' : 'multiply', opacity: DARK.has(bg) ? 0.12 : 0.5}}>
        <filter id={`n-${seedKey}-${boil}`}>
          <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" seed={boil + 3} />
          <feColorMatrix type="matrix" values="0 0 0 0 0.45  0 0 0 0 0.38  0 0 0 0 0.28  0 0 0 -1.4 1.05" />
        </filter>
        <rect width={W} height={H} filter={`url(#n-${seedKey}-${boil})`} />
      </svg>
      <Decor seedKey={seedKey} boil={boil} dark={DARK.has(bg)} />
    </AbsoluteFill>
  );
};

// ดาว/ประกายเล็กๆ ตามขอบ (ไม่เข้ากลางจอ) — แบบคลิปตัวอย่าง
const DECOR_SLOTS = [[0.07, 0.07], [0.93, 0.09], [0.05, 0.36], [0.95, 0.33], [0.06, 0.6], [0.94, 0.57], [0.1, 0.8], [0.9, 0.79], [0.5, 0.035]];
const DECOR_COLS = ['#ef4444', '#facc15', '#10b981', '#3b82f6'];
const Decor = ({seedKey, boil, dark}) => {
  const r = (k) => random(`${seedKey}d${k}`);
  const n = 4 + Math.floor(r('n') * 3);
  const used = DECOR_SLOTS.map((s, i) => [r(`o${i}`), s]).sort((a, b) => a[0] - b[0]).slice(0, n).map((x) => x[1]);
  return (
    <svg width={W} height={H} style={{position: 'absolute'}}>
      {used.map(([sx, sy], i) => {
        const kind = Math.floor(r(`k${i}`) * 3);
        const col = DECOR_COLS[Math.floor(r(`c${i}`) * DECOR_COLS.length)];
        const rot = (r(`r${i}`) - 0.5) * 60 + jit(`${seedKey}dr${i}`, boil, 8);
        const g = {transform: `translate(${sx * W}px,${sy * H}px) rotate(${rot}deg) scale(${0.6 + r(`s${i}`) * 0.5})`};
        if (kind === 0) { // ประกาย 8 แฉก
          const p = Array.from({length: 16}, (_, k) => { const a = (k * Math.PI) / 8, rr = k % 2 ? 14 : 44; return `${rr * Math.cos(a)},${rr * Math.sin(a)}`; }).join(' ');
          return <polygon key={i} style={g} points={p} fill={col} />;
        }
        if (kind === 1) { // ดาวโครงเส้น
          const p = Array.from({length: 10}, (_, k) => { const a = (k * Math.PI) / 5 - Math.PI / 2, rr = k % 2 ? 12 : 28; return `${rr * Math.cos(a)},${rr * Math.sin(a)}`; }).join(' ');
          return <polygon key={i} style={g} points={p} fill="none" stroke={dark ? '#fcfaf4' : INK} strokeWidth={4} strokeLinejoin="round" />;
        }
        const p = Array.from({length: 24}, (_, k) => { const a = (k * Math.PI) / 12, rr = k % 2 ? 22 : 40; return `${rr * Math.cos(a)},${rr * Math.sin(a)}`; }).join(' ');
        return <polygon key={i} style={g} points={p} fill={col} />;
      })}
    </svg>
  );
};

const Piece = ({x, y, rot = 0, enter = 'pop', delay = 0, seedKey, children, shadow = true, jitter = 1}) => {
  const frame = useCurrentFrame();
  if (frame < delay) return null;
  const s = Math.floor((frame - delay) / STEP);
  const E = ENTER[enter] || ENTER.pop;
  const [scale, dx, dy, drot] = s < E.length ? E[s] : [1, 0, 0, 0];
  return (
    <div style={{
      position: 'absolute', left: x * W, top: y * H,
      transform: `translate(-50%,-50%) translate(${dx + jit(seedKey + 'x', s, 5 * jitter)}px,${dy + jit(seedKey + 'y', s, 5 * jitter)}px) rotate(${rot + drot + jit(seedKey + 'r', s, 2 * jitter)}deg) scale(${scale})`,
      filter: shadow ? 'drop-shadow(8px 11px 0 rgba(0,0,0,.25))' : undefined,
    }}>{children}</div>
  );
};

// ป้ายหัวข้อแบบแถบกระดาษสี + เส้นขอบ
const Title = ({text, color = '#facc15', seedKey, font, y = 0.105}) => {
  const fg = color === '#facc15' || color === '#fcfaf4' ? INK : '#fff';
  return (
    <Piece x={0.5} y={y} rot={jit(seedKey + 'tr', 0, 5)} enter="slap" seedKey={seedKey + 't'}>
      <div style={{fontFamily: font, fontWeight: 800, fontSize: Math.max(52, Math.min(78, 1100 / Math.max(6, [...text].length))), color: fg,
        background: color, border: `6px solid ${INK}`, padding: '4px 34px 12px', whiteSpace: 'nowrap', boxShadow: `6px 7px 0 ${INK}`}}>{text}</div>
    </Piece>
  );
};

// ป้ายคำเล็กๆ เด้งตามคำพูด
// ท่าเด้งแบบไม่ยึดตำแหน่ง (ใช้ใน flex) — ก่อนถึงเวลาจองที่ไว้แต่ซ่อน
const Pop = ({delay = 0, seedKey, rot = 0, children}) => {
  const frame = useCurrentFrame();
  if (frame < delay) return <div style={{visibility: 'hidden'}}>{children}</div>;
  const s = Math.floor((frame - delay) / STEP);
  const [scale, , , drot] = s < ENTER.slap.length ? ENTER.slap[s] : [1, 0, 0, 0];
  return <div style={{transform: `rotate(${rot + drot + jit(seedKey, s, 2)}deg) scale(${scale})`, filter: 'drop-shadow(5px 7px 0 rgba(0,0,0,.25))'}}>{children}</div>;
};

const Tags = ({tags = [], seedKey, font, fps, y = 0.47}) => (
  <div style={{position: 'absolute', left: 40, right: 40, top: y * H, display: 'flex', justifyContent: 'center', flexWrap: 'wrap', gap: 16}}>
    {tags.map((t, i) => {
      const [bg, fg] = PILL[(i + Math.floor(random(seedKey + 'pc') * PILL.length)) % PILL.length];
      return (
        <Pop key={i} delay={Math.round((t.at || 0) * fps)} seedKey={`${seedKey}g${i}`} rot={jit(seedKey + 'g' + i, 0, 8)}>
          <div style={{fontFamily: font, fontWeight: 800, fontSize: 46, background: bg, color: fg, border: `5px solid ${INK}`, borderRadius: 10, padding: '0 20px 6px', whiteSpace: 'nowrap'}}>{t.text}</div>
        </Pop>
      );
    })}
  </div>
);

const Item = ({it, i, seedKey, fps}) => (
  <Piece x={it.x ?? 0.5} y={it.y ?? 0.3} rot={it.rot ?? jit(seedKey + 'ir' + i, 0, 14)} enter={it.enter || 'pop'}
    delay={Math.round((it.at || 0) * fps)} seedKey={`${seedKey}i${i}`}>
    <Img src={asset(it.src)} style={{width: (it.size || 0.3) * W, imageRendering: 'pixelated', display: 'block'}} />
  </Piece>
);

// ---------- ชั้นกล้อง: วิดีโอคนพูดเล่นต่อเนื่องทั้งคลิป ย้ายกรอบตามฉาก ----------
const camBox = (cam, srcAR) => {
  const vertical = srcAR < 1;
  if (cam === 'full') return {x: 0, y: 0, w: W, h: H, rot: 0, frame: 'none'};
  if (cam === 'polaroid') {
    const w = W * 0.84, h = vertical ? H * 0.4 : Math.min(H * 0.4, w / srcAR);
    return {x: (W - w) / 2, y: H * 0.89 - h, w, h, rot: -1.5, frame: 'polaroid'};
  }
  if (cam === 'corner') return {x: W * 0.6, y: H * 0.17, w: W * 0.34, h: W * 0.4, rot: 5, frame: 'polaroid'};
  if (cam === 'circle') return {x: W * 0.06, y: H * 0.17, w: W * 0.46, h: W * 0.46, rot: 0, frame: 'circle'};
  return {x: W * 0.62, y: H * 1.1, w: W * 0.34, h: W * 0.4, rot: 8, frame: 'polaroid'}; // none = เลื่อนออกนอกจอ
};
const lerp = (a, b, t) => a + (b - a) * t;

// ---------- ซูมตามบริบท (focus.py) — สูตรเดียวกับ render_edit ----------
// ฉากมี focus = [{at, mode: speaker|box|wide, box}] · speaker = หน้าคนที่กำลังพูด (ตามหน้าจาก faces.tracks + ซับบอกว่าใครพูด)
const WIDE = {cx: 0.5, cy: 0.5, w: 1, h: 1};
const speakerAt = (subs, t) => {
  let last = null;
  for (const s of subs) {
    if (t >= s.start && t < s.end) return s.speaker || null;
    if (s.end <= t && t - s.end < 1.5) last = s.speaker || null;
  }
  return last;
};
const facePos = (tr, t) => {
  const p = tr.pts;
  if (!p.length) return null;
  let lo = 0, hi = p.length - 1;
  while (hi - lo > 1) { const m = (lo + hi) >> 1; if (p[m][0] <= t) lo = m; else hi = m; }
  const a = p[lo], b = p[hi];
  if (Math.min(Math.abs(a[0] - t), Math.abs(b[0] - t)) > 1.2) return null; // ไม่เห็นหน้าช่วงนี้
  const f = b[0] > a[0] ? Math.min(1, Math.max(0, (t - a[0]) / (b[0] - a[0]))) : 0;
  return {x: lerp(a[1], b[1], f), y: lerp(a[2], b[2], f), w: lerp(a[3], b[3], f), h: lerp(a[4], b[4], f)};
};
const rawRegion = (t, scenes, faces, subs) => {
  let k = 0;
  for (let i = 0; i < scenes.length; i++) if (t >= scenes[i].start) k = i;
  const sc = scenes[k] || {};
  let kf = {mode: 'speaker'};
  for (const f of sc.focus || []) if (t - sc.start >= (f.at || 0)) kf = f;
  if (kf.mode === 'box' && kf.box) {
    const [x0, y0, x1, y1] = kf.box;
    return {cx: (x0 + x1) / 2, cy: (y0 + y1) / 2, w: (x1 - x0) * 1.3, h: (y1 - y0) * 1.3};
  }
  if (kf.mode === 'wide') return WIDE;
  const tracks = (faces && faces.tracks) || [];
  if (!tracks.length) return WIDE;
  const sp = speakerAt(subs, t);
  let tr = tracks.find((x) => sp && x.speaker === sp) || (tracks.length === 1 ? tracks[0] : null);
  if (!tr) { // ไม่รู้ว่าใครพูด → คนที่เห็นหน้าตอนนี้ / หลายคน = ภาพกว้าง
    const vis = tracks.filter((x) => facePos(x, t));
    if (vis.length !== 1) return WIDE;
    tr = vis[0];
  }
  const p = facePos(tr, t);
  if (!p) return WIDE;
  const tight = sc.cam === 'circle' || sc.cam === 'corner';
  // กรอบเล็ก = หน้าเต็มกรอบ · กรอบใหญ่ = หัวถึงอก
  return tight ? {cx: p.x, cy: p.y + p.h * 0.15, w: p.w * 2.2, h: p.h * 2.4} : {cx: p.x, cy: p.y + p.h * 0.7, w: p.w * 3.6, h: p.h * 4.4};
};
// เฉลี่ย ±0.3 วิ = กล้องเลื่อนนุ่ม ไม่กระตุกตามหน้าที่สั่น/เปลี่ยนจุดแบบตัดฉับ
const focusRegion = (t, scenes, faces, subs) => {
  let cx = 0, cy = 0, w = 0, h = 0;
  for (let k = -3; k <= 3; k++) { const r = rawRegion(t + k * 0.1, scenes, faces, subs); cx += r.cx; cy += r.cy; w += r.w; h += r.h; }
  return {cx: cx / 7, cy: cy / 7, w: Math.min(1, w / 7), h: Math.min(1, h / 7)};
};

// วางวิดีโอในกล่องให้ "region" อยู่กลางและเห็นครบ · ไม่ซูมน้อยกว่า cover (ไม่มีขอบดำ) ไม่เกิน 4 เท่า (ไม่แตก)
// เต็มจอแนวตั้งกับคลิปแนวนอนที่ไม่มีจุดให้ซูม = ภาพเต็มกลางจอ + พื้นเบลอ
// โครงสร้างต้องคงที่ทั้งคลิป (วิดีโอตัวเดิมเสมอ เปลี่ยนแค่ style) — สร้าง <video> ใหม่ทุกฉาก = พรีวิวภาพค้าง
const View = ({video, bw, bh, srcW, srcH, region, blurBg}) => {
  const vs = {position: 'absolute', display: 'block', maxWidth: 'none'};
  const landscape = srcW > srcH; // คงที่ทั้งคลิป → ชั้นพื้นเบลอมี/ไม่มีตลอด ไม่ทำให้ remount
  const kCover = Math.max(bw / srcW, bh / srcH);
  const kFit = Math.min(bw / (region.w * srcW), bh / (region.h * srcH));
  let box;
  if (blurBg && Math.abs(bw / bh - srcW / srcH) > 0.15 && kFit < kCover * 1.05) {
    const kc = Math.min(bw / srcW, bh / srcH);
    box = {left: (bw - srcW * kc) / 2, top: (bh - srcH * kc) / 2, width: srcW * kc, height: srcH * kc};
  } else {
    const k = Math.min(kCover * 4, Math.max(kCover, kFit));
    const vw = srcW * k, vh = srcH * k;
    box = {left: Math.min(0, Math.max(bw - vw, bw / 2 - region.cx * vw)), top: Math.min(0, Math.max(bh - vh, bh / 2 - region.cy * vh)), width: vw, height: vh};
  }
  const blurOn = blurBg && box.height < bh - 2;
  return (
    <>
      {landscape && <OffthreadVideo key="bg" src={asset(video)} muted style={{...vs, inset: 0, width: '100%', height: '100%', objectFit: 'cover', filter: 'blur(36px) brightness(.7)', transform: 'scale(1.15)', opacity: blurOn ? 1 : 0}} />}
      <OffthreadVideo key="main" src={asset(video)} muted style={{...vs, ...box}} />
    </>
  );
};

const Cam = ({scenes, video, srcW, srcH, faces, subs}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  let k = 0;
  for (let i = 0; i < scenes.length; i++) if (frame >= scenes[i].startF) k = i;
  const ar = srcW / srcH;
  const cur = camBox(scenes[k]?.cam || 'full', ar);
  const prev = k > 0 ? camBox(scenes[k - 1].cam || 'full', ar) : cur;
  const t = Math.min(1, (frame - (scenes[k]?.startF || 0)) / 8);
  const e = Easing.out(Easing.back(1.4))(t);
  const b = {x: lerp(prev.x, cur.x, e), y: lerp(prev.y, cur.y, e), w: lerp(prev.w, cur.w, e), h: lerp(prev.h, cur.h, e), rot: lerp(prev.rot, cur.rot, e)};
  const fr = (t < 0.5 ? prev : cur).frame;
  const pad = fr === 'polaroid' ? 16 : 0;
  const outer = {position: 'absolute', left: b.x, top: b.y, width: b.w, height: b.h, transform: `rotate(${b.rot}deg)`, boxSizing: 'border-box'};
  if (fr === 'circle') {
    const d = Math.min(b.w, b.h);
    Object.assign(outer, {width: d, height: d, borderRadius: '50%', border: '10px solid #facc15', boxShadow: `0 0 0 6px ${INK}, 10px 12px 0 rgba(0,0,0,.25)`});
  } else if (fr === 'polaroid') {
    Object.assign(outer, {background: '#fcfaf4', padding: pad, border: `5px solid ${INK}`, boxShadow: '10px 12px 0 rgba(0,0,0,.25)'});
  }
  const iw = (fr === 'circle' ? Math.min(b.w, b.h) - 20 : b.w - pad * 2 - (fr === 'polaroid' ? 10 : 0));
  const ih = (fr === 'circle' ? iw : b.h - pad * 2 - (fr === 'polaroid' ? 10 : 0));
  const region = focusRegion(frame / fps, scenes, faces, subs);
  return (
    <div style={outer}>
      <div style={{position: 'relative', width: iw, height: ih, overflow: 'hidden', borderRadius: fr === 'circle' ? '50%' : 0, background: '#000'}}>
        <View video={video} bw={iw} bh={ih} srcW={srcW} srcH={srcH} region={region} blurBg={fr === 'none'} />
      </div>
      {fr === 'polaroid' && (
        <>
          <div style={{position: 'absolute', left: -22, top: -22, width: Math.min(150, b.w * 0.35), height: 40, background: '#3b82f6cc', transform: 'rotate(-14deg)'}} />
          <div style={{position: 'absolute', right: -22, top: -22, width: Math.min(150, b.w * 0.35), height: 40, background: '#facc15cc', transform: 'rotate(12deg)'}} />
        </>
      )}
    </div>
  );
};

// ---------- ซับเต็มล่าง ----------
const Subs = ({subs, font, fps}) => {
  const frame = useCurrentFrame();
  const t = frame / fps;
  const cur = subs.find((s) => t >= s.start && t < s.end);
  if (!cur) return null;
  const since = Math.floor((frame - cur.start * fps) / STEP);
  const pop = since === 0 ? 0.8 : since === 1 ? 1.08 : 1;
  return (
    <div style={{position: 'absolute', left: 30, right: 30, bottom: H * 0.035, display: 'flex', justifyContent: 'center'}}>
      <div style={{fontFamily: font, fontWeight: 800, fontSize: 66, color: '#fff', textAlign: 'center', lineHeight: 1.25,
        WebkitTextStroke: `14px ${INK}`, paintOrder: 'stroke fill', transform: `scale(${pop})`, textShadow: '5px 6px 0 rgba(0,0,0,.35)'}}>{cur.text}</div>
    </div>
  );
};

const SceneLayer = ({sc, idx, layer, font}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const step = Math.floor(frame / STEP);
  const T = TRANS[idx === 0 ? 'cut' : sc.transition || 'slide'] || [];
  const [scale, dx, dy, rot] = step < T.length ? T[step] : [1, 0, 0, 0];
  const seedKey = `s${idx}`;
  const tf = {transform: `translate(${dx}px,${dy}px) rotate(${rot}deg) scale(${scale})`};
  if (layer === 'bg') {
    if (sc.cam === 'full') return null; // กล้องเต็มจอทับพื้นอยู่แล้ว
    return <AbsoluteFill style={{...tf, overflow: 'hidden'}}><PaperBg bg={sc.bg} step={step} seedKey={seedKey} /></AbsoluteFill>;
  }
  const tagY = sc.cam === 'polaroid' ? 0.42 : sc.cam === 'full' ? 0.78 : 0.82;
  return (
    <AbsoluteFill style={tf}>
      {(sc.items || []).map((it, i) => <Item key={i} it={it} i={i} seedKey={seedKey} fps={fps} />)}
      {sc.title && <Title text={sc.title} color={sc.title_color} seedKey={seedKey} font={font} />}
      {sc.tags && sc.tags.length > 0 && <Tags tags={sc.tags} seedKey={seedKey} font={font} fps={fps} y={tagY} />}
    </AbsoluteFill>
  );
};

export const Explainer = ({video, srcW = 1080, srcH = 1920, face = null, faces = null, scenes = [], subs = [], fontName = 'Kanit', total = 30}) => {
  // โปรเจกต์เก่ามีแค่ face (จุดเดียวทั้งคลิป) → ทำเป็น track เดียว
  const fcs = faces || (face ? {tracks: [{id: 0, speaker: null, pts: [[0, face.x, face.y, face.size, face.size * srcW / srcH], [1e6, face.x, face.y, face.size, face.size * srcW / srcH]]}]} : null);
  const {fps} = useVideoConfig();
  const font = FONTS[fontName] || FONTS.Kanit;
  const sc = scenes.map((s) => ({...s, startF: Math.round(s.start * fps)}));
  const seq = (layer) => sc.map((s, i) => {
    const next = sc[i + 1];
    const len = (next ? next.startF - s.startF + OVER : total - s.startF) || 1;
    return (
      <Sequence key={layer + i} from={s.startF} durationInFrames={len} layout="none">
        <SceneLayer sc={s} idx={i} layer={layer} font={font} />
      </Sequence>
    );
  });
  return (
    <AbsoluteFill style={{background: '#111'}}>
      {seq('bg')}
      {video && <Cam scenes={sc} video={video} srcW={srcW} srcH={srcH} faces={fcs} subs={subs} />}
      {seq('fg')}
      <Subs subs={subs} font={font} fps={fps} />
    </AbsoluteFill>
  );
};
