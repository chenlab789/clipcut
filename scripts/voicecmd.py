"""คำสั่งเสียงตามบริบท — เฉินพูดสั่งคนตัดต่อในคลิปได้เลย ไม่ต้องมีคำปลุก

    "เอารูปกุ้งขึ้นตรงนี้ให้หน่อย" (ชี้)  → รูปถ่ายกุ้งจริงจากเน็ต (photos.py) ขึ้นข้างนิ้ว
    "ซูมเข้านี่ให้หน่อย"                  → ซูมเข้าจุดที่ชี้ / หน้าคนพูด
    "ใส่เสียงตูมตรงนี้"                    → เสียงประกอบ

detect(): AI อ่านบท (ข้อความล้วน) ชี้ว่าประโยคไหนเป็นคำสั่ง → from_ai() หาเวลาจบคำสั่ง · ซูม: locate() AI ดูภาพหาของ+จังหวะ
→ apply() วางเอฟเฟกต์หลังตัดแล้ว + ป้ายบนไทม์ไลน์ (E["commands"]) · ประโยคที่สั่งยังอยู่ในคลิปตามปกติ (เฉินสั่งไม่ให้ตัด)
"""
import os
import re
import subprocess

FF = "ffmpeg"
HAND_MODEL = os.path.join(os.path.expanduser("~"), ".clipcut", "models", "hand_landmarker.task")
HAND_URL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task"
TONES = re.compile(r"[\s่้๊๋็์ํ]")
ACTIONS = ("image", "zoom", "sfx")

PROMPT = """บทคลิปของเฉิน (ถอดเสียงอัตโนมัติ index|วินาที|ข้อความ):
{lines}

หา "คำสั่งตัดต่อ" — ประโยคที่เฉินพูดสั่งคนตัดต่อ/AI ให้ทำอะไรกับคลิปนี้ตอนตัดต่อ
เฉินมักเรียกคนตัดต่อว่า "กุ้ง" "กุ้งเต้น" "มึง" หรือไม่เรียกเลย เช่น "เอารูปกุ้งขึ้นตรงนี้ให้หน่อย" "กุ้งเต้นซูมเข้ามาตรงนี้" "ซูมเข้านี่ให้หน่อย"
"เดี๋ยวตอนกินน้ำช่วยซูมหน้ากูนะ" (สั่งล่วงหน้า) "ใส่เสียงตูมตรงนี้" — ประโยคเดียวอาจถูกตัดเป็นหลายท่อน (i ถึง i_end)
ไม่ใช่คำสั่ง: คุยกับคนในคลิปจริงๆ (บอกแฟนให้ซูมกล้องมือถือ) · เล่าเรื่องรูปที่เคยเห็น · พูดถึงอาหารกุ้งเต้น

ทำได้ (หนึ่งคำสั่งทำได้หลายอย่าง):
- image = รูปถ่ายจริง: query อังกฤษสั้นๆ ค้นแล้วเจอรูปนั้น ("orange fruit", "blue whale")
- zoom: target = ของ/คนที่ต้องอยู่กลางเฟรม ดูบริบทประโยครอบๆ (กำลังพูดถึงขวดน้ำ แล้วบอก "ซูมตรงนี้" = ขวดน้ำ · "ซูมหน้ากู" = หน้าเฉิน)
  later = ถ้าสั่งให้ซูม "ตอน..." ที่ยังไม่เกิดตอนพูด (เช่น "ตอนเฉินกินน้ำ") ไม่งั้น null · hold ไม่บอก = 3
- sfx: เลือกจาก {sfx}
point = true ถ้าอ้างตำแหน่ง ("ตรงนี้/ตรงนั้น/นี่")

ตอบ JSON อย่างเดียว (ไม่มี = []):
[{{"i": <index ท่อนแรก>, "i_end": <index ท่อนสุดท้าย>, "said": "<คำสั่งตามบท>", "point": true,
   "do": [{{"action": "zoom", "target": "ขวดน้ำ", "later": null, "hold": 3}}
          | {{"action": "image", "query": "...", "desc": "<ขอรูปอะไร>"}} | {{"action": "sfx", "sfx": "..."}}],
   "label": "<สรุปสั้นๆ เช่น ซูมขวดน้ำ / รูปส้ม>"}}]"""


