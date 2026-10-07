#!/usr/bin/env python
"""Motion Explainer — คลิปคนพูด → จัดฉากใหม่ทุกประโยค (แนวกระดาษปะติด + ภาพพิกเซลแบบ animclip) ผ่าน Remotion

  python explainer.py plan   <edit.json> [--density 2]   AI กำกับฉาก → E["scenes"] (+ วาดไอคอนที่ขาดอัตโนมัติ)
  python explainer.py render <edit.json> [--preview]     Remotion ทำภาพ + ffmpeg ผสมเสียง (ระบบเดียวกับ render_edit)

ฉาก (E["scenes"]):  {start, cam, bg, title, title_color, transition,
                    items: [{src, x, y, size, at}], tags: [{text, at}]}
  cam   : full (คนพูดเต็มจอ) | polaroid (กรอบรูปครึ่งล่าง) | corner (รูปเล็กมุมขวาบน) | circle (วงกลมซ้ายบน) | none (ซ่อน)
  item src: "pixel/<ไฟล์>" = คลังกลาง assets/pixel · อื่นๆ = path ในโฟลเดอร์โปรเจกต์ (เช่น broll/px_..png)
ตำแหน่งของ (x, y, size) จัดอัตโนมัติตามแบบกล้องให้ไม่ทับกล้อง/หัวข้อ/ซับ — AI เลือกแค่ "อะไร" ไม่ต้องเลือก "ตรงไหน"
"""
import os
import re
import sys
import json
import hashlib
import argparse
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ccfx  # noqa: E402
import pixel  # noqa: E402
import pixel_gen  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
RM = os.path.join(os.path.dirname(HERE), "remotion")
FPS = 30
CAMS = ["full", "polaroid", "corner", "circle", "none"]
BGS = ["grid", "paper", "lined", "kraft", "navy", "mint", "pink", "yellow"]
COLORS = {"red": "#ef4444", "yellow": "#facc15", "green": "#10b981", "blue": "#3b82f6"}
TRANSITIONS = ["slide", "slap", "drop", "punch", "cut"]
# ช่องวางของตามแบบกล้อง: จำนวนของ 1/2/3 ชิ้น → [(x, y, ขนาด=ความกว้าง/จอ)]
SLOTS = {
    "full": [[(0.8, 0.62, 0.22)], [(0.2, 0.6, 0.2), (0.8, 0.64, 0.22)],
             [(0.18, 0.58, 0.18), (0.82, 0.6, 0.2), (0.8, 0.3, 0.16)]],
    "polaroid": [[(0.5, 0.3, 0.4)], [(0.3, 0.3, 0.34), (0.72, 0.28, 0.3)],
                 [(0.24, 0.31, 0.3), (0.58, 0.27, 0.26), (0.84, 0.37, 0.17)]],
    "corner": [[(0.36, 0.55, 0.5)], [(0.3, 0.52, 0.36), (0.72, 0.64, 0.32)],
               [(0.26, 0.48, 0.32), (0.7, 0.6, 0.3), (0.32, 0.72, 0.22)]],
    "circle": [[(0.55, 0.62, 0.42)], [(0.78, 0.3, 0.24), (0.5, 0.63, 0.4)],
               [(0.78, 0.28, 0.22), (0.3, 0.63, 0.32), (0.72, 0.64, 0.3)]],
    "none": [[(0.5, 0.46, 0.56)], [(0.3, 0.43, 0.4), (0.7, 0.53, 0.4)],
             [(0.28, 0.37, 0.34), (0.72, 0.43, 0.32), (0.5, 0.66, 0.34)]],
}
SCENE_LEN = {1: "6-9 วิ", 2: "3-5 วิ", 3: "2-3 วิ"}


