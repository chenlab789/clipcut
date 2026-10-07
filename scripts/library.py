"""คลังคลิป — อัปคลิปเก็บไว้ก่อน ยังไม่ตัด · ตัดเมื่อไหร่ก็หยิบจากคลัง (ต้นฉบับไม่โดนแตะ ตัดซ้ำกี่รอบก็ได้)

ไฟล์ใหม่ลง <root>/_library/<YYYYMMDD>/<ชื่อไฟล์> · คลิปที่เคยอัปก่อนมีคลัง (clips_*/ และต้นฉบับในโฟลเดอร์งาน) ดึงเข้ารายการเอง
รายการอยู่ <root>/_library/library.json: {path: {title, by, added, dur, ctime, vertical, uses: [edit.json]}}
ชื่อ: by = "frames" (AI ดู 4 เฟรมตอนอัป) → "project" (AI อ่านบทตอนตัด แม่นกว่า) → "user" (เฉินตั้งเอง ห้ามทับ)
"""
import os
import re
import json
import time
import threading
import subprocess

VIDEO_EXT = (".mp4", ".mov", ".mkv", ".m4v", ".webm", ".avi")
DERIVED = re.compile(r"\.(cut|proxy|gap|s[0-9a-f]+)\b|_(edit|preview|explainer)_\d+x\d+|\.raw\.", re.I)
TRASH_DAYS = 30  # อยู่ในถังขยะครบเท่านี้ = ลบจริง (ไฟล์ไปถังขยะ Windows อีกชั้น)
_lock = threading.Lock()
_name_q, _naming = [], [False]


def root_dir(root):
    d = os.path.join(root, "_library")
    os.makedirs(d, exist_ok=True)
    return d


def _index(root):
    return os.path.join(root_dir(root), "library.json")


def load(root):
    try:
        return json.load(open(_index(root), encoding="utf-8"))
    except Exception:
        return {}


