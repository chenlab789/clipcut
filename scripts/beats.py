#!/usr/bin/env python
"""วางกล้องแบบ beat — AI อ่านบทแล้วแบ่งเป็นช่วงความคิด (beat) แต่ละ beat เลือกขนาดภาพ 1 แบบค้างทั้งช่วง

ไอเดียจาก flow ตัดต่อมืออาชีพ: ถอดเสียง → ตัด → **วาง beat** → ใส่ของ → ตรวจ
  - ซูม = การเลือกช็อตของทั้งช่วง ไม่ใช่เอฟเฟกต์โปรย · เปลี่ยนช็อตแบบตัดฉับตรงรอยต่อ beat (ทับรอยตัด dead air = jump cut เนียน)
  - ห้ามซูมเข้าออกกลางประโยค (เดิม drift หายใจทั้งคลิป + punch ตามเสียงดัง = ซูมพร่ำเพรื่อ)
  - punch เลือกจาก "ความหมาย" (คำที่ต้องเน้นจริง) แล้วค่อยใช้จุดเสียงดังแค่จูนเวลาให้ตรงคำ
  - ซูมไปที่ของ: บทต้องพูดถึงของนั้น + ภาพต้องเห็น (smartcam ใช้ beat "object" เป็นตัวกรอง)

  wide   = ภาพปกติ (ไม่ใส่ fx)       medium = shot 1.15       close = shot 1.3
  object = ของที่กำลังโชว์ (smartcam หากรอบของแล้วใส่ focus)
"""
import re

SHOT_AMT = {"medium": 1.15, "close": 1.3}
BEAT_LEN = {1: "10-15", 2: "5-8", 3: "3-5"}  # density → beat ยาวกี่วิ
PUNCH_GAP = {1: 20, 2: 12, 3: 7}  # density → punch ห่างกันอย่างน้อยกี่วิ
# คำชี้ของ — ไม่มี beat (AI พัง) ก็ยังกรองซูมของด้วยคำพวกนี้
DEICTIC = re.compile(r"อันนี้|ตัวนี้|ชิ้นนี้|นี่ไง|ดูนี่|ดูสิ|ดูตรงนี้|ตรงนี้|แบบนี้นะ|เห็นมั้ย|เห็นไหม|โชว์|this one|look at|check this|right here")


def plan(subs, dur, cuts, opts, ai):
    """subs = ซับ (เวลาหลังตัด) · cuts = รอยตัด dead air · ai = autopilot.ai → [beat dict] เรียงเวลา"""
    dens = int(opts.get("density", 2))
    lines = "\n".join(f"{s['start']:.1f}-{s['end']:.1f}|{s.get('speaker') or ''}|{s['text']}" for s in subs)
    cut_txt = ", ".join(f"{c:.1f}" for c in cuts[:300]) or "-"
    prompt = f"""คุณคือช่างกล้อง/ตากล้องตัดต่อคลิปพูด ({'แนวตั้ง 9:16' if opts.get('aspect') == '9x16' else 'แนวนอน 16:9'} ยาว {dur:.0f} วิ)
บท (วินาที|คนพูด|ข้อความ):
{lines}

รอยตัดในคลิป (วินาที): {cut_txt}

งาน: แบ่งคลิปเป็น "beat" = ช่วงความคิดเดียวกัน (1 ประเด็น/มุก/ขั้นตอน) ยาวประมาณ {BEAT_LEN[dens]} วิ แล้วเลือกขนาดภาพของแต่ละ beat:
- "wide"   = ภาพปกติ — ใช้เป็นหลัก: เกริ่น อธิบาย เล่าเรื่องทั่วไป
- "medium" = ขยายนิดนึง — ประเด็นสำคัญ บอกตรงกับคนดู สรุป
- "close"  = ใกล้หน้า — พีค มุก อารมณ์แรง ช็อค ประโยคเด็ด (ใช้น้อยที่สุด)
- "object" = ซูมไปที่ของ — เฉพาะตอนที่คนพูด "กำลังโชว์/ชี้/พูดถึงของที่ถืออยู่" ชัดๆ ในบท (อันนี้/ตัวนี้/ดูนี่/ชื่อของที่ยกขึ้นมา) ใส่ "thing" = ชื่อของนั้น

กติกา:
- beat เริ่มตรงต้นประโยคเท่านั้น ห้ามเปลี่ยนกลางประโยค · ถ้ามีรอยตัดใกล้ต้นประโยค (ห่าง ≤0.6 วิ) ใช้เวลารอยตัด (ตัดฉับทับรอยตัด = เนียน)
- beat ติดกันห้ามใช้ขนาดเดียวกัน (ยกเว้น wide) · หลัง close ต้องกลับ wide หรือ medium
- คลิปแกะกล่อง/รีวิว/กินของ: ตอนเผยของ ยกของขึ้นโชว์ หรือชมของที่ถืออยู่ ("ตัวนี้" "น่ารัก" "ดูดิ") = object ได้หลายครั้ง
- สัดส่วนโดยประมาณ: wide 50% · medium 35% · close 15% · object เฉพาะที่บทชัดเท่านั้น (ไม่มีก็ไม่ต้องใส่)
- "emph" = วินาทีของคำเดียวใน beat ที่ควรซูมกระแทก (คำพีคจริงที่ความหมายแรง ไม่ใช่แค่พูดดัง) ไม่มีใส่ null · ทั้งคลิปไม่เกิน {max(1, int(dur / PUNCH_GAP[dens]))} จุด ห่างกัน ≥{PUNCH_GAP[dens]} วิ
- 2 วิแรกของคลิปควรเป็น medium หรือ close (hook)

ตอบ JSON: {{"beats": [{{"start": s, "shot": "wide|medium|close|object", "thing": null, "emph": null, "why": "<สั้นๆ>"}}]}}"""
    try:
        r = ai(prompt)
    except BaseException as ex:  # ai() พัง = SystemExit — ไม่มี beat ก็ยังตัดคลิปต่อได้
        print(f"  ! AI วาง beat ไม่ได้: {ex}", flush=True)
        return []
    return clean(r.get("beats") if isinstance(r, dict) else r, subs, dur, cuts)


