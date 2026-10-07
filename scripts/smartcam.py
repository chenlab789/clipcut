#!/usr/bin/env python
"""ซูมอัจฉริยะ (แบบแปะเอฟเฟกต์) — 4 อย่าง

1. กล้องตามหน้าคนพูด: กรอบครอปขนาดคงที่ เลื่อนตามหน้าคนที่กำลังพูด (คลิปแนวนอน → 9:16 = ตัดเต็มจอตามคน แทนพื้นเบลอ)
   E["cam"] = {"mode": "follow"|"fit", "zoom": z, "w": cw, "h": ch, "path": [[t, x0, y0], ...]}
   w/h/x0/y0 = สัดส่วน 0-1 ของภาพต้นฉบับ (มุมซ้ายบนกรอบ) · ระหว่าง key = เส้นตรง
   ตัวเล่นสามที่ต้องสูตรตรงกัน: cam_at() ที่นี่ · camAt() ใน app.js · crop expr ใน render_edit
2. ซูมกระแทกตามจังหวะ: หาจุดเสียงเน้น (voice_peaks) ส่งให้ AI วาง punch + ขยับ punch ให้ตรงจุดเน้น
3. ซูมไปของที่ถือ/ชี้: AI ดูภาพทั้งคลิปทีละช่วง → เจอของ = fx "focus" (ซูมเข้าค้างแล้วออก) + กล้องเลื่อนไปหาของ
4. ซูมช้ากันภาพนิ่ง: ช่วงยาวที่ไม่มีเอฟเฟกต์ → zoomin/zoomout เบาๆ สลับกัน (auto: "drift") จบตรงรอยตัด

  python smartcam.py <edit.json> [--mode follow|fit] [--zoom 1.15]   คำนวณเส้นทางกล้องใหม่ (editor เรียกตอนกดสลับ)
"""
import os
import sys
import json
import subprocess
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ccfx  # noqa: E402

ZOOMS = ("punch", "zoomin", "zoomout", "shake", "focus")
STEP = 0.2  # = focus.FPS 5


def out_ar(E):
    W, H = ccfx.out_size(E.get("aspect", "9x16"))
    return W / H


def default_zoom(E):
    sw, sh = E["source_wh"]
    # สัดส่วนต่างกันมาก (แนวนอน → 9:16) กรอบ cover ก็แคบพอให้เลื่อนแล้ว · สัดส่วนเดียวกัน = ต้องซูมนิดนึงถึงมีที่ให้เลื่อน
    return 1.0 if abs(sw / sh - out_ar(E)) > 0.3 else 1.15


def window(E, zoom):
    """→ (w, h) ของกรอบครอป เป็นสัดส่วนของภาพต้นฉบับ"""
    sw, sh = E["source_wh"]
    ar = out_ar(E)
    cw = min(sw, sh * ar) / zoom  # พิกเซลต้นฉบับ
    return cw / sw, cw / ar / sh


def cam_on(E):
    c = E.get("cam")
    return bool(c and c.get("mode") == "follow" and c.get("path"))


def cam_at(E, t):
    """มุมซ้ายบนกรอบที่เวลา t (สัดส่วน) — = camAt ใน app.js"""
    p = E["cam"]["path"]
    if t <= p[0][0]:
        return p[0][1], p[0][2]
    if t >= p[-1][0]:
        return p[-1][1], p[-1][2]
    lo, hi = 0, len(p) - 1
    while hi - lo > 1:
        m = (lo + hi) // 2
        if p[m][0] <= t:
            lo = m
        else:
            hi = m
    a, b = p[lo], p[hi]
    f = (t - a[0]) / (b[0] - a[0]) if b[0] > a[0] else 0
    return a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f


def src_to_out(E, t, x, y):
    """จุดบนภาพต้นฉบับ → จุดบนเฟรมผลลัพธ์ (ก่อนซูมเอฟเฟกต์)"""
    if cam_on(E):
        x0, y0 = cam_at(E, t)
        return (x - x0) / E["cam"]["w"], (y - y0) / E["cam"]["h"]
    import focus
    return focus.to_composite(E, x, y)