def plan(E, proj, density=2, vibe="tech"):
    """AI กำกับฉากจากซับ → E["scenes"] (resolve รูป + จัดตำแหน่งแล้ว)"""
    import autopilot
    subs = [x for x in E["items"] if x["track"] == "sub"]
    lines = "\n".join(f"{x['start']:.2f}|{x['text']}" for x in subs)
    px = pixel.names()
    icons = pixel_gen.lib()
    icon_desc = ", ".join(f"{n}" + (f"({icons[n]['desc']})" if n in icons else "") for n in px["icons"])
    prompt = f"""กำกับฉากคลิปสั้นแนวตั้งสไตล์ "motion explainer กระดาษปะติด" (คนพูด + ภาพประกอบพิกเซลอาร์ต เปลี่ยนฉากทุกประโยค)
คลิปยาว {E['duration']:.1f} วิ · อารมณ์: {autopilot.VIBES.get(vibe, vibe)} · ซับ (วินาที|ข้อความ):
{lines}

ตอบ JSON {{"scenes": [...]}} แต่ละฉาก:
{{"start": <วินาที = เวลาเริ่มของซับสักบรรทัด>, "cam": "full|polaroid|corner|circle|none", "bg": "{'|'.join(BGS)}",
 "title": "<หัวข้อฉากสั้นๆ ≤ 18 ตัวอักษร>", "title_color": "red|yellow|green|blue", "transition": "slide|slap|drop|punch|cut",
 "items": [ <1-3 ชิ้น> {{"icon": "<ชื่อ>"}} หรือ {{"sprite": "<ชื่อ>"}} หรือ {{"brand": "<โดเมน>"}} หรือ {{"new": "<ชื่ออังกฤษ snake_case>", "desc": "<อธิบายภาพไทย>"}} + "at": <วินาทีหลังเริ่มฉาก> ],
 "tags": [ <1-3 ป้ายคำ> {{"text": "<คำสำคัญ 1-3 คำจากที่พูด>", "at": <วินาทีหลังเริ่มฉาก ตรงตอนพูดคำนั้น>}} ]}}

กล้อง (ตำแหน่งคนพูด):
- full = เต็มจอ ของเล็กแปะขอบ → ใช้ตอน hook ต้นคลิป ประโยคอารมณ์/มุก/สรุป
- polaroid = รูปติดเทปครึ่งล่าง ภาพประกอบครึ่งบน → ใช้บ่อยที่สุด
- corner = รูปเล็กมุมขวาบน ภาพประกอบใหญ่ → ตอนอธิบายของ/ขั้นตอน
- circle = วงกลมซ้ายบน + ของขวา/ล่าง → ตอนพูดถึงตัวเอง/ความรู้สึก
- none = ซ่อนคนพูด (≤ 10% ของฉาก) → ภาพรวม/แผนภาพล้วน
ของที่มี:
- sprite (ตัวการ์ตูนเฉิน ท่าตรงอารมณ์): {", ".join(px['sprites'])}
- icon: {icon_desc}
- brand: โดเมนแอป/ยี่ห้อที่พูดถึง (ระบบดึงโลโก้มาทำพิกเซลเอง) เช่น github.com
- new: ของที่ยังไม่มีในคลัง ระบบจะวาดพิกเซลให้ (ใช้ได้ไม่เกิน 12 ชิ้นต่อคลิป ตั้งชื่อกลางๆ ใช้ซ้ำได้ เช่น laptop, cloud, server)

กติกา:
- ฉากต่อกันครอบทั้งคลิป ฉากแรก start 0 · แต่ละฉากยาว {SCENE_LEN[density]} (ตัดตรงต้นประโยค)
- ห้ามกล้องแบบเดียวกันติดกันเกิน 2 ฉาก · พื้น (bg) สลับไม่ซ้ำฉากติดกัน
- ของต้องตรงกับที่พูดในฉากนั้น (พูดชื่อแอป = brand, พูดถึงของ = icon/new, อารมณ์ = sprite ท่าตรงอารมณ์)
- ของโผล่ทีละชิ้นตอนพูดถึง ("at") · title = หัวข้อฉาก ไม่ใช่ประโยคเต็ม"""
    out = autopilot.ai(prompt, model="opus")
    raw = out.get("scenes", out) if isinstance(out, dict) else out
    # ไอคอนใหม่ที่ AI ขอ → วาดก่อน (ขนาน)
    wants = {}
    for sc in raw:
        for it in sc.get("items") or []:
            if it.get("new"):
                n = re.sub(r"[^a-z0-9_]", "_", str(it["new"]).lower()).strip("_")[:30]
                if n:
                    it["icon"] = n
                    wants.setdefault(n, it.get("desc") or n)
    if wants:
        print(f"  วาดไอคอนใหม่ {len(wants)} ชิ้น: {', '.join(wants)}", flush=True)
        pixel_gen.ensure(dict(list(wants.items())[:12]))
    E["scenes"] = resolve(raw, proj, E["duration"])
    E["mode"] = "explainer"
    return E


