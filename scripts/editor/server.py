#!/usr/bin/env python
"""ClipCut — โปรแกรมตัดคลิปบนเครื่อง (หน้าต่าง Chrome --app)

  python server.py                 หน้าแรก: ลากคลิปวาง → เลือกแบบ → AI ทำให้ → เข้า editor
  python server.py <คลิป.mp4>       เปิดหน้าแรกพร้อมคลิปนี้ (ลากไฟล์ใส่ไอคอน Desktop = แบบนี้)
  python server.py <ชื่อ>.edit.json  เปิด editor ตรง
  [--port 8765] [--no-open]

- หน้าแรก (home.html): ลากวาง / ตัวเลือก / แถบความคืบหน้า autopilot.py / โปรเจกต์ล่าสุด
- editor (index.html): พรีวิวสด + timeline · เฉินแก้ในเบราว์เซอร์ → เซฟลงไฟล์ · กุ้งแก้ไฟล์ → หน้าเว็บอัปเดตเอง (SSE)
- ปุ่ม Render → render_edit.py (log สดในหน้าเว็บ)
- เปิดซ้ำตอนตัวเดิมรันอยู่ → ส่งไฟล์ให้ตัวเดิม (ตัวเดียวพอ)
"""
import os
import sys
import json
import time
import hashlib
import argparse
import mimetypes
import threading
import subprocess
import webbrowser
import urllib.request
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import unquote, urlparse, parse_qs

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # pythonw ไม่มี stdout
    pass
UI = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(UI)
sys.path.insert(0, SCRIPTS)
import ccfx  # noqa: E402
import pixel  # noqa: E402

SKILL_PIX = pixel.PIX

mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("font/ttf", ".ttf")

EDIT = PROJ = None
# rev เริ่มจากเวลา (ไม่ใช่ 0) — server รีสตาร์ทแล้วหน้าต่างเก่าที่ยังเปิดอยู่ต้องไม่มีเลขตรงกันโดยบังเอิญ
# (เคยเกิด: หน้าเก่าส่ง base_rev ตรงพอดี → เซฟข้อมูลเก่าทับ ข้อมูลหน้า/โฟกัสที่เพิ่งทำหาย)
state = {"hash": None, "rev": int(time.time()), "render": None, "staged": None}
job = {"state": "idle"}
clients = []  # queue ของ SSE แต่ละแท็บ
lock = threading.Lock()
PORT = 8765
RECENT = os.path.join(os.path.expanduser("~"), ".clipcut", "recent.json")
VIDEO_EXT = (".mp4", ".mov", ".mkv", ".m4v", ".webm", ".avi")


def projects_root():
    """โปรเจกต์ใหม่ไปอยู่ที่นี่ (ตั้งเองได้ด้วย env CLIPCUT_HOME)"""
    r = os.environ.get("CLIPCUT_HOME")
    if not r:
        r = (r"D:\ChenLab-Recordings\clipcut" if os.path.isdir(r"D:\ChenLab-Recordings")
             else os.path.join(os.path.expanduser("~"), "Videos", "clipcut"))
    os.makedirs(r, exist_ok=True)
    return r