def hold_on(E, t0, t1, cx, cy):
    """ช่วง t0-t1 กล้องจัดจุด (cx, cy ของต้นฉบับ) ไว้กลางกรอบ (คำสั่ง "ซูมเข้าขวด") · คืนขนาดกรอบ (w, h) ไว้คำนวณแรงซูม"""
    if not cam_on(E):
        return 1.0, 1.0
    w, h = E["cam"]["w"], E["cam"]["h"]
    x, y = round(min(max(cx - w / 2, 0), 1 - w), 4), round(min(max(cy - h / 2, 0), 1 - h), 4)
    a, b = t0 - 0.4, t1 + 0.4
    pa, pb = cam_at(E, a), cam_at(E, b)
    p = [k for k in E["cam"]["path"] if not a <= k[0] <= b]
    p += [[round(a, 3), *pa], [round(t0, 3), x, y], [round(t1, 3), x, y], [round(b, 3), *pb]]
    E["cam"]["path"] = sorted(p, key=lambda k: k[0])
    return w, h


# ---------- 1. กล้องตามหน้า ----------
def _speaker_at(subs, t):
    last = None
    for s in subs:
        if s["start"] <= t < s["end"]:
            return s.get("speaker")
        if s["end"] <= t and t - s["end"] < 1.5:
            last = s.get("speaker")
    return last


def _face(tr, t):
    p = tr["pts"]
    if not p:
        return None
    i = int(np.searchsorted([q[0] for q in p], t))
    best = min((p[j] for j in (i - 1, i) if 0 <= j < len(p)), key=lambda q: abs(q[0] - t))
    return best if abs(best[0] - t) <= 1.2 else None


def build_path(E, mode=None, zoom=None):
    """เขียน E["cam"] — ไม่เจอหน้าใครเลย = mode fit (ภาพเต็มแบบเดิม)"""
    old = E.get("cam") or {}
    mode = mode or old.get("mode") or "follow"
    zoom = float(zoom or old.get("zoom") or default_zoom(E))
    tracks = (E.get("faces") or {}).get("tracks") or []
    cw, ch = window(E, zoom)
    cam = {"mode": mode if tracks else "fit", "zoom": round(zoom, 3), "w": round(cw, 5), "h": round(ch, 5), "path": []}
    E["cam"] = cam
    if not tracks:
        return cam
    dur = E["duration"]
    subs = [x for x in E["items"] if x["track"] == "sub"]
    objs = [x for x in E["items"] if x["track"] == "fx" and x.get("box_src")]
    ts = np.arange(0, dur + STEP, STEP)
    tgt = []
    prev = (0.5, 0.5)
    for t in ts:
        c = None
        ob = next((o for o in objs if o["start"] - 0.3 <= t <= o["end"]), None)
        if ob:  # ของที่ยกโชว์อยู่นอกกรอบ → กล้องไปหาของ
            x0, y0, x1, y1 = ob["box_src"]
            c = ((x0 + x1) / 2, (y0 + y1) / 2)
        else:
            sp = _speaker_at(subs, t)
            tr = next((x for x in tracks if sp and x.get("speaker") == sp), tracks[0] if len(tracks) == 1 else None)
            f = _face(tr, t) if tr else None
            if f:
                c = (f[1], f[2] + f[4] * 0.6)  # หัวค่อนบน ไม่ใช่หน้ากลางจอพอดี
            else:  # ไม่รู้ใครพูด → กลางระหว่างทุกหน้าที่เห็น
                vis = [v for v in (_face(x, t) for x in tracks) if v]
                if vis:
                    c = (float(np.mean([v[1] for v in vis])), float(np.mean([v[2] + v[4] * 0.6 for v in vis])))
        prev = c or prev
        tgt.append(prev)
    # deadzone: หน้าขยับนิดหน่อยกล้องไม่ตาม (ภาพนิ่ง ไม่วูบวาบ)
    held, cur = [], tgt[0]
    for c in tgt:
        if abs(c[0] - cur[0]) > cw * 0.12 or abs(c[1] - cur[1]) > ch * 0.12:
            cur = c
        held.append(cur)
    pos = np.array([[min(max(x - cw / 2, 0), 1 - cw), min(max(y - ch / 2, 0), 1 - ch)] for x, y in held])
    # ย้ายไกล (สลับคนพูด/ไปหาของ) = ตัดฉับ · ย้ายใกล้ = เลื่อนนุ่ม 1 วิ
    jump = [0] + [i for i in range(1, len(pos)) if np.abs(pos[i] - pos[i - 1]).max() > 0.18] + [len(pos)]
    keys = []
    for a, b in zip(jump, jump[1:]):
        seg = pos[a:b].copy()
        if len(seg) > 2:
            k = 2
            seg = np.array([seg[max(0, i - k): i + k + 1].mean(0) for i in range(len(seg))])
        pts = [[float(ts[a + i]), float(seg[i][0]), float(seg[i][1])] for i in range(len(seg))]
        if keys:  # ตัดฉับ = ค้างที่เดิมจนถึง 1 มิลลิวิก่อน key ใหม่
            keys.append([pts[0][0] - 0.001, keys[-1][1], keys[-1][2]])
        keys += _simplify(pts, 0.004)
    cam["path"] = [[round(t, 3), round(x, 4), round(y, 4)] for t, x, y in keys]
    return cam


