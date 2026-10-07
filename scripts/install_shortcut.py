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


def make_app_icons():
    """ไอคอนตอน "เพิ่มลงหน้าจอโฮม" บนไอโฟน/ไอแพด — สี่เหลี่ยมเต็ม ไม่โปร่งใส (iOS ตัดมุมมนเอง, ส่วนใส = ดำ)"""
    spr = Image.open(os.path.join(SKILL, "assets", "pixel", "hoodie_cheer.png")).convert("RGBA")
    out = []
    for S in (180, 512):
        bg = Image.new("RGBA", (S, S), (16, 185, 129, 255))
        k = S * 0.78 / max(spr.size)
        sp = spr.resize((round(spr.width * k), round(spr.height * k)), Image.NEAREST)
        bg.alpha_composite(sp, ((S - sp.width) // 2, S - sp.height - round(S * 0.06)))
        p = os.path.join(HERE, "editor", f"icon-{S}.png")
        bg.convert("RGB").save(p)
        out.append(p)
    return out


def desktop():
    """Desktop จริง (OneDrive ย้ายไปได้) — ถาม Windows ตรง ไม่เดา path"""
    r = subprocess.run(["powershell", "-NoProfile", "-Command",
                        "[Console]::OutputEncoding=[Text.UTF8Encoding]::new(); [Environment]::GetFolderPath('Desktop')"],
                       capture_output=True, text=True, encoding="utf-8")
    return r.stdout.strip()


def shortcut(lnk, pyw, args, desc):
    ps = f"""$s = (New-Object -ComObject WScript.Shell).CreateShortcut('{lnk}')
$s.TargetPath = '{pyw}'
$s.Arguments = '{args}'
$s.WorkingDirectory = '{os.path.join(HERE, "editor")}'
$s.IconLocation = '{ICO},0'
$s.Description = '{desc}'
$s.Save()
"""
    f = os.path.join(tempfile.gettempdir(), "clipcut_shortcut.ps1")
    with open(f, "w", encoding="utf-8-sig") as fh:  # BOM — path ไทย (เดสก์ท็อป) ใน PowerShell 5
        fh.write(ps)
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", f], check=True)
    print("✓", lnk)


def main():
    """ไอคอน Desktop (เปิดหน้าต่าง) + Startup (เริ่มเบื้องหลังตอนล็อกอิน มีไอคอนถาด — มือถือใช้ได้ทันทีหลังรีสตาร์ท)
    ไม่อยากให้เริ่มเอง: python install_shortcut.py --no-startup"""
    make_icon()
    make_app_icons()
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.exists(pyw):
        pyw = sys.executable
    server = os.path.join(HERE, "editor", "server.py")
    shortcut(os.path.join(desktop(), "ClipCut.lnk"), pyw, f'"{server}"', "ClipCut — ลากคลิปมาวาง ได้คลิปตัดเสร็จ")
    startup = os.path.join(os.environ["APPDATA"], "Microsoft", "Windows", "Start Menu", "Programs", "Startup", "ClipCut.lnk")
    if "--no-startup" in sys.argv:
        if os.path.exists(startup):
            os.remove(startup)
            print("ลบเริ่มเองตอนล็อกอินแล้ว")
    else:
        shortcut(startup, pyw, f'"{server}" --no-open', "ClipCut เบื้องหลัง (ไอคอนถาด)")


if __name__ == "__main__":
    main()