def detect(segs, ai, sfx_names):
    """บททั้งคลิป → คำสั่ง (AI ข้อความล้วน แยกจาก pass1 — เคยฝากไว้ใน pass1 แล้วบางรอบตอบว่าง ทั้งที่สั่งชัดๆ 5 จุด)"""
    lines = "\n".join(f"{i}|{s['start']:.1f}|{s['text']}" for i, s in enumerate(segs) if s["text"].strip())
    try:
        r = ai(PROMPT.format(lines=lines, sfx=", ".join(sfx_names)))
    except BaseException as ex:  # ai() พัง = SystemExit
        print(f"  ! หาคำสั่งเสียงไม่ได้: {ex}", flush=True)
        return []
    return from_ai(segs, r if isinstance(r, list) else (r or {}).get("commands") or [])


def norm(s):
    return TONES.sub("", s)


def _chars(seg):
    """ตัวอักษรของวลี (ไม่รวมช่องว่าง) + เวลาแต่ละตัว — มีเวลารายตัว (seg.wt จาก EL) ใช้เลย · ไม่มี = เฉลี่ยทั้งวลี"""
    out = []
    ws = [w for w in seg.get("wt") or seg.get("words") or [] if (w.get("word") or "").strip()]
    if ws:
        for w in ws:
            t = [c for c in w["word"] if not c.isspace()]
            for k, c in enumerate(t):
                out.append((c, w["start"] + (w["end"] - w["start"]) * k / len(t)))
    else:
        t = [c for c in seg["text"] if not c.isspace()]
        for k, c in enumerate(t):
            out.append((c, seg["start"] + (seg["end"] - seg["start"]) * k / max(1, len(t))))
    return out


def _said_span(seg, said):
    """คำสั่งอยู่ช่วงไหนของวลี → (เริ่ม, จบ) · หาไม่เจอ = ทั้งวลี"""
    ch = [(c, t) for c, t in _chars(seg) if not TONES.match(c)]
    text, want = "".join(c for c, _ in ch), norm(said or "")
    if not ch or not want:
        return seg["start"], seg["end"]
    k = text.find(want)
    if k < 0:  # AI แก้คำนิดหน่อย → จับหัว/ท้าย 4 ตัว
        a, b = text.find(want[:4]), text.find(want[-4:])
        if a < 0 and b < 0:
            return seg["start"], seg["end"]
        k = a if a >= 0 else max(0, b + 4 - len(want))
        e = (b + 3) if b >= 0 else min(len(ch) - 1, k + len(want) - 1)
    else:
        e = k + len(want) - 1
    e = min(max(e, k), len(ch) - 1)
    return round(ch[k][1], 3), round(min(ch[e][1] + 0.25, seg["end"]), 3)


def from_ai(segs, cmds):
    """คำตอบ AI → [{id, t0, t1, said, point, do, label}] (เวลาต้นฉบับ) · เรียกก่อน drop_retakes (index ยังตรงบท)"""
    out = []
    for n, c in enumerate(cmds or []):
        if not isinstance(c, dict):
            continue
        i = c.get("i")
        if not isinstance(i, int) or not 0 <= i < len(segs):
            continue
        dos = [d for d in c.get("do") or [] if isinstance(d, dict) and d.get("action") in ACTIONS]
        if not dos:
            continue
        j = c.get("i_end") if isinstance(c.get("i_end"), int) and i <= c["i_end"] < min(len(segs), i + 6) else i
        t0, t1 = _said_span(segs[i], c.get("said")) if j == i else (segs[i]["start"], segs[j]["end"])
        out.append({"id": f"c{n + 1}", "t0": t0, "t1": t1, "said": str(c.get("said") or segs[i]["text"])[:80],
                    "point": bool(c.get("point")), "do": dos, "label": str(c.get("label") or "")[:40] or "คำสั่ง"})
    return out