def resolve(raw, proj, dur):
    """ตรวจ/เติมค่า + แปลงของเป็นไฟล์ + จัดตำแหน่งตามช่อง"""
    px = pixel.names()
    scenes, last = [], -1
    for sc in sorted(raw, key=lambda s: float(s.get("start", 0))):
        st = round(max(0.0, min(float(sc.get("start", 0)), dur - 0.5)), 3)
        if scenes and st - scenes[-1]["start"] < 1.0:  # ฉากสั้นเกิน = รวมกับฉากก่อน
            continue
        cam = sc.get("cam") if sc.get("cam") in CAMS else "polaroid"
        items = []
        for it in (sc.get("items") or [])[:3]:
            src = None
            if it.get("sprite") in px["sprites"]:
                src = f"pixel/{it['sprite']}.png"
            elif it.get("icon") in px["icons"]:
                src = f"pixel/icon_{it['icon']}.png"
            elif it.get("brand"):
                try:
                    p = pixel.make({"brand": it["brand"]}, os.path.join(proj, "broll"))
                    src = os.path.relpath(p, proj).replace("\\", "/")
                except Exception:
                    src = None
            if src:
                items.append({"src": src, "at": round(max(0.0, float(it.get("at", 0.3 * len(items)))), 2)})
        slots = SLOTS[cam][max(0, len(items) - 1)] if items else []
        for it, (x, y, s) in zip(items, slots):
            it.update(x=x, y=y, size=s)
        tags = [{"text": str(t.get("text", ""))[:24], "at": round(max(0.0, float(t.get("at", 0.5))), 2)}
                for t in (sc.get("tags") or [])[:3] if str(t.get("text", "")).strip()]
        scenes.append({"start": 0.0 if not scenes else st, "cam": cam,
                       "bg": sc.get("bg") if sc.get("bg") in BGS else BGS[len(scenes) % len(BGS)],
                       "title": str(sc.get("title", ""))[:28],
                       "title_color": COLORS.get(sc.get("title_color"), COLORS["yellow"]),
                       "transition": sc.get("transition") if sc.get("transition") in TRANSITIONS else "slide",
                       "items": items, "tags": tags})
        last = st
    return scenes


def add_focus(E, proj, vision=True):
    """ซูมตามบริบท: ตามหน้า + จับคู่คนพูด (E["faces"]) แล้วให้ AI ดูภาพทีละฉาก → sc["focus"]"""
    import focus
    src = os.path.join(proj, E["video"])
    subs = [x for x in E["items"] if x["track"] == "sub"]
    E["faces"] = focus.track_faces(src, subs)
    print(f"  ตามหน้าได้ {len(E['faces']['tracks'])} คน", flush=True)
    if not vision:
        return
    sc = E["scenes"]
    units = []
    for i, s in enumerate(sc):
        t1 = sc[i + 1]["start"] if i + 1 < len(sc) else E["duration"]
        text = " ".join(x["text"] for x in subs if x["start"] < t1 and x["end"] > s["start"])
        units.append({"id": i, "t0": s["start"], "t1": t1, "text": text})
    res = focus.vision_focus(src, units, os.path.join(proj, "_focus"))
    nbox = 0
    for i, s in enumerate(sc):
        s["focus"] = res.get(i) or [{"at": 0, "mode": "speaker"}]
        nbox += sum(1 for f in s["focus"] if f["mode"] == "box")
    print(f"  AI ดูภาพ {len(sc)} ฉาก · ซูมเข้าของ/จุดที่ชี้ {nbox} จุด", flush=True)


def scene_sfx(E):
    """เสียงเปลี่ยนฉาก (whoosh เบาๆ) — แทนของเดิมที่ระบบใส่ไว้ (id ขึ้นต้น x)"""
    E["items"] = [x for x in E["items"] if not str(x.get("id", "")).startswith("x")]
    for i, sc in enumerate(E["scenes"][1:], 1):
        E["items"].append({"id": f"x{i}", "track": "sfx", "start": max(0, round(sc["start"] - 0.08, 3)),
                           "end": round(sc["start"] + 0.4, 3), "sfx": "whoosh_fast", "vol": 0.45})


# ---------- render ----------
def junction(link, target):
    if os.path.exists(link):
        return
    os.makedirs(os.path.dirname(link), exist_ok=True)
    subprocess.run(["cmd", "/c", "mklink", "/J", link, target], check=True, capture_output=True)


def props_for(E, proj, url=False):
    """edit.json → props ของ Explainer · url=True = พรีวิวใน editor (ชี้ path ของ server)"""
    proj = os.path.normpath(os.path.abspath(proj))  # D:/x กับ D:\x ต้องได้ hash เดียวกัน · mklink รับแต่ \
    jid = hashlib.md5(proj.encode()).hexdigest()[:10]
    if url:
        p_pix, p_proj = "/pixel/", "/media/"
    else:
        junction(os.path.join(RM, "public", "pixel"), pixel.PIX)
        junction(os.path.join(RM, "public", "jobs", jid), proj)
        p_pix, p_proj = "pixel/", f"jobs/{jid}/"
    fix = lambda s: (p_pix + s[6:]) if s.startswith("pixel/") else p_proj + s  # noqa: E731
    sw, sh = E.get("source_wh", [1080, 1920])
    font = E.get("style", {}).get("font", "Kanit")
    return {
        "video": fix(E["video"]), "srcW": sw, "srcH": sh, "face": E.get("face"), "faces": E.get("faces"),
        "fontName": font if font in ("Kanit", "Mali") else "Kanit",
        "total": int(round(E["duration"] * FPS)),
        "subs": [{"start": x["start"], "end": x["end"], "text": x["text"], "speaker": x.get("speaker")}
                 for x in E["items"] if x["track"] == "sub"],
        "scenes": [dict(sc, items=[dict(it, src=fix(it["src"])) for it in sc.get("items", [])]) for sc in E.get("scenes", [])],
    }


