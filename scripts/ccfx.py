"""ccfx — ของที่ editor (server.py) กับ render_edit.py ใช้ร่วมกัน
ต้องตรงกับ editor/app.js (anim curve / zoom curve) ไม่งั้นพรีวิวไม่ตรงคลิปจริง
"""
import os
import json
import math
import time
import subprocess

if os.name == "nt" and not getattr(subprocess, "_clipcut_nowin", False):
    # โปรแกรม ClipCut รันเบื้องหลัง (pythonw) → ffmpeg / claude -p / python ลูกๆ ห้ามเด้งหน้าต่างดำเต็มจอ
    _Popen_init = subprocess.Popen.__init__

    def _no_window(self, *a, **kw):
        kw["creationflags"] = kw.get("creationflags", 0) | 0x08000000  # CREATE_NO_WINDOW
        _Popen_init(self, *a, **kw)
    subprocess.Popen.__init__ = _no_window
    subprocess._clipcut_nowin = True

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
SFX_DIR = os.path.join(SKILL, "assets", "sfx")
EMOJI_DIR = os.path.join(SKILL, "assets", "emoji")
MUSIC_DIR = os.path.join(SKILL, "assets", "music")
VOICE_LUFS = -16.0   # render ยกเสียงพูดมาที่ระดับนี้ (มาตรฐานคลิปโซเชียล)
MIX_DEFAULT = {"sfx": 0.8}
MUSIC_DEFAULT = {"vol": 0.35, "duck": True}
FONTS = os.path.join(SKILL, "fonts")
TRACKS = ["sub", "broll", "gif", "emoji", "sfx", "fx"]
FX_TYPES = ["punch", "zoomin", "zoomout", "focus", "shake", "flash"]
FX_DEFAULT = {"punch": 1.18, "zoomin": 1.25, "zoomout": 1.25, "focus": 1.6, "shake": 18, "flash": 0.7}
EMOJI_PALETTE = ["😂", "🤣", "😭", "😱", "🤯", "😎", "🥹", "😡", "🤔", "🙄", "😏", "🫠", "💀", "🔥", "💯",
                 "✨", "⚡", "💥", "💸", "💰", "🚀", "🎯", "👀", "👍", "👎", "👏", "🙏", "💪", "🤝", "❤️",
                 "💔", "✅", "❌", "⚠️", "❓", "❗", "🎉", "🏆", "📈", "📉", "⏰", "🧠", "💡"]


def emoji_code(ch):
    """'❤️' → '2764' (ตัด FE0F ตามชื่อไฟล์ noto-emoji)"""
    return "_".join(f"{ord(c):x}" for c in ch if ord(c) != 0xFE0F)


def emoji_png(ch):
    """path PNG 512px ของอีโมจิแบบสติกเกอร์ (ขอบขาว+เงา) — วาดจาก Segoe UI Emoji ของ Windows แล้วแคช
    (ฟอนต์ MS ห้ามแจกต่อ → assets/emoji/ อยู่ใน .gitignore)"""
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
    os.makedirs(EMOJI_DIR, exist_ok=True)
    path = os.path.join(EMOJI_DIR, emoji_code(ch) + ".png")
    if os.path.exists(path):
        return path
    font = ImageFont.truetype(os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "seguiemj.ttf"), 380)
    big = Image.new("RGBA", (900, 900), (0, 0, 0, 0))
    ImageDraw.Draw(big).text((450, 450), ch, font=font, embedded_color=True, anchor="mm")
    big = big.crop(big.getbbox())
    k = 420 / max(big.size)
    big = big.resize((round(big.width * k), round(big.height * k)), Image.LANCZOS)
    out = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    ox, oy = (512 - big.width) // 2, (512 - big.height) // 2
    a = Image.new("L", (512, 512), 0); a.paste(big.getchannel("A"), (ox, oy))
    stroke = a.filter(ImageFilter.MaxFilter(27)).point(lambda v: 255 if v > 40 else 0)
    shadow = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    shadow.putalpha(stroke.filter(ImageFilter.GaussianBlur(10)).point(lambda v: v * 0.45))
    shadow = shadow.transform((512, 512), Image.AFFINE, (1, 0, -6, 0, 1, -10))
    white = Image.new("RGBA", (512, 512), (255, 255, 255, 0)); white.putalpha(stroke)
    out = Image.alpha_composite(out, shadow); out = Image.alpha_composite(out, white)
    out.alpha_composite(big, (ox, oy))
    out.save(path)
    return path