def _simplify(pts, tol):
    """ตัด key ที่อยู่บนเส้นตรงอยู่แล้ว (Ramer–Douglas–Peucker) — นิ่งทั้งคลิป = 2 key"""
    if len(pts) <= 2:
        return pts
    a, b = np.array(pts[0]), np.array(pts[-1])
    best, bi = 0, 0
    for i in range(1, len(pts) - 1):
        f = (pts[i][0] - a[0]) / max(b[0] - a[0], 1e-9)
        d = max(abs(pts[i][1] - (a[1] + (b[1] - a[1]) * f)), abs(pts[i][2] - (a[2] + (b[2] - a[2]) * f)))
        if d > best:
            best, bi = d, i
    if best <= tol:
        return [pts[0], pts[-1]]
    return _simplify(pts[: bi + 1], tol)[:-1] + _simplify(pts[bi:], tol)


def refocus(E):
    """fx ที่ AI ตั้งจุดจากภาพต้นฉบับ (fx_src) → คำนวณ fx_x/fx_y ใหม่ตามกล้องตอนนี้"""
    for it in E["items"]:
        if it["track"] == "fx" and it.get("fx_src"):
            m = (it["start"] + it["end"]) / 2
            x, y = src_to_out(E, m, *it["fx_src"])
            it["fx_x"], it["fx_y"] = round(min(max(x, 0), 1), 4), round(min(max(y, 0), 1), 4)


# ---------- 2. จุดเสียงเน้น ----------
def voice_peaks(src, n_max=40):
    """เสียงพูดดังเด่นกว่ารอบข้าง (เน้นคำ/ตะโกน/หัวเราะ) → [วินาที] เรียงตามเวลา"""
    raw = subprocess.run([os.environ.get("FFMPEG", "ffmpeg"), "-v", "error", "-i", src, "-ac", "1", "-ar", "16000",
                          "-f", "s16le", "-"], capture_output=True, check=True).stdout
    a = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    hop = 800  # 50ms
    n = len(a) // hop
    if n < 10:
        return []
    db = 20 * np.log10(np.sqrt((a[: n * hop].reshape(n, hop) ** 2).mean(1)) + 1e-9)
    speech = db[db > -45]
    if not len(speech):
        return []
    thr = np.median(speech) + 5
    out = []
    for i in range(n):
        w = db[max(0, i - 8): i + 9]  # ±0.4 วิ
        if db[i] >= thr and db[i] == w.max():
            t = i * 0.05
            if not out or t - out[-1][0] >= 1.0:
                out.append((t, db[i]))
    out = sorted(sorted(out, key=lambda x: -x[1])[:n_max])
    return [round(t, 2) for t, _ in out]


