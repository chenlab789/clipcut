#!/usr/bin/env python
"""ช่วงเงียบที่กำลังสาธิต/ทำให้ดู (พิมพ์ แกะกล่อง ต่อสาย) — ไม่ตัดทิ้ง แต่ เก็บ / เร่ง / ข้าม

ขั้นที่ 3 ของการตัด dead air (ต่อจาก compute_keep + tighten_keep):
  1. ช่วงที่จะโดนตัด ≥ 1.5 วิ → วัดภาพขยับ (เฟรมต่อเฟรม) เทียบช่วงที่พูด
  2. ภาพขยับพอ → AI ดูภาพ 4 เฟรม + ประโยคก่อน/หลัง ตัดสินว่า "สาธิต" หรือ "ว่าง"
  3. สาธิต: < 4 วิ = เก็บความเร็วปกติ · 4-24 วิ = เร่ง 2-4 เท่า (ป้าย ×N) · ยาวกว่านั้น = เก็บต้น+จบ (ข้าม)

ไฟล์:
  <base>.cut1.mp4  ตัดแล้ว ความเร็วปกติทุกช่วง (เก็บไว้ ให้ editor สลับ ตัด/เร่ง/ปกติ ได้โดยไม่ต้องตัดจากต้นฉบับใหม่)
  <base>.cut.mp4   ช่วงสาธิตยาวถูกเร่งแล้ว (= video_base ของ gaps.py)
E["speedups"] = [{"id","start","end","speed","mode","src"}]  start/end = เวลาบน timeline ผลลัพธ์ · mode = speed|normal|cut
"""
import os
import sys
import json
import math
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ccfx  # noqa: E402,F401  (ซ่อนหน้าต่าง subprocess)

FPS = 30
FF = os.environ.get("FFMPEG", "ffmpeg")
MIN_GAP = 1.5      # ช่วงเงียบสั้นกว่านี้ไม่ต้องดู (ตัดตามปกติ)
KEEP_MAX = 4.0     # สาธิตสั้นกว่านี้ = เก็บความเร็วปกติ
JUMP_OVER = 24.0   # ยาวกว่านี้ = เก็บต้น 2.5 วิ + จบ 2.5 วิ


def snap(t):
    return round(t * FPS) / FPS


def gaps_between(keep, dur):
    """ช่วงที่ keep ตัดทิ้ง (เวลาต้นฉบับ)"""
    out, cur = [], 0.0
    for s, e in keep:
        if s - cur >= MIN_GAP:
            out.append((cur, s))
        cur = e
    if dur - cur >= MIN_GAP:
        out.append((cur, dur))
    return out


def motion(src, spans, fps=4, w=96):
    """ค่าเฉลี่ยภาพขยับต่อช่วง (ต่างกันระหว่างเฟรม 0-255) — ถอดภาพจิ๋วทีเดียวทั้งคลิป"""
    import numpy as np
    h = w * 16 // 9
    p = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                        "-of", "csv=p=0", src], capture_output=True, text=True).stdout.strip().split(",")
    if len(p) == 2 and int(p[0]) > int(p[1]):
        w, h = h, w
    raw = subprocess.run([FF, "-v", "error", "-i", src, "-vf", f"fps={fps},scale={w}:{h},format=gray", "-f", "rawvideo", "-"],
                         capture_output=True, check=True).stdout
    n = len(raw) // (w * h)
    fr = np.frombuffer(raw[: n * w * h], np.uint8).reshape(n, h, w).astype(np.int16)
    d = np.abs(np.diff(fr, axis=0)).mean((1, 2)) if n > 1 else np.zeros(1)
    out = []
    for s, e in spans:
        a, b = int(s * fps), max(int(s * fps) + 1, int(e * fps))
        seg = d[a:b]
        out.append(float(seg.mean()) if len(seg) else 0.0)
    return out