def save(root, L):
    f = _index(root)
    json.dump(L, open(f + ".tmp", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(f + ".tmp", f)


def update(root, path, **kv):
    with _lock:
        L = load(root)
        k = _key(L, path)
        if k:
            L[k].update(kv); save(root, L)


def _key(L, path):
    n = os.path.normcase(os.path.abspath(path))
    return next((k for k in L if os.path.normcase(k) == n), None)


def dest(root, name):
    """ที่เก็บไฟล์อัปใหม่ — ชื่อซ้ำ (IMG_0001 คนละวัน) ต่อท้าย _2"""
    d = os.path.join(root_dir(root), time.strftime("%Y%m%d"))
    os.makedirs(d, exist_ok=True)
    b, e = os.path.splitext(os.path.basename(name))
    p, n = os.path.join(d, b + e), 2
    while os.path.exists(p):
        p = os.path.join(d, f"{b}_{n}{e}"); n += 1
    return p


def _probe(p):
    try:
        import multiclip
        i = multiclip.probe(p)
        return {"dur": round(i["dur"], 1), "ctime": i["ctime"], "vertical": i["h"] >= i["w"]}
    except Exception:
        return {"dur": 0, "ctime": None, "vertical": True}


def add(root, path, title=None, by=None):
    path = os.path.abspath(path)
    with _lock:
        L = load(root)
        if _key(L, path):
            return
    info = dict(_probe(path), title=title or os.path.splitext(os.path.basename(path))[0], by=by, added=time.time(), uses=[],
                size=os.path.getsize(path))
    with _lock:
        L = load(root)
        L.setdefault(path, info); save(root, L)


def scan_old(root, recent):
    """คลิปที่อัปไว้ก่อนมีคลัง → เข้ารายการ (ไม่ย้ายไฟล์) · ไฟล์ชื่อ+ขนาดซ้ำกัน (อัปซ้ำคนละกลุ่ม) เก็บตัวเดียว
    งานเก่าที่ทำจากคลิปไหน (autopilot.opts.json / ชื่อโฟลเดอร์) → uses + ชื่องานเป็นชื่อคลิป"""
    L = load(root)
    seen = {(os.path.basename(k).lower(), (L[k].get("size") or 0)) for k in L}
    found = []
    for d in os.scandir(root):
        if not d.is_dir() or d.name.startswith((".", "_")) or d.name.startswith("multi_"):
            continue
        for f in os.scandir(d.path):
            if f.is_file() and f.name.lower().endswith(VIDEO_EXT) and not DERIVED.search(f.name):
                if d.name.startswith("clips_") or os.path.splitext(f.name)[0] == d.name:
                    found.append(f)
    new = 0
    for f in sorted(found, key=lambda f: f.stat().st_mtime):
        k = (f.name.lower(), f.stat().st_size)
        if k in seen or _key(L, f.path):
            continue
        seen.add(k)
        L[os.path.abspath(f.path)] = dict(_probe(f.path), title=os.path.splitext(f.name)[0], by=None, added=f.stat().st_mtime,
                                          uses=[], size=f.stat().st_size)
        new += 1
    # งานที่เคยทำ: ชี้กลับหาคลิปต้นฉบับ (เทียบชื่อไฟล์)
    by_name = {os.path.basename(k).lower(): k for k in L}
    for e in recent:
        d = os.path.dirname(e)
        try:
            o = json.load(open(os.path.join(d, "autopilot.opts.json"), encoding="utf-8"))
        except Exception:
            o = {}
        srcs = o.get("clips") or [os.path.basename(d) + ext for ext in VIDEO_EXT]
        for s in srcs:
            k = by_name.get(os.path.basename(s).lower())
            if k and e not in L[k]["uses"]:
                L[k]["uses"].append(e)
                try:
                    t = json.load(open(e, encoding="utf-8")).get("title")
                except Exception:
                    t = None
                if t and not L[k].get("by"):
                    L[k].update(title=t, by="project")
    if new or recent:
        with _lock:
            cur = load(root)
            for k, v in L.items():
                cur.setdefault(k, v)
                cur[k]["uses"] = sorted(set(cur[k].get("uses", [])) | set(v.get("uses", [])))
                if v.get("by") == "project" and not cur[k].get("by"):
                    cur[k].update(title=v["title"], by="project")
            _dedupe(cur)
            save(root, cur)
    return new


def _dedupe(L):
    """ไฟล์เดียวกันอัปซ้ำคนละกลุ่ม (ชื่อ+ความยาวเท่ากัน — ขนาดไฟล์อาจต่างนิดหน่อย) → เหลือตัวเดียว รวม uses"""
    groups = {}
    for k, v in L.items():
        groups.setdefault((os.path.basename(k).lower(), round(v.get("dur") or 0)), []).append(k)
    for ks in groups.values():
        if len(ks) < 2 or not ks[0]:
            continue
        ks.sort(key=lambda k: (-len(L[k].get("uses", [])), "_library" not in k, L[k].get("added") or 0))
        main = L[ks[0]]
        for k in ks[1:]:
            main["uses"] = sorted(set(main.get("uses", [])) | set(L[k].get("uses", [])))
            if L[k].get("by") and not main.get("by"):
                main.update(title=L[k]["title"], by=L[k]["by"])
            L.pop(k)


def unnamed(root):
    return [k for k, v in load(root).items() if not v.get("by") and not v.get("trashed") and os.path.exists(k)]


def listing(root, trashed=False):
    """คลิปในคลัง · trashed=True = ในถังขยะแอป (ไฟล์ยังอยู่ที่เดิม แค่ซ่อน)"""
    L = load(root)
    out = []
    for k, v in L.items():
        if os.path.exists(k) and bool(v.get("trashed")) == trashed:
            out.append(dict(v, path=k, name=os.path.basename(k), uses=[u for u in v.get("uses", []) if os.path.exists(u)]))
    return sorted(out, key=lambda x: -(x.get("added") or 0))


def trash(root, path, on=True):
    """ลบในแอป = ย้ายเข้าถังขยะแอป (ไฟล์ไม่ขยับ) · on=False = กู้คืน"""
    with _lock:
        L = load(root)
        k = _key(L, path)
        if not k:
            return False
        if on:
            L[k]["trashed"] = time.time()
        else:
            L[k].pop("trashed", None)
        save(root, L)
    return True


def purge_old(root):
    """ในถังขยะครบ TRASH_DAYS วัน → ลบจริง"""
    old = [k for k, v in load(root).items() if v.get("trashed") and time.time() - v["trashed"] > TRASH_DAYS * 86400]
    for k in old:
        remove(root, k)
    return len(old)


def recycle(path):
    """ส่งไฟล์/โฟลเดอร์ไปถังขยะ Windows (กู้คืนได้) — ห้ามลบตรง"""
    fn = "DeleteDirectory" if os.path.isdir(path) else "DeleteFile"
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    f"Add-Type -AssemblyName Microsoft.VisualBasic; [Microsoft.VisualBasic.FileIO.FileSystem]::{fn}("
                    "$env:CC_DEL, 'OnlyErrorDialogs', 'SendToRecycleBin')"],
                   env=dict(os.environ, CC_DEL=path), capture_output=True, timeout=120,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return not os.path.exists(path)


def remove(root, path):
    """ลบถาวร: เอาออกจากคลัง + ไฟล์ไปถังขยะ Windows (กู้คืนได้จากถัง Windows)"""
    with _lock:
        L = load(root)
        k = _key(L, path)
        if not k:
            return False
        L.pop(k); save(root, L)
    if os.path.exists(k):
        recycle(k)
        for x in (k + ".segments.json", os.path.join(os.path.dirname(k), "_thumbs", os.path.basename(k) + ".jpg")):
            if os.path.exists(x):
                recycle(x)
    return True


def link(root, src, edit, title=None):
    """ตัดเสร็จ → จดว่าคลิปนี้ทำงานไหนไปแล้ว + ชื่อจากบท (ถ้าเฉินยังไม่ตั้งเอง)"""
    with _lock:
        L = load(root)
        k = _key(L, src)
        if not k:
            return
        if edit not in L[k]["uses"]:
            L[k]["uses"].append(edit)
        if title and L[k].get("by") != "user":
            L[k].update(title=title, by="project")
        save(root, L)


# ---------- ตั้งชื่อตอนอัป: AI ดู 4 เฟรม (คิว ทีละคลิป) ----------
def name_later(root, path):
    """path = คลิปในคลัง (ดูภาพ) หรือ .edit.json ของงานเก่าที่ยังไม่มีชื่อ (อ่านซับ)"""
    _name_q.append((root, path))
    if not _naming[0]:
        _naming[0] = True
        threading.Thread(target=_namer, daemon=True).start()


def _namer():
    try:
        while _name_q:
            root, path = _name_q.pop(0)
            try:
                if path.endswith(".edit.json"):
                    title_project(path)
                    continue
                t = title_from_frames(path)
                if t:
                    with _lock:
                        L = load(root)
                        k = _key(L, path)
                        if k and not L[k].get("by"):
                            L[k].update(title=t, by="frames"); save(root, L)
            except BaseException as ex:  # ai() พัง = SystemExit · server รันด้วย pythonw (ไม่มี stdout) → จดลงไฟล์
                _log(root, f"ตั้งชื่อ {os.path.basename(path)} ไม่ได้: {ex!r}")
    finally:
        _naming[0] = False


def _log(root, msg):
    try:
        with open(os.path.join(root_dir(root), "library.log"), "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")
    except OSError:
        pass


def title_project(edit):
    """งานเก่า (ก่อนมีชื่ออัตโนมัติ) → AI อ่านซับตั้งชื่อตามเนื้อหา · ข้อความล้วน ไม่ดูภาพ"""
    import autopilot
    import ccfx
    E = ccfx.load_edit(edit)
    if E.get("title"):
        return
    subs = [x["text"] for x in sorted(E["items"], key=lambda x: x["start"]) if x["track"] == "sub" and x.get("text", "").strip()]
    if not subs:
        return
    text = " / ".join(subs)[:2500]
    r = autopilot.ai(f"""ซับของคลิปวิดีโอเฉิน (ภาษาพูด): {text}
ตั้งชื่อคลิปภาษาไทยสั้นๆ ไม่เกิน 30 ตัวอักษร บอกว่าคลิปเกี่ยวกับอะไร ให้หาเจอง่ายทีหลัง ห้ามใส่วันที่/อีโมจิ
ตอบ JSON: {{"title": "..."}}""")
    t = str((r or {}).get("title") or "").strip()[:40]
    if t:
        E = ccfx.load_edit(edit)
        if not E.get("title"):  # ระหว่างรอ AI เฉินอาจตั้งเองแล้ว
            E["title"] = t
            ccfx.save_edit(edit, E)


def title_from_frames(path):
    import autopilot
    sheet = os.path.splitext(path)[0] + "._name.jpg"
    try:
        autopilot.contact_sheet(path, sheet, n=4)
        r = autopilot.ai(f"""Read ภาพนี้ (4 เฟรมเรียงเวลาจากคลิปวิดีโอของเฉิน): {sheet}
ตั้งชื่อคลิปภาษาไทยสั้นๆ ไม่เกิน 30 ตัวอักษร บอกว่าในคลิปทำอะไร/ที่ไหน ให้หาเจอง่ายทีหลัง (เช่น "แกะกล่องของขวัญที่ห้าง", "ทำกับข้าวกับแฟนที่คอนโด")
ห้ามใส่วันที่ ห้ามใส่อีโมจิ · ตอบ JSON: {{"title": "..."}}""", read=True)
        return str((r or {}).get("title") or "").strip()[:40] or None
    finally:
        if os.path.exists(sheet):
            os.remove(sheet)
