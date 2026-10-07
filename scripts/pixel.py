#!/usr/bin/env python
"""ภาพประกอบพิกเซล (แนวเดียวกับ /animclip) → PNG สติกเกอร์ขอบครีม

ของ 3 อย่าง ผสมกันในการ์ดเดียวได้:
  sprite : ตัวการ์ตูนเฉิน  <ชุด>_<ท่า>  ชุด = tee | hoodie | coat
           ท่า = idle happy cheer think shock sad angry point shrug wave type guard fall kick dodge_l dodge_r shake_a shake_b
  icon   : bag bolt bulb check chip clock coin cross down exclaim fire gold heart question rocket skull star up
  brand  : โดเมนเว็บ เช่น "tailscale.com" — ดึง favicon แล้วแปลงเป็นพิกเซลอัตโนมัติ (ยี่ห้อไหนก็ได้)

  python pixel.py out.png --sprite hoodie_point --brand tailscale.com
ใน plan: {"track":"broll","start":..,"end":..,"pixel":{"sprite":"hoodie_point","brand":"tailscale.com"}}
sprite/icon มาจาก animclip/scripts/sprites.py (ก๊อปไว้ที่ assets/pixel/) — ท่าใหม่ไปวาดที่ animclip แล้วก๊อปมา
"""
import os
import io
import sys
import json
import hashlib
import argparse
import urllib.request
from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
PIX = os.path.join(os.path.dirname(HERE), "assets", "pixel")
CACHE = os.path.join(PIX, "_brands")
SCALE, BORDER = 18, 16           # เท่ากับ animclip — สติกเกอร์ทุกชิ้นหน้าตาเดียวกัน
OUTLINE = (26, 22, 28, 255)
CREAM = (252, 250, 244, 255)


def sticker(spr, border=BORDER):
    """ขอบครีมรอบภาพ (ก๊อปจาก animclip sprites.sticker)"""
    pad = border * 2
    W, H = spr.width + pad * 2, spr.height + pad * 2
    base = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    base.paste(spr, (pad, pad), spr)
    m = base.split()[3].filter(ImageFilter.MaxFilter(border * 2 + 1))
    m = m.filter(ImageFilter.GaussianBlur(3)).point(lambda v: 255 if v > 100 else 0)
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    out.paste(Image.new("RGBA", (W, H), CREAM), (0, 0), m)
    out.alpha_composite(base)
    return out.crop(out.getbbox())


def names():
    fs = [f[:-4] for f in os.listdir(PIX) if f.endswith(".png")]
    return {"sprites": sorted(f for f in fs if not f.startswith("icon_")),
            "icons": sorted(f[5:] for f in fs if f.startswith("icon_"))}


def load(name):
    p = os.path.join(PIX, name + ".png")
    if not os.path.exists(p):
        raise SystemExit(f"ไม่มี {name} — ดู python pixel.py --list")
    return Image.open(p).convert("RGBA")


def favicon(domain):
    os.makedirs(CACHE, exist_ok=True)
    p = os.path.join(CACHE, domain.replace("/", "_") + ".png")
    if not os.path.exists(p):
        url = f"https://www.google.com/s2/favicons?domain={domain}&sz=256"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            Image.open(io.BytesIO(r.read())).convert("RGBA").save(p)
    return Image.open(p).convert("RGBA")


def drop_bg(im, tol=40):
    """favicon ส่วนใหญ่มีกล่องพื้นหลังทึบ → ถ้า 4 มุมสีเดียวกัน ถมจากมุมให้โปร่งใส (เหลือแต่โลโก้)"""
    from PIL import ImageDraw
    im = im.copy()
    w, h = im.size
    corners = [im.getpixel(p) for p in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1))]
    if any(c[3] < 200 for c in corners):
        return im  # มุมใสอยู่แล้ว = ไม่มีกล่อง
    c0 = corners[0]
    if any(sum(abs(a - b) for a, b in zip(c[:3], c0[:3])) > tol for c in corners):
        return im  # มุมสีไม่เหมือนกัน = ภาพเต็มกรอบ ไม่ใช่พื้นหลัง
    for p in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
        ImageDraw.floodfill(im, p, (0, 0, 0, 0), thresh=tol)
    return im if (im.getbbox() and im.getchannel("A").getextrema()[1] > 0) else im


def pixelate(im, cells=20, colors=10):
    """รูปไหนก็ได้ → พิกเซลอาร์ต cells×cells + เส้นขอบดำ 1 ช่อง แบบ sprite animclip"""
    im = drop_bg(im)
    bb = im.getbbox() or (0, 0, im.width, im.height)
    im = im.crop(bb)
    k = cells / max(im.size)
    w, h = max(1, round(im.width * k)), max(1, round(im.height * k))
    small = im.resize((w, h), Image.LANCZOS)
    a = small.getchannel("A").point(lambda v: 255 if v > 110 else 0)
    rgb = small.convert("RGB").quantize(colors, method=Image.Quantize.MEDIANCUT).convert("RGB")
    g = Image.new("RGBA", (w + 2, h + 2), (0, 0, 0, 0))
    g.paste(rgb, (1, 1), a)
    ga = g.getchannel("A")
    ring = ga.filter(ImageFilter.MaxFilter(3))  # ขยาย 1 ช่อง = เส้นขอบ
    outl = Image.new("RGBA", g.size, OUTLINE)
    out = Image.new("RGBA", g.size, (0, 0, 0, 0))
    out.paste(outl, (0, 0), ring)
    out.alpha_composite(g)
    return out.resize((out.width * SCALE, out.height * SCALE), Image.NEAREST)


def card(sprite=None, icon=None, brand=None):
    """ตัวการ์ตูน + (โลโก้/ไอคอน) วางคู่กัน → สติกเกอร์ใบเดียว"""
    parts = []
    if sprite:
        parts.append(load(sprite))
    for thing in ([load("icon_" + icon)] if icon else []) + ([sticker(pixelate(favicon(brand)))] if brand else []):
        parts.append(thing)
    if not parts:
        raise SystemExit("ต้องมี sprite / icon / brand อย่างน้อย 1")
    if len(parts) == 1:
        return parts[0]
    # ตัวการ์ตูนซ้าย ของขวา ยกขึ้นนิดให้ดูเหมือนถือ/ชี้ · ซ้อนกันนิดหน่อยให้เป็นก้อนเดียว
    H = max(p.height for p in parts)
    gap = -24
    W = sum(p.width for p in parts) + gap * (len(parts) - 1)
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    x = 0
    for i, p in enumerate(parts):
        y = H - p.height if i == 0 else max(0, (H - p.height) // 2 - H // 10)
        out.alpha_composite(p, (x, y))
        x += p.width + gap
    return out


def make(spec, outdir):
    """spec {"sprite","icon","brand"} → path (แคชตาม spec)"""
    key = hashlib.md5(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:10]
    nm = "_".join(str(spec[k]).split(".")[0] for k in ("sprite", "icon", "brand") if spec.get(k))
    p = os.path.join(outdir, f"px_{nm}_{key}.png")
    if not os.path.exists(p):
        os.makedirs(outdir, exist_ok=True)
        card(spec.get("sprite"), spec.get("icon"), spec.get("brand")).save(p)
    return p


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("out", nargs="?")
    ap.add_argument("--sprite"); ap.add_argument("--icon"); ap.add_argument("--brand")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    if a.list:
        print(json.dumps(names(), ensure_ascii=False))
    else:
        card(a.sprite, a.icon, a.brand).save(a.out); print("✓", a.out)