def render(path, preview=False, out=None, to=None):
    import render_edit
    E = ccfx.load_edit(path)
    proj = os.path.dirname(os.path.abspath(path))
    base = os.path.basename(path)[: -len(".edit.json")]
    out = out or os.path.join(proj, f"{base}_{'preview' if preview else 'explainer'}_9x16.mp4")
    props = props_for(E, proj)
    if to:
        props["total"] = int(to * FPS)
    pf = os.path.join(proj, "_explainer.props.json")
    json.dump(props, open(pf, "w", encoding="utf-8"), ensure_ascii=False)
    silent = os.path.join(proj, "_explainer.silent.mp4")
    npx = os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "nodejs", "npx.cmd")
    cmd = [npx, "remotion", "render", "src/index.jsx", "Explainer", silent, f"--props={pf}", "--codec=h264",
           "--muted", "--log=info", "--concurrency=50%"]
    cmd += ["--scale=0.5", "--crf=28"] if preview else ["--crf=18"]
    print(f"Remotion: {props['total']} เฟรม · {len(props['scenes'])} ฉาก", flush=True)
    p = subprocess.Popen(cmd, cwd=RM, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                         encoding="utf-8", errors="replace")
    last = -10
    for line in p.stdout:
        m = re.search(r"Rendered (\d+)/(\d+)", line)
        if m:
            pct = 100 * int(m.group(1)) / max(1, int(m.group(2)))
            if pct - last >= 5:
                print(f"  ภาพ {pct:5.1f}%", flush=True); last = pct
        elif "rror" in line:
            print(line.rstrip(), flush=True)
    if p.wait() != 0:
        raise SystemExit("Remotion เรนเดอร์ไม่ผ่าน")
    # ผสมเสียง: ภาพเงียบจาก Remotion + เสียงพูด/SFX/เพลง ระบบเดียวกับ render_edit
    dur = props["total"] / FPS
    E2 = dict(E, duration=dur)
    sfx = sorted([x for x in E["items"] if x["track"] == "sfx" and x["start"] < dur], key=lambda x: x["start"])
    ain, lines = render_edit.audio_graph(E2, 1, 2, sfx)
    gf = os.path.join(proj, "_explainer.audio.txt")
    open(gf, "w", encoding="utf-8").write(";\n".join(lines))
    subprocess.run([render_edit.FF, "-y", "-v", "error", "-i", silent, "-i", os.path.join(proj, E["video"]), *ain,
                    "-/filter_complex", gf, "-map", "0:v", "-map", "[aout]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-t", f"{dur:.3f}", "-movflags", "+faststart", out], check=True)
    os.remove(silent)
    m = E.get("music") and next((x for x in ccfx.music_list() if x["id"] == E["music"]["src"]), None)
    if m and m["credit"]:
        print("\nเครดิตเพลง (ก๊อปใส่ใต้คลิป — CC BY บังคับ):\n" + m["credit"] + "\n")
    print("OUTPUT " + out, flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["plan", "render", "focus"])
    ap.add_argument("edit")
    ap.add_argument("--density", type=int, default=2)
    ap.add_argument("--vibe", default="tech")
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--to", type=float)
    ap.add_argument("--out")
    a = ap.parse_args()
    path = os.path.abspath(a.edit)
    if a.cmd == "plan":
        E = ccfx.load_edit(path)
        if not E.get("face"):
            import face
            E["face"] = face.find_face(os.path.join(os.path.dirname(path), E["video"]))
        plan(E, os.path.dirname(path), a.density, a.vibe)
        add_focus(E, os.path.dirname(path))
        scene_sfx(E)
        ccfx.save_edit(path, E)
        print(f"✓ {len(E['scenes'])} ฉาก → {path}")
    elif a.cmd == "focus":  # ทำซูมตามบริบทใหม่ให้โปรเจกต์ที่มีฉากแล้ว (ไม่แตะฉาก)
        E = ccfx.load_edit(path)
        add_focus(E, os.path.dirname(path))
        ccfx.save_edit(path, E)
        print("✓ focus →", path)
    else:
        render(path, a.preview, a.out, a.to)


if __name__ == "__main__":
    main()
