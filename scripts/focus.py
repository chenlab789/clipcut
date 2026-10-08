#!/usr/bin/env python
"""ซูมตามบริบท — หา "จุดที่คนดูควรมอง" ทีละช่วง

1. ตามหน้าทุกคน (YuNet ทุก 0.2 วิ) → แยกเป็นคน (track) · กรองตำแหน่งให้นิ่ง
2. จับคู่คนพูด: ปากใครขยับตอนตัวถอดเสียงบอกว่า speaker_X พูด → track นั้นคือ speaker_X
3. AI ดูภาพ (ภาพนิ่ง 2 ภาพ + ตารางพิกัด + ประโยคที่พูด) ทีละช่วง → มองคนพูด / มองของที่ยก-ชี้ (กรอบ) / ภาพกว้าง

ผล (พิกัด 0-1 ของภาพต้นฉบับ, เวลา = cut.mp4):
  E["faces"] = {"fps": 5, "tracks": [{"id", "speaker", "pts": [[t, cx, cy, w, h], ...]}]}
  focus ของแต่ละช่วง = [{"at": วินาทีหลังเริ่มช่วง, "mode": "speaker"|"box"|"wide", "box": [x0, y0, x1, y1]}]
  ตัวเล่นคำนวณกรอบกล้องจากนี้ (Explainer.jsx focusRegion / render_edit zoom) — สูตรต้องตรงกันทั้งสองที่

  python focus.py <edit.json>          ตามหน้า + จับคู่คนพูด (เขียน E["faces"])
"""
import os
import sys
import json
import subprocess
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
MODEL = os.path.join(os.path.dirname(HERE), "assets", "models", "yunet.onnx")
FF = os.environ.get("FFMPEG", "ffmpeg")
FPS = 5


def _frames(src, fps, long_side=960):
    p = subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                 "stream=width,height", "-of", "csv=p=0", src], text=True).strip().split(",")
    sw, sh = int(p[0]), int(p[1])
    k = long_side / max(sw, sh)
    w, h = int(sw * k) // 2 * 2, int(sh * k) // 2 * 2
    # อ่านทีละเฟรมจาก pipe — คลิป 24 นาทีถ้าโหลดรวดเดียว = ~11GB → MemoryError
    pr = subprocess.Popen([FF, "-v", "error", "-i", src, "-vf", f"fps={fps},scale={w}:{h}", "-pix_fmt", "bgr24",
                           "-f", "rawvideo", "-"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    def gen():
        size = w * h * 3
        try:
            while True:
                buf = pr.stdout.read(size)
                if len(buf) < size:
                    break
                yield np.frombuffer(buf, np.uint8).reshape(h, w, 3)
        finally:
            pr.stdout.close()
            pr.wait()
    return gen(), w, h


def track_faces(src, subs=None):
    """→ {"fps", "tracks": [...]} — หน้าที่โผล่น้อยกว่า 15% ของคลิปทิ้ง (คนเดินผ่าน/จับผิด)"""
    import cv2
    # คลิปยาวเกิน 10 นาที: ภาพเล็กลง + ห่างขึ้น (5→3 fps) — หาหน้า 24 นาทีจาก ~5.5 → ~2 นาที
    dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                         "-of", "csv=p=0", src], text=True).strip() or 0)
    fps, side = (3, 640) if dur > 600 else (FPS, 960)
    frames, w, h = _frames(src, fps, side)
    det = cv2.FaceDetectorYN.create(MODEL, "", (w, h), 0.75, 0.3, 50)
    tracks = []  # {pts, mouth: {t: crop}, last}
    n_frames = 0
    for i, fr in enumerate(frames):
        n_frames += 1
        t = round(i / fps, 2)
        _, faces = det.detect(fr)
        gray = None
        for f in (faces if faces is not None else []):
            x, y, fw, fh = f[:4]
            cx, cy, nw, nh = (x + fw / 2) / w, (y + fh / 2) / h, fw / w, fh / h
            best, bd = None, 0.12
            for tr in tracks:
                if t - tr["last"][0] > 1.5 or tr["last"][0] == t:
                    continue
                d = np.hypot(tr["last"][1] - cx, (tr["last"][2] - cy) * h / w)
                if d < bd:
                    best, bd = tr, d
            if best is None:
                best = {"pts": [], "mouth": {}, "last": None}
                tracks.append(best)
            best["pts"].append([t, cx, cy, nw, nh])
            best["last"] = (t, cx, cy)
            # ปาก: มุมปากขวา (10,11) ซ้าย (12,13) ของ landmark YuNet
            mx, my = (f[10] + f[12]) / 2, (f[11] + f[13]) / 2
            md = max(6.0, abs(f[12] - f[10]))
            if gray is None:
                gray = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
            x0, x1 = int(max(0, mx - md)), int(min(w, mx + md))
            y0, y1 = int(max(0, my - md * 0.6)), int(min(h, my + md * 0.6))
            if x1 - x0 > 3 and y1 - y0 > 3:
                best["mouth"][t] = cv2.resize(gray[y0:y1, x0:x1], (24, 12)).astype(np.float32)
    # คนเดียวกันหลุดเฟรม/หันหน้าไปพักนึง = โดนแยกเป็นหลาย track → รวมถ้าเวลาไม่ซ้อนกันและอยู่ที่เดียวกัน
    tracks.sort(key=lambda tr: tr["pts"][0][0])
    merged = []
    for tr in tracks:
        mx = np.median([p[1] for p in tr["pts"]])
        for m in merged:
            overlap = min(m["pts"][-1][0], tr["pts"][-1][0]) - max(m["pts"][0][0], tr["pts"][0][0])
            if overlap <= 0.4 and abs(np.median([p[1] for p in m["pts"]]) - mx) < 0.12:
                m["pts"] = sorted(m["pts"] + tr["pts"]); m["mouth"].update(tr["mouth"])
                break
        else:
            merged.append(tr)
    tracks = merged
    keep = [tr for tr in tracks if len(tr["pts"]) >= max(5, 0.15 * n_frames)]
    out = []
    for i, tr in enumerate(sorted(keep, key=lambda tr: np.median([p[1] for p in tr["pts"]]))):  # ซ้าย→ขวา
        a = np.array(tr["pts"])
        for c in range(1, 5):  # median 5 จุด = ตัดกระตุก
            col = a[:, c].copy()
            a[:, c] = [np.median(col[max(0, k - 2): k + 3]) for k in range(len(col))]
        energy = {}
        ts = sorted(tr["mouth"])
        for t0, t1 in zip(ts, ts[1:]):
            if t1 - t0 <= 1.3 / fps:  # เฟรมติดกัน
                energy[t1] = float(np.abs(tr["mouth"][t1] - tr["mouth"][t0]).mean())
        out.append({"id": i, "speaker": None, "pts": [[round(float(v), 4) for v in p] for p in a],
                    "_energy": energy})
    map_speakers(out, subs or [])
    for tr in out:
        tr.pop("_energy", None)
    return {"fps": fps, "tracks": out}