def judge(src, cands, segs, workdir):
    """AI ดูภาพ 4 เฟรมต่อช่วง → {i: True ถ้าสาธิต}"""
    import autopilot
    from PIL import Image, ImageDraw
    os.makedirs(workdir, exist_ok=True)
    res = {}
    for b in range(0, len(cands), 6):
        part = cands[b: b + 6]
        rows, desc = [], []
        for k, (i, s, e) in enumerate(part):
            ims = []
            for j, f in enumerate((0.1, 0.4, 0.7, 0.95)):
                pth = os.path.join(workdir, f"_sp{i}_{j}.jpg")
                subprocess.run([FF, "-y", "-v", "error", "-ss", f"{s + (e - s) * f:.2f}", "-i", src, "-frames:v", "1",
                                "-vf", "scale=-2:240", pth], capture_output=True)
                if os.path.exists(pth):
                    ims.append(Image.open(pth).convert("RGB")); os.remove(pth)
            if not ims:
                continue
            row = Image.new("RGB", (sum(x.width for x in ims) + 60, ims[0].height + 8), (25, 25, 25))
            ImageDraw.Draw(row).text((8, ims[0].height // 2), f"#{i}", fill=(255, 255, 0))
            x = 56
            for im in ims:
                row.paste(im, (x, 4)); x += im.width + 2
            rows.append(row)
            before = " ".join(t["text"] for t in segs if t["end"] <= s + 0.5 and t["end"] > s - 6)[-80:]
            after = " ".join(t["text"] for t in segs if t["start"] >= e - 0.5 and t["start"] < e + 6)[:80]
            desc.append(f"#{i} เงียบ {e - s:.1f} วิ · ก่อนหน้าพูดว่า: {before or '-'} · หลังจากนั้นพูดว่า: {after or '-'}")
        if not rows:
            continue
        sh = Image.new("RGB", (max(r.width for r in rows), sum(r.height for r in rows)), (25, 25, 25))
        y = 0
        for r in rows:
            sh.paste(r, (0, y)); y += r.height
        sp = os.path.join(workdir, f"_speed_{b}.jpg")
        sh.save(sp, quality=85)
        prompt = f"""Read ภาพนี้: {sp}
แต่ละแถว = ช่วงที่คนในคลิปเงียบไม่พูด (4 เฟรมเรียงเวลา)
{chr(10).join(desc)}

แต่ละช่วง คนดูควรได้เห็นไหม:
- "demo" = กำลังทำ/โชว์ให้ดู: พิมพ์/กดจอ, แกะกล่อง/ประกอบของ, ทำอาหาร, ชี้ของ, จอเปลี่ยนตามที่สอน, ผลลัพธ์กำลังเกิด
- "dead" = ไม่มีอะไรให้ดู: นิ่ง คิดคำพูด เตรียมตัว หยิบของ ขยับกล้อง เดินไปมา
ตอบ JSON: {{"items": [{{"i": <เลข>, "kind": "demo|dead"}}]}}"""
        try:
            r = autopilot.ai(prompt, read=True, model="sonnet")
            for it in r.get("items", []):
                res[it.get("i")] = it.get("kind") == "demo"
        except Exception as ex:
            print(f"  ! AI ดูช่วงเงียบไม่ได้: {ex}", flush=True)
    return res


def plan(src, keep, segs, dur, workdir):
    """→ (keep ใหม่, speeds [(s, e, speed)] เวลาต้นฉบับ, รายงาน)"""
    gaps = gaps_between(keep, dur)
    if not gaps:
        return keep, [], []
    print(f"  ดูภาพช่วงเงียบ {len(gaps)} ช่วง หาช่วงสาธิต…", flush=True)
    speech = [(s, e) for s, e in keep if e - s > 0.8][:200]
    mv = motion(src, gaps + speech)
    gm, sm = mv[: len(gaps)], mv[len(gaps):]
    base = sorted(sm)[len(sm) // 2] if sm else 1.0
    # เทียบกับตอนพูดของคลิปนั้นเอง (กล้องถ่ายคน ~1-3 · อัดจอ ~0.05-0.1) — ขยับมากกว่าตอนพูด = น่าจะมีอะไรให้ดู ให้ AI ตัดสิน
    cands = sorted([(i, s, e, m) for i, ((s, e), m) in enumerate(zip(gaps, gm)) if m >= max(0.04, 1.2 * base)],
                   key=lambda c: -c[3])[:24]
    cands = sorted((i, s, e) for i, s, e, _ in cands)
    if not cands:
        return keep, [], []
    print(f"  ช่วงเงียบที่ภาพขยับ {len(cands)} ช่วง → AI ดูว่าเป็นช่วงสาธิตไหม…", flush=True)
    ok = judge(src, cands, segs, workdir)
    add, speeds, rep = [], [], []
    for i, s, e in cands:
        if not ok.get(i):
            continue
        d = e - s
        if d < KEEP_MAX:
            add.append((s, e)); rep.append(("เก็บ", s, d))
        elif d <= JUMP_OVER:
            sp = min(4, max(2, math.ceil(d / KEEP_MAX)))
            add.append((s, e)); speeds.append((snap(s), snap(e), sp)); rep.append((f"เร่ง ×{sp}", s, d))
        else:
            add += [(s, s + 2.5), (e - 2.5, e)]; rep.append(("ข้าม", s, d))
    k = sorted([(snap(a), snap(b)) for a, b in list(keep) + add])
    merged = []
    for a, b in k:
        if merged and a <= merged[-1][1] + 1e-6:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    return merged, speeds, rep


def out_time(t1, speeds1):
    """เวลาบน cut1 (ปกติทุกช่วง) → เวลาบน cut (เร่งแล้ว) · speeds1 = [(s1, e1, sp)] เวลาบน cut1"""
    acc = 0.0
    for s, e, sp in speeds1:
        if t1 <= s:
            break
        acc += (min(t1, e) - s) * (1 - 1 / sp)
    return t1 - acc


def to_cut1(speeds, keep):
    """speeds เวลาต้นฉบับ → เวลาบน cut1"""
    import clipcut as cc
    return [(snap(cc.remap(s, keep)), snap(cc.remap(e, keep)), sp) for s, e, sp in speeds]


def build(cut1, speeds1, out):
    """cut1 → cut: ช่วงในรายการเร่ง sp เท่า (เสียงเงียบ — ช่วงสาธิตไม่มีคนพูด เพลงคลอแทน) · ไม่มีช่วงเร่ง = ก๊อปไฟล์"""
    import shutil
    if not speeds1:
        shutil.copyfile(cut1, out)
        return
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", cut1],
                               capture_output=True, text=True).stdout.strip())
    parts, cur = [], 0.0
    for s, e, sp in sorted(speeds1):
        if s > cur:
            parts.append((cur, s, 1))
        parts.append((s, e, sp))
        cur = e
    if dur - cur > 0.02:
        parts.append((cur, dur, 1))
    g = []
    parts = [x for x in parts if x[2] > 0]  # sp 0 = ตัดทิ้ง (editor สั่ง)
    for k, (s, e, sp) in enumerate(parts):
        g.append(f"[0:v]trim=start={s:.4f}:end={e:.4f},setpts=(PTS-STARTPTS)/{sp},fps={FPS}[v{k}]")
        if sp == 1:
            g.append(f"[0:a]atrim=start={s:.4f}:end={e:.4f},asetpts=PTS-STARTPTS[a{k}]")
        else:
            g.append(f"aevalsrc=0:c=stereo:s=48000:d={(e - s) / sp:.4f}[a{k}]")
    g.append("".join(f"[v{k}][a{k}]" for k in range(len(parts))) + f"concat=n={len(parts)}:v=1:a=1[v][a]")
    gf = out + ".graph.txt"
    open(gf, "w", encoding="utf-8").write(";\n".join(g))
    subprocess.run([FF, "-y", "-v", "error", "-i", cut1, "-/filter_complex", gf, "-map", "[v]", "-map", "[a]", "-r", str(FPS),
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "192k", out], check=True)
    os.remove(gf)


def items_for(speeds1):
    """E["speedups"] — ไว้โชว์ป้าย ×N + ให้ editor สลับโหมด"""
    out = []
    for n, (s, e, sp) in enumerate(sorted(speeds1), 1):
        out.append({"id": f"sp{n}", "src": [s, e], "speed": sp, "mode": "speed",
                    "start": round(out_time(s, speeds1), 3), "end": round(out_time(e, speeds1), 3)})
    return out


def set_mode(E, proj, sid, mode):
    """editor สลับช่วงสาธิต: speed (เร่งตามเดิม) / normal (ความเร็วปกติ) / cut (ตัดทิ้ง)
    → สร้าง cut ใหม่จาก cut1 · เลื่อนทุกอย่างหลังช่วงนั้น · สร้างคลิปเว้นช่อง GIF ใหม่"""
    import gaps
    sps = E.get("speedups") or []
    it = next((x for x in sps if x["id"] == sid), None)
    if not it or mode not in ("speed", "normal", "cut"):
        return False
    import hashlib
    base = (E.get("video_base") or E["video"]).split(".cut")[0]
    cut1 = os.path.join(proj, base + ".cut1.mp4")
    if not os.path.exists(cut1):
        raise RuntimeError("ไม่มีไฟล์ cut1 (โปรเจกต์เก่า)")
    eff = lambda x: {"speed": x["speed"], "normal": 1, "cut": 0}[x.get("mode", "speed")]  # noqa: E731
    old_len = it["end"] - it["start"]
    it["mode"] = mode
    s1, e1 = it["src"]
    new_len = (e1 - s1) / eff(it) if eff(it) else 0.0
    d = round(new_len - old_len, 3)
    # ชื่อไฟล์ใหม่ตามชุดโหมด — ชื่อเดิม = เบราว์เซอร์/editor ไม่รู้ว่าคลิปเปลี่ยน
    tag = hashlib.md5(repr([(x["id"], x.get("mode")) for x in sps]).encode()).hexdigest()[:6]
    cut = os.path.join(proj, f"{base}.cut.s{tag}.mp4")
    old = E.get("video_base")
    build(cut1, [(x["src"][0], x["src"][1], eff(x)) for x in sps if eff(x) != 1], cut)
    if abs(d) > 1e-3:
        t = it["end"]
        gaps._shift(E, t, d)  # เลื่อน speedups/clips ตัวอื่นด้วย (ตัวนี้เริ่มก่อน t ไม่โดน)
        it["end"] = round(it["start"] + new_len, 3)
    E["video_base"] = os.path.basename(cut)
    gaps.build_video(E, proj)
    if old and old != E["video_base"] and ".cut.s" in old:  # รุ่นก่อนหน้าที่สร้างจาก editor
        for f in (old, os.path.splitext(old)[0] + ".proxy.mp4"):
            try:
                os.remove(os.path.join(proj, f))
            except OSError:
                pass
    return True


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    import argparse
    ap = argparse.ArgumentParser(description="ทดสอบ: หาช่วงสาธิตในคลิป")
    ap.add_argument("src")
    ap.add_argument("segments")
    a = ap.parse_args()
    import clipcut as cc
    segs = ccfx.load_edit(a.segments)["segments"]
    keep = cc.tighten_keep(a.src, cc.compute_keep(segs, 0.15, 0.6))
    k2, speeds, rep = plan(a.src, keep, segs, cc.probe_dur(a.src), os.path.join(os.path.dirname(a.src), "_speed"))
    for r in rep:
        print(f"  {r[0]:8} ที่ {r[1]:.1f} วิ ยาว {r[2]:.1f} วิ")
    print(json.dumps(speeds))


if __name__ == "__main__":
    main()
