"""รูปถ่ายจริงจากเน็ต (ไม่ใช่ AI วาด) — เฉินพูดในคลิป "เอารูปกุ้งขึ้นตรงนี้" → หารูปกุ้งจริง

ค้น Openverse (รูป CC ไม่ต้องใช้ key) + Wikimedia Commons → ภาพย่อ ~12 รูปต่อคำสั่ง ทำเป็นแผ่นมีเลข
→ AI ดูทุกแผ่นในการเรียกเดียว เลือกรูปที่ตรงสุด/ชัดสุด → โหลดตัวเต็ม ใส่กรอบขาวแบบรูปแปะ → png
"""
import io
import os
import json
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

UA = {"User-Agent": "clipcut/1.1 (https://github.com/chenlab789/clipcut)"}


def _get(url, timeout=20):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()


def openverse(q, n=8):
    u = "https://api.openverse.org/v1/images/?" + urllib.parse.urlencode({"q": q, "page_size": n, "mature": "false"})
    try:
        d = json.loads(_get(u))
    except Exception:
        return []
    return [{"full": r["url"], "thumb": r.get("thumbnail") or r["url"], "title": r.get("title") or "", "src": "openverse"}
            for r in d.get("results", []) if r.get("url")]


def wikimedia(q, n=5):
    u = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode({
        "action": "query", "generator": "search", "gsrsearch": q + " filetype:bitmap", "gsrnamespace": 6, "gsrlimit": n,
        "prop": "imageinfo", "iiprop": "url", "iiurlwidth": 1080, "format": "json"})
    try:
        d = json.loads(_get(u))
    except Exception:
        return []
    out = []
    for p in sorted((d.get("query") or {}).get("pages", {}).values(), key=lambda p: p.get("index", 0)):
        ii = (p.get("imageinfo") or [{}])[0]
        if ii.get("thumburl"):
            out.append({"full": ii["thumburl"], "thumb": ii["thumburl"].replace("/1080px-", "/400px-"), "title": p["title"], "src": "wikimedia"})
    return out


def candidates(q):
    with ThreadPoolExecutor(2) as ex:
        a, b = ex.submit(openverse, q), ex.submit(wikimedia, q)
        return (a.result() + b.result())[:12]


def sheet(items, out, cell=260):
    """ภาพย่อเป็นตาราง 4 คอลัมน์ มีเลขมุมซ้ายบน → คืน index ที่โหลดได้"""
    from PIL import Image, ImageDraw, ImageFont

    def load(it):
        try:
            im = Image.open(io.BytesIO(_get(it["thumb"], 15))).convert("RGB")
            im.thumbnail((cell, cell))
            return im
        except Exception:
            return None
    with ThreadPoolExecutor(6) as ex:
        ims = list(ex.map(load, items))
    ok = [i for i, im in enumerate(ims) if im]
    if not ok:
        return []
    cols = 4
    rows = (len(ok) + cols - 1) // cols
    S = Image.new("RGB", (cols * cell, rows * cell), "#222")
    d = ImageDraw.Draw(S)
    try:
        f = ImageFont.truetype("arial.ttf", 34)
    except OSError:
        f = ImageFont.load_default()
    for k, i in enumerate(ok):
        x, y = k % cols * cell, k // cols * cell
        im = ims[i]
        S.paste(im, (x + (cell - im.width) // 2, y + (cell - im.height) // 2))
        d.rectangle([x, y, x + 46, y + 42], fill="#000")
        d.text((x + 8, y + 3), str(i), fill="#ff0", font=f)
    S.save(out, quality=85)
    return ok


def stick(raw, out, long_side=900):
    """รูปเต็ม → ย่อ + มุมมน + เงาจางใต้ภาพ → png โปร่งใส (เฉินไม่เอากรอบขาว)"""
    from PIL import Image, ImageDraw, ImageFilter
    im = Image.open(io.BytesIO(raw)).convert("RGBA")
    im.thumbnail((long_side, long_side))
    R, m = max(8, int(im.width * 0.055)), max(10, int(im.width * 0.06))
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, im.width - 1, im.height - 1], R, fill=255)
    S = Image.new("RGBA", (im.width + m * 2, im.height + m * 2), (0, 0, 0, 0))
    sh = Image.new("RGBA", S.size, (0, 0, 0, 0))
    sh.paste((0, 0, 0, 115), (m, m + m // 3), mask)
    S = Image.alpha_composite(S, sh.filter(ImageFilter.GaussianBlur(m / 2.2)))
    im.putalpha(mask)
    S.alpha_composite(im, (m, m))
    S.save(out)
    return out


def find_all(reqs, workdir, ai):
    """reqs [{key, query, desc}] → {key: path png} · ai = autopilot.ai (เรียกครั้งเดียวทุกคำสั่ง)"""
    os.makedirs(workdir, exist_ok=True)
    jobs = []
    for r in reqs:
        c = candidates(r["query"])
        if not c:
            print(f"  ! ไม่เจอรูป \"{r['query']}\"", flush=True)
            continue
        sh = os.path.join(workdir, f"_pick_{r['key']}.jpg")
        ok = sheet(c, sh)
        if ok:
            jobs.append((r, c, ok, sh))
    if not jobs:
        return {}
    lines = "\n".join(f"- คำสั่ง {r['key']}: เฉินขอ \"{r['desc']}\" (ค้นด้วย \"{r['query']}\") → Read {sh} (เลขที่ใช้ได้: {ok})"
                      for r, c, ok, sh in jobs)
    prompt = f"""เฉินพูดในคลิปขอให้เอารูปขึ้นจอ เลือกรูปที่ดีที่สุดของแต่ละคำสั่ง (ตรงกับที่ขอ ชัด เห็นของชัดเต็มตา ไม่มีตัวหนังสือ/ลายน้ำเยอะ)
{lines}
ตอบ JSON อย่างเดียว: {{"<คำสั่ง>": <เลขรูป>, ...}} — ไม่มีรูปไหนตรงเลย = null"""
    try:
        pick = ai(prompt, read=True)
    except BaseException as ex:
        print(f"  ! AI เลือกรูปไม่ได้ ใช้รูปแรก: {ex}", flush=True)
        pick = {}
    out = {}
    for r, c, ok, sh in jobs:
        i = pick.get(r["key"], ok[0]) if isinstance(pick, dict) else ok[0]
        if i is None or not isinstance(i, int) or i not in ok:
            continue
        for j in [i] + [k for k in ok if k != i][:2]:  # รูปเต็มโหลดไม่ได้ = ลองตัวถัดไป
            try:
                out[r["key"]] = stick(_get(c[j]["full"], 30), os.path.join(workdir, f"photo_{r['key']}.png"))
                break
            except Exception:
                continue
    return out