def map_speakers(tracks, subs):
    """ปากใครขยับมากสุดตอน speaker_X พูด = คนนั้น · คนเดียว = ทุกเสียงเป็นคนนั้น"""
    if not tracks:
        return
    spk = sorted({s.get("speaker") for s in subs if s.get("speaker")})
    if len(tracks) == 1 or len(spk) <= 1:
        tracks[0 if len(tracks) == 1 else int(np.argmax([len(t["pts"]) for t in tracks]))]["speaker"] = spk[0] if spk else "speaker_0"
        return
    score = np.zeros((len(spk), len(tracks)))
    for si, sp in enumerate(spk):
        spans = [(s["start"], s["end"]) for s in subs if s.get("speaker") == sp]
        for ti, tr in enumerate(tracks):
            e = [v for t, v in tr["_energy"].items() if any(a <= t <= b for a, b in spans)]
            score[si, ti] = np.mean(e) if e else 0
    used = set()
    for si in np.argsort(-score.max(1)):  # คนพูดที่ชัดสุดเลือกก่อน
        order = [ti for ti in np.argsort(-score[si]) if ti not in used]
        if order:
            tracks[order[0]]["speaker"] = spk[si]
            used.add(order[0])


# ---------- AI ดูภาพ ----------
def _grid_frame(src, t, out, hgt=420):
    from PIL import Image, ImageDraw
    subprocess.run([FF, "-y", "-v", "error", "-ss", f"{max(0, t):.2f}", "-i", src, "-frames:v", "1",
                    "-vf", f"scale=-2:{hgt}", out], check=True)
    im = Image.open(out).convert("RGB")
    d = ImageDraw.Draw(im)
    W, H = im.size
    for k in range(1, 10):  # เส้นตารางทุก 0.1 + ตัวเลขที่ขอบ
        x, y = W * k / 10, H * k / 10
        d.line([(x, 0), (x, H)], fill=(255, 255, 0), width=1)
        d.line([(0, y), (W, y)], fill=(255, 255, 0), width=1)
        d.text((x + 2, 2), f".{k}", fill=(255, 255, 0))
        d.text((2, y + 1), f".{k}", fill=(255, 255, 0))
    return im