def snap_punches(E, peaks):
    for it in E["items"]:
        if it["track"] == "fx" and it["fx"] == "punch" and peaks:
            p = min(peaks, key=lambda x: abs(x - it["start"]))
            if abs(p - it["start"]) <= 0.35:
                d = it["end"] - it["start"]
                it["start"] = round(max(0, p - 0.03), 3)
                it["end"] = round(it["start"] + d, 3)


# ---------- 3. ของที่ถือ/ชี้ ----------
def scan_units(E, length=4.5):
    """ซับต่อกันเป็นช่วงละ ~4-5 วิ ให้ AI ดูภาพทีละช่วง"""
    subs = sorted((x for x in E["items"] if x["track"] == "sub"), key=lambda x: x["start"])
    units, cur = [], None
    for s in subs:
        if cur and s["start"] - cur["t0"] < length:
            cur["t1"] = s["end"]; cur["text"] += " " + s["text"]
        else:
            cur = {"id": len(units), "t0": s["start"], "t1": s["end"], "text": s["text"]}
            units.append(cur)
    return units


def key_at(units, res, t):
    u = next((u for u in units if u["t0"] - 0.3 <= t <= u["t1"] + 0.3), None)
    if not u:
        return None
    kf = None
    for k in res.get(u["id"]) or []:
        if t - u["t0"] >= k["at"] or kf is None:
            kf = k
    return kf


def add_focus_items(E, units, res, density):
    """AI เห็นของ (mode box) → fx "focus" · ทับ zoom ที่ AI วางไว้ = เอา focus (โชว์ของสำคัญกว่า)"""
    cap = max(1, int(E["duration"] / {1: 14, 2: 9, 3: 6}[density]))
    cand = []
    for u in units:
        ks = res.get(u["id"]) or []
        for i, k in enumerate(ks):
            if k["mode"] != "box":
                continue
            s = u["t0"] + k["at"]
            e = u["t0"] + ks[i + 1]["at"] if i + 1 < len(ks) else u["t1"]
            e = min(max(e, s + 1.5), s + 4.0, E["duration"])
            if e - s >= 1.0:
                cand.append((s, e, k["box"]))
    cand.sort(key=lambda c: (c[2][2] - c[2][0]) * (c[2][3] - c[2][1]))  # ของชิ้นเล็ก = ควรซูมก่อน
    added = []
    for s, e, box in cand:
        if len(added) >= cap or any(s < a["end"] + 0.5 and e > a["start"] - 0.5 for a in added):
            continue
        added.append({"track": "fx", "fx": "focus", "start": round(s, 3), "end": round(e, 3), "box_src": box,
                      "fx_src": [round((box[0] + box[2]) / 2, 4), round((box[1] + box[3]) / 2, 4)], "auto": "object"})
    if added:
        E["items"] = [x for x in E["items"] if not (x["track"] == "fx" and x["fx"] in ZOOMS
                      and any(x["start"] < a["end"] and x["end"] > a["start"] for a in added))]
    return added


def size_focus(E):
    """ซูมแค่ไหน = ให้ของกว้าง ~60% ของจอ (หลังกล้องครอปแล้ว) · ไม่เกิน 2.2 เท่า (ไม่แตก)"""
    cw, ch = (E["cam"]["w"], E["cam"]["h"]) if cam_on(E) else (1, 1)
    for it in E["items"]:
        if it["track"] == "fx" and it["fx"] == "focus" and it.get("box_src") and it.get("auto") == "object":
            x0, y0, x1, y1 = it["box_src"]
            big = max((x1 - x0) / cw, (y1 - y0) / ch)
            it["amount"] = round(min(2.2, max(1.25, 0.6 / max(big, 0.05))), 2)