def measure_lufs(path):
    """integrated loudness ของเสียงในไฟล์ (ffmpeg ebur128)"""
    import re
    import subprocess
    ff = os.environ.get("FFMPEG", "ffmpeg")
    r = subprocess.run([ff, "-hide_banner", "-nostats", "-i", path, "-vn", "-af", "ebur128", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr)
    return float(m[-1]) if m else -23.0


def music_list():
    meta = {}
    try:
        meta = json.load(open(os.path.join(MUSIC_DIR, "music.json"), encoding="utf-8"))
    except Exception:
        pass
    out = []
    if os.path.isdir(MUSIC_DIR):
        for f in sorted(os.listdir(MUSIC_DIR)):
            if f.lower().endswith((".mp3", ".wav", ".m4a", ".ogg")):
                slug = os.path.splitext(f)[0]
                m = meta.get(slug, {})
                out.append({"id": slug, "file": f, "title": m.get("title", slug), "mood": m.get("mood", ""),
                            "credit": m.get("credit", "")})
    return out


def music_file(mid):
    return next((os.path.join(MUSIC_DIR, m["file"]) for m in music_list() if m["id"] == mid), None)


def load_edit(path):
    return json.load(open(path, encoding="utf-8-sig"))


def save_edit(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    for i in range(40):  # Windows: ถ้าอีกฝั่ง (server watcher) เปิดอ่านอยู่ replace จะโดน Access denied → รอแป๊บ
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if i == 39:
                raise
            time.sleep(0.05)


def out_size(aspect):
    return (1080, 1920) if aspect == "9x16" else (1920, 1080)


# ---------- anim curves (ตรงกับ app.js) ----------
def emoji_anim(anim, t, dur):
    """→ (scale, rot_deg, alpha, dy_frac) ที่เวลา t (วินาทีนับจากเริ่ม item)"""
    out_t = min(0.15, dur / 3)
    if anim == "float":
        k = t / max(dur, 1e-3)
        a = min(1, t / 0.15) * min(1, (dur - t) / 0.25)
        return 1.0, math.sin(t * 6) * 6, max(0, a), -0.08 * k
    if anim == "shake":
        s = min(1, t / 0.08)
        a = min(1, (dur - t) / out_t)
        return s, math.sin(t * 40) * 12, max(0, a), 0.0
    # pop (default): 0 → 1.25 → 1.0 แล้วโยกเบา ๆ หดหายตอนจบ
    if t < 0.12:
        s = 1.25 * (t / 0.12)
    elif t < 0.24:
        s = 1.25 - 0.25 * ((t - 0.12) / 0.12)
    else:
        s = 1.0
    if t > dur - out_t:
        s *= max(0, (dur - t) / out_t)
    return s, math.sin(t * 5) * 5, 1.0, 0.0


def zoom_at(fx_items, t):
    """→ (zoom, shake_x, shake_y, flash) ที่เวลา t — สูตรเดียวกับ expr ffmpeg ใน render_edit"""
    z, sx, sy, fl = 1.0, 0.0, 0.0, 0.0
    for it in fx_items:
        s, e = it["start"], it["end"]
        if not (s <= t <= e):
            continue
        a = it.get("amount", FX_DEFAULT[it["fx"]])
        d = max(e - s, 1e-3)
        p = (t - s) / d
        if it["fx"] == "punch":
            z += (a - 1) * min(1, (t - s) / 0.08, (e - t) / 0.15)
        elif it["fx"] == "zoomin":
            z += (a - 1) * p
        elif it["fx"] == "zoomout":
            z += (a - 1) * (1 - p)
        elif it["fx"] == "focus":  # ซูมไปที่ของ: เข้า 0.35 วิ ค้าง แล้วออก 0.35 วิ
            z += (a - 1) * min(1, (t - s) / 0.35, (e - t) / 0.35)
        elif it["fx"] == "shake":
            z += 0.06
            sx += a * math.sin(t * 47)
            sy += a * math.sin(t * 61 + 1)
        elif it["fx"] == "flash":
            fl += a * math.exp(-(t - s) * 4 / d)
    return z, sx, sy, fl
