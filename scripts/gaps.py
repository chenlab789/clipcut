#!/usr/bin/env python
"""ช่องหยุดคลิป (ตัดเข้า GIF เต็มจอ / หยุดภาพ+ข้อความ) — คลิปเฉินหยุดแป๊บนึง แล้วเล่นต่อ (คลิปยาวขึ้น)

E["gaps"] = [{"id", "at", "dur"}]   at = วินาทีบน timeline ผลลัพธ์ (เวลาเดียวกับ items)
E["video_base"] = คลิปที่ตัด dead air แล้ว (ไม่มีช่อง) · E["video"] = คลิปที่เว้นช่องแล้ว (ภาพค้างเฟรมสุดท้าย + เสียงเงียบ)
→ editor/render ใช้ E["video"] ตามปกติ เวลาตรงกันเองหมด ไม่ต้องแปลงเวลา

ใส่/ลบช่อง = เลื่อนทุกอย่างที่อยู่หลังจุดนั้น (items, ช่องอื่น, faces, เส้นทางกล้อง) แล้วสร้างคลิปใหม่
"""
import os
import sys
import hashlib
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ccfx  # noqa: E402

FPS = 30
FF = os.environ.get("FFMPEG", "ffmpeg")


def snap(x):
    return round(round(x * FPS) / FPS, 3)


def boundary(E, t, reach=1.5):
    """จุดใส่ช่องที่ไม่ผ่ากลางประโยค: ท้ายซับที่ใกล้ t ที่สุด (ไม่ไกลเกิน reach) — อยู่ระหว่างซับอยู่แล้วใช้ t เลย"""
    subs = sorted((x for x in E["items"] if x["track"] == "sub"), key=lambda x: x["start"])
    if not any(s["start"] < t < s["end"] for s in subs):
        return snap(t)
    ends = [s["end"] for s in subs if abs(s["end"] - t) <= reach and not any(o["start"] < s["end"] < o["end"] for o in subs)]
    return snap(min(ends, key=lambda e: abs(e - t))) if ends else snap(t)


def _shift(E, t, d):
    """ทุกอย่างที่ ≥ t เลื่อนไป d วิ (d ติดลบ = ดึงกลับ)"""
    for it in E["items"]:
        if it["start"] >= t - 1e-6:
            it["start"] = round(it["start"] + d, 3)
            if it.get("end") is not None:
                it["end"] = round(it["end"] + d, 3)
        elif it.get("end") is not None and it["end"] > t + 1e-6 and it["track"] != "sub":
            it["end"] = round(max(it["start"] + 0.05, it["end"] + d), 3)
    for g in E.get("gaps", []):
        if g["at"] >= t - 1e-6:
            g["at"] = round(g["at"] + d, 3)
    for tr in (E.get("faces") or {}).get("tracks", []):
        tr["pts"] = [[round(p[0] + d, 3) if p[0] >= t else p[0], *p[1:]] for p in tr["pts"] if not (d < 0 and t + d <= p[0] < t)]
    cam = E.get("cam") or {}
    if cam.get("path"):
        import smartcam
        if d > 0:
            x, y = smartcam.cam_at(E, t)
            p = [[k[0] + d if k[0] >= t else k[0], *k[1:]] for k in cam["path"]]
            p += [[t, x, y], [t + d, x, y]]  # ระหว่างช่อง กล้องค้างที่เดิม
        else:
            p = [[k[0] + d if k[0] >= t else k[0], *k[1:]] for k in cam["path"] if not (t + d <= k[0] < t)]
        cam["path"] = sorted(([round(k[0], 3), k[1], k[2]] for k in p), key=lambda k: k[0])
    E["duration"] = round(E["duration"] + d, 3)


def insert(E, t, dur, gid=None):
    """เว้นช่องที่ t (snap ให้ไม่ผ่ากลางประโยคแล้ว) → คืน gap dict"""
    E.setdefault("video_base", E["video"])
    E.setdefault("gaps", [])
    dur = max(snap(dur), 0.4)
    _shift(E, t, dur)
    n = 1
    while any(g["id"] == f"gap{n}" for g in E["gaps"]):
        n += 1
    g = {"id": gid or f"gap{n}", "at": snap(t), "dur": dur}
    E["gaps"].append(g)
    E["gaps"].sort(key=lambda g: g["at"])
    return g


