#!/usr/bin/env python
"""โหลดเพลงพื้นหลัง (Kevin MacLeod — CC BY 4.0) → assets/music/<slug>.mp3 (ปรับดัง -20 LUFS)
เพลงไม่เก็บใน git (ไฟล์ใหญ่) — เครื่องใหม่รันสคริปต์นี้ครั้งเดียว
CC BY = ใช้ฟรีแต่ต้องใส่เครดิตใต้คลิป → render_edit.py พิมพ์บรรทัดเครดิตให้ก๊อป
ใส่เพลงของตัวเองได้: วาง .mp3 ใน assets/music/ ได้เลย (ไม่ต้องอยู่ในลิสต์นี้)
"""
import os
import sys
import json
import tempfile
import subprocess
import urllib.request
import urllib.parse

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "assets", "music")
FF = os.environ.get("FFMPEG", "ffmpeg")

TRACKS = {  # slug: (ชื่อเพลง, อารมณ์)
    "local_forecast": ("Local Forecast - Elevator", "ชิล สบายๆ แจ๊ส — คลิปเล่าเรื่องทั่วไป"),
    "wallpaper": ("Wallpaper", "ชิล อิเล็กทรอนิกส์ — คลิปเทค/สอน"),
    "carefree": ("Carefree", "สดใส ร่าเริง — vlog/แกะกล่อง"),
    "fluffing_a_duck": ("Fluffing a Duck", "ตลก กวนๆ — มุก/เฟล"),
    "sneaky_snitch": ("Sneaky Snitch", "แอบๆ กวนตีน — แกล้ง/ลับๆ"),
    "investigations": ("Investigations", "สืบสวน ลึกลับ — เล่าเรื่องปริศนา"),
    "funkorama": ("Funkorama", "ฟังก์ เท่ — โชว์ของ"),
    "hyperfun": ("Hyperfun", "มันส์ เร็ว — ตัดไว/มอนทาจ"),
    "pixelland": ("Pixelland", "8-bit เกม — คลิปเกม/เทค"),
}


def credit(title):
    return (f'"{title}" Kevin MacLeod (incompetech.com)\n'
            f"Licensed under Creative Commons: By Attribution 4.0 License\n"
            f"http://creativecommons.org/licenses/by/4.0/")


def main():
    os.makedirs(OUT, exist_ok=True)
    meta = {}
    for slug, (title, mood) in TRACKS.items():
        meta[slug] = {"title": title, "mood": mood, "credit": credit(title)}
        dst = os.path.join(OUT, slug + ".mp3")
        if os.path.exists(dst):
            continue
        url = "https://incompetech.com/music/royalty-free/mp3-royaltyfree/" + urllib.parse.quote(title) + ".mp3"
        tmp = os.path.join(tempfile.gettempdir(), slug + "_raw.mp3")
        print("↓", title, flush=True)
        urllib.request.urlretrieve(url, tmp)
        subprocess.run([FF, "-y", "-v", "error", "-i", tmp, "-af", "loudnorm=I=-20:TP=-2", "-ar", "44100",
                        "-ac", "2", "-b:a", "160k", dst], check=True)
        os.remove(tmp)
    json.dump(meta, open(os.path.join(OUT, "music.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("✓", OUT, len(meta), "เพลง")


if __name__ == "__main__":
    main()
