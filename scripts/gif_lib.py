#!/usr/bin/env python
"""คลัง GIF/meme ในเครื่อง — AI หยิบมาแปะ/ตัดเข้าตามบริบท

  python gif_lib.py build [--per 10] [--cat shocked,...]   โหลดจาก GIPHY ตามหมวด → AI คัดทีละหมวด → เข้าคลัง
  python gif_lib.py mine                                   นำเข้าไฟล์ที่เฉินโยนใส่ assets/gif/_mine/ (gif/mp4/webm)
  python gif_lib.py list

คลัง: assets/gif/<หมวด>/<id>.mp4 + assets/gif/library.json  (ไม่ขึ้น GitHub — ลิขสิทธิ์เป็นของเจ้าของภาพ)
  library[id] = {cat, file, dur, w, h, desc, tags, src, uses}
GIPHY key = env GIPHY_API_KEY (ตัวแปรผู้ใช้ Windows)
"""
import os
import re
import sys
import json
import shutil
import threading
import subprocess
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ccfx  # noqa: E402,F401  (ซ่อนหน้าต่าง subprocess)

ROOT = os.path.join(os.path.dirname(HERE), "assets", "gif")
LIB = os.path.join(ROOT, "library.json")
MINE = os.path.join(ROOT, "_mine")
FF = os.environ.get("FFMPEG", "ffmpeg")
_lock = threading.Lock()

# หมวด: (ชื่อไทย, ใช้ตอนไหน, คำค้น GIPHY)
CATS = {
    "shocked": ("ช็อค/ตกใจ", "เห็นราคา เจอของไม่คาดคิด ข่าวช็อค", ["shocked reaction", "surprised face", "jaw drop"]),
    "laugh": ("ขำหนัก", "มุกฮา เรื่องตลก ขำตัวเอง", ["laughing hard", "lol reaction", "crying laughing"]),
    "facepalm": ("กุมขมับ", "ทำพลาดโง่ๆ เพื่อนพูดโง่ เบื่อกับความโง่", ["facepalm", "smh disappointed"]),
    "confused": ("งง/ห๊ะ", "ไม่เข้าใจ อะไรวะ ตามไม่ทัน", ["confused reaction", "what huh", "math lady confused"]),
    "mindblown": ("ทึ่ง/สุดยอด", "ไอเดียเจ๋ง เทคโนโลยีว้าว เพิ่งรู้", ["mind blown", "wow amazed"]),
    "celebrate": ("ดีใจ/ฉลอง", "สำเร็จ ได้ของ ชนะ", ["celebration dance", "yes victory", "happy dance"]),
    "fail": ("พัง/เฟล", "ของพัง ทำไม่สำเร็จ ล้ม", ["epic fail", "fail funny", "oops"]),
    "money": ("เงิน/รวย", "ได้เงิน รวย ของแพง จ่ายหนัก", ["money rain", "rich flex money", "make it rain"]),
    "broke": ("จน/หมดตัว", "เงินหมด กระเป๋าแห้ง ราคาแพงเกิน", ["broke no money", "empty wallet"]),
    "waiting": ("รอนาน/เบื่อ", "รอโหลด รอนาน น่าเบื่อ", ["waiting bored", "skeleton waiting", "still waiting"]),
    "thinking": ("คิดหนัก", "กำลังคิด คิดเลข วางแผน", ["thinking hard", "calculating"]),
    "nope": ("ไม่!/ปฏิเสธ", "ไม่เอา ปฏิเสธ หนี", ["nope", "no no no"]),
    "agree": ("เห็นด้วย/โอเค", "ใช่เลย ถูกต้อง ยกนิ้ว", ["thumbs up", "agree nodding", "exactly"]),
    "awkward": ("อึดอัด/เงียบ", "มุกแป้ก เงียบกริบ เขินๆ", ["awkward silence", "awkward smile", "crickets"]),
    "plottwist": ("พลิกล็อค", "เรื่องหักมุม เปิดเผยความจริง", ["plot twist", "dramatic reveal", "dramatic chipmunk"]),
    "runaway": ("วิ่งหนี", "หนีปัญหา ชิ่ง ไปละ", ["running away", "nope run"]),
    "angry": ("โกรธ/หัวร้อน", "หงุดหงิด โมโห ระเบิด", ["angry rage", "mad reaction"]),
    "sad": ("เศร้า/ร้องไห้", "ผิดหวัง เสียใจ ดราม่า", ["crying sad", "sad reaction"]),
    "cute": ("น่ารัก/เขิน", "แฟน หวาน เขิน ของน่ารัก", ["cute blush", "aww cute", "shy"]),
    "suspicious": ("มองค้อน/สงสัย", "ไม่เชื่อ จับผิด มองเหล่", ["side eye", "suspicious"]),
    "hacker": ("แฮกเกอร์/พิมพ์รัว", "เขียนโค้ด เทค ทำงานคอม", ["hacker typing", "typing fast computer"]),
    "hungry": ("กิน/หิว", "อาหาร หิว อร่อย", ["hungry eating", "delicious food reaction"]),
    "tired": ("ง่วง/เหนื่อย", "เหนื่อย ง่วง ทำงานหนัก", ["tired exhausted", "sleepy"]),
    "cool": ("เท่/เก๋า", "ทำได้เท่ๆ อวด ภูมิใจ", ["deal with it", "cool sunglasses"]),
    "applause": ("ปรบมือ", "ชม เก่งมาก ยอมรับ", ["applause clapping", "slow clap"]),
}