def clean(raw, subs, dur, cuts):
    """จัด beat ให้ถูกกติกา: เริ่มต้นประโยค/รอยตัด · เรียง · ไม่ซ้ำขนาดติดกัน · ใส่ end"""
    starts = sorted({round(s["start"], 3) for s in subs} | {0.0})
    out = []
    for b in raw or []:
        try:
            t = float(b.get("start"))
        except (TypeError, ValueError):
            continue
        shot = b.get("shot") if b.get("shot") in ("wide", "medium", "close", "object") else "wide"
        if not 0 <= t < dur - 0.5:
            continue
        c = min(cuts, key=lambda x: abs(x - t)) if cuts else None
        s = min(starts, key=lambda x: abs(x - t))
        t = c if c is not None and abs(c - t) <= 0.6 else s  # รอยตัดก่อน ไม่งั้นต้นประโยค
        emph = b.get("emph")
        emph = float(emph) if isinstance(emph, (int, float)) else None
        out.append({"start": round(t, 3), "shot": shot, "thing": (str(b.get("thing") or "").strip() or None) if shot == "object" else None,
                    "emph": emph, "why": str(b.get("why") or "")[:80]})
    out.sort(key=lambda b: b["start"])
    merged = []
    for b in out:  # เวลาเดียวกัน/ขนาดเดียวกันติดกัน = beat เดียว
        if merged and (b["start"] - merged[-1]["start"] < 1.2 or (b["shot"] == merged[-1]["shot"] and b["shot"] != "object")):
            if b["emph"] is not None and merged[-1]["emph"] is None:
                merged[-1]["emph"] = b["emph"]
            continue
        merged.append(b)
    if not merged or merged[0]["start"] > 0:
        merged.insert(0, {"start": 0.0, "shot": "wide", "thing": None, "emph": None, "why": ""})
    for a, b in zip(merged, merged[1:] + [{"start": dur}]):
        a["end"] = round(b["start"], 3)
    return [b for b in merged if b["end"] - b["start"] > 0.3]


def to_items(E, beats, opts, new_id):
    """beat → fx items: shot (medium/close) + punch (emph) · object ไม่ใส่ที่นี่ (smartcam หาของเอง)"""
    dens = int(opts.get("density", 2))
    added, last_p = [], -99.0

    def add(it):  # ใส่ทันที — new_id ดู id ที่มีใน E แล้ว
        it["id"] = new_id("fx"); E["items"].append(it); added.append(it)
    subs = sorted((x for x in E["items"] if x["track"] == "sub"), key=lambda x: x["start"])
    for b in beats:
        if b["shot"] in SHOT_AMT:
            for s, e in speaker_parts(subs, b["start"], b["end"]):
                add({"track": "fx", "fx": "shot", "start": s, "end": e,
                     "amount": SHOT_AMT[b["shot"]], "auto": "beat", "beat": b["shot"]})
        e = b.get("emph")
        if e is not None and b["start"] - 0.2 <= e <= b["end"] and e - last_p >= PUNCH_GAP[dens] and b["shot"] != "object":
            add({"track": "fx", "fx": "punch", "start": round(max(0, e - 0.03), 3),
                          "end": round(min(E["duration"], e + 0.42), 3), "amount": 1.12 if b["shot"] == "close" else 1.18,
                          "auto": "emph"})
            last_p = e
    E["beats"] = beats
    return added


def speaker_parts(subs, t0, t1, min_len=0.8):
    """beat เดียวมีหลายคนพูด → แบ่งช่วงตามคนพูด (ซูมจุดเดียวทั้ง beat = หน้าอีกคนหลุดกรอบ)
    แต่ละท่อนได้จุดซูมที่หน้าคนพูดท่อนนั้น = ตัดสลับแบบกล้องหลายตัว · ท่อนสั้นกว่า min_len รวมกับท่อนก่อน"""
    cuts = [t0]
    last = None
    for s in subs:
        if s["end"] <= t0 or s["start"] >= t1:
            continue
        sp = s.get("speaker")
        if last is not None and sp and sp != last and s["start"] - cuts[-1] >= min_len and t1 - s["start"] >= min_len:
            cuts.append(round(s["start"], 3))
        last = sp or last
    return list(zip(cuts, cuts[1:] + [t1]))


def object_spans(beats):
    """beat ที่บทบอกว่ากำลังโชว์ของ → [(t0, t1, thing)]"""
    return [(b["start"], b["end"], b.get("thing")) for b in beats if b["shot"] == "object"]
