#!/usr/bin/env python
"""หลายคลิป → คลิปเดียว แล้วเข้า autopilot ตามปกติ

  เล่าเรื่อง (story) : เรียงตามที่เฉินจัด · ไม่ตัดหัวท้าย
  รวมฉากฮา (funny)  : แต่ละคลิป = 1 ฉากจบในตัว · AI ตัดหัวท้ายให้เหลือช่วงฮา
                      ลำดับ: AI จัดจังหวะ (ฮาสุดไว้ต้น แรงไว้ท้าย สลับอารมณ์) หรือสุ่ม
ก่อนรวม: ทุกคลิปขนาด/สัดส่วน/fps/ความดังเท่ากัน (สัดส่วนไม่ตรง = ภาพเต็มกลางจอบนพื้นเบลอ)

ผล: <out>/<name>.mp4 (ต้นฉบับรวม) + segments.json (ถอดเสียงแล้ว เวลาตรงกับไฟล์รวม)
     clips = [{"name", "start", "end"}] เวลาบนไฟล์รวม → autopilot แปลงเป็นเวลาหลังตัด ใส่ E["clips"] (เส้นบน timeline)
"""
import os
import re
import sys
import json
import random
import shutil
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ccfx  # noqa: E402

FF = os.environ.get("FFMPEG", "ffmpeg")
FPS = 30
VOICE = -16.0


def probe(p):
    o = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height:stream_side_data=rotation:stream_tags=rotate:format=duration:format_tags=creation_time",
                        "-of", "json", p], capture_output=True, text=True).stdout
    j = json.loads(o or "{}")
    st = (j.get("streams") or [{}])[0]
    w, h = st.get("width", 0), st.get("height", 0)
    rot = 0
    for sd in st.get("side_data_list") or []:
        rot = int(sd.get("rotation", 0) or 0)
    rot = rot or int((st.get("tags") or {}).get("rotate", 0) or 0)
    if abs(rot) in (90, 270):  # มือถือถ่ายแนวตั้งเก็บเป็นแนวนอน+หมุน
        w, h = h, w
    fmt = j.get("format") or {}
    return {"w": w, "h": h, "dur": float(fmt.get("duration") or 0), "ctime": (fmt.get("tags") or {}).get("creation_time", "")}


def target_size(infos):
    """สัดส่วนที่เยอะสุดชนะ · ขนาด = คลิปแรกที่สัดส่วนนั้น (ปัดเลขคู่)"""
    vert = sum(1 for i in infos if i["h"] >= i["w"])
    want_v = vert * 2 >= len(infos)
    ref = next(i for i in infos if (i["h"] >= i["w"]) == want_v)
    k = min(1.0, 1920 / max(ref["w"], ref["h"]))
    return int(ref["w"] * k) // 2 * 2, int(ref["h"] * k) // 2 * 2


def normalize(src, dst, W, H, t0=0.0, t1=None):
    """→ mp4 ขนาด W×H 30fps เสียง 48k stereo ความดังเสียงพูด ≈ -16 LUFS · ตัด [t0, t1] ได้"""
    lufs = ccfx.measure_lufs(src)
    gain = max(-12.0, min(18.0, VOICE - lufs)) if lufs > -70 else 0.0
    vf = (f"[0:v]fps={FPS},split=2[a][b];[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=24:2[bg];"
          f"[b]scale={W}:{H}:force_original_aspect_ratio=decrease[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1,format=yuv420p[v];"
          f"[0:a]aresample=48000,volume={gain:.2f}dB[a2]")
    cut = ["-ss", f"{t0:.3f}"] + (["-to", f"{t1:.3f}"] if t1 else [])
    has_a = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", src],
                           capture_output=True, text=True).stdout.strip()
    if not has_a:  # คลิปไม่มีเสียง → ใส่เงียบ
        vf = vf.replace(f"[0:a]aresample=48000,volume={gain:.2f}dB[a2]", "anullsrc=r=48000:cl=stereo[a2]")
    subprocess.run([FF, "-y", "-v", "error", *cut, "-i", src, "-filter_complex", vf, "-map", "[v]", "-map", "[a2]",
                    "-shortest", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-r", str(FPS),
                    "-c:a", "aac", "-b:a", "192k", "-ac", "2", dst], check=True)