def key():
    k = os.environ.get("GIPHY_API_KEY")
    if not k and os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as h:
                k = winreg.QueryValueEx(h, "GIPHY_API_KEY")[0]
        except OSError:
            pass
    if not k:
        raise SystemExit("ไม่มี GIPHY_API_KEY")
    return k


def lib():
    try:
        return json.load(open(LIB, encoding="utf-8"))
    except Exception:
        return {}


def save_lib(d):
    os.makedirs(ROOT, exist_ok=True)
    tmp = LIB + ".tmp"
    json.dump(d, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(tmp, LIB)


def path(gid, L=None):
    g = (L or lib()).get(gid)
    return os.path.join(ROOT, g["file"]) if g else None


def probe(p):
    o = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height:format=duration", "-of", "json", p], capture_output=True, text=True).stdout
    j = json.loads(o or "{}")
    st = (j.get("streams") or [{}])[0]
    return float(j.get("format", {}).get("duration") or 0), st.get("width", 0), st.get("height", 0)


def search(q, limit=25):
    url = "https://api.giphy.com/v1/gifs/search?" + urllib.parse.urlencode(
        {"api_key": key(), "q": q, "limit": limit, "rating": "pg-13", "lang": "en"})
    with urllib.request.urlopen(url, timeout=20) as r:
        data = json.load(r)["data"]
    out = []
    for d in data:
        im = d.get("images", {}).get("original_mp4") or {}
        if not im.get("mp4"):
            continue
        out.append({"gid": "g_" + d["id"], "url": im["mp4"], "w": int(im.get("width") or 0), "h": int(im.get("height") or 0),
                    "size": int(im.get("mp4_size") or 0), "title": d.get("title", "")})
    return out


def download(url, dst):
    req = urllib.request.Request(url, headers={"User-Agent": "clipcut"})
    with urllib.request.urlopen(req, timeout=30) as r, open(dst, "wb") as f:
        shutil.copyfileobj(r, f)


def to_mp4(src, dst):
    """gif/webm/mp4 ใดๆ → mp4 h264 เล่นลื่น seek ง่าย (keyframe ถี่) · ไม่เกิน 6 วิ"""
    subprocess.run([FF, "-y", "-v", "error", "-i", src, "-t", "6", "-an", "-vf",
                    "scale='trunc(min(iw,720)/2)*2':-2,fps=30,format=yuv420p", "-c:v", "libx264", "-preset", "veryfast",
                    "-crf", "23", "-g", "15", "-movflags", "+faststart", dst], check=True)


def sheet(items, out, cell=220):
    """ภาพตัวอย่าง 3 เฟรม/ตัว เรียงเป็นแถว มีเลขกำกับ → ให้ AI ดู"""
    from PIL import Image, ImageDraw
    rows = []
    for i, it in enumerate(items):
        d = max(0.3, it["dur"])
        fr = []
        for k, f in enumerate((0.15, 0.5, 0.85)):
            p = it["mp4"] + f".{k}.jpg"
            subprocess.run([FF, "-y", "-v", "error", "-ss", f"{d * f:.2f}", "-i", it["mp4"], "-frames:v", "1",
                            "-vf", f"scale={cell}:{cell}:force_original_aspect_ratio=decrease", p], capture_output=True)
            if os.path.exists(p):
                fr.append(Image.open(p).convert("RGB")); os.remove(p)
        row = Image.new("RGB", (cell * 3 + 70, cell + 8), (25, 25, 25))
        ImageDraw.Draw(row).text((8, cell // 2 - 8), f"#{i}", fill=(255, 255, 0))
        for k, im in enumerate(fr):
            row.paste(im, (60 + k * cell + (cell - im.width) // 2, 4 + (cell - im.height) // 2))
        rows.append(row)
    cols = 2
    W = rows[0].width * cols
    H = rows[0].height * ((len(rows) + cols - 1) // cols)
    sh = Image.new("RGB", (W, H), (25, 25, 25))
    for i, r in enumerate(rows):
        sh.paste(r, ((i % cols) * r.width, (i // cols) * r.height))
    sh.save(out, quality=88)
    return out


def judge(cat, items, want, workdir):
    """AI ดูภาพตัวอย่าง → เลือกตัวที่ตรงหมวด + เขียนคำอธิบาย/แท็ก"""
    import autopilot
    th, when, _ = CATS.get(cat, (cat, "", []))
    sp = sheet(items, os.path.join(workdir, f"_judge_{cat}.jpg"))
    prompt = f"""Read ภาพนี้: {sp}
แต่ละช่อง (#เลข) = GIF 1 ตัว แสดง 3 เฟรม (ต้น กลาง ท้าย)
หมวด "{th}" — ใช้ตัดต่อคลิป TikTok ภาษาไทยตอน: {when}

เลือกไม่เกิน {want} ตัวที่ดีที่สุดสำหรับหมวดนี้:
- คนดูเข้าใจอารมณ์ทันทีใน 1 วิ ไม่ต้องรู้บริบท (reaction ชัด หน้าชัด ท่าชัด)
- ไม่เอา: ตัวหนังสือภาษาอังกฤษเต็มภาพ, ลายน้ำ/โลโก้ใหญ่, ภาพแตก/มืด, ส่อเพศ/รุนแรง, โฆษณา, ซ้ำกันเอง
- ให้หลากหลาย (คน สัตว์ การ์ตูน)
ตอบ JSON: {{"pick": [{{"i": <เลข>, "desc": "<อธิบายภาพเป็นไทยสั้นๆ เช่น แมวตาโตอ้าปากค้าง>", "tags": ["<คำไทย/อังกฤษ 3-6 คำ>"]}}]}}"""
    r = autopilot.ai(prompt, read=True, model="sonnet")
    return [p for p in r.get("pick", []) if isinstance(p.get("i"), int) and 0 <= p["i"] < len(items)]


def build_cat(cat, per=10, workdir=None):
    workdir = workdir or os.path.join(ROOT, "_tmp")
    os.makedirs(workdir, exist_ok=True)
    L = lib()
    have = [g for g in L.values() if g["cat"] == cat]
    if len(have) >= per:
        return 0
    seen, cands = {g.get("src_id") for g in L.values()}, []
    for q in CATS[cat][2]:
        for c in search(q):
            if c["gid"] not in seen and c["size"] < 6_000_000 and c["w"] >= 200:
                seen.add(c["gid"]); cands.append(c)
    cands.sort(key=lambda c: -min(c["w"], 480))  # ภาพใหญ่ก่อน (ตัดเข้าเต็มจอไม่แตก)
    cands = cands[:18]
    items = []
    for c in cands:
        raw = os.path.join(workdir, c["gid"] + ".raw.mp4")
        mp4 = os.path.join(workdir, c["gid"] + ".mp4")
        try:
            download(c["url"], raw); to_mp4(raw, mp4)
            dur, w, h = probe(mp4)
            if 0.4 <= dur:
                items.append(dict(c, mp4=mp4, dur=dur, w=w, h=h))
        except Exception as e:
            print(f"  ! โหลด {c['gid']} ไม่ได้: {e}", flush=True)
        finally:
            if os.path.exists(raw):
                os.remove(raw)
    if not items:
        return 0
    picks = judge(cat, items, per - len(have), workdir)
    os.makedirs(os.path.join(ROOT, cat), exist_ok=True)
    n = 0
    with _lock:
        L = lib()
        for p in picks:
            it = items[p["i"]]
            gid = it["gid"]
            dst = os.path.join(ROOT, cat, gid + ".mp4")
            shutil.move(it["mp4"], dst)
            L[gid] = {"cat": cat, "file": f"{cat}/{gid}.mp4", "dur": round(it["dur"], 2), "w": it["w"], "h": it["h"],
                      "desc": str(p.get("desc", ""))[:80], "tags": [str(t) for t in p.get("tags", [])][:8],
                      "src": "giphy", "src_id": gid, "title": it["title"][:80], "uses": 0}
            n += 1
        save_lib(L)
    for it in items:
        if os.path.exists(it["mp4"]):
            os.remove(it["mp4"])
    print(f"  {cat}: +{n} (คัดจาก {len(items)})", flush=True)
    return n


def build(cats=None, per=10, workers=4):
    cats = cats or list(CATS)
    todo = list(cats)
    total = [0]

    def run():
        while True:
            with _lock:
                if not todo:
                    return
                c = todo.pop(0)
            try:
                n = build_cat(c, per)
                with _lock:
                    total[0] += n
            except Exception as e:
                print(f"  ! {c}: {e}", flush=True)
    ts = [threading.Thread(target=run) for _ in range(workers)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    shutil.rmtree(os.path.join(ROOT, "_tmp"), ignore_errors=True)
    print(f"✓ เพิ่ม {total[0]} ตัว · คลังรวม {len(lib())}")


def import_mine():
    """ไฟล์ที่เฉินโยนใส่ _mine/ → แปลง mp4 → AI ดูแล้วจัดหมวด+คำอธิบาย"""
    import autopilot
    os.makedirs(MINE, exist_ok=True)
    fs = [f for f in os.listdir(MINE) if re.search(r"\.(gif|mp4|webm|mov)$", f, re.I)]
    if not fs:
        print("ไม่มีไฟล์ใหม่ใน", MINE); return
    work = os.path.join(ROOT, "_tmp"); os.makedirs(work, exist_ok=True)
    items = []
    for f in fs:
        gid = "m_" + re.sub(r"[^a-zA-Z0-9]", "_", os.path.splitext(f)[0])[:40]
        mp4 = os.path.join(work, gid + ".mp4")
        to_mp4(os.path.join(MINE, f), mp4)
        dur, w, h = probe(mp4)
        items.append({"gid": gid, "mp4": mp4, "dur": dur, "w": w, "h": h, "orig": f, "title": f})
    L = lib()
    for b in range(0, len(items), 12):
        part = items[b: b + 12]
        sp = sheet(part, os.path.join(work, f"_mine_{b}.jpg"))
        cats = ", ".join(f"{k} ({v[0]})" for k, v in CATS.items())
        r = autopilot.ai(f"""Read ภาพนี้: {sp}
แต่ละช่อง (#เลข) = GIF/meme 1 ตัว (3 เฟรม) — จัดหมวดให้แต่ละตัว
หมวดที่มี: {cats}  (ไม่เข้าหมวดไหนเลย ตั้งชื่อหมวดใหม่ภาษาอังกฤษสั้นๆ ได้)
ตอบ JSON: {{"items": [{{"i": <เลข>, "cat": "<หมวด>", "desc": "<อธิบายไทยสั้นๆ>", "tags": ["..."]}}]}}""", read=True, model="sonnet")
        for p in r.get("items", []):
            it = part[p["i"]]
            cat = re.sub(r"[^a-z0-9_]", "", str(p.get("cat", "mine")).lower()) or "mine"
            os.makedirs(os.path.join(ROOT, cat), exist_ok=True)
            shutil.move(it["mp4"], os.path.join(ROOT, cat, it["gid"] + ".mp4"))
            L[it["gid"]] = {"cat": cat, "file": f"{cat}/{it['gid']}.mp4", "dur": round(it["dur"], 2), "w": it["w"], "h": it["h"],
                            "desc": str(p.get("desc", ""))[:80], "tags": p.get("tags", [])[:8], "src": "mine", "title": it["orig"], "uses": 0}
            os.replace(os.path.join(MINE, it["orig"]), os.path.join(MINE, "_done_" + it["orig"]))
    save_lib(L)
    shutil.rmtree(work, ignore_errors=True)
    print(f"✓ นำเข้า {len(items)} ตัว")


def online(query, cat, workdir):
    """คลังไม่มีตัวที่ตรง → ค้น GIPHY สด เอาตัวที่ AI เลือกเข้าคลังเลย (คลังโตเอง) → คืน gid หรือ None"""
    items = []
    for c in search(query, 12)[:8]:
        if c["gid"] in lib():
            return c["gid"]
        raw, mp4 = os.path.join(workdir, c["gid"] + ".raw.mp4"), os.path.join(workdir, c["gid"] + ".mp4")
        try:
            download(c["url"], raw); to_mp4(raw, mp4)
            dur, w, h = probe(mp4)
            items.append(dict(c, mp4=mp4, dur=dur, w=w, h=h))
        except Exception:
            pass
        finally:
            if os.path.exists(raw):
                os.remove(raw)
    if not items:
        return None
    CATS.setdefault(cat, (cat, query, [query]))
    picks = judge(cat, items, 1, workdir)
    if not picks:
        return None
    it = items[picks[0]["i"]]
    os.makedirs(os.path.join(ROOT, cat), exist_ok=True)
    shutil.move(it["mp4"], os.path.join(ROOT, cat, it["gid"] + ".mp4"))
    with _lock:
        L = lib()
        L[it["gid"]] = {"cat": cat, "file": f"{cat}/{it['gid']}.mp4", "dur": round(it["dur"], 2), "w": it["w"], "h": it["h"],
                        "desc": str(picks[0].get("desc", ""))[:80], "tags": picks[0].get("tags", [])[:8], "src": "giphy",
                        "src_id": it["gid"], "title": it["title"][:80], "uses": 0}
        save_lib(L)
    return it["gid"]


def ban(gid):
    """เฉินกดลบออกจากคลังใน editor"""
    with _lock:
        L = lib()
        g = L.pop(gid, None)
        if g:
            p = os.path.join(ROOT, g["file"])
            if os.path.exists(p):
                os.remove(p)
            save_lib(L)
    return bool(g)


def bump(gids):
    with _lock:
        L = lib()
        for g in gids:
            if g in L:
                L[g]["uses"] = L[g].get("uses", 0) + 1
        save_lib(L)


def catalog(L=None):
    """รายการสั้นให้ AI เลือก: หมวด → id|ยาว|คำอธิบาย (ใช้น้อยก่อน)"""
    L = L or lib()
    out = []
    for cat in sorted({g["cat"] for g in L.values()}):
        gs = sorted(((k, g) for k, g in L.items() if g["cat"] == cat), key=lambda kv: kv[1].get("uses", 0))
        th = CATS.get(cat, (cat,))[0]
        out.append(f"[{cat} {th}] " + " · ".join(f"{k}:{g['dur']:.1f}s:{g['desc']}" for k, g in gs))
    return "\n".join(out)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build", "mine", "list"])
    ap.add_argument("--per", type=int, default=10)
    ap.add_argument("--cat")
    a = ap.parse_args()
    if a.cmd == "build":
        build(a.cat.split(",") if a.cat else None, a.per)
    elif a.cmd == "mine":
        import_mine()
    else:
        L = lib()
        for cat in sorted({g["cat"] for g in L.values()}):
            print(f"{cat:12} {sum(1 for g in L.values() if g['cat'] == cat)}")
        print("รวม", len(L))


if __name__ == "__main__":
    main()