# ---------- ปลายนิ้วชี้ (MediaPipe) ----------
def fingertip(src, t0, t1):
    """ช่วงที่พูดคำสั่ง → จุดปลายนิ้วชี้ (x, y ต้นฉบับ 0-1) · ไม่เจอท่าชี้ = None"""
    try:
        import numpy as np
        import mediapipe as mp
        if not os.path.exists(HAND_MODEL):
            import urllib.request
            os.makedirs(os.path.dirname(HAND_MODEL), exist_ok=True)
            urllib.request.urlretrieve(HAND_URL, HAND_MODEL)
        p = subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height:stream_side_data=rotation",
                                     "-of", "csv=p=0", src], text=True).strip().split("\n")[0].split(",")
        sw, sh = int(p[0]), int(p[1])
        if len(p) > 2 and p[2].strip().lstrip("-") in ("90", "270"):
            sw, sh = sh, sw
        k = 640 / max(sw, sh)
        w, h = int(sw * k) // 2 * 2, int(sh * k) // 2 * 2
        raw = subprocess.run([FF, "-v", "error", "-ss", f"{max(0, t0 - 0.3):.2f}", "-t", f"{t1 - t0 + 0.6:.2f}", "-i", src,
                              "-vf", f"fps=8,scale={w}:{h}", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"],
                             capture_output=True, check=True).stdout
        n = len(raw) // (w * h * 3)
        frames = np.frombuffer(raw[: n * w * h * 3], np.uint8).reshape(n, h, w, 3)
        V = mp.tasks.vision
        err = os.dup(2); nul = os.open(os.devnull, os.O_WRONLY); os.dup2(nul, 2)  # log C++ ของ MediaPipe ไม่ให้รกหน้าความคืบหน้า
        try:
            pts = _detect(V, mp, np, frames)
        finally:
            os.dup2(err, 2); os.close(err); os.close(nul)
        if not pts:
            return None
        xs, ys = sorted(p[0] for p in pts), sorted(p[1] for p in pts)
        return round(xs[len(xs) // 2], 4), round(ys[len(ys) // 2], 4)
    except Exception as ex:
        print(f"  ! หานิ้วไม่ได้: {ex}", flush=True)
        return None


def _detect(V, mp, np, frames):
    """ทุกเฟรม → ปลายนิ้วชี้ของมือที่ทำท่าชี้ [(x, y, ext)]"""
    det = V.HandLandmarker.create_from_options(V.HandLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=HAND_MODEL), num_hands=2, min_hand_detection_confidence=0.4))
    pts = []
    for f in frames:
        r = det.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(f)))
        for lm in r.hand_landmarks:
            d = lambda a, b: ((lm[a].x - lm[b].x) ** 2 + (lm[a].y - lm[b].y) ** 2) ** 0.5  # noqa: E731
            # นิ้วชี้เหยียด (ปลายไกลข้อมือกว่าข้อนิ้ว) และยื่นกว่านิ้วอื่น = ท่าชี้
            ext = d(8, 0) / max(d(5, 0), 1e-3)
            other = max(d(12, 0), d(16, 0)) / max(d(9, 0), 1e-3)
            if ext > 1.6 and ext > other + 0.25:
                pts.append((lm[8].x, lm[8].y, ext))
    det.close()
    return pts