def file_hash():
    if not EDIT:
        return None
    try:
        with open(EDIT, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()
    except FileNotFoundError:
        return None


def broadcast(event, data):
    msg = f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode("utf-8")
    with lock:
        for q in list(clients):
            q.append(msg)


def watcher():
    """ไฟล์เปลี่ยนจากข้างนอก (กุ้งแก้) → บอกทุกแท็บให้โหลดใหม่"""
    while True:
        time.sleep(0.4)
        if not EDIT:
            continue
        h = file_hash()
        if h and h != state["hash"]:
            try:
                data = ccfx.load_edit(EDIT)
            except Exception:
                continue  # เขียนไม่เสร็จ/JSON พัง — รอรอบหน้า
            state["hash"] = h
            state["rev"] += 1
            broadcast("edit", {"rev": state["rev"], "edit": data, "by": "file", "file": os.path.basename(EDIT)})


# ---------- โปรเจกต์ ----------
HIDDEN = os.path.join(os.path.dirname(RECENT), "hidden.json")  # รุ่นเก่า: กด "เอาออกจากรายการ" (ไม่ลบไฟล์)
TRASH = os.path.join(os.path.dirname(RECENT), "trash.json")    # ถังขยะแอป: [{edit, t}] ครบ 30 วัน = ลบโฟลเดอร์จริง
rlock = threading.Lock()


def trashed_projects():
    with rlock:
        return [x for x in _jload(TRASH) if isinstance(x, dict) and os.path.exists(x.get("edit", ""))]


def project_trash(edit, on=True):
    with rlock:
        t = [x for x in _jload(TRASH) if isinstance(x, dict) and os.path.normcase(x.get("edit", "")) != os.path.normcase(edit)]
        if on:
            t.append({"edit": edit, "t": time.time()})
        _jsave(TRASH, t)


def project_purge(edit):
    """ลบถาวร: โฟลเดอร์งานไปถังขยะ Windows (กู้ได้จากถัง Windows) · ต้องเป็นโฟลเดอร์งานใต้ projects_root เท่านั้น"""
    global EDIT, PROJ
    import library
    d = os.path.realpath(os.path.dirname(edit))
    root = os.path.realpath(projects_root())
    if os.path.dirname(d) != root or os.path.basename(d).startswith(("_", ".")) or not edit.endswith(".edit.json"):
        return False
    if job.get("state") == "running" and os.path.normcase(os.path.dirname(job.get("edit") or "")) == os.path.normcase(d):
        return False
    if EDIT and os.path.normcase(os.path.dirname(EDIT)) == os.path.normcase(d):
        EDIT = PROJ = None
    ok = library.recycle(d)
    if ok:
        project_trash(edit, False)
        save_recent([x for x in _jload(RECENT) if os.path.normcase(os.path.dirname(x)) != os.path.normcase(d)])
    return ok


def purge_old_projects():
    import library
    for x in trashed_projects():
        if time.time() - x["t"] > library.TRASH_DAYS * 86400:
            project_purge(x["edit"])


def trash_listing():
    import library
    root, days = projects_root(), library.TRASH_DAYS
    left = lambda t: max(0, days - int((time.time() - t) // 86400))  # noqa: E731
    clips = [dict(c, left=left(c["trashed"])) for c in library.listing(root, trashed=True)]
    projs = []
    for x in trashed_projects():
        try:
            projs.append(dict(project_info(x["edit"]), trashed=x["t"], left=left(x["t"])))
        except Exception:
            pass
    return {"clips": sorted(clips, key=lambda c: -c["trashed"]), "projects": sorted(projs, key=lambda c: -c["trashed"]), "days": days}


# ---------- เวลาที่ใช้ตัด (ไว้เดาว่าเหลืออีกกี่นาที) ----------
STATS = os.path.join(os.path.dirname(RECENT), "jobstats.json")


def est_secs(dur, opts):
    """เวลาทั้งงาน ≈ 60 + k × ความยาวคลิป · k = มัธยฐานจากงานจริงแบบเดียวกัน 12 งานล่าสุด"""
    mode = opts.get("mode") or "fx"
    ks = sorted((x["secs"] - 60) / x["dur"] for x in _jload(STATS)[-40:]
                if isinstance(x, dict) and x.get("mode") == mode and x.get("dur", 0) > 5)[-12:]
    k = ks[len(ks) // 2] if ks else (5.0 if mode == "explainer" else 4.0)
    return 60 + max(1.0, k) * dur


def save_stat(dur, secs, opts):
    if dur > 5 and secs > 20:
        with rlock:
            _jsave(STATS, (_jload(STATS) + [{"dur": round(dur, 1), "secs": round(secs), "mode": opts.get("mode") or "fx",
                                              "clips": len(opts.get("clips") or [1]), "t": int(time.time())}])[-200:])


def src_dur(paths):
    import multiclip
    tot = 0.0
    for q in paths:
        try:
            tot += multiclip.probe(q)["dur"]
        except Exception:
            pass
    return tot


# ---------- แจ้งเตือนมือถือ (Web Push) — ตัด/เรนเดอร์เสร็จ เด้งบอกแม้ปิดหน้าไปแล้ว ----------
PUSH_SUBS = os.path.join(os.path.dirname(RECENT), "push.json")
VAPID_PEM = os.path.join(os.path.dirname(RECENT), "vapid.pem")


def vapid_public():
    """กุญแจสาธารณะ (base64url) ให้หน้าเว็บสมัครรับแจ้งเตือน · กุญแจลับอยู่ ~/.clipcut/vapid.pem เท่านั้น"""
    import base64
    from py_vapid import Vapid
    from cryptography.hazmat.primitives import serialization
    if not os.path.exists(VAPID_PEM):
        v = Vapid(); v.generate_keys(); v.save_key(VAPID_PEM)
    v = Vapid.from_file(VAPID_PEM)
    raw = v.public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def push_send(title, body, url="/"):
    def go():
        try:
            from pywebpush import webpush, WebPushException
        except ImportError:
            return
        with rlock:
            subs = _jload(PUSH_SUBS)
        dead = []
        for sub in subs:
            try:
                webpush(sub, json.dumps({"title": title, "body": body, "url": url}, ensure_ascii=False),
                        vapid_private_key=VAPID_PEM, vapid_claims={"sub": "https://github.com/chenlab789/clipcut"}, timeout=15)
            except WebPushException as ex:
                if ex.response is not None and ex.response.status_code in (404, 410):  # ยกเลิก/ลบแอปไปแล้ว
                    dead.append(sub.get("endpoint"))
            except Exception:
                pass
        if dead:
            with rlock:
                _jsave(PUSH_SUBS, [x for x in _jload(PUSH_SUBS) if x.get("endpoint") not in dead])
    if os.path.exists(PUSH_SUBS):
        threading.Thread(target=go, daemon=True).start()


def _jload(f):
    try:
        return json.load(open(f, encoding="utf-8"))
    except Exception:
        return []


def _jsave(f, obj):  # เขียนไฟล์ชั่วคราวแล้วสลับ — อ่านพร้อมกันจะไม่เจอไฟล์ว่างครึ่งๆ (เคยทำรายการหายเหลืองานเดียว)
    os.makedirs(os.path.dirname(f), exist_ok=True)
    t = f + ".tmp"
    json.dump(obj, open(t, "w", encoding="utf-8"), ensure_ascii=False)
    os.replace(t, f)


def recent_list():
    """งานที่เพิ่งเปิด (recent.json) + งานอื่นที่อยู่ในโฟลเดอร์โปรเจกต์ (สแกนเอง ล่าสุดก่อน) · ยกเว้นที่กดเอาออก"""
    with rlock:
        rec, hid = _jload(RECENT), {os.path.normcase(x) for x in _jload(HIDDEN)}
        hid |= {os.path.normcase(x.get("edit", "")) for x in _jload(TRASH) if isinstance(x, dict)}
    out, seen = [], set()
    for p in rec:
        if os.path.exists(p) and os.path.normcase(p) not in seen and os.path.normcase(p) not in hid:
            out.append(p); seen.add(os.path.normcase(p))
    root, found = projects_root(), []
    try:
        for d in os.scandir(root):
            if d.is_dir() and not d.name.startswith((".", "_")):
                for f in os.scandir(d.path):
                    if f.name.endswith(".edit.json"):
                        found.append((f.stat().st_mtime, f.path))
    except OSError:
        pass
    for _, p in sorted(found, reverse=True):
        if os.path.normcase(p) not in seen and os.path.normcase(p) not in hid:
            out.append(p); seen.add(os.path.normcase(p))
    return out[:40]


def save_recent(lst):
    with rlock:
        _jsave(RECENT, lst[:30])


def open_project(edit):
    """สลับ editor ไปโปรเจกต์นี้"""
    global EDIT, PROJ
    edit = os.path.abspath(edit)
    E = ccfx.load_edit(edit)
    proj = os.path.dirname(edit)
    if "voice_lufs" not in E:  # edit.json รุ่นเก่า → วัดความดังเสียงพูดเพิ่ม
        E["voice_lufs"] = round(ccfx.measure_lufs(os.path.join(proj, E["video"])), 1)
        E.setdefault("mix", dict(ccfx.MIX_DEFAULT)); E.setdefault("music", None)
        ccfx.save_edit(edit, E)
    EDIT, PROJ = edit, proj
    threading.Thread(target=make_proxy, args=(edit,), daemon=True).start()
    state["hash"] = file_hash()
    state["rev"] += 1
    save_recent([edit] + [p for p in _jload(RECENT) if os.path.normcase(p) != os.path.normcase(edit)])
    with rlock:  # เปิดงานที่เคยเอาออก = กลับมาในรายการ
        h = _jload(HIDDEN)
        if any(os.path.normcase(x) == os.path.normcase(edit) for x in h):
            _jsave(HIDDEN, [x for x in h if os.path.normcase(x) != os.path.normcase(edit)])


def proxy_path(edit):
    E = ccfx.load_edit(edit)
    return os.path.join(os.path.dirname(edit), os.path.splitext(E["video"])[0] + ".proxy.mp4")


def make_proxy(edit):
    """ไฟล์พรีวิว 540 px + keyframe ทุก 0.5 วิ — ไฟล์เต็ม 1080×1920 seek ช้า พรีวิวใน editor ภาพค้าง
    (เรนเดอร์จริงยังใช้ไฟล์เต็ม)"""
    E = ccfx.load_edit(edit)
    src = os.path.join(os.path.dirname(edit), E["video"])
    dst = proxy_path(edit)
    if os.path.exists(dst) and os.path.getmtime(dst) >= os.path.getmtime(src):
        return
    tmp = dst + ".tmp.mp4"
    r = subprocess.run([ccfx_ff(), "-y", "-v", "error", "-i", src, "-vf", "scale='if(gt(iw,ih),960,540)':-2",
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "26", "-g", "15", "-keyint_min", "15",
                        "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", tmp],
                       capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if r.returncode == 0:
        os.replace(tmp, dst)
        if EDIT and os.path.normcase(EDIT) == os.path.normcase(edit):
            broadcast("proxy", {"proxy": os.path.basename(dst)})


def ccfx_ff():
    return os.environ.get("FFMPEG", "ffmpeg")


def project_info(edit):
    d = os.path.dirname(edit)
    name = os.path.basename(edit)[: -len(".edit.json")]
    outs = sorted((f for f in os.listdir(d) if f.startswith(name + "_") and f.endswith(".mp4")),
                  key=lambda f: os.path.getmtime(os.path.join(d, f)))  # ล่าสุดอยู่ท้าย
    try:
        E = ccfx.load_edit(edit)
        dur, n = E.get("duration", 0), len([x for x in E["items"] if x["track"] != "sub"])
        n += len(E.get("scenes") or [])
        title, mode, aspect, video = E.get("title") or name, E.get("mode") or "fx", E.get("aspect", "9x16"), E.get("video")
    except Exception:
        dur, n, title, mode, aspect, video = 0, 0, name, "fx", "9x16", None
    return {"edit": edit, "name": name, "title": title, "mode": mode, "aspect": aspect, "dir": d,
            "mtime": os.path.getmtime(edit), "duration": dur, "fx": n, "outputs": [os.path.join(d, f) for f in outs],
            "out_mtimes": [os.path.getmtime(os.path.join(d, f)) for f in outs],
            "thumb": bool(video) or os.path.exists(os.path.join(d, "_frames.jpg"))}


def scan_library():
    """เปิดโปรแกรม → คลิปที่อัปไว้ก่อนมีคลัง (clips_*/ ต้นฉบับในโฟลเดอร์งาน) เข้าคลังเอง"""
    import library
    state["lib_scan"] = True
    try:
        library.purge_old(projects_root())
        purge_old_projects()
        if library.scan_old(projects_root(), recent_list()):
            broadcast("library", {})
        for p in library.unnamed(projects_root()):  # คลิปเก่าที่ยังไม่มีชื่อ → AI ตั้งให้ (ทีละคลิปเบื้องหลัง)
            library.name_later(projects_root(), p)
        for e in recent_list():  # งานเก่าที่ยังไม่มีชื่อ → AI อ่านซับตั้งชื่อ
            try:
                if not ccfx.load_edit(e).get("title"):
                    library.name_later(projects_root(), e)
            except Exception:
                pass
    except Exception as ex:
        print("สแกนคลังคลิปไม่ได้:", ex, flush=True)
    finally:
        state["lib_scan"] = False


def dl_name(p):
    """ชื่อไฟล์ตอนโหลดลงเครื่อง = ชื่องาน (AI ตั้งจากบท) + แบบ · หาเจอง่ายในแอปไฟล์"""
    import re as _re
    d, f = os.path.dirname(p), os.path.basename(p)
    t = None
    for e in os.listdir(d):
        if e.endswith(".edit.json"):
            try:
                t = ccfx.load_edit(os.path.join(d, e)).get("title")
            except Exception:
                pass
    m = _re.search(r"_(edit|preview|explainer)[^_]*_(\d+x\d+)", f)
    tag = {"edit": "", "preview": " (ทดสอบ)", "explainer": " (explainer)"}.get(m.group(1), "") if m else ""
    t = _re.sub(r'[\\/:*?"<>|]', "", t or "").strip()
    return f"{t}{tag} {m.group(2).replace('x', '-') if m else ''}".strip() + ".mp4" if t else f


def thumb_path(edit):
    """ภาพปกโปรเจกต์ = เฟรมเดียวจากคลิปที่ตัดแล้ว (ช่วง 1/3) · ทำครั้งเดียวเก็บเป็น _thumb.jpg"""
    d = os.path.dirname(edit)
    out = os.path.join(d, "_thumb.jpg")
    if os.path.exists(out):
        return out
    try:
        E = ccfx.load_edit(edit)
        subprocess.run([ccfx_ff(), "-y", "-v", "error", "-ss", f"{E.get('duration', 3) / 3:.2f}", "-i",
                        os.path.join(d, E["video"]), "-frames:v", "1", "-vf", "scale=-2:360", out],
                       capture_output=True, timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception:
        pass
    return out if os.path.exists(out) else os.path.join(d, "_frames.jpg")


def run_job(src, opts):
    """autopilot.py ทั้งสาย → แถบความคืบหน้าในหน้าแรก → จบแล้วเปิด editor
    หลายคลิป: opts["clips"] = [path...] · ชื่องาน/โฟลเดอร์ = โฟลเดอร์กลุ่มที่อัปไว้"""
    base = os.path.splitext(os.path.basename(src))[0]
    out = os.path.join(projects_root(), base)
    if len(opts.get("clips") or []) > 1:  # โฟลเดอร์ใหม่เสมอ — ไฟล์รวมชื่อ = ชื่อโฟลเดอร์ ห้ามทับคลิปต้นฉบับ
        base = opts["name"] = "multi_" + time.strftime("%Y%m%d_%H%M%S")
        out = os.path.join(projects_root(), base)
    n = 2
    while os.path.isdir(out) and any(f.endswith(".edit.json") for f in os.listdir(out)):  # ตัดคลิปเดิมซ้ำ = งานใหม่ ไม่ทับงานเก่า
        out = os.path.join(projects_root(), f"{base}_{n}"); n += 1
    job.clear()
    dur = src_dur(opts.get("clips") or [src])
    job.update(state="running", name=base, src=src, srcs=opts.get("clips") or [src], step=0, total=5, msg="เริ่ม", prog=0,
               log=[], edit=None, steps=[], notes={}, doing="", t0=time.time(), dur=round(dur, 1), eta=round(est_secs(dur, opts)),
               seen=False)
    broadcast("job", job)
    cmd = [sys.executable, "-u", os.path.join(SCRIPTS, "autopilot.py"), src, "--out", out,
           "--opts", json.dumps(opts, ensure_ascii=False)]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                         errors="replace", bufsize=1, env=dict(os.environ, PYTHONIOENCODING="utf-8"),
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    job["pid"] = p.pid
    for line in p.stdout:
        line = line.rstrip()
        if line.startswith("STEPS "):  # รายชื่อขั้นตอนของงานนี้ (ตามตัวเลือกที่เปิด)
            try:
                job["steps"] = json.loads(line[6:])
            except ValueError:
                pass
            continue
        if line.startswith("NOTE "):  # ของที่ได้ระหว่างทาง (ชื่อ / คำสั่งเสียง / ตัดเหลือกี่วิ / รูป / GIF) + กำลังทำอะไร
            try:
                d = json.loads(line[5:])
            except ValueError:
                continue
            if d.get("k") == "doing":
                job["doing"] = d.get("text", "")
            else:
                job["notes"][d.pop("k")] = d
            job["now"] = time.time()
            broadcast("job", job)
            continue
        if line.startswith("STEP "):
            n, _, msg = line[5:].partition(" ")
            job["step"], job["total"] = (int(x) for x in n.split("/"))
            job["msg"] = msg
            job["doing"] = ""
        elif line.startswith("PROG "):
            job["prog"] = int(line[5:])
            broadcast("job", job)
            continue
        elif line.startswith("EDIT "):
            job["edit"] = line[5:]
        job["log"] = (job["log"] + [line])[-80:]
        job["now"] = time.time()
        broadcast("job", job)
    p.wait()
    job.pop("pid", None)
    if p.returncode == 0 and job.get("edit"):
        try:  # คลังคลิป: จดว่าคลิปนี้ทำงานไหนแล้ว + ชื่อจากบท
            import library
            t = ccfx.load_edit(job["edit"]).get("title")
            for s in opts.get("clips") or [src]:
                library.link(projects_root(), s, job["edit"], t)
            broadcast("library", {})
        except Exception:
            pass
        if not EDIT:  # editor ว่างอยู่ → เปิดงานนี้เลย · กำลังแก้งานอื่นอยู่ = ไม่สลับใต้มือ (กดเปิดจากแถบแจ้ง/หน้าแรกเอง)
            open_project(job["edit"])
        job["state"] = "done"
        save_stat(dur, time.time() - job["t0"], opts)
        t = (job["notes"].get("title") or {}).get("text") or base
        push_send("ตัดเสร็จแล้ว", f"{t} · เปิดดูใน editor ได้เลย", "/?open=1")
    else:
        job["state"] = "error"
        if job.get("cancel"):
            job["state"] = "cancel"
        else:
            push_send("ตัดคลิปพัง", f"{base} · เปิดดูรายละเอียดในแอป", "/")
    job["now"] = time.time()
    broadcast("job", job)


def keep_focus(new, disk):
    """ฉากที่หน้าเว็บส่งมาไม่มี focus แต่บนดิสก์มี (ฉากเดียวกัน = เวลาเริ่มใกล้กัน) → เก็บของดิสก์ไว้"""
    old = disk.get("scenes") or []
    for sc in new.get("scenes") or []:
        if "focus" not in sc:
            m = next((o for o in old if abs(o["start"] - sc["start"]) < 0.05 and "focus" in o), None)
            if m:
                sc["focus"] = m["focus"]


def list_assets():
    sfx = sorted(f[:-4] for f in os.listdir(ccfx.SFX_DIR) if f.endswith(".wav"))
    imgs = []
    for root, _, files in os.walk(PROJ):
        if os.path.relpath(root, PROJ).count(os.sep) > 1:
            continue
        for f in files:
            if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp")) and not f.startswith("_"):
                imgs.append(os.path.relpath(os.path.join(root, f), PROJ).replace("\\", "/"))
    return {"sfx": sfx, "images": sorted(imgs), "music": ccfx.music_list(),
            "voice_lufs_target": ccfx.VOICE_LUFS, "mix_default": ccfx.MIX_DEFAULT,
            "music_default": ccfx.MUSIC_DEFAULT, "emoji": ccfx.EMOJI_PALETTE, "fx": ccfx.FX_TYPES,
            "fx_default": ccfx.FX_DEFAULT,
            "fonts": sorted(f for f in os.listdir(ccfx.FONTS) if f.endswith(".ttf"))}


def run_render(opts):
    out = opts.get("out") or None
    if ccfx.load_edit(EDIT).get("mode") == "explainer":  # แบบจัดฉาก → Remotion
        cmd = [sys.executable, "-u", os.path.join(SCRIPTS, "explainer.py"), "render", EDIT]
    else:
        cmd = [sys.executable, "-u", os.path.join(SCRIPTS, "render_edit.py"), EDIT]
        if opts.get("aspect"):
            cmd += ["--aspect", opts["aspect"]]
    if opts.get("preview"):
        cmd += ["--preview"]
    if out:
        cmd += ["--out", out]
    broadcast("render", {"line": "▶ " + " ".join(os.path.basename(c) for c in cmd[2:]), "state": "running"})
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env,
                         text=True, encoding="utf-8", errors="replace", bufsize=1,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    state["render"] = p
    state["rstate"], state["rlog"], state["rout"] = "running", [], None  # มือถือ poll /api/render/status
    result = None
    for line in p.stdout:
        line = line.rstrip()
        if line.startswith("OUTPUT "):
            result = line[7:]
        state["rlog"] = (state["rlog"] + [line])[-40:]
        broadcast("render", {"line": line, "state": "running"})
    p.wait()
    state["render"] = None
    state["rstate"], state["rout"] = ("done" if p.returncode == 0 else "error"), result
    if p.returncode == 0 and not opts.get("preview"):
        push_send("เรนเดอร์เสร็จแล้ว", os.path.basename(result or "") + " · กดเพื่อโหลด/บันทึกลงรูป", "/m")
    elif p.returncode and not state.get("rcancel"):
        push_send("เรนเดอร์พัง", "เปิด editor ดูรายละเอียด", "/")
    state["rcancel"] = False
    broadcast("render", {"line": "", "state": "done" if p.returncode == 0 else "error",
                         "output": result, "code": p.returncode})


# ---------- ใช้ผ่านมือถือ (tailscale serve → https://chenlab.<tailnet>.ts.net) ----------
# server ยังฟังแค่ 127.0.0.1 · tailscale serve ส่งต่อเข้ามาพร้อม header Tailscale-User-Login / X-Forwarded-For
# คำขอจากนอกเครื่อง = ต้องมี cookie ที่ได้จากการใส่ PIN (ในวง Tailscale มีเครื่องคนอื่นด้วย)
AUTH_DIR = os.path.join(os.path.expanduser("~"), ".clipcut")


def _auth_file(name, make):
    p = os.path.join(AUTH_DIR, name)
    if not os.path.exists(p):
        os.makedirs(AUTH_DIR, exist_ok=True)
        open(p, "w", encoding="utf-8").write(make())
    return open(p, encoding="utf-8").read().strip()


def pin_code():
    import secrets
    return _auth_file("pin.txt", lambda: f"{secrets.randbelow(10 ** 6):06d}")


def auth_token():
    import hmac
    import secrets
    key = _auth_file("secret.txt", lambda: secrets.token_hex(32))
    return hmac.new(key.encode(), ("clipcut:" + pin_code()).encode(), "sha256").hexdigest()


APP_ICONS = {"/apple-touch-icon.png": "icon-180.png", "/apple-touch-icon-precomposed.png": "icon-180.png",
             "/icon-180.png": "icon-180.png", "/icon-512.png": "icon-512.png", "/manifest.webmanifest": None,
             "/sw.js": "sw.js"}  # service worker (แจ้งเตือน) — ไม่มีข้อมูลลับ โหลดได้ไม่ต้อง PIN
MANIFEST = {"name": "ClipCut", "short_name": "ClipCut", "start_url": "/", "display": "standalone",
            "background_color": "#060606", "theme_color": "#10b981",
            "icons": [{"src": "/icon-180.png", "sizes": "180x180", "type": "image/png"},
                      {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"}]}
pin_fails = []  # เวลาที่ใส่ PIN ผิด (กันเดา: ผิด 8 ครั้งใน 15 นาที = ล็อก)

LOGIN_HTML = """<!doctype html><html lang="th"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>ClipCut</title>
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="manifest" href="/manifest.webmanifest">
<meta name="apple-mobile-web-app-title" content="ClipCut">
<meta name="theme-color" content="#10b981">

<style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:#060606;color:#e8eceb;font:16px "Segoe UI",system-ui,sans-serif}
form{width:min(320px,90vw);display:flex;flex-direction:column;gap:14px;text-align:center}
b{font-size:22px}input{font-size:28px;letter-spacing:10px;text-align:center;padding:12px;border-radius:12px;border:1px solid #2a2f2e;background:#101111;color:#fff}
button{padding:14px;border-radius:12px;border:0;background:#10b981;color:#031a12;font-weight:700;font-size:17px}p{color:#ff8a8a;min-height:1em;margin:0}</style></head>
<body><form method="post" action="/login"><b>ClipCut</b><span style="color:#7d8584">ใส่ PIN (ดูได้ในคอม)</span>
<input name="pin" inputmode="numeric" autocomplete="one-time-code" maxlength="6" autofocus><button>เข้า</button><p>%MSG%</p></form></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def remote(self):
        """มาจากมือถือผ่าน tailscale serve (หรือเครื่องอื่น) — ไม่ใช่หน้าต่างบนคอมเอง"""
        return bool(self.headers.get("Tailscale-User-Login") or self.headers.get("X-Forwarded-For")
                     or self.client_address[0] not in ("127.0.0.1", "::1"))

    def authed(self):
        if not self.remote():
            return True
        import hmac
        from http.cookies import SimpleCookie
        c = SimpleCookie(self.headers.get("Cookie") or "")
        return "cc_auth" in c and hmac.compare_digest(c["cc_auth"].value, auth_token())

    def gate(self, path, method):
        """True = ผ่าน · False = ตอบไปแล้ว (หน้า PIN / 401)"""
        if path in APP_ICONS:  # ไอคอนหน้าจอโฮม — iOS โหลดตอนกด "เพิ่มลงหน้าจอโฮม" อาจไม่ส่ง cookie มา
            return True
        if path == "/login":
            if method == "POST":
                n = int(self.headers.get("Content-Length") or 0)
                pin = parse_qs(self.rfile.read(n).decode("utf-8", "replace")).get("pin", [""])[0].strip()
                now = time.time()
                pin_fails[:] = [t for t in pin_fails if now - t < 900]
                if len(pin_fails) >= 8:
                    return self.send_html(LOGIN_HTML.replace("%MSG%", "ผิดหลายครั้ง รอ 15 นาที"), 429)
                import hmac
                if hmac.compare_digest(pin, pin_code()):
                    self.send_response(303)
                    self.send_header("Set-Cookie", f"cc_auth={auth_token()}; Path=/; Max-Age=31536000; HttpOnly; Secure; SameSite=Lax")
                    self.send_header("Location", "/")
                    self.end_headers()
                    return False
                pin_fails.append(now)
                return self.send_html(LOGIN_HTML.replace("%MSG%", "PIN ไม่ถูก"), 401)
            return self.send_html(LOGIN_HTML.replace("%MSG%", ""))
        if self.authed():
            return True
        if path.startswith("/api/"):
            self.send_json({"ok": False, "error": "ต้องใส่ PIN"}, 401)
        else:
            self.send_response(303)
            self.send_header("Location", "/login")
            self.end_headers()
        return False

    def send_html(self, html, code=200):
        b = html.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)
        return False

    def own_video(self, q):
        """ไฟล์ mp4 ที่อยู่ในโฟลเดอร์ของโปรเจกต์ในรายการเท่านั้น (กันขอไฟล์อื่นในเครื่อง)"""
        q = os.path.realpath(q or "")
        dirs = {os.path.realpath(os.path.dirname(e)) for e in recent_list()}
        return q if q.lower().endswith(".mp4") and os.path.dirname(q) in dirs and os.path.isfile(q) else None

    def send_json(self, obj, code=200):
        b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def send_file(self, path, cache=False, dl=None):
        if not path or not os.path.isfile(path):
            return self.send_error(404)
        size = os.path.getsize(path)
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        rng = self.headers.get("Range")
        start, end = 0, size - 1
        if rng and rng.startswith("bytes="):
            a, _, b = rng[6:].partition("-")
            if a:
                start = int(a); end = int(b) if b else size - 1
            else:
                start = size - int(b)
            end = min(end, size - 1)
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        else:
            self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Cache-Control", "max-age=3600" if cache else "no-cache")
        if dl:  # โหลดลงเครื่อง (มือถือ: Safari → แอปไฟล์)
            from urllib.parse import quote
            self.send_header("Content-Disposition", f"attachment; filename=\"clipcut.mp4\"; filename*=UTF-8''{quote(dl)}")
        self.end_headers()
        try:
            with open(path, "rb") as f:
                f.seek(start)
                left = end - start + 1
                while left > 0:
                    chunk = f.read(min(1 << 20, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            pass

    def safe_join(self, root, rel):
        if not root:
            return None
        p = os.path.realpath(os.path.join(root, rel))
        return p if p.startswith(os.path.realpath(root)) else None

    def do_GET(self):
        url = urlparse(self.path)
        path = unquote(url.path)
        if not self.gate(path, "GET"):
            return
        if path in APP_ICONS:
            if APP_ICONS[path] is None:
                b = json.dumps(MANIFEST).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/manifest+json")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                return self.wfile.write(b)
            return self.send_file(os.path.join(UI, APP_ICONS[path]), cache=True)
        if path in ("/m", "/m.html"):  # editor แบบย่อสำหรับมือถือ
            return self.send_file(os.path.join(UI, "m.html"))
        if path == "/api/clipthumb":  # ภาพปกคลิปที่อัปไว้ (ยังไม่เป็นงาน)
            q = os.path.realpath(parse_qs(url.query).get("path", [""])[0])
            if not q.startswith(os.path.realpath(projects_root())) or not os.path.isfile(q):
                return self.send_error(404)
            th = os.path.join(os.path.dirname(q), "_thumbs", os.path.basename(q) + ".jpg")
            if not os.path.exists(th):
                os.makedirs(os.path.dirname(th), exist_ok=True)
                subprocess.run([ccfx_ff(), "-y", "-v", "error", "-ss", "0.5", "-i", q, "-frames:v", "1", "-vf", "scale=-2:240", th],
                               capture_output=True, timeout=30)
            return self.send_file(th, cache=True)
        if path == "/api/library":
            import library
            return self.send_json({"clips": library.listing(projects_root()), "scanning": bool(state.get("lib_scan")),
                                   "naming": library._naming[0]})
        if path == "/api/clipinfo":
            import multiclip
            out = []
            for q in parse_qs(url.query).get("path", []):
                q = os.path.realpath(q)
                if q.startswith(os.path.realpath(projects_root())) and os.path.isfile(q):
                    i = multiclip.probe(q)
                    out.append({"path": q, "name": os.path.basename(q), "dur": round(i["dur"], 1), "ctime": i["ctime"],
                                "vertical": i["h"] >= i["w"]})
            return self.send_json(out)
        if path == "/api/video":  # ดู/โหลดคลิปที่เรนเดอร์บนมือถือ
            qs = parse_qs(url.query)
            q = self.own_video(qs.get("path", [""])[0])
            dl = dl_name(q) if q and qs.get("dl") else None
            return self.send_file(q, dl=dl) if q else self.send_error(404)
        if path == "/api/render/status":
            return self.send_json({"state": state.get("rstate", "idle"), "log": state.get("rlog", [])[-6:],
                                   "output": state.get("rout"), "running": bool(state["render"])})
        if path in ("/", "/home"):
            return self.send_file(os.path.join(UI, "home.html"))
        if path in ("/edit", "/index.html"):
            return self.send_file(os.path.join(UI, "index.html"))
        if path in ("/app.js", "/app.css", "/home.js", "/player.js", "/theme.js", "/jobpill.js"):
            return self.send_file(os.path.join(UI, path[1:]))
        if path == "/favicon.ico":
            return self.send_file(os.path.join(UI, "clipcut.ico"), cache=True)
        if path == "/api/ping":
            return self.send_json({"ok": True, "app": "clipcut"})
        if path == "/api/job":
            return self.send_json(dict(job, now=time.time()))
        if path == "/api/trash":
            import library
            library.purge_old(projects_root()); purge_old_projects()
            return self.send_json(trash_listing())
        if path == "/api/jobimg":  # รูป/GIF ที่ได้ระหว่างตัด (โชว์ในหน้ารอ) — เฉพาะในโฟลเดอร์งาน/คลัง GIF
            import gif_lib
            q = os.path.realpath(parse_qs(url.query).get("path", [""])[0])
            okroot = any(q.startswith(os.path.realpath(r) + os.sep) for r in (projects_root(), gif_lib.ROOT))
            return self.send_file(q, cache=True) if okroot and os.path.isfile(q) else self.send_error(404)
        if path == "/api/push/key":
            try:
                return self.send_json({"ok": True, "key": vapid_public()})
            except Exception as ex:
                return self.send_json({"ok": False, "error": str(ex)})
        if path == "/api/home":
            ps = [project_info(p) for p in recent_list()]
            return self.send_json({"projects": ps, "root": projects_root(),
                                   "staged": state["staged"], "job": job, "current": EDIT})
        if path == "/api/thumb":
            q = parse_qs(url.query).get("edit", [""])[0]
            ok = any(os.path.normcase(q) == os.path.normcase(p) for p in recent_list() + [x["edit"] for x in trashed_projects()])
            return self.send_file(thumb_path(q)) if ok else self.send_error(404)
        if path == "/api/edit":
            if not EDIT:
                return self.send_json({"error": "ยังไม่ได้เปิดโปรเจกต์"}, 404)
            px = proxy_path(EDIT)
            return self.send_json({"rev": state["rev"], "edit": ccfx.load_edit(EDIT), "name": os.path.basename(EDIT),
                                   "proxy": os.path.basename(px) if os.path.exists(px) else None})
        if path == "/api/assets":
            return self.send_json(list_assets())
        if path == "/api/events":
            return self.sse()
        if path.startswith("/media/"):
            p = self.safe_join(PROJ, path[7:])
            return self.send_file(p) if p else self.send_error(403)
        if path.startswith("/pixel/"):
            return self.send_file(os.path.join(SKILL_PIX, os.path.basename(path)), cache=True)
        if path == "/api/pixel":
            import pixel_gen
            n, lib = pixel.names(), pixel_gen.lib()
            return self.send_json({"sprites": n["sprites"], "icons": [{"name": i, "desc": lib.get(i, {}).get("desc", "")} for i in n["icons"]]})
        if path.startswith("/gif/"):  # คลัง GIF กลาง (assets/gif)
            import gif_lib
            p = self.safe_join(gif_lib.ROOT, unquote(path[5:]))
            return self.send_file(p, cache=True) if p else self.send_error(403)
        if path == "/api/gifs":
            import gif_lib
            return self.send_json({"lib": gif_lib.lib(), "cats": {k: v[0] for k, v in gif_lib.CATS.items()}})
        if path.startswith("/sfx/"):
            return self.send_file(os.path.join(ccfx.SFX_DIR, os.path.basename(path)), cache=True)
        if path.startswith("/music/"):
            return self.send_file(os.path.join(ccfx.MUSIC_DIR, os.path.basename(path)), cache=True)
        if path.startswith("/fonts/"):
            return self.send_file(os.path.join(ccfx.FONTS, os.path.basename(path)), cache=True)
        if path.startswith("/emoji/"):
            try:
                return self.send_file(ccfx.emoji_png(path[7:]), cache=True)
            except Exception:
                return self.send_error(404)
        self.send_error(404)

    def do_POST(self):
        path = urlparse(self.path).path
        if not self.gate(path, "POST"):
            return
        n = int(self.headers.get("Content-Length") or 0)
        if path == "/api/upload":  # ลากไฟล์ใส่หน้าเว็บ (เบราว์เซอร์ไม่ให้ path จริง) → สตรีมลงโฟลเดอร์โปรเจกต์
            name = os.path.basename(unquote(self.headers.get("X-Filename") or "clip.mp4"))
            if not name.lower().endswith(VIDEO_EXT):
                return self.send_json({"ok": False, "error": "ไม่ใช่ไฟล์วิดีโอ"}, 400)
            import library  # ทุกไฟล์ที่อัป = เข้าคลังคลิป (ต้นฉบับแยกจากโฟลเดอร์งาน ตัดซ้ำได้)
            dst = library.dest(projects_root(), name)
            left = n
            try:
                with open(dst, "wb") as f:
                    while left > 0:
                        chunk = self.rfile.read(min(1 << 20, left))
                        if not chunk:
                            break
                        f.write(chunk)
                        left -= len(chunk)
            except OSError:
                pass
            if left > 0:  # มือถือออกจากเว็บ/จอล็อกกลางทาง = ไฟล์ไม่ครบ → ทิ้ง ไม่ให้เข้าคลัง
                try:
                    os.remove(dst)
                except OSError:
                    pass
                return self.send_json({"ok": False, "error": "อัปไม่ครบ (การเชื่อมต่อหลุด) — อัปใหม่อีกที"}, 400)
            library.add(projects_root(), dst)
            library.name_later(projects_root(), dst)  # AI ดู 4 เฟรมตั้งชื่อ (เบื้องหลัง)
            broadcast("library", {})
            return self.send_json({"ok": True, "path": dst})
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return self.send_json({"ok": False, "error": "JSON เสีย"}, 400)
        if path == "/api/edit":
            if body.get("file") and EDIT and body["file"] != os.path.basename(EDIT):
                return self.send_json({"ok": False, "switched": True, "file": os.path.basename(EDIT)}, 409)
            if body.get("base_rev") is not None and body["base_rev"] != state["rev"]:
                # มีคนแก้ไฟล์แทรกระหว่างนั้น → ไม่ทับ ให้หน้าเว็บ merge ก่อน
                return self.send_json({"ok": False, "conflict": True, "rev": state["rev"],
                                       "edit": ccfx.load_edit(EDIT)}, 409)
            new, disk = body["edit"], ccfx.load_edit(EDIT)
            for k, v in disk.items():  # หน้าเว็บไม่รู้จัก field นี้ (เช่น faces จาก focus.py) → ห้ามเซฟแล้วหาย
                new.setdefault(k, v)
            keep_focus(new, disk)
            ccfx.save_edit(EDIT, new)
            body["edit"] = new
            state["hash"] = file_hash()
            state["rev"] += 1
            broadcast("edit", {"rev": state["rev"], "edit": body["edit"], "by": body.get("client"), "file": os.path.basename(EDIT)})
            return self.send_json({"ok": True, "rev": state["rev"]})
        if path == "/api/job":
            if job.get("state") == "running":
                return self.send_json({"ok": False, "error": "กำลังทำคลิปอื่นอยู่"}, 409)
            paths = [x for x in (body.get("paths") or [body.get("path")]) if x]
            if not paths or not all(os.path.isfile(x) for x in paths):
                return self.send_json({"ok": False, "error": "ไม่เจอไฟล์"}, 400)
            opts = body.get("opts") or {}
            if len(paths) > 1:
                opts["clips"] = paths
            state["staged"] = None
            threading.Thread(target=run_job, args=(paths[0], opts), daemon=True).start()
            return self.send_json({"ok": True})
        if path == "/api/job/cancel":
            if job.get("pid"):
                job["cancel"] = True
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(job["pid"])], capture_output=True)
            return self.send_json({"ok": True})
        if path == "/api/job/seen":  # ปิดแถบ "ตัดเสร็จแล้ว"
            job["seen"] = True
            broadcast("job", dict(job, now=time.time()))
            return self.send_json({"ok": True})
        if path == "/api/open":
            open_project(body["edit"])
            if job.get("edit") and os.path.normcase(job["edit"]) == os.path.normcase(body["edit"]) and not job.get("seen"):
                job["seen"] = True
                broadcast("job", dict(job, now=time.time()))
            return self.send_json({"ok": True})
        if path == "/api/push/sub":
            sub = body.get("sub") or {}
            if not str(sub.get("endpoint", "")).startswith("https://"):
                return self.send_json({"ok": False, "error": "subscription เสีย"}, 400)
            with rlock:
                _jsave(PUSH_SUBS, [x for x in _jload(PUSH_SUBS) if x.get("endpoint") != sub["endpoint"]] + [sub])
            if body.get("test"):
                push_send("ClipCut", "แจ้งเตือนใช้ได้แล้ว — ตัด/เรนเดอร์เสร็จจะเด้งบอกตรงนี้", "/")
            return self.send_json({"ok": True})
        if path == "/api/push/unsub":
            with rlock:
                _jsave(PUSH_SUBS, [x for x in _jload(PUSH_SUBS) if x.get("endpoint") != body.get("endpoint")])
            return self.send_json({"ok": True})
        if path == "/api/trash/add":  # ลบในแอป = เข้าถังขยะ (ไฟล์ไม่ขยับ)
            import library
            ok = (library.trash(projects_root(), str(body.get("path"))) if body.get("kind") == "clip"
                  else bool(project_trash(str(body.get("path")))) or True)
            broadcast("library" if body.get("kind") == "clip" else "projects", {})
            return self.send_json({"ok": ok})
        if path == "/api/trash/restore":
            import library
            ok = (library.trash(projects_root(), str(body.get("path")), False) if body.get("kind") == "clip"
                  else bool(project_trash(str(body.get("path")), False)) or True)
            broadcast("library" if body.get("kind") == "clip" else "projects", {})
            return self.send_json({"ok": ok})
        if path == "/api/trash/purge":  # ลบถาวร (ไฟล์ไปถังขยะ Windows) · items ว่าง = ล้างถังทั้งหมด
            import library
            T = trash_listing()
            items = body.get("items") or [{"kind": "clip", "path": c["path"]} for c in T["clips"]] + \
                [{"kind": "project", "path": x["edit"]} for x in T["projects"]]
            inclip = {os.path.normcase(c["path"]) for c in T["clips"]}
            inproj = {os.path.normcase(x["edit"]) for x in T["projects"]}
            n = 0
            for it in items:  # ลบได้เฉพาะของที่อยู่ในถังแล้วเท่านั้น
                q = os.path.normcase(str(it.get("path")))
                if it.get("kind") == "clip" and q in inclip:
                    n += bool(library.remove(projects_root(), it["path"]))
                elif it.get("kind") == "project" and q in inproj:
                    n += bool(project_purge(it["path"]))
            broadcast("library", {}); broadcast("projects", {})
            return self.send_json({"ok": True, "n": n})
        if path == "/api/stage":  # เปิดซ้ำโดยลากไฟล์ใส่ไอคอน → ส่งไฟล์มาให้ตัวที่เปิดอยู่
            state["staged"] = body.get("path")
            broadcast("stage", {"path": state["staged"]})
            return self.send_json({"ok": True})
        if path == "/api/unstage":
            state["staged"] = None
            return self.send_json({"ok": True})
        if path == "/api/rename":  # ชื่อที่โชว์ (ไฟล์จริงไม่เปลี่ยน)
            edit = body.get("edit") or EDIT
            if not edit or not any(os.path.normcase(edit) == os.path.normcase(p) for p in recent_list()):
                return self.send_json({"ok": False, "error": "ไม่เจอโปรเจกต์"}, 404)
            E = ccfx.load_edit(edit)
            E["title"] = str(body.get("title") or "").strip()[:80] or None
            ccfx.save_edit(edit, E)
            return self.send_json({"ok": True})
        if path == "/api/gif/ban":
            import gif_lib
            return self.send_json({"ok": gif_lib.ban(str(body.get("gif")))})
        if path == "/api/gap":  # ตัดเข้า GIF / หยุดภาพ จาก editor: เว้นช่องหรือลบช่อง → สร้างคลิปใหม่ → watcher ส่งให้หน้าเว็บ
            import gaps
            if not EDIT:
                return self.send_json({"ok": False, "error": "ยังไม่ได้เปิดโปรเจกต์"}, 400)
            E = ccfx.load_edit(EDIT)
            if body.get("op") == "del":
                gaps.remove(E, body.get("id"))
            else:
                g = gaps.insert(E, gaps.boundary(E, float(body.get("t", 0))), float(body.get("dur", 1.3)))
                it = {"id": "g" + str(int(time.time() * 1000) % 100000), "track": "gif", "mode": body.get("mode", "cut"),
                      "start": g["at"], "end": round(g["at"] + g["dur"], 3), "caption": body.get("caption", ""), "gap": g["id"]}
                if body.get("gif"):
                    it["gif"] = body["gif"]
                E["items"].append(it)
            gaps.build_video(E, PROJ)
            ccfx.save_edit(EDIT, E)
            threading.Thread(target=make_proxy, args=(EDIT,), daemon=True).start()
            return self.send_json({"ok": True})
        if path == "/api/speed":  # ช่วงสาธิต: เร่ง / ความเร็วปกติ / ตัดทิ้ง → สร้างคลิปใหม่ (speedup.set_mode)
            import speedup
            if not EDIT:
                return self.send_json({"ok": False, "error": "ยังไม่ได้เปิดโปรเจกต์"}, 400)
            E = ccfx.load_edit(EDIT)
            try:
                ok = speedup.set_mode(E, PROJ, str(body.get("id")), str(body.get("mode")))
            except Exception as ex:
                return self.send_json({"ok": False, "error": str(ex)}, 400)
            if ok:
                ccfx.save_edit(EDIT, E)
                threading.Thread(target=make_proxy, args=(EDIT,), daemon=True).start()
            return self.send_json({"ok": ok})
        if path == "/api/library/rename":
            import library
            library.update(projects_root(), str(body.get("path")), title=str(body.get("title") or "").strip()[:60] or "คลิป", by="user")
            return self.send_json({"ok": True})
        if path == "/api/library/delete":  # รุ่นเก่า → เข้าถังขยะแอป
            import library
            ok = library.trash(projects_root(), str(body.get("path")))
            broadcast("library", {})
            return self.send_json({"ok": ok})
        if path == "/api/forget":  # รุ่นเก่า → เข้าถังขยะแอป
            project_trash(str(body.get("edit") or ""))
            broadcast("projects", {})
            return self.send_json({"ok": True})
        if path == "/api/pixel/new":  # วาดไอคอนใหม่จาก editor (AI วาดตาราง 16×16 → เข้าคลังกลาง)
            import re as _re
            import pixel_gen
            name = _re.sub(r"[^a-z0-9_]", "_", str(body.get("name", "")).lower()).strip("_")[:30]
            if not name:
                return self.send_json({"ok": False, "error": "ตั้งชื่อภาษาอังกฤษ"}, 400)
            ok = name in pixel_gen.ensure({name: body.get("desc") or name}, redraw=bool(body.get("redraw")))
            return self.send_json({"ok": ok, "name": name, "src": f"pixel/icon_{name}.png"})
        if path == "/api/cam":  # กล้องตามหน้า: เปิด/ปิด/ซูม/หาหน้าใหม่ (smartcam.py) → เขียนไฟล์ → watcher ส่งให้หน้าเว็บ
            import smartcam
            if not EDIT:
                return self.send_json({"ok": False, "error": "ยังไม่ได้เปิดโปรเจกต์"}, 400)

            def cam_job(edit=EDIT):
                E = ccfx.load_edit(edit)
                if body.get("scan") or not E.get("faces"):
                    import focus
                    E["faces"] = focus.track_faces(os.path.join(os.path.dirname(edit), E["video"]),
                                                   [x for x in E["items"] if x["track"] == "sub"])
                    E = dict(ccfx.load_edit(edit), faces=E["faces"])  # ระหว่างหาหน้า หน้าเว็บอาจเซฟของใหม่มา
                smartcam.build_path(E, body.get("mode") or ("follow" if body.get("scan") else None), body.get("zoom"))
                smartcam.size_focus(E)
                smartcam.refocus(E)
                ccfx.save_edit(edit, E)
                return E
            if body.get("scan"):
                threading.Thread(target=cam_job, daemon=True).start()
                return self.send_json({"ok": True, "msg": "กำลังหาหน้าคน… (ไม่กี่วินาที)"})
            E = cam_job()
            return self.send_json({"ok": True, "msg": "กล้องตามหน้าแล้ว" if smartcam.cam_on(E) else "ภาพเต็ม (ไม่ตามหน้า)"})
        if path == "/api/render":
            if state["render"]:
                return self.send_json({"ok": False, "error": "กำลังเรนเดอร์อยู่"}, 409)
            threading.Thread(target=run_render, args=(body,), daemon=True).start()
            return self.send_json({"ok": True})
        if path == "/api/render/cancel":
            if state["render"]:
                state["rcancel"] = True
                state["render"].kill()
            return self.send_json({"ok": True})
        if path == "/api/play":
            p = body.get("path", "")
            if p.lower().endswith(".mp4") and os.path.isfile(p):
                os.startfile(p)
            return self.send_json({"ok": True})
        if path == "/api/reveal":
            p = body.get("path", "")
            if not (os.path.isabs(p) and os.path.exists(p)):
                p = self.safe_join(PROJ, p) or PROJ
            subprocess.Popen(["explorer", "/select,", p] if os.path.isfile(p) else ["explorer", p])
            return self.send_json({"ok": True})
        self.send_error(404)

    def sse(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        q = []
        with lock:
            clients.append(q)
        try:
            self.wfile.write(b": hi\n\n"); self.wfile.flush()
            idle = 0
            while True:
                if q:
                    with lock:
                        msgs, q[:] = list(q), []
                    for m in msgs:
                        self.wfile.write(m)
                    self.wfile.flush(); idle = 0
                else:
                    time.sleep(0.1); idle += 1
                    if idle > 150:
                        self.wfile.write(b": ping\n\n"); self.wfile.flush(); idle = 0
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, OSError):
            pass
        finally:
            with lock:
                if q in clients:
                    clients.remove(q)


def open_app(url):
    """เปิดเป็นหน้าต่างแอป (Chrome/Edge --app = ไม่มีแถบ URL/แท็บ) — ไม่เจอค่อยใช้เบราว์เซอร์ปกติ"""
    pf = [os.environ.get(k, "") for k in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")]
    cands = [os.path.join(b, r) for b in pf if b for r in
             (r"Google\Chrome\Application\chrome.exe", r"Microsoft\Edge\Application\msedge.exe")]
    exe = next((c for c in cands if os.path.isfile(c)), None)
    if exe:
        subprocess.Popen([exe, f"--app={url}", "--window-size=1600,1000",
                          "--autoplay-policy=no-user-gesture-required"])
    else:
        webbrowser.open(url)


def already_running(port):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/ping", timeout=1) as r:
            return json.loads(r.read()).get("app") == "clipcut"
    except Exception:
        return False


def post(port, path, data):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=json.dumps(data).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    urllib.request.urlopen(req, timeout=30).read()


def tray(srv, page):
    """ไอคอนถาดข้างนาฬิกา = โปรแกรมรันอยู่ · คลิก = เปิด ClipCut · คลิกขวา = เมนู (ปิดโปรแกรมได้ถ้าไม่มีงานค้าง)
    ไม่มี pystray = ไม่มีถาด (โปรแกรมยังรันปกติ)"""
    try:
        import pystray
        from PIL import Image
    except ImportError:
        return srv.serve_forever()
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    def busy():
        return job.get("state") == "running" or bool(state["render"])

    def tip():
        e = os.path.basename(EDIT)[: -len(".edit.json")] if EDIT else "-"
        return f"ClipCut — รันอยู่ · งาน: {e[:40]}" + (" · กำลังทำงาน" if busy() else "")

    def quit_(icon, _):
        if busy():
            return icon.notify("กำลังทำคลิป/เรนเดอร์อยู่ — รอเสร็จก่อนค่อยปิด", "ClipCut")
        icon.stop()
        srv.shutdown()

    icon = pystray.Icon("clipcut", Image.open(os.path.join(UI, "icon-180.png")), tip(), pystray.Menu(
        pystray.MenuItem("เปิด ClipCut", lambda *_: open_app(page), default=True),
        pystray.MenuItem("เปิดโฟลเดอร์งาน", lambda *_: subprocess.Popen(["explorer", projects_root()])),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("ปิดโปรแกรม (มือถือจะใช้ไม่ได้)", quit_)))

    def keep_tip():
        while True:
            time.sleep(3)
            try:
                icon.title = tip()
            except Exception:
                pass
    threading.Thread(target=keep_tip, daemon=True).start()
    icon.run()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target", nargs="?", help="คลิปวิดีโอ (รอเลือกแบบ) หรือ <ชื่อ>.edit.json (เปิด editor ตรง)")
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--no-open", action="store_true")
    a = ap.parse_args()
    t = os.path.abspath(a.target) if a.target else None
    is_edit = bool(t and t.endswith(".edit.json"))
    page = f"http://127.0.0.1:{a.port}/" + ("edit" if is_edit else "")

    if already_running(a.port):  # เปิดซ้ำ → ส่งงานให้ตัวเดิม แล้วเปิดหน้าต่างชี้ไปตัวเดิม
        if t and is_edit:
            post(a.port, "/api/open", {"edit": t})
        elif t:
            post(a.port, "/api/stage", {"path": t})
        if not a.no_open:
            open_app(page)
        return

    if is_edit:
        open_project(t)
    elif t:
        state["staged"] = t
    threading.Thread(target=watcher, daemon=True).start()
    threading.Thread(target=scan_library, daemon=True).start()
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), H)
    srv.daemon_threads = True
    print(f"🦞 clipcut → {page}", flush=True)
    if not a.no_open:
        open_app(page)
    tray(srv, f"http://127.0.0.1:{a.port}/")


if __name__ == "__main__":
    main()
