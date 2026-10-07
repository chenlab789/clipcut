#!/usr/bin/env python
"""ตัวการ์ตูนพิกเซลคนอื่นในคลิป (ไม่ใช่เฉิน) — ใช้โครง/ท่า/ลายเส้นเดียวกับ animclip/scripts/sprites.py

  python char_sprites.py            → assets/pixel/girl_<ท่า>.png (แฟนเฉิน: ผมยาวหน้าม้า แว่น เสื้อน้ำตาล)

ท่าเหมือนตัวเฉินทุกท่า (idle wave point cheer happy shock think sad shrug angry type) → AI ใช้ชื่อท่าเดียวกันได้เลย
เปลี่ยนแค่ prefix: hoodie_ = เฉิน · girl_ = แฟน
"""
import os
import sys

ANIM = os.path.join(os.path.expanduser("~"), ".claude", "skills", "animclip", "scripts")
sys.path.insert(0, ANIM)
import sprites as S  # noqa: E402

S.PAL.setdefault("N", (150, 112, 74))   # น้ำตาลเสื้อเชิ้ต
S.PAL.setdefault("n", (112, 80, 52))
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "assets", "pixel")


def outfit_girl(g):
    """ผมยาวคลุมไหล่ + หน้าม้า + แว่น + เสื้อเชิ้ตน้ำตาล"""
    rows = len(g) - S.TOP
    # หน้าม้าเต็มหน้าผาก + ปลายหน้าม้าแหลมลงมาแถวถัดไป
    for c in range(4, 18):
        if S.get(g, 5, c) in "SH":
            S.put(g, 5, c, "H")
    for c in (4, 17):  # ปลายหน้าม้าแค่ขอบ — ตรงกลางต้องเห็นแว่น
        if S.get(g, 6, c) == "S":
            S.put(g, 6, c, "H")
    # ผมยาวสองข้าง (เฉพาะช่องว่าง — แขนที่ยกขึ้นยังอยู่หน้าผม)
    for r in range(3, 15):
        for c, edge in ((2, 1), (19, 20)):
            if S.get(g, r, c) == ".":
                S.put(g, r, c, "H")
            if S.get(g, r, edge) == ".":
                S.put(g, r, edge, "K")
    for c in (1, 2, 19, 20):
        if S.get(g, 15, c) == ".":
            S.put(g, 15, c, "K")
    # แว่น (แบบเดียวกับตัวเฉิน)
    for ec in S.EYES:
        for c in range(ec - 1, ec + 3):
            S.put(g, 6 if S.get(g, 7, ec) == "E" else 7, c, "K"); S.put(g, 10, c, "K")
        for r in range(7, 11):
            if S.get(g, r, ec - 1) == "S" or r in (7, 10):
                S.put(g, r, ec - 1, "K")
            S.put(g, r, ec + 2, "K")
    for c in range(9, 14):
        S.put(g, 8, c, "K")
    # เสื้อเชิ้ตน้ำตาล
    for r in range(14, min(20, rows)):
        for c in range(len(g[0])):
            ch = S.get(g, r, c)
            if ch == "W":
                S.put(g, r, c, "N")
            elif ch == "w":
                S.put(g, r, c, "n")
            elif ch == "G":  # โลโก้กลางอกของตัวเฉิน → กระดุมเสื้อ
                S.put(g, r, c, "n")
    # ปากชมพู
    for c in (10, 11):
        if S.get(g, 11, c) == "M":
            S.put(g, 11, c, "R")
    return g


CHARS = {"girl": outfit_girl}


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    os.makedirs(OUT, exist_ok=True)
    n = 0
    for cname, fn in CHARS.items():
        for pname, pfn in S.POSES.items():
            g = fn(pfn(S.grid()))
            S.sticker(S.render(["".join(r) for r in g])).save(os.path.join(OUT, f"{cname}_{pname}.png"))
            n += 1
    print(f"✓ {n} ท่า → {OUT}")


if __name__ == "__main__":
    main()
