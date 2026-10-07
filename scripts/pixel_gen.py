#!/usr/bin/env python
"""วาดไอคอนพิกเซลใหม่อัตโนมัติ (ให้ AI วาดเป็นตาราง 16×16 แบบเดียวกับ animclip/sprites.py) → คลังโตเรื่อยๆ

  python pixel_gen.py laptop "แล็ปท็อปเปิดจอ" microphone "ไมค์อัดเสียง" ...
  python pixel_gen.py --list
  python pixel_gen.py --redraw laptop "..."      วาดทับของเดิม

ผล: assets/pixel/icon_<name>.png + ตารางเก็บใน assets/pixel/icons.json (แก้มือแล้ว --render ได้)
autopilot เรียก ensure([...]) เองตอน AI กำกับฉากอยากได้ของที่ยังไม่มี
"""
import os
import re
import sys
import json
import argparse
import threading
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pixel  # noqa: E402

LIB = os.path.join(pixel.PIX, "icons.json")
SIZE = 16
SCALE = 14  # 16×14 ≈ 12×18 ของ animclip — ไอคอนทุกตัวขนาดใกล้กัน
PAL = {  # ชุดสีเดียวกับ animclip/scripts/sprites.py
    'K': (26, 22, 28), 'W': (246, 246, 242), 'w': (200, 208, 214), 'A': (148, 163, 184), 'a': (71, 85, 105),
    'G': (16, 185, 129), 'g': (8, 120, 86), 'Y': (250, 204, 21), 'y': (202, 138, 4), 'R': (239, 68, 68),
    'd': (153, 27, 27), 'L': (96, 165, 250), 'l': (37, 99, 235), 'O': (249, 115, 22), 'V': (167, 139, 250),
    'S': (242, 196, 158), 's': (214, 160, 124), 'P': (44, 58, 88), 'p': (30, 40, 62), 'T': (110, 180, 240),
    'M': (170, 70, 70), 'r': (240, 150, 140), 'Z': (255, 255, 255), 'B': (250, 250, 250), 'E': (20, 18, 24),
}
LEGEND = ("K=เส้นขอบดำ W=ขาว w=เทาอ่อน A=เทา a=เทาเข้ม G=เขียว g=เขียวเข้ม Y=เหลือง y=เหลืองเข้ม/ทอง "
          "R=แดง d=แดงเข้ม L=ฟ้า l=น้ำเงิน O=ส้ม V=ม่วง S=ผิว s=ผิวเงา P=กรมท่า p=กรมท่าเข้ม T=ฟ้าน้ำทะเล "
          "M=น้ำตาลแดง r=ชมพู Z=ขาวสว่าง(แสงสะท้อน) .=โปร่งใส")
EXAMPLES = {  # จาก animclip (12×12) — ให้ AI เห็นลายเส้น
    "rocket": [".....KK.....", "....KWWK....", "...KWWWWK...", "...KWLLWK...", "...KWLLWK...", "...KWWWWK...",
               "..KRKWWKRK..", ".KRRKWWKRRK.", ".KKKKWWKKKK.", "....KOOK....", "....KYYK....", ".....KK....."],
    "bulb": ["....KKKK....", "...KYYYYK...", "..KYZYYYYK..", "..KYYYYYYK..", "..KYYYYYYK..", "...KYYYYK...",
             "....KYYK....", "....KAAK....", "....KaaK....", "....KAAK....", ".....KK.....", "............"],
}


def lib():
    try:
        return json.load(open(LIB, encoding="utf-8"))
    except Exception:
        return {}


def save_lib(d):
    json.dump(d, open(LIB, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def render(rows, name):
    h, w = len(rows), max(len(r) for r in rows)
    im = Image.new("RGBA", (w * SCALE, h * SCALE), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch in PAL:
                d.rectangle([x * SCALE, y * SCALE, (x + 1) * SCALE - 1, (y + 1) * SCALE - 1], fill=PAL[ch] + (255,))
    im = im.crop(im.getbbox())
    pixel.sticker(im).save(os.path.join(pixel.PIX, f"icon_{name}.png"))


def clean(rows):
    """AI ส่งตารางมาเบี้ยวได้ → บังคับ 16×16 ตัวอักษรที่รู้จัก · ต้องมีเส้นขอบ K และไม่โล่ง"""
    rows = [re.sub(f"[^{''.join(PAL)}.]", ".", str(r))[:SIZE].ljust(SIZE, ".") for r in rows][:SIZE]
    rows += ["." * SIZE] * (SIZE - len(rows))
    filled = sum(c != "." for r in rows for c in r)
    if filled < 30 or sum(r.count("K") for r in rows) < 12:
        raise ValueError("ตารางโล่งเกิน/ไม่มีเส้นขอบ")
    return rows


def draw(name, desc):
    import autopilot  # ใช้ ai() ตัวเดียวกัน (claude -p)
    ex = "\n".join(f'"{k}": {json.dumps(v)}' for k, v in EXAMPLES.items())
    prompt = f"""วาดไอคอนพิกเซลอาร์ต "{name}" ({desc}) เป็นตาราง {SIZE}x{SIZE}
สไตล์ต้องเหมือนตัวอย่าง (ไอคอนสติกเกอร์เกม 8-bit, เส้นขอบดำ K รอบรูปทุกด้าน, สีแบน, มีแสงสะท้อน Z 1-2 จุด, อ่านออกทันทีว่าเป็นอะไร, เต็มกรอบเกือบทั้ง {SIZE} ช่อง):
{ex}
สีที่ใช้ได้ (ตัวอักษร 1 ตัว = 1 ช่อง): {LEGEND}
ตอบ JSON: {{"rows": [<{SIZE} สตริง แต่ละสตริงยาว {SIZE} ตัวอักษรพอดี>]}}"""
    last = None
    for _ in range(3):
        try:
            return clean(autopilot.ai(prompt, model="opus")["rows"])
        except Exception as e:
            last = e
    raise RuntimeError(f"วาด {name} ไม่ได้: {last}")


def ensure(wants, redraw=False):
    """wants = {name: desc} → วาดเฉพาะตัวที่ยังไม่มี (ขนานกัน) · คืน set ชื่อที่ใช้ได้"""
    have = set(pixel.names()["icons"])
    todo = {n: d for n, d in wants.items() if redraw or n not in have}
    d, lock, ok = lib(), threading.Lock(), set(have)

    def one(n, desc):
        try:
            rows = draw(n, desc)
            render(rows, n)
            with lock:
                d[n] = {"desc": desc, "rows": rows}
                ok.add(n)
            print(f"  + ไอคอนใหม่ {n}", flush=True)
        except Exception as e:
            print(f"  ! {e}", flush=True)
    ts = [threading.Thread(target=one, args=(n, x)) for n, x in todo.items()]
    for i in range(0, len(ts), 4):  # ทีละ 4 ตัว
        for t in ts[i:i + 4]:
            t.start()
        for t in ts[i:i + 4]:
            t.join()
    if todo:
        save_lib(d)
    return ok


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("pairs", nargs="*", help="name desc name desc ...")
    ap.add_argument("--redraw", action="store_true")
    ap.add_argument("--render", action="store_true", help="เรนเดอร์ใหม่จาก icons.json (หลังแก้ตารางมือ)")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    if a.list:
        print(", ".join(pixel.names()["icons"])); return
    if a.render:
        for n, v in lib().items():
            render(v["rows"], n)
        print("✓ render", len(lib())); return
    wants = dict(zip(a.pairs[::2], a.pairs[1::2]))
    ensure(wants, a.redraw)


if __name__ == "__main__":
    main()