def remove(E, gid):
    """ลบช่อง + ของที่ผูกกับช่อง (gif/sfx/fx ที่ autopilot ใส่คู่กัน) → ดึงทุกอย่างหลังช่องกลับ"""
    g = next((x for x in E.get("gaps", []) if x["id"] == gid), None)
    if not g:
        return False
    E["items"] = [x for x in E["items"] if x.get("gap") != gid]
    for it in E["items"]:  # ของที่เฉินวางไว้ในช่องเอง → ย้ายไปไว้ต้นช่อง
        if g["at"] <= it["start"] < g["at"] + g["dur"]:
            d = it["start"] - g["at"]
            it["start"] = g["at"]
            if it.get("end") is not None:
                it["end"] = round(max(g["at"] + 0.1, it["end"] - d), 3)
    E["gaps"] = [x for x in E["gaps"] if x["id"] != gid]
    _shift(E, g["at"] + g["dur"], -g["dur"])
    return True


def build_video(E, proj):
    """คลิปไม่มีช่อง → คลิปเว้นช่อง (ภาพค้าง + เสียงเงียบ) · ชื่อไฟล์ตามชุดช่อง (เบราว์เซอร์ไม่ใช้ของเก่าในแคช)"""
    base = E.get("video_base") or E["video"]
    gaps = sorted(E.get("gaps") or [], key=lambda g: g["at"])
    stem = os.path.splitext(base)[0]
    for f in os.listdir(proj):  # ไฟล์เว้นช่องรุ่นเก่า
        if f.startswith(stem + ".gap") and f.endswith(".mp4"):
            try:
                os.remove(os.path.join(proj, f))
            except OSError:
                pass
    if not gaps:
        E["video"] = base
        return base
    h = hashlib.md5(repr([(g["at"], g["dur"]) for g in gaps]).encode()).hexdigest()[:8]
    out = f"{stem}.gap{h}.mp4"
    # เวลาบนคลิปไม่มีช่อง ที่แต่ละช่องแทรก
    cuts, acc = [], 0.0
    for g in gaps:
        cuts.append((g["at"] - acc, g["dur"]))
        acc += g["dur"]
    fc, prev = [], 0.0
    for k, (b, d) in enumerate(cuts + [(None, 0)]):
        end = f":end={b:.4f}" if b is not None else ""
        pad_v = f",tpad=stop_mode=clone:stop_duration={d:.4f}" if d else ""
        pad_a = f",apad=pad_dur={d:.4f}" if d else ""
        fc.append(f"[0:v]trim=start={prev:.4f}{end},setpts=PTS-STARTPTS{pad_v}[v{k}]")
        fc.append(f"[0:a]atrim=start={prev:.4f}{end},asetpts=PTS-STARTPTS{pad_a}[a{k}]")
        prev = b if b is not None else prev
    n = len(cuts) + 1
    fc.append("".join(f"[v{k}][a{k}]" for k in range(n)) + f"concat=n={n}:v=1:a=1[v][a]")
    gf = os.path.join(proj, "_gaps_graph.txt")
    open(gf, "w", encoding="utf-8").write(";\n".join(fc))
    subprocess.run([FF, "-y", "-v", "error", "-i", os.path.join(proj, base), "-/filter_complex", gf, "-map", "[v]", "-map", "[a]",
                    "-r", str(FPS), "-c:v", "libx264", "-preset", "superfast", "-crf", "18", "-c:a", "aac", "-b:a", "192k",
                    "-movflags", "+faststart", os.path.join(proj, out)], check=True)
    os.remove(gf)
    E["video"] = out
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    import argparse
    ap = argparse.ArgumentParser(description="เว้น/ลบช่องหยุดคลิป")
    ap.add_argument("edit")
    ap.add_argument("--add", type=float, help="วินาที")
    ap.add_argument("--dur", type=float, default=1.2)
    ap.add_argument("--remove")
    a = ap.parse_args()
    E = ccfx.load_edit(a.edit)
    if a.add is not None:
        print(insert(E, boundary(E, a.add), a.dur))
    if a.remove:
        print(remove(E, a.remove))
    build_video(E, os.path.dirname(os.path.abspath(a.edit)))
    ccfx.save_edit(a.edit, E)
    print(E["video"], E["duration"])


if __name__ == "__main__":
    main()