# ---------- หาของที่ต้องซูม + จังหวะ (AI ดูภาพ) ----------
def _sheet(src, ts, out, hgt=420):
    """เฟรมตามเวลา ts → แผ่นเดียว 4 คอลัมน์ · แต่ละช่องมีเส้นตาราง 0.1 + เลขช่อง/เวลา"""
    import focus
    from PIL import Image, ImageDraw, ImageFont
    ims = []
    for k, t in enumerate(ts):
        im = focus._grid_frame(src, t, out + f".{k}.jpg", hgt)
        os.remove(out + f".{k}.jpg")
        d = ImageDraw.Draw(im)
        try:
            f = ImageFont.truetype("arial.ttf", 30)
        except OSError:
            f = ImageFont.load_default()
        d.rectangle([0, 0, 118, 38], fill=(0, 0, 0))
        d.text((6, 3), f"#{k} {t:.1f}s", fill=(255, 80, 80), font=f)
        ims.append(im)
    cols = min(4, len(ims))
    rows = (len(ims) + cols - 1) // cols
    w, h = ims[0].size
    S = Image.new("RGB", (cols * (w + 6), rows * (h + 6)), (40, 40, 40))
    for k, im in enumerate(ims):
        S.paste(im, (k % cols * (w + 6), k // cols * (h + 6)))
    S.save(out, quality=88)
    return out


def locate(cmds, src, workdir, ai):
    """คำสั่งซูม → {id: {"t": เวลาต้นฉบับที่เริ่มซูม, "t_end": ..., "box": [x0,y0,x1,y1] ของบนภาพต้นฉบับ}} · เรียก AI ครั้งเดียว"""
    import clipcut as cc
    dur = cc.probe_dur(src)
    os.makedirs(workdir, exist_ok=True)
    jobs = []
    for c in cmds:
        z = next((d for d in c["do"] if d["action"] == "zoom"), None)
        if not z:
            continue
        if z.get("later"):  # สั่งล่วงหน้า → ไล่ดู 20 วิถัดไปหาจังหวะ
            ts = [c["t1"] + 0.5 + k * 1.25 for k in range(16)]
        else:
            ts = [c["t0"] + (c["t1"] + 1.5 - c["t0"]) * k / 3 for k in range(4)]
        ts = [round(t, 2) for t in ts if t < dur - 0.2]
        if not ts:
            continue
        jobs.append((c, z, ts, _sheet(src, ts, os.path.join(workdir, f"_zoom_{c['id']}.jpg"))))
    if not jobs:
        return {}
    lines = "\n".join(
        f"- {c['id']}: เฉินพูดว่า \"{c['said']}\" → ซูมไปที่: {z.get('target') or 'สิ่งที่เฉินชี้/ยก/พูดถึงตอนนั้น'}"
        + (f" · ซูมตอน: {z['later']} (ยังไม่เกิดตอนพูด หาช่องที่เกิดจริง)" if z.get("later") else "")
        + f" → Read {sh} (ช่อง #0-#{len(ts) - 1})" for c, z, ts, sh in jobs)
    prompt = f"""เฉินสั่งซูมในคลิป หาว่าต้องซูมไปที่ไหน ช่วงไหน — แต่ละแผ่นคือเฟรมเรียงเวลา มุมซ้ายบนบอก #ช่อง เวลา · เส้นเหลือง = ตารางทุก 0.1 ของภาพ (เลขที่ขอบ)
{lines}

ตอบ JSON อย่างเดียว: {{"<id>": {{"cell": <ช่องที่เริ่มซูม>, "end_cell": <ช่องสุดท้ายที่ยังควรซูม หรือ null>, "box": [x0, y0, x1, y1]}}, ...}}
- box = กรอบของสิ่งที่ต้องซูมในช่อง cell เป็นสัดส่วน 0-1 ของภาพช่องนั้น (อ่านจากเส้นตาราง) ครอบให้พอดีของ ไม่ต้องเผื่อ
- ซูมหน้า = กรอบหน้า (หัวถึงคาง) · ซูมของ = กรอบของชิ้นนั้นทั้งชิ้น
- ไม่ได้สั่งล่วงหน้า: cell = ช่องที่เห็นของชัดสุด end_cell = null · สั่งล่วงหน้า: cell = ช่องแรกที่เหตุการณ์เกิด end_cell = ช่องสุดท้ายที่ยังเกิดอยู่
- หาไม่เจอจริงๆ = null"""
    try:
        r = ai(prompt, read=True, model="opus")
    except BaseException as ex:  # ai() พัง = SystemExit
        print(f"  ! AI หาจุดซูมไม่ได้: {ex}", flush=True)
        return {}
    out = {}
    for c, z, ts, sh in jobs:
        v = (r or {}).get(c["id"]) if isinstance(r, dict) else None
        try:
            k = int(v["cell"]); b = [min(max(float(x), 0.0), 1.0) for x in v["box"]]
            if not 0 <= k < len(ts) or b[2] - b[0] < 0.02 or b[3] - b[1] < 0.02:
                raise ValueError
        except (TypeError, KeyError, ValueError):
            continue
        e = v.get("end_cell")
        out[c["id"]] = {"t": ts[k], "t_end": ts[int(e)] if isinstance(e, int) and k <= e < len(ts) else None, "box": b,
                        "later": bool(z.get("later"))}
    return out


# ---------- วางเอฟเฟกต์ (หลังตัดแล้ว) ----------
def protect(spots):
    """ซูมแบบสั่งล่วงหน้า ("ตอนกินน้ำซูม") มักเป็นช่วงเงียบ → ห้ามตัด dead air ตรงนั้น (เคยโดนตัดทิ้ง ซูมไปตกรอยต่อถัดไป)"""
    return [(max(0.0, s["t"] - 0.4), (s["t_end"] or s["t"]) + 1.2) for s in spots.values() if s.get("later")]


def apply(E, cmds, outdir, src, to_out, sfx_ok, nid, ai, spots=None):
    """cmds (เวลาต้นฉบับ) → item บน timeline · to_out(t) = เวลาต้นฉบับ → เวลาหลังตัด · ai = autopilot.ai (เลือกรูป)"""
    import smartcam
    import edit_apply
    import photos
    pts = {c["id"]: fingertip(src, c["t0"], c["t1"]) if c["point"] and any(d["action"] == "image" for d in c["do"]) else None
           for c in cmds}
    if spots is None:  # ซูม: AI ดูภาพหาของ (ขวด/หน้า) + จังหวะ (สั่งล่วงหน้า) · autopilot หาไว้ก่อนตัดแล้ว
        spots = locate(cmds, src, os.path.join(outdir, "_focus"), ai)
    reqs = [{"key": c["id"], "query": str(d.get("query") or d.get("desc") or "")[:60], "desc": str(d.get("desc") or d.get("query") or "")[:60]}
            for c in cmds for d in c["do"] if d["action"] == "image" and (d.get("query") or d.get("desc"))]
    pics = {}
    if reqs:
        print(f"  หารูปจริง {len(reqs)} รูป: {', '.join(r['query'] for r in reqs)}", flush=True)
        pics = photos.find_all(reqs, os.path.join(outdir, "photos"), ai)
    out = []
    for c in cmds:
        t = round(max(0.0, to_out(c["t1"]) - 0.2), 3)  # ขึ้นตอนพูดคำสั่งจบ
        pt, done = pts.get(c["id"]), []
        for d in c["do"]:
            try:
                if d["action"] == "zoom":
                    hold = min(8.0, max(1.0, float(d.get("hold") or 3)))
                    sp, zt = spots.get(c["id"]), t
                    if sp and sp["later"]:  # "ตอนกูกินน้ำซูม…" = ซูมตอนที่เกิดจริง ไม่ใช่ตอนพูด
                        zt = round(to_out(sp["t"]), 3)
                        if sp["t_end"]:
                            hold = min(8.0, max(2.0, sp["t_end"] - sp["t"] + 1.0))
                    it = {"id": nid("z"), "track": "fx", "fx": "focus", "start": zt, "end": zt + hold,
                          "amount": round(min(2.2, max(1.2, float(d.get("amount") or 1.6))), 2), "cmd": c["id"]}
                    if sp:  # ของอยู่กลางเฟรม: กล้องเลื่อนไปจัดกลาง + แรงซูมตามขนาดของ (กว้าง ~60% จอ)
                        x0, y0, x1, y1 = sp["box"]
                        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
                        it["fx_src"], it["box_src"] = [round(cx, 4), round(cy, 4)], [round(v, 4) for v in sp["box"]]
                        cw, ch = smartcam.hold_on(E, zt, zt + hold, cx, cy)
                        it["amount"] = round(min(2.4, max(1.3, 0.6 / max((x1 - x0) / cw, (y1 - y0) / ch, 0.05))), 2)
                    elif E.get("faces"):  # AI หาไม่เจอ = ซูมหน้าคนพูด
                        import focus
                        f = focus.speaker_face(E, t + 0.5)
                        if f:
                            it["fx_src"] = [round(f[1], 4), round(f[2] + f[4] * 0.3, 4)]
                    it = edit_apply.fill(it, E)
                    # ซูมอื่นที่ทับช่วงนี้ออก (ซูมซ้อนกัน = จุดซูมตีกัน)
                    E["items"] = [x for x in E["items"] if not (x["track"] == "fx" and x["fx"] in ("shot", "punch", "zoomin", "zoomout", "focus")
                                  and not x.get("cmd") and not x.get("gap") and x["start"] < it["end"] and x["end"] > it["start"])]
                    E["items"].append(it); done.append("ซูม" + ("ตรงที่ชี้" if pt else ""))
                elif d["action"] == "image":
                    p = pics.get(c["id"])
                    if not p:
                        raise ValueError("หารูปไม่เจอ")
                    x, y = smartcam.src_to_out(E, t + 0.5, *pt) if pt else (0.5, 0.3)
                    x, y = min(max(x, 0.25), 0.75), min(max(y, 0.2), 0.75)
                    w = 0.62 if E["aspect"] == "9x16" else 0.34
                    E["items"].append(edit_apply.fill({"id": nid("b"), "track": "broll", "src": os.path.relpath(p, outdir).replace("\\", "/"),
                                                       "start": t, "end": t + 3.0, "x": round(x, 3), "y": round(y, 3), "w": w, "cmd": c["id"]}, E))
                    if "pop" in sfx_ok and not any(x["action"] == "sfx" for x in c["do"]):
                        E["items"].append(edit_apply.fill({"id": nid("a"), "track": "sfx", "sfx": "pop", "start": t, "vol": 0.8, "cmd": c["id"]}, E))
                    done.append("รูป" + ("ตรงที่ชี้" if pt else ""))
                elif d["action"] == "sfx" and d.get("sfx") in sfx_ok:
                    E["items"].append(edit_apply.fill({"id": nid("a"), "track": "sfx", "sfx": d["sfx"], "start": t, "vol": 0.9, "cmd": c["id"]}, E))
                    done.append("เสียง " + d["sfx"])
            except Exception as ex:
                print(f"  ! คำสั่ง \"{c['said']}\" ({d['action']}) ทำไม่ได้: {ex}", flush=True)
        out.append({"id": c["id"], "t": t, "said": c["said"], "label": c["label"], "done": done, "ok": bool(done),
                    **({"point": list(pt)} if pt else {})})
        print(f"  คำสั่ง \"{c['said']}\" → {', '.join(done) or 'ทำไม่ได้'}", flush=True)
    E["commands"] = out
    smartcam.refocus(E)
    return out