def vision_focus(src, units, workdir, model="opus"):
    """units = [{"id", "t0", "t1", "text"}] → {id: [focus keyframes]} · AI ดูทีละแผ่น (6 ช่วง/แผ่น)"""
    import autopilot
    from PIL import Image, ImageDraw
    os.makedirs(workdir, exist_ok=True)
    result = {}

    def one(b):
        batch = units[b: b + 6]
        rows, desc = [], []
        for u in batch:
            d = max(0.4, u["t1"] - u["t0"])
            ims = [_grid_frame(src, u["t0"] + d * f, os.path.join(workdir, f"_f{u['id']}_{k}.png"))
                   for k, f in enumerate((0.3, 0.75))]
            row = Image.new("RGB", (sum(i.width for i in ims) + 16, ims[0].height + 30), (20, 20, 20))
            ImageDraw.Draw(row).text((6, 6), f"#{u['id']}   (A = +{d * 0.3:.1f}s   B = +{d * 0.75:.1f}s)", fill=(255, 255, 255))
            x = 0
            for im in ims:
                row.paste(im, (x, 30)); x += im.width + 16
            rows.append(row)
            desc.append(f"#{u['id']} ยาว {d:.1f} วิ พูดว่า: {u['text'][:200]}")
        sheet = Image.new("RGB", (max(r.width for r in rows), sum(r.height for r in rows)), (20, 20, 20))
        y = 0
        for r in rows:
            sheet.paste(r, (0, y)); y += r.height
        sp = os.path.join(workdir, f"_focus_{b // 6}.png")
        sheet.save(sp)
        prompt = f"""Read ภาพนี้: {sp}
แต่ละแถว = 1 ช่วงของวิดีโอ (#id) มีภาพนิ่ง 2 ภาพ (A, B) ทับตารางพิกัดสีเหลือง (เส้นทุก 0.1 ของกว้าง/สูงภาพ)
{chr(10).join(desc)}

งาน: เลือกว่าแต่ละช่วงกล้องควรซูมไปที่ไหน ให้คนดูเห็นสิ่งที่คนในคลิปอยากให้ดู
- "speaker" = หน้าคนที่กำลังพูด (ค่าปกติ ส่วนใหญ่ใช้อันนี้)
- "box" = มีของ/จุดที่ควรดูชัดๆ: คนยกของโชว์ ชี้ไปที่อะไร ถือเมนู/มือถือให้กล้องดู หรือบนจอมีสิ่งที่กำลังพูดถึง → ให้กรอบ [x0,y0,x1,y1] เป็นสัดส่วน 0-1 ของภาพ (อ่านจากตาราง) ครอบของนั้นพอดี
- "wide" = หลายคนทำอะไรด้วยกัน/บรรยากาศ/ไม่มีจุดเด่น → ภาพกว้าง
ถ้าในช่วงเดียวเปลี่ยนจุด (เช่นพูดก่อนแล้วค่อยยกของ) ให้หลายจุดพร้อม "at" = วินาทีหลังเริ่มช่วง (ดูจากเวลา A/B)
อย่าเลือก box ถ้าไม่เห็นของชัดในภาพ (คำพูดอย่างเดียวไม่พอ)

ตอบ JSON: {{"units": [{{"id": <id>, "focus": [{{"at": 0, "mode": "speaker|box|wide", "box": [x0,y0,x1,y1]}}], "why": "<สั้นๆ>"}}]}}"""
        try:
            r = autopilot.ai(prompt, read=True, model=model)
            for u in r.get("units", []):
                result[u.get("id")] = clean_focus(u.get("focus"))
        except BaseException as e:  # ai() พังแบบ SystemExit — แผ่นเดียวพังไม่ให้ล้มทั้งงาน
            print(f"  ! AI ดูภาพแผ่น {b // 6} ไม่ได้: {e}", flush=True)

    # ยิงพร้อมกัน 4 แผ่น (เดิมทีละแผ่น ~23 วิ/แผ่น → คลิป 24 นาที ~20 นาที)
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(4) as ex:
        list(ex.map(one, range(0, len(units), 6)))
    return result