def concat(parts, out):
    lst = out + ".txt"
    open(lst, "w", encoding="utf-8").write("".join(f"file '{p.replace(chr(39), chr(39) + chr(92) + chr(39) + chr(39))}'\n" for p in parts))
    subprocess.run([FF, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", "-movflags", "+faststart", out], check=True)
    os.remove(lst)


def scene_plan(parts, segs, bounds, order, workdir):
    """รวมฉากฮา: AI ดูภาพ 3 เฟรม + บทของแต่ละฉาก → ช่วงที่ฮา [a, b] (+ ลำดับถ้า order=ai)"""
    import autopilot
    from PIL import Image, ImageDraw
    rows, desc = [], []
    for i, (p, (s, e)) in enumerate(zip(parts, bounds)):
        d = e - s
        ims = []
        for k, f in enumerate((0.2, 0.5, 0.8)):
            fp = os.path.join(workdir, f"_sc{i}_{k}.jpg")
            subprocess.run([FF, "-y", "-v", "error", "-ss", f"{d * f:.2f}", "-i", p, "-frames:v", "1", "-vf", "scale=-2:200", fp], capture_output=True)
            if os.path.exists(fp):
                ims.append(Image.open(fp).convert("RGB")); os.remove(fp)
        row = Image.new("RGB", (sum(x.width for x in ims) + 60, (ims[0].height if ims else 200) + 8), (25, 25, 25))
        ImageDraw.Draw(row).text((8, row.height // 2), f"#{i}", fill=(255, 255, 0))
        x = 56
        for im in ims:
            row.paste(im, (x, 4)); x += im.width + 2
        rows.append(row)
        lines = [f"{t['start'] - s:.1f}-{t['end'] - s:.1f}: {t['text']}" for t in segs if s <= t["start"] < e]
        desc.append(f"#{i} ยาว {d:.1f} วิ\n" + ("\n".join(lines) or "(ไม่มีคนพูด)"))
    sh = Image.new("RGB", (max(r.width for r in rows), sum(r.height for r in rows)), (25, 25, 25))
    y = 0
    for r in rows:
        sh.paste(r, (0, y)); y += r.height
    sp = os.path.join(workdir, "_scenes.jpg")
    sh.save(sp, quality=85)
    ask_order = order == "ai"
    prompt = f"""Read ภาพนี้: {sp}
คลิปรวมฉากฮา (TikTok) — แต่ละแถว = 1 ฉากจบในตัว (ภาพ 3 เฟรม) · บทแต่ละฉาก (วินาทีในฉาก: ข้อความ):
{chr(10).join(desc)}

1) แต่ละฉาก เลือกช่วงที่ควรเก็บ [a, b] (วินาทีในฉาก): ตัดช่วงเตรียมตัว/คุยเรื่องอื่น/หลังมุกจบที่ยืด
   ให้เหลือ setup สั้นๆ + มุก/เหตุการณ์ฮา + reaction · ไม่แน่ใจ = เก็บทั้งฉาก · ห้ามตัดกลางประโยค (ดูเวลาบท)
{"2) เรียงลำดับฉากให้คนดูไม่เลื่อนผ่าน: ฉากฮา/แรงสุดไว้แรก (ดึงใน 3 วิ) ฉากแรงรองลงมาไว้ท้าย ตรงกลางสลับอารมณ์ไม่ซ้ำติดกัน" if ask_order else ""}
ตอบ JSON: {{"scenes": [{{"i": <เลข>, "a": <วิ>, "b": <วิ>, "why": "<สั้นๆ>"}}]{', "order": [<เลขฉากเรียงตามลำดับที่ควรเล่น>]' if ask_order else ""}}}"""
    r = autopilot.ai(prompt, read=True, model="opus")
    trims = {}
    for sc in r.get("scenes", []):
        i = sc.get("i")
        if isinstance(i, int) and 0 <= i < len(parts):
            d = bounds[i][1] - bounds[i][0]
            a, b = max(0.0, float(sc.get("a", 0))), min(d, float(sc.get("b", d)))
            trims[i] = (a, b) if b - a >= 1.0 else (0.0, d)
    od = [i for i in r.get("order", []) if isinstance(i, int) and 0 <= i < len(parts)] if ask_order else []
    od = list(dict.fromkeys(od)) + [i for i in range(len(parts)) if i not in od]
    return trims, (od if ask_order else list(range(len(parts))))


def build(clips, outdir, name, kind="story", order="manual", log=print):
    """→ (ไฟล์รวม, segments, clips[{name,start,end}])"""
    os.makedirs(outdir, exist_ok=True)
    work = os.path.join(outdir, "_multi")
    os.makedirs(work, exist_ok=True)
    infos = [probe(c) for c in clips]
    W, H = target_size(infos)
    if kind == "funny" and order == "random":
        idx = list(range(len(clips))); random.shuffle(idx)
        clips, infos = [clips[i] for i in idx], [infos[i] for i in idx]
    log(f"  รวม {len(clips)} คลิป → {W}x{H}")
    parts = []
    for i, c in enumerate(clips):
        p = os.path.join(work, f"part{i:02d}.mp4")
        log(f"  เตรียมคลิป {i + 1}/{len(clips)}: {os.path.basename(c)}")
        normalize(c, p, W, H)
        parts.append(p)
    merged = os.path.join(outdir, name + ".mp4")
    concat(parts, merged)
    bounds, t = [], 0.0
    for p in parts:
        d = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p],
                                 capture_output=True, text=True).stdout.strip())
        bounds.append((t, t + d)); t += d
    seg_json = os.path.join(outdir, name + ".segments.json")
    log("  ถอดเสียงคลิปรวม…")
    subprocess.run([sys.executable, os.path.join(HERE, "transcribe.py"), merged, seg_json, "medium"], check=True)
    data = ccfx.load_edit(seg_json)
    segs = data["segments"]
    names = [os.path.basename(c) for c in clips]
    if kind == "funny":
        log("  AI ดูแต่ละฉาก ตัดหัวท้ายให้เหลือช่วงฮา" + (" + จัดลำดับ" if order == "ai" else ""))
        trims, od = scene_plan(parts, segs, bounds, order, work)
        # สร้างไฟล์รวมใหม่ตามลำดับ+ช่วงที่ตัด แล้วเลื่อนเวลาบทตาม (ไม่ต้องถอดเสียงซ้ำ)
        parts2, new_segs, nb, t = [], [], [], 0.0
        for k, i in enumerate(od):
            s, e = bounds[i]
            a, b = trims.get(i, (0.0, e - s))
            p2 = os.path.join(work, f"scene{k:02d}.mp4")
            subprocess.run([FF, "-y", "-v", "error", "-ss", f"{a:.3f}", "-to", f"{b:.3f}", "-i", parts[i],
                            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-r", str(FPS), "-c:a", "aac", "-b:a", "192k", p2], check=True)
            d2 = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p2],
                                      capture_output=True, text=True).stdout.strip())
            for sg in segs:
                if s + a - 0.2 <= sg["start"] and sg["end"] <= s + b + 0.2:
                    g2 = dict(sg, start=round(t + max(0, sg["start"] - s - a), 3), end=round(t + min(d2, sg["end"] - s - a), 3))
                    for wd in g2.get("words") or []:
                        wd["start"] = round(t + max(0, wd["start"] - s - a), 3); wd["end"] = round(t + min(d2, wd["end"] - s - a), 3)
                    new_segs.append(g2)
            parts2.append(p2); nb.append((names[i], t, t + d2)); t += d2
            if (a, b) != (0.0, e - s):
                log(f"    ฉาก {names[i]}: เก็บ {a:.1f}-{b:.1f} จาก {e - s:.1f} วิ")
        concat(parts2, merged)
        data["segments"] = new_segs
        json.dump(data, open(seg_json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        out_clips = [{"name": n, "start": round(s, 3), "end": round(e, 3)} for n, s, e in nb]
    else:
        out_clips = [{"name": n, "start": round(s, 3), "end": round(e, 3)} for n, (s, e) in zip(names, bounds)]
    shutil.rmtree(work, ignore_errors=True)
    json.dump(out_clips, open(os.path.join(outdir, name + ".clips.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return merged, seg_json, out_clips


def drop_retakes(segs, sim=0.85, within=15.0):
    """พูดประโยคเดิมซ้ำติดกัน (พูดผิดแล้วพูดใหม่) → เก็บเทคสุดท้าย (ลบข้อความเทคก่อน = compute_keep ไม่เก็บช่วงนั้น)"""
    from difflib import SequenceMatcher
    norm = lambda x: re.sub(r"\s+", "", x)  # noqa: E731
    n = 0
    for i in range(len(segs) - 1):
        a = norm(segs[i]["text"])
        if len(a) < 8:
            continue
        for j in range(i + 1, min(len(segs), i + 4)):
            b = norm(segs[j]["text"])
            if segs[j]["start"] - segs[i]["end"] > within:
                break
            if len(b) >= 8 and SequenceMatcher(None, a, b[: len(a) + 4]).ratio() >= sim:
                segs[i]["text"] = ""; segs[i]["retake"] = True; n += 1
                break
    return n
