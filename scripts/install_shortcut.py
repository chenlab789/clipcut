#!/usr/bin/env python
"""สร้างไอคอน ClipCut บน Desktop (Windows)
ดับเบิลคลิก = เปิดหน้าแรก · ลากคลิปใส่ไอคอน = เปิดพร้อมคลิปนั้น

  python install_shortcut.py
"""
import os
import sys
import subprocess
import tempfile
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
ICO = os.path.join(HERE, "editor", "clipcut.ico")


def make_icon():
    """ตัวการ์ตูนพิกเซล (ท่าดีใจ) บนพื้นเขียว emerald มุมมน"""
    from PIL import ImageDraw
    spr = Image.open(os.path.join(SKILL, "assets", "pixel", "hoodie_cheer.png")).convert("RGBA")
    S = 256
    bg = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(bg).rounded_rectangle([8, 8, S - 8, S - 8], radius=52, fill=(16, 185, 129, 255))
    k = (S - 40) / max(spr.size)
    spr = spr.resize((round(spr.width * k), round(spr.height * k)), Image.NEAREST)
    bg.alpha_composite(spr, ((S - spr.width) // 2, S - spr.height - 14))
    bg.save(ICO, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return ICO


def desktop():
    """Desktop จริง (OneDrive ย้ายไปได้) — ถาม Windows ตรง ไม่เดา path"""
    r = subprocess.run(["powershell", "-NoProfile", "-Command",
                        "[Console]::OutputEncoding=[Text.UTF8Encoding]::new(); [Environment]::GetFolderPath('Desktop')"],
                       capture_output=True, text=True, encoding="utf-8")
    return r.stdout.strip()


def main():
    make_icon()
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.exists(pyw):
        pyw = sys.executable
    server = os.path.join(HERE, "editor", "server.py")
    lnk = os.path.join(desktop(), "ClipCut.lnk")
    ps = f"""$s = (New-Object -ComObject WScript.Shell).CreateShortcut('{lnk}')
$s.TargetPath = '{pyw}'
$s.Arguments = '"{server}"'
$s.WorkingDirectory = '{os.path.dirname(server)}'
$s.IconLocation = '{ICO},0'
$s.Description = 'ClipCut — ลากคลิปมาวาง ได้คลิปตัดเสร็จ'
$s.Save()
"""
    f = os.path.join(tempfile.gettempdir(), "clipcut_shortcut.ps1")
    with open(f, "w", encoding="utf-8-sig") as fh:  # BOM — path ไทย (เดสก์ท็อป) ใน PowerShell 5
        fh.write(ps)
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", f], check=True)
    print("✓", lnk)


if __name__ == "__main__":
    main()