def clean_focus(fs):
    out = []
    for f in fs or []:
        m = f.get("mode") if f.get("mode") in ("speaker", "box", "wide") else "speaker"
        k = {"at": round(max(0.0, float(f.get("at", 0) or 0)), 2), "mode": m}
        if m == "box":
            try:
                x0, y0, x1, y1 = [min(1.0, max(0.0, float(v))) for v in f["box"]]
                if x1 - x0 < 0.03 or y1 - y0 < 0.03:
                    raise ValueError
                k["box"] = [round(min(x0, x1), 3), round(min(y0, y1), 3), round(max(x0, x1), 3), round(max(y0, y1), 3)]
            except Exception:
                k["mode"] = "speaker"
        out.append(k)
    return sorted(out, key=lambda k: k["at"]) or [{"at": 0, "mode": "speaker"}]


def speaker_face(E, t):
    """หน้าคนที่พูดตอน t (พิกัดต้นฉบับ) หรือ None — ตรรกะเดียวกับ rawRegion ใน Explainer.jsx"""
    tracks = (E.get("faces") or {}).get("tracks") or []
    if not tracks:
        return None
    sp = None
    for s in E["items"]:
        if s["track"] != "sub":
            continue
        if s["start"] <= t < s["end"]:
            sp = s.get("speaker"); break
        if s["end"] <= t and t - s["end"] < 1.5:
            sp = s.get("speaker")
    tr = next((x for x in tracks if sp and x["speaker"] == sp), tracks[0] if len(tracks) == 1 else None)
    if not tr:
        return None
    best = min(tr["pts"], key=lambda p: abs(p[0] - t))
    return best if abs(best[0] - t) <= 1.2 else None


def to_composite(E, x, y):
    """พิกัดต้นฉบับ → พิกัดบนเฟรมผลลัพธ์ (9:16 จากคลิปแนวนอน = ภาพวางกลางจอบนพื้นเบลอ)"""
    sw, sh = E.get("source_wh", [1080, 1920])
    W, H = (1080, 1920) if E.get("aspect", "9x16") == "9x16" else (1920, 1080)
    if sw / sh > W / H:  # กว้างกว่าจอ → เต็มกว้าง ขอบบนล่าง
        fh = W * sh / sw
        return x, ((H - fh) / 2 + y * fh) / H
    fw = H * sw / sh
    return ((W - fw) / 2 + x * fw) / W, y


def fx_focus(E, proj, vision=True):
    """ซูมกระแทก/ซูมช้า (แบบแปะเอฟเฟกต์) → fx_x, fx_y = จุดที่ควรซูมเข้า (ของที่ยก/ชี้ ไม่งั้นหน้าคนพูด)"""
    src = os.path.join(proj, E["video"])
    subs = [x for x in E["items"] if x["track"] == "sub"]
    if not E.get("faces"):
        E["faces"] = track_faces(src, subs)
    zs = [x for x in E["items"] if x["track"] == "fx" and x["fx"] in ("punch", "zoomin", "zoomout", "shake")]
    res = {}
    if vision and zs:
        units = [{"id": i, "t0": max(0, x["start"] - 0.4), "t1": x["end"] + 0.4,
                  "text": " ".join(s["text"] for s in subs if s["start"] < x["end"] + 0.4 and s["end"] > x["start"] - 0.4)}
                 for i, x in enumerate(zs)]
        res = vision_focus(src, units, os.path.join(proj, "_focus"))
    for i, it in enumerate(zs):
        fs = res.get(i) or [{"at": 0, "mode": "speaker"}]
        kf = fs[-1] if len(fs) > 1 and fs[-1]["at"] <= 0.5 else fs[0]
        if kf["mode"] == "box":
            x0, y0, x1, y1 = kf["box"]
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        elif kf["mode"] == "speaker" and speaker_face(E, (it["start"] + it["end"]) / 2):
            p = speaker_face(E, (it["start"] + it["end"]) / 2)
            cx, cy = p[1], p[2] + p[4] * 0.3
        else:
            it.pop("fx_x", None); it.pop("fx_y", None); continue
        it["fx_x"], it["fx_y"] = [round(v, 4) for v in to_composite(E, cx, cy)]


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    import ccfx
    path = os.path.abspath(sys.argv[1])
    E = ccfx.load_edit(path)
    subs = [x for x in E["items"] if x["track"] == "sub"]
    F = track_faces(os.path.join(os.path.dirname(path), E["video"]), subs)
    E["faces"] = F
    ccfx.save_edit(path, E)
    for tr in F["tracks"]:
        print(f"  คน {tr['id']}: {len(tr['pts'])} จุด · {tr['speaker']} · x≈{np.median([p[1] for p in tr['pts']]):.2f}")


if __name__ == "__main__":
    main()
