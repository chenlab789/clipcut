#!/usr/bin/env python
"""ใส่ของจากแผน (plan.json) ลง edit.json ทีละชิ้น — editor ที่เปิดอยู่จะเห็นของเด้งขึ้นทีละอัน

  python edit_apply.py <ชื่อ>.edit.json plan.json [--stagger 0.5] [--clear emoji,sfx,fx,broll]

plan.json = list ของ item (ไม่ต้องใส่ id) เช่น
  [{"track":"sfx","start":12.0,"sfx":"pop"},
   {"track":"emoji","start":12.0,"end":13.2,"emoji":"🤔"},
   {"track":"fx","start":15.2,"end":15.65,"fx":"punch"}]
ค่าที่ไม่ใส่ เติม default ให้ (ตำแหน่ง/ขนาด/ความดัง/ความยาว sfx ตามไฟล์จริง)
--clear = ลบของเดิมใน track นั้นก่อน (ร่างใหม่ทั้งชุด) — ซับไม่ให้ลบผ่านทางนี้
"""
import os
import sys
import time
import wave
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ccfx  # noqa: E402

if sys.stdout:  # server รันด้วย pythonw = ไม่มี stdout
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
PREFIX = {"sub": "s", "broll": "b", "gif": "g", "emoji": "e", "sfx": "a", "fx": "z"}


def sfx_len(name):
    with wave.open(os.path.join(ccfx.SFX_DIR, name + ".wav")) as w:
        return w.getnframes() / w.getframerate()


def fill(it, E):
    v = E["aspect"] == "9x16"
    tr = it["track"]
    if tr == "sfx":
        if not os.path.exists(os.path.join(ccfx.SFX_DIR, it["sfx"] + ".wav")):
            raise SystemExit(f"ไม่มีเสียง {it['sfx']} — ดูรายชื่อใน assets/sfx/")
        it.setdefault("vol", 0.8)
        it.setdefault("end", round(it["start"] + sfx_len(it["sfx"]), 3))
    elif tr == "emoji":
        it.setdefault("end", it["start"] + 1.2)
        it.setdefault("x", 0.72); it.setdefault("y", 0.3 if v else 0.25)
        it.setdefault("size", 0.22); it.setdefault("anim", "pop")
    elif tr == "broll":
        it.setdefault("end", it["start"] + 2.5)
        it.setdefault("x", 0.5); it.setdefault("y", 0.17 if v else 0.3); it.setdefault("w", 0.86 if v else 0.4)
    elif tr == "gif":  # mode overlay = แปะทับ · cut/freeze = ช่องหยุดคลิป (gaps.py ตั้งเวลาให้)
        it.setdefault("mode", "overlay")
        it.setdefault("end", it["start"] + 1.8)
        if it["mode"] == "overlay":
            it.setdefault("x", 0.5); it.setdefault("y", 0.3 if v else 0.3); it.setdefault("w", 0.55 if v else 0.32)
            it.setdefault("rot", -3)
    elif tr == "fx":
        it.setdefault("amount", ccfx.FX_DEFAULT[it["fx"]])
        it.setdefault("end", it["start"] + {"punch": 0.45, "zoomin": 2.5, "zoomout": 2.5, "focus": 2.5,
                                             "shake": 0.5, "flash": 0.35}[it["fx"]])
    it["start"] = round(max(0, it["start"]), 3)
    it["end"] = round(min(E["duration"], it["end"]), 3)
    return it


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("edit")
    ap.add_argument("plan")
    ap.add_argument("--stagger", type=float, default=0.5, help="วินาทีระหว่างแต่ละชิ้น (0 = ใส่ทีเดียว)")
    ap.add_argument("--clear", default="", help="track ที่ล้างก่อน เช่น emoji,sfx,fx")
    a = ap.parse_args()

    plan = ccfx.load_edit(a.plan)
    clear = {t for t in a.clear.split(",") if t and t != "sub"}
    if clear:
        E = ccfx.load_edit(a.edit)
        E["items"] = [x for x in E["items"] if x["track"] not in clear]
        ccfx.save_edit(a.edit, E)
        print("ล้าง:", ", ".join(sorted(clear)))
        time.sleep(a.stagger)
    for it in sorted(plan, key=lambda x: x["start"]):
        E = ccfx.load_edit(a.edit)  # อ่านใหม่ทุกรอบ — เฉินอาจแก้อยู่ในหน้า editor
        ids = {x["id"] for x in E["items"]}
        n = 1
        while f"{PREFIX[it['track']]}{n}" in ids:
            n += 1
        it = fill(dict(it, id=f"{PREFIX[it['track']]}{n}"), E)
        E["items"].append(it)
        ccfx.save_edit(a.edit, E)
        what = it.get("sfx") or it.get("emoji") or it.get("fx") or it.get("src") or it.get("text")
        print(f"+ {it['track']:5} {it['start']:7.2f}  {what}", flush=True)
        if a.stagger:
            time.sleep(a.stagger)
    print("✓ ใส่", len(plan), "ชิ้น")


if __name__ == "__main__":
    main()