# ---------- 4. ซูมช้ากันภาพนิ่ง ----------
def add_drift(E, cuts, density):
    amt = {1: 1.05, 2: 1.07, 3: 1.09}[density]
    zs = [x for x in E["items"] if x["track"] == "fx" and x["fx"] in ZOOMS]
    bounds = sorted({0.0, E["duration"], *[c for c in cuts if 0 < c < E["duration"]]})
    n = 0
    for a, b in zip(bounds, bounds[1:]):
        free, t = [], a
        for z in sorted((z for z in zs if z["end"] > a and z["start"] < b), key=lambda z: z["start"]):
            if z["start"] - 0.15 - t >= 3.0:
                free.append((t, z["start"] - 0.15))
            t = max(t, z["end"] + 0.15)
        if b - t >= 3.0:
            free.append((t, b))
        for s, e in free:
            k = max(1, round((e - s) / 6))
            step = (e - s) / k
            for j in range(k):  # เข้า-ออก-เข้า ต่อกันพอดี = หายใจเนียน ไม่กระตุก
                E["items"].append({"track": "fx", "fx": "zoomin" if (n + j) % 2 == 0 else "zoomout",
                                   "start": round(s + j * step, 3), "end": round(s + (j + 1) * step, 3),
                                   "amount": amt, "auto": "drift"})
            n += k


# ---------- รวม ----------
def run(E, proj, opts, cuts, new_id):
    """autopilot เรียกหลังวางเอฟเฟกต์ของ AI แล้ว"""
    import focus
    density = int(opts.get("density", 2))
    src = os.path.join(proj, E["video"])
    subs = [x for x in E["items"] if x["track"] == "sub"]
    print("  ตามหน้าคนในคลิป…", flush=True)
    E["faces"] = focus.track_faces(src, subs)
    units, res, added = scan_units(E), {}, []
    if opts.get("fx"):  # ปิดซูม/สั่น = เหลือแค่กล้องตามหน้า ไม่ต้องให้ AI ดูภาพ
        print(f"  เจอ {len(E['faces']['tracks'])} คน · AI ดูภาพหาของที่ยก/ชี้…", flush=True)
        res = focus.vision_focus(src, units, os.path.join(proj, "_focus"))
        added = add_focus_items(E, units, res, density)
    for it in added:
        E["items"].append(dict(it, id=new_id("fx")))
    # จุดซูมของเอฟเฟกต์ที่ AI วาง: ของที่ยก > หน้าคนพูด > กลางจอ
    for it in E["items"]:
        if it["track"] != "fx" or it["fx"] not in ZOOMS or it.get("fx_src"):
            continue
        m = (it["start"] + it["end"]) / 2
        k = key_at(units, res, m) or {"mode": "speaker"}
        if k["mode"] == "box":
            b = k["box"]; it["fx_src"] = [round((b[0] + b[2]) / 2, 4), round((b[1] + b[3]) / 2, 4)]
        elif k["mode"] == "speaker":
            f = focus.speaker_face(E, m)
            if f:
                it["fx_src"] = [round(f[1], 4), round(f[2] + f[4] * 0.3, 4)]
    build_path(E, "follow" if opts.get("cam", 1) else "fit")
    size_focus(E)
    if opts.get("fx") and opts.get("drift", 1):
        before = len(E["items"])
        add_drift(E, cuts, density)
        for it in E["items"][before:]:
            it["id"] = new_id("fx")
            f = focus.speaker_face(E, (it["start"] + it["end"]) / 2)
            if f:
                it["fx_src"] = [round(f[1], 4), round(f[2] + f[4] * 0.3, 4)]
    refocus(E)
    nobj = len(added)
    ndr = sum(1 for x in E["items"] if x.get("auto") == "drift")
    print(f"  กล้อง {'ตามหน้า' if cam_on(E) else 'ภาพเต็ม'} · ซูมไปที่ของ {nobj} จุด · ซูมช้ากันนิ่ง {ndr} ช่วง", flush=True)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("edit")
    ap.add_argument("--mode", choices=["follow", "fit"])
    ap.add_argument("--zoom", type=float)
    a = ap.parse_args()
    E = ccfx.load_edit(a.edit)
    build_path(E, a.mode, a.zoom)
    size_focus(E)
    refocus(E)
    ccfx.save_edit(a.edit, E)
    print(json.dumps({k: v for k, v in E["cam"].items() if k != "path"}, ensure_ascii=False), len(E["cam"]["path"]), "keys")


if __name__ == "__main__":
    main()
