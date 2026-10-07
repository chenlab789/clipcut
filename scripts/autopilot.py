#!/usr/bin/env python
"""autopilot — คลิปดิบ → edit.json พร้อมเปิดใน editor (ไม่ต้องคุยกับกุ้ง)

  python autopilot.py <คลิป> [--out DIR] [--opts '{"cut":1,"subs":1,"sfx":1,"emoji":1,"broll":1,"fx":1,"music":1,
                                                  "vibe":"tech","aspect":"9x16","density":2}']

ขั้นตอน (พิมพ์ "STEP i/N ข้อความ" + "PROG 0-100" ให้หน้าเว็บทำแถบความคืบหน้า):
  1 ถอดเสียง (ElevenLabs)   2 AI ดูภาพ+อ่านบท → แก้คำเพี้ยน / เลือกสีซับ / ช่วงเงียบที่ต้องเก็บ / เพลง
  3 ตัด dead air            4 AI วางเอฟเฟกต์ตามบท       5 ภาพประกอบพิกเซล + เขียน edit.json
AI = `claude -p` (Claude Code แบบเบื้องหลัง ใช้แพ็กเกจของเฉิน) — ไม่ต้องมี API key
จบด้วยบรรทัด "EDIT <path>" → server เปิด editor ให้ · เฉินกด Render เอง
"""
import os
import re
import sys
import json
import shutil
import argparse
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import clipcut as cc  # noqa: E402
import ccfx  # noqa: E402
import edit_init  # noqa: E402
import edit_apply  # noqa: E402
import pixel  # noqa: E402

if sys.stdout:  # server รันด้วย pythonw = ไม่มี stdout
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
DEFAULT_OPTS = {"cut": 1, "subs": 1, "sfx": 1, "emoji": 0, "broll": 1, "gif": 1, "fx": 1, "cam": 1, "music": 1, "voice": 1,
                "vibe": "tech", "aspect": "9x16", "density": 2}
VIBES = {"tech": "สอน/เทค เล่าเรื่องจริงจังแต่กันเอง", "funny": "ฮา กวนตีน เน้นมุก",
         "vlog": "vlog ชีวิตประจำวัน/แกะกล่อง สดใส", "hype": "มันส์ ตื่นเต้น จังหวะเร็ว"}
DENSITY = {1: "น้อย ~1 จุดต่อ 12-15 วิ เฉพาะพีคจริงๆ", 2: "พอดี ~1 จุดต่อ 6-10 วิ",
           3: "แน่นสาย TikTok ~1 จุดต่อ 3-5 วิ"}
SFX_DESC = {
    "whoosh": "เปลี่ยนเรื่อง/ภาพโผล่", "whoosh_fast": "ภาพโผล่เร็ว", "swoosh_down": "ของหล่น/ลง",
    "boom": "พีค/reveal ใหญ่", "bass_drop": "พีคหนักมาก", "riser": "บิ้วก่อนพีค ยาว 2 วิ (ให้จบตรงพีค)",
    "ding": "ถูก/ไอเดีย", "confirm": "สำเร็จ", "tada": "ฉลอง/โคตรเจ๋ง", "coin": "เงิน",
    "pop": "อีโมจิ/ของเด้ง", "click": "กด/คลิก", "tick": "นับ/เช็ค", "drop": "วางของ",
    "boing": "มุก/งง/เด้ง", "record_scratch": "หยุดเรื่อง/เฟล/อ้าว", "buzzer": "ผิด/ไม่ใช่",
    "error": "พัง/ใช้ไม่ได้", "question": "สงสัย/คำถาม", "punch": "ต่อย/กระแทกแรง",
    "punch_light": "กระแทกเบา", "hit_soft": "ตุบ", "glitch": "ระบบ/เทค/ภาพแตก", "glitch_2": "เทคแบบสั้น",
    "laser": "เกม/ยิง", "zap": "ไฟช็อต", "powerup": "เก่งขึ้น/อัปเลเวล", "phaser_up": "ขึ้น/บิน",
    "glass": "แตก/เปราะ", "metal_clang": "โลหะกระแทก", "bell": "ระฆัง/ประกาศ", "wood_knock": "เคาะ",
    "pluck": "น่ารักๆ", "open": "เปิดแอป/หน้าต่าง", "scratch": "ขูดสั้น", "shutter": "ถ่ายรูป/แคปจอ",
    # ชุด meme (ใช้คู่กับตัดเข้า GIF)
    "vine_boom": "บึ้ม meme ช็อค/ตบมุก", "crickets": "จิ้งหรีด เงียบกริบ/มุกแป้ก", "dun_dun": "ดั่นดั่นดั๊น ดราม่า",
    "sad_trombone": "วาวาวาาา เฟล/ผิดหวัง", "slide_down": "นกหวีดลง ล้ม/พัง", "slide_up": "นกหวีดขึ้น ลอย/ดีขึ้น",
    "bonk": "เคาะหัว โง่/โดนตบ", "reveal_sting": "ตึ่งง เผยความจริง/plot twist", "zoom_out": "ฟิ้ววว หายตัว/ชิ่ง",
}
GIF_SPACING = {1: (20, 12), 2: (14, 8), 3: (10, 6)}  # density → (ตัดเข้าเต็มจอห่างกันอย่างน้อย, แปะทับห่างกันอย่างน้อย) วิ


def gif_spacing(opts):
    """เลือก GIF อย่างเดียว (ไม่มีภาพพิกเซล) → แปะทับถี่ขึ้น ~40% เพราะเป็นภาพเดียวที่ทำให้คลิปไม่แช่"""
    c, o = GIF_SPACING[opts["density"]]
    return (c, o) if opts.get("broll") else (c, round(o * 0.6, 1))
EMOJI_SPEC = '- emoji: {"track":"emoji","start":s,"end":e,"emoji":"<อีโมจิ 1 ตัว>","anim":"pop|shake|float","x":0.72 หรือ 0.28}\n'
EMOJI_RULE = "- อีโมจิ 1 ตัวเดี่ยว ห้ามอีโมจิผสม (ZWJ) ห้ามสีผิว · ตรงอารมณ์ประโยค สลับ x 0.72/0.28 ไม่ซ้ำที่เดิมติดกัน · ยาว 1.2-2 วิ\n"
CHAR = {"เฉิน": "hoodie_", "แฟน": "girl_"}  # ตัวการ์ตูนพิกเซลของแต่ละคน (char_sprites.py)
SYS = ("คุณคือ backend ของโปรแกรมตัดต่อวิดีโอ ตอบเป็น JSON ที่ถูกต้องอย่างเดียว ห้ามมีข้อความอื่น "
       "ห้ามใส่ markdown code fence ห้ามใช้เครื่องมือ ยกเว้นถูกบอกให้ Read ไฟล์ภาพ")
N_STEPS = 5
NEW_ICONS = {1: 2, 2: 4, 3: 6}


def step(i, msg):
    print(f"STEP {i}/{N_STEPS} {msg}", flush=True)


def prog(p):
    print(f"PROG {int(p)}", flush=True)


def claude_exe():
    p = os.path.join(os.environ.get("APPDATA", ""), "npm", "node_modules", "@anthropic-ai", "claude-code", "bin", "claude.exe")
    return p if os.path.exists(p) else (shutil.which("claude.exe") or shutil.which("claude") or "claude")


USAGE = os.path.join(os.path.expanduser("~"), ".clipcut", "usage.jsonl")


def log_usage(out, model):
    """จดการใช้ AI ทุกครั้ง → ~/.clipcut/usage.jsonl (งาน = env CLIPCUT_JOB) · สรุปท้ายงานด้วย usage_summary()"""
    try:
        u = out.get("usage") or {}
        rec = {"t": round(__import__("time").time()), "job": os.environ.get("CLIPCUT_JOB", ""), "model": model,
               "in": u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0) + u.get("cache_read_input_tokens", 0),
               "out": u.get("output_tokens", 0), "usd": round(out.get("total_cost_usd") or 0, 5)}
        os.makedirs(os.path.dirname(USAGE), exist_ok=True)
        with open(USAGE, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception:
        pass


def usage_summary(job):
    n = tin = tout = usd = 0
    try:
        for line in open(USAGE, encoding="utf-8"):
            r = json.loads(line)
            if r.get("job") == job:
                n += 1; tin += r["in"]; tout += r["out"]; usd += r["usd"]
    except Exception:
        pass
    return n, tin, tout, usd


def ai(prompt, read=False, model="sonnet", tries=2, turns=6):
    """ถาม claude -p → dict/list (ดึง JSON ก้อนแรกจากคำตอบ)"""
    # ไม่โหลดของ Claude Code ที่งานนี้ไม่ใช้ (เครื่องมือ/MCP/skill/settings ผู้ใช้) — "say ok" เดิม ~30k tokens → ~5k
    # (--bare ลดได้อีกแต่ใช้กับแพ็กเกจ claude.ai ไม่ได้ ต้องมี API key)
    cmd = [claude_exe(), "-p", "--output-format", "json", "--model", model, "--system-prompt", SYS,
           "--tools", "Read" if read else "", "--strict-mcp-config", "--setting-sources", "project", "--disable-slash-commands"]
    cmd += ["--allowedTools", "Read", "--max-turns", str(turns)] if read else ["--max-turns", "1"]
    last = None
    for _ in range(tries):
        r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=600)
        try:
            out = json.loads(r.stdout)
            txt = out["result"]
            log_usage(out, model)
        except Exception:
            last = (r.stdout or r.stderr)[-500:]; continue
        m = re.search(r"[\[{].*[\]}]", txt, re.S)
        try:
            return json.loads(m.group(0))
        except Exception:
            last = txt[-500:]
    raise SystemExit("AI ตอบไม่เป็น JSON: " + str(last))


def contact_sheet(src, out, n=8):
    """ภาพนิ่ง n เฟรมทั่วคลิป ต่อเป็นแผ่นเดียว — ให้ AI ดูธีม/สีของคลิป"""
    dur = cc.probe_dur(src)
    fps = n / max(dur, 1)
    subprocess.run([cc.FF, "-y", "-v", "error", "-i", src, "-vf",
                    f"fps={fps:.5f},scale=360:-2,tile={n // 2}x2:padding=6", "-frames:v", "1", out], check=True)
    return out


def pass1(segs, sheet, opts):
    lines = "\n".join(f"{i}|{s['start']:.1f}|{s.get('speaker') or '-'}|{s['text']}" for i, s in enumerate(segs))
    speakers = sorted({s.get("speaker") for s in segs if s.get("speaker")})
    musics = "\n".join(f"- {m['id']}: {m['title']} — {m['mood']}" for m in ccfx.music_list())
    prompt = f"""คลิปของ ChenLab (เฉิน ผู้ชาย พูดภาษาไทยกันเองแบบกู/มึง) ถอดเสียงอัตโนมัติมา ช่วยเตรียมตัดต่อ
1) Read ภาพนี้ก่อน (ภาพนิ่งจากทั้งคลิป 8 ช่อง เรียงตามเวลา): {sheet}
2) บท (index|วินาที|คนพูด|ข้อความ):
{lines}

ตอบ JSON:
{{"title": "<ชื่อคลิปภาษาไทย ≤30 ตัว ตามเนื้อหา>",
 "fixes": [{{"i": <index>, "text": "<ข้อความที่แก้>"}}],
 "chen": "<speaker id ของเฉิน หรือ null>",
 "style": {{"font": "Mali|Kanit|Itim", "outline": "#hex", "shadow_color": "#hex", "speakers": {{"<speaker id>": "#hex"}}, "highlights": {{"<คำเด่น>": "#hex"}}}},
 "music": "<id เพลง>"}}

กติกา:
- title: ชื่อที่บอกว่าคลิปนี้เกี่ยวกับอะไร ให้เฉินหาเจอง่ายทีหลัง เช่น "แกะกล่องของขวัญวันเกิดแฟน", "รีวิว Claude Code บน iPhone" ห้ามใส่วันที่/อีโมจิ
- fixes: แก้เฉพาะคำที่ถอดเพี้ยนชัดๆ จากบริบท โดยเฉพาะชื่อแบรนด์/แอป/ศัพท์อังกฤษ (เช่น "Cort Code"→"Claude Code") ห้ามแก้สำนวนพูด ห้ามเกลาคำหยาบ ไม่แน่ใจ = ไม่แก้
  คำที่แก้ต้องออกเสียงใกล้ของเดิม (ถอดเพี้ยน) เท่านั้น — ห้ามเปลี่ยนเป็นคำอื่นตามที่เห็นในภาพ (เคยแก้ "ขึ้นรูป…ส้ม" เป็น "ซูมรูป…ขวด" = เฉินไม่ได้พูดแบบนั้น)
- speakers ที่พบ: {speakers or "ไม่มี (คนเดียว)"} — เฉิน = ฟ้าอ่อน #9AD8FF · คนอื่นสีอ่อนที่ต่างชัด (#FFE066, #FF9AC8) · คนเดียว = {{}}
- font: เทค/จริงจัง = Kanit, ชิล/น่ารัก = Mali, สบายๆ = Itim · outline/shadow_color = สีเข้มโทนเดียวกับคลิป (ดำได้)
- highlights: 3-8 คำสำคัญที่พูดบ่อย (ชื่อของ/แอป/คำเด่น) สีตัดกับคลิป ห้ามซ้ำสีคนพูด
- music: เลือก 1 เพลงที่เข้ากับอารมณ์ "{VIBES[opts['vibe']]}":
{musics}"""
    return ai(prompt, read=True)


def roles(subs, chen):
    """speaker id → เฉิน / แฟน (คนพูดเยอะสุดที่ไม่ใช่เฉิน) / คนอื่น"""
    talk = {}
    for s in subs:
        if s.get("speaker"):
            talk[s["speaker"]] = talk.get(s["speaker"], 0) + s["end"] - s["start"]
    order = sorted(talk, key=lambda k: -talk[k])
    chen = chen if chen in talk else (order[0] if order else None)
    rest = [k for k in order if k != chen]
    return {k: ("เฉิน" if k == chen else "แฟน" if rest and k == rest[0] else "คนอื่น") for k in talk}


def pass2(items, dur, opts, vertical, peaks=(), role=None):
    role = role or {}
    subs = "\n".join(f"{x['start']:.2f}-{x['end']:.2f}|{role.get(x.get('speaker'), 'เฉิน')}|{x['text']}"
                     for x in items if x["track"] == "sub")
    px = pixel.names()
    poses = sorted({sp[len("hoodie_"):] for sp in px["sprites"] if sp.startswith("hoodie_")})
    want = [k for k in ("sfx", "emoji", "broll", "gif", "fx") if opts.get(k)]
    gif_txt = gif_rule = broll_rule = ""
    if opts.get("broll"):  # ภาพพิกเซล: เลือกอย่างเดียว = ได้โควตาเต็ม · คู่กับ GIF = ได้รอง (GIF สำคัญกว่า)
        every = {1: 12, 2: 8, 3: 5}[opts["density"]] * (1.3 if opts.get("gif") else 0.6)
        broll_rule = f"\n- ภาพพิกเซล (broll) ประมาณ {max(1, round(dur / every))} ภาพ กระจายทั้งคลิป" + (
            " · ห้ามวางช่วงเวลาเดียวกับ gif (gif สำคัญกว่า)" if opts.get("gif") else "")
    if opts.get("gif"):
        import gif_lib
        cut_gap, ov_gap = GIF_SPACING[opts["density"]]
        gif_txt = f"""- gif  : GIF/meme จากคลัง 3 แบบ
    แปะทับ    {{"track":"gif","mode":"overlay","start":s,"gif":"<id>"}}  GIF กรอบสติกเกอร์บนคลิป 1.5-2.5 วิ เสริมอารมณ์ประโยค
    ตัดเข้า    {{"track":"gif","mode":"cut","start":s,"gif":"<id>","caption":"<คำมุกไทยสั้นๆ หรือว่าง>","sfx":"<เสียงชุด meme>"}}
              คลิปหยุด แล้วตัดไป GIF เต็มจอ 1-2 วิ ค่อยกลับมา · start = ท้ายประโยคที่ปล่อยมุก/พีค (ระบบเลื่อนไปท้ายประโยคให้)
    หยุดภาพ   {{"track":"gif","mode":"freeze","start":s,"caption":"<เช่น เดี๋ยวนะ... / ก็คือ...>","sfx":"record_scratch"}}  ภาพค้าง+ซูม+ข้อความ ตอนเรื่องหักมุม/พูดอะไรแปลกๆ
    ไม่มีตัวที่ตรงในคลัง → "gif":null,"query":"<คำค้นภาษาอังกฤษ>","cat":"<หมวด>" ระบบค้นออนไลน์ให้
    คลัง (หมวด → id:ยาว:คำอธิบาย · ตัวต้นๆ ใช้น้อย เลือกก่อน):
{gif_lib.catalog()}"""
        n_cut, n_ov = max(1, round(dur / (cut_gap * 1.4))), max(1, round(dur / (ov_gap * 1.8)))
        if not opts.get("broll"):  # เลือก GIF อย่างเดียว = GIF ได้โควตาภาพทั้งหมด (แปะทับถี่ขึ้น)
            ov_gap = gif_spacing(opts)[1]
            n_cut, n_ov = round(n_cut * 1.3 + 0.2), max(2, round(dur / (ov_gap * 1.5)))
        gif_rule = (f"\n- GIF สำคัญ (คลิปห้ามแช่หน้าคนพูดอย่างเดียวจนน่าเบื่อ): ใส่ตัดเข้า/หยุดภาพประมาณ {n_cut} ครั้ง + แปะทับประมาณ {n_ov} ครั้ง กระจายทั้งคลิป · "
                    f"ตัดเข้า/หยุดภาพ ห่างกันอย่างน้อย {cut_gap} วิ · แปะทับห่างกัน {ov_gap} วิ · "
                    "ใช้ตอนพีค/มุก/ช็อค/อารมณ์ชัด ไม่ใส่ตอนกำลังอธิบายเรื่องสำคัญ · ห้ามใช้ gif ตัวเดิมซ้ำในคลิป · ตัดเข้าต้องมี sfx ชุด meme คู่เสมอ")
    prompt = f"""วางเอฟเฟกต์ให้คลิปสั้น ({'แนวตั้ง 9:16' if vertical else 'แนวนอน 16:9'} ยาว {dur:.0f} วิ) ตามบทนี้ (วินาทีหลังตัดต่อแล้ว|คนพูด|ข้อความ):
{subs}

อารมณ์คลิป: {VIBES[opts['vibe']]} · ความแน่น: {DENSITY[opts['density']]}
ใส่ได้เฉพาะ track: {", ".join(want)}

ตอบ JSON array ของ item (เรียงตามเวลา):
- sfx  : {{"track":"sfx","start":s,"sfx":"<ชื่อ>","vol":0.5-1.0}}
{EMOJI_SPEC if opts.get("emoji") else ""}- fx   : {{"track":"fx","start":s,"end":e,"fx":"punch|zoomin|zoomout|shake|flash","amount":ค่า}}  (punch 0.45 วิ amount 1.15-1.25 · zoomin/zoomout 2-4 วิ amount 1.08-1.15 · shake 0.5 วิ amount 12-20 · flash 0.35 วิ amount 0.5-0.7)
- broll: {{"track":"broll","start":s,"end":e,"pixel":{{"sprite":"<ท่า>","brand":"<โดเมน>","icon":"<ไอคอน>"}}}}  ภาพประกอบพิกเซลอาร์ต ใส่ 1-2 อย่างใน pixel
    sprite = ท่าของตัวการ์ตูน "คนที่พูดประโยคนั้น" (ระบบเลือกตัวเฉิน/ตัวแฟนให้เองตามคนพูด · ประโยคของ "คนอื่น" ไม่ต้องใส่ sprite ใช้ icon/brand อย่างเดียว): {", ".join(poses)}
    icon ที่มีแล้ว: {", ".join(px["icons"])}
    ไม่มีไอคอนที่ตรงของที่พูดถึง → ตั้งชื่อใหม่ภาษาอังกฤษ snake_case แล้วใส่ "icon_desc":"<อธิบายรูปเป็นไทยสั้นๆ>" ใน pixel ระบบจะวาดพิกเซลให้ (ใหม่ไม่เกิน {NEW_ICONS[opts['density']]} ตัว ใช้กับของเฉพาะเรื่องที่ภาพชัด เช่น ไมค์ กล้อง ทุเรียน)
    brand = โดเมนเว็บของแอป/ยี่ห้อที่พูดถึง เช่น "github.com" (ระบบดึงโลโก้มาทำพิกเซลเอง)
    ใช้ตอนพูดชื่อแอป/ของ (sprite ท่า point + brand) หรือตอนอารมณ์ชัด (sprite ท่าตรงอารมณ์ + icon) ยาว 2-4 วิ

{gif_txt}

ชื่อ sfx ที่มี (ห้ามใช้ชื่ออื่น): {json.dumps(SFX_DESC, ensure_ascii=False)}

กติกา:
- วางเฉพาะจังหวะที่มีเหตุผล: พีค ปล่อยมุก ช็อค เปลี่ยนเรื่อง พูดชื่อของ — ห้ามโปรยทุกประโยค
- punch วางตรงจุดเสียงเน้น (วินาทีที่คนพูดเน้นเสียง/ตะโกน/หัวเราะ): {", ".join(f"{p:.1f}" for p in peaks) or "-"} — เลือกเฉพาะจุดที่ประโยคมีความหมายพีคจริง ไม่ต้องใช้ทุกจุด
- ไม่ต้องวางซูมช้ากันภาพนิ่งหรือซูมไปที่ของ ระบบดูภาพแล้วใส่ให้เอง
- sfx ตรงจังหวะคำ (start = เวลาเริ่มประโยคนั้น) · ภาพโผล่ = whoosh นำหน้า 0.05 วิ · อีโมจิเด้ง = pop · riser จบตรงพีคแล้วตามด้วย boom+punch
{EMOJI_RULE if opts.get("emoji") else ""}- ห้ามของซ้อนเวลาเดียวกันเกิน 3 อย่าง · ห้ามใช้ sfx ตัวเดิมติดกันเกิน 2 ครั้ง
- ช่วงต้นคลิป 3 วิแรกควรมี hook (whoosh/punch/ภาพ/gif){gif_rule}{broll_rule}"""
    out = ai(prompt)
    return out if isinstance(out, list) else out.get("items", [])


def declutter(E):
    """ลำดับความสำคัญ GIF > ภาพพิกเซล > อีโมจิ (เฉินให้คะแนนเอง) — ช่วงเวลาชนกัน = เก็บตัวที่สำคัญกว่า"""
    hit = lambda a, b, m=0.3: a["start"] < b["end"] + m and a["end"] > b["start"] - m  # noqa: E731
    mine = [x for x in E["items"] if x.get("cmd") and x["track"] in ("gif", "broll")]  # สั่งด้วยเสียง = สำคัญสุด
    drop = {id(x) for x in E["items"] if x["track"] in ("gif", "broll") and not x.get("cmd") and not x.get("gap")
            and any(hit(x, m) for m in mine)}
    gifs = [x for x in E["items"] if x["track"] == "gif" and id(x) not in drop] + [m for m in mine if m["track"] == "broll"]
    pix = [x for x in E["items"] if x["track"] == "broll" and not x.get("cmd") and id(x) not in drop]
    drop |= {id(b) for b in pix if any(hit(b, g) for g in gifs)}
    drop |= {id(e) for e in E["items"] if e["track"] == "emoji"
             and any(hit(e, o) for o in gifs + [p for p in pix if id(p) not in drop])}
    gone = [x for x in E["items"] if id(x) in drop]
    drop |= {id(s) for s in E["items"] if s["track"] == "sfx" and s["sfx"] in ("pop", "whoosh", "whoosh_fast")
             and any(abs(s["start"] - g["start"]) < 0.15 for g in gone)}  # เสียงที่วางคู่ภาพที่ถูกเอาออก
    if drop:
        E["items"] = [x for x in E["items"] if id(x) not in drop]
        print(f"  เอาภาพที่ชน GIF ออก {len(drop)} ชิ้น", flush=True)
    return len(drop)


def place_gifs(E, plan, outdir, opts):
    """GIF จาก AI → แปะทับ = item ธรรมดา · ตัดเข้า/หยุดภาพ = เว้นช่องหยุดคลิป (gaps.py) แล้วสร้างคลิปใหม่"""
    import gif_lib
    import gaps
    GL = gif_lib.lib()
    cut_gap, ov_gap = gif_spacing(opts)
    work = os.path.join(outdir, "_gif")
    os.makedirs(work, exist_ok=True)
    want, used, last = [], set(), {"cut": -99.0, "overlay": -99.0}
    for it in sorted((x for x in plan if x.get("track") == "gif" and isinstance(x.get("start"), (int, float))), key=lambda x: x["start"]):
        mode = it.get("mode") if it.get("mode") in ("overlay", "cut", "freeze") else "overlay"
        kind = "overlay" if mode == "overlay" else "cut"
        if any(abs(it["start"] - c["t"]) < 2.0 for c in E.get("commands") or []):
            continue  # ตรงนั้นเฉินสั่งเองแล้ว
        if it["start"] - last[kind] < (ov_gap if kind == "overlay" else cut_gap):
            print(f"  ข้าม GIF ที่ {it['start']:.1f} (ถี่เกิน)", flush=True)
            continue
        gid = it.get("gif")
        if mode != "freeze" and (gid not in GL or gid in used):
            gid = None
            if it.get("query"):
                print(f"  ค้น GIF ออนไลน์: {it['query']}", flush=True)
                cat = re.sub(r"[^a-z0-9_]", "", str(it.get("cat") or "online").lower()) or "online"
                gid = gif_lib.online(str(it["query"]), cat, work)
                GL = gif_lib.lib()
            if not gid or gid in used:
                continue
        if gid:
            used.add(gid)
        last[kind] = it["start"]
        want.append(dict(it, mode=mode, gif=gid))

    def nid(pre):
        n = 1
        while any(x.get("id") == f"{pre}{n}" for x in E["items"]):
            n += 1
        return f"{pre}{n}"
    # แปะทับก่อน (ไม่ขยับเวลา) แล้วค่อยเว้นช่องจากท้ายคลิปมาหน้า — ช่องหลังไม่ทำให้เวลาช่องหน้าเพี้ยน
    for it in [x for x in want if x["mode"] == "overlay"]:
        d = min(2.5, max(1.2, GL[it["gif"]]["dur"]))
        E["items"].append(edit_apply.fill({"id": nid("g"), "track": "gif", "mode": "overlay", "gif": it["gif"], "start": it["start"],
                                           "end": it["start"] + d, "caption": str(it.get("caption") or "")[:40]}, E))
    n_cut = 0
    for it in sorted([x for x in want if x["mode"] != "overlay"], key=lambda x: -x["start"]):
        t = gaps.boundary(E, it["start"])
        d = 1.3 if it["mode"] == "freeze" else min(2.0, max(0.9, GL[it["gif"]]["dur"]))
        g = gaps.insert(E, t, d)
        gi = {"id": nid("g"), "track": "gif", "mode": it["mode"], "start": g["at"], "end": round(g["at"] + g["dur"], 3),
              "caption": str(it.get("caption") or "")[:40], "gap": g["id"]}
        if it["mode"] == "cut":
            gi["gif"] = it["gif"]
        E["items"].append(gi)
        sfx = it.get("sfx") if it.get("sfx") in SFX_DESC else ("record_scratch" if it["mode"] == "freeze" else "vine_boom")
        E["items"].append(edit_apply.fill({"id": nid("a"), "track": "sfx", "sfx": sfx, "start": g["at"], "vol": 0.9, "gap": g["id"]}, E))
        if it["mode"] == "freeze":  # ภาพค้าง + ดันซูมเข้าช้าๆ
            E["items"].append({"id": nid("z"), "track": "fx", "fx": "focus", "start": g["at"], "end": round(g["at"] + g["dur"], 3),
                               "amount": 1.18, "gap": g["id"], "auto": "freeze"})
        n_cut += 1
    if n_cut:
        print(f"  เว้นช่องตัดเข้า GIF {n_cut} จุด → สร้างคลิปใหม่…", flush=True)
        gaps.build_video(E, outdir)
    gif_lib.bump([x["gif"] for x in want if x.get("gif")])
    shutil.rmtree(work, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("--out")
    ap.add_argument("--opts", default="{}")
    a = ap.parse_args()
    opts = dict(DEFAULT_OPTS, **json.loads(a.opts))
    opts["density"] = int(opts["density"])
    opts["emoji"] = 0  # เฉินสั่งเอาอีโมจิออก (2026-10-07) — หน้าแรกส่งอะไรมาก็ไม่ใส่
    src = os.path.abspath(a.input)
    base = os.path.splitext(os.path.basename(src))[0]
    multi = [os.path.abspath(c) for c in opts.get("clips") or []]
    if len(multi) > 1:  # หลายคลิป → ชื่องาน = ชื่อโฟลเดอร์กลุ่ม
        base = opts.get("name") or base
    outdir = os.path.abspath(a.out or os.path.join(os.path.dirname(src), "clipcut_" + base))
    os.makedirs(outdir, exist_ok=True)
    seg_json = os.path.join(outdir, base + ".segments.json")
    cut = os.path.join(outdir, base + ".cut.mp4")
    edit = os.path.join(outdir, base + ".edit.json")
    json.dump(opts, open(os.path.join(outdir, "autopilot.opts.json"), "w", encoding="utf-8"), ensure_ascii=False)
    os.environ.setdefault("CLIPCUT_JOB", f"{base}@{int(__import__('time').time())}")  # ลูก (pixel_gen/focus) จดรวมงานนี้

    # 1 ถอดเสียง (หลายคลิป = รวมเป็นคลิปเดียวก่อน — multiclip.py)
    step(1, "รวมคลิป + ถอดเสียง" if len(multi) > 1 else "ถอดเสียง"); prog(2)
    clips = None
    if len(multi) > 1:
        import multiclip
        src, seg_json, clips = multiclip.build(multi, outdir, base, opts.get("kind", "story"), opts.get("order", "manual"),
                                               log=lambda m: print(m, flush=True))
    elif not os.path.exists(seg_json):
        # คลิปในคลัง: ถอดเสียงครั้งเดียวเก็บข้างไฟล์ → ตัดซ้ำรอบหน้าไม่ต้องถอดใหม่
        cache = src + ".segments.json" if "_library" in src.replace("\\", "/").split("/") else None
        if cache and os.path.exists(cache):
            shutil.copy(cache, seg_json); print("  ใช้ผลถอดเสียงเดิมของคลิปนี้", flush=True)
        else:
            subprocess.run([sys.executable, os.path.join(HERE, "transcribe.py"), src, seg_json, "medium"], check=True)
            if cache:
                shutil.copy(seg_json, cache)
    data = ccfx.load_edit(seg_json)
    segs = data["segments"]
    if not segs:
        raise SystemExit("ไม่พบเสียงพูดในคลิป")
    prog(15)

    # 2 AI รอบแรก: แก้คำ / สไตล์ / keep / เพลง
    step(2, "AI ดูคลิป แก้คำเพี้ยน เลือกสไตล์ซับ")
    sheet = contact_sheet(src, os.path.join(outdir, "_frames.jpg"))
    p1 = pass1(segs, sheet, opts)
    json.dump(p1, open(os.path.join(outdir, "_ai_pass1.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    # คำสั่งเสียงตามบริบท ("เอารูปกุ้งขึ้นตรงนี้" / "ซูมเข้าขวด") — หาจากบทดิบก่อนแก้คำ (เคยโดนแก้ "ขึ้นรูปอ่า…ส้ม" → "ซูมรูปขวด")
    import voicecmd
    vcmds = voicecmd.detect(segs, ai, list(SFX_DESC)) if opts.get("voice", 1) else []
    # ซูม: หาของ+จังหวะก่อนตัด dead air — สั่งล่วงหน้า ("ตอนกินน้ำ") เป็นช่วงเงียบ ต้องกันไม่ให้โดนตัด
    vspots = voicecmd.locate(vcmds, src, os.path.join(outdir, "_focus"), ai) if vcmds else {}
    nfix = 0
    for f in p1.get("fixes", []):
        i = f.get("i")
        if isinstance(i, int) and 0 <= i < len(segs) and f.get("text"):
            segs[i]["text"] = f["text"]; nfix += 1
    for c in vcmds:
        print(f"  คำสั่งเสียง {c['t1']:.1f} วิ: \"{c['said']}\" → {c['label']}", flush=True)
    import multiclip
    nre = multiclip.drop_retakes(segs)  # พูดประโยคเดิมซ้ำติดกัน = เก็บเทคสุดท้าย
    if nre:
        print(f"  เทคซ้ำ {nre} จุด → เก็บเทคสุดท้าย", flush=True)
    json.dump(data, open(seg_json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    style = cc.load_style(None)
    st = p1.get("style") or {}
    for k in ("font", "outline", "shadow_color", "speakers", "highlights"):
        if st.get(k):
            style[k] = st[k]
    if style["font"] not in ("Mali", "Kanit", "Itim"):
        style["font"] = "Mali"
    json.dump(style, open(os.path.join(outdir, "style.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"  แก้คำ {nfix} จุด · ฟอนต์ {style['font']} · เพลง {p1.get('music')}", flush=True)
    prog(30)

    # 3 ตัด dead air
    step(3, "ตัด dead air" if opts["cut"] else "เตรียมคลิป")
    # ไม่ใช้ "keep" ที่ AI เดาจากภาพนิ่ง 8 ช่อง — มันเดาช่วงยาวๆ ว่าต้องเก็บ แล้วช่วงนั้นไม่โดนตัดเงียบ
    # (เทสจริง: เงียบเหลือ 17.6 วิ vs 5.7 วิ ถ้าไม่ใช้) · ช่วงเงียบที่ต้องเก็บจริง → สั่งในแชทด้วย --keep
    extra = voicecmd.protect(vspots)
    if opts["cut"]:
        keep = cc.tighten_keep(src, cc.compute_keep(segs, 0.15, 0.6, extra=extra), protect=extra)
    else:
        keep = [(0.0, round(cc.probe_dur(src) * cc.FPS) / cc.FPS)]
    # ช่วงเงียบที่กำลังสาธิต (พิมพ์/แกะกล่อง/ทำให้ดู) → เก็บ / เร่ง ×2-4 / ข้าม แทนตัดทิ้ง (speedup.py)
    import speedup
    speeds1 = []
    if opts["cut"] and opts.get("demo", 1):
        keep, speeds, rep = speedup.plan(src, keep, segs, cc.probe_dur(src), os.path.join(outdir, "_speed"))
        for r in rep:
            print(f"  ช่วงสาธิต {r[0]} ที่ {r[1]:.0f} วิ ({r[2]:.1f} วิ)", flush=True)
        speeds1 = speedup.to_cut1(speeds, keep)
    print("  กำลังตัดคลิป (คลิปยาว/หลายคลิปใช้เวลาหลายนาที)…", flush=True); prog(45)
    if speeds1:  # cut1 = ความเร็วปกติทุกช่วง (เก็บไว้ให้ editor สลับเร่ง/ปกติ/ตัด) → cut = เร่งแล้ว
        cut1 = os.path.join(outdir, base + ".cut1.mp4")
        cc.cut_video(src, keep, cut1)
        print("  เร่งช่วงสาธิต…", flush=True); prog(52)
        speedup.build(cut1, speeds1, cut)
        json.dump([[round(s, 4), round(e, 4)] for s, e in keep], open(os.path.join(outdir, base + ".keep.json"), "w"))
    else:
        cc.cut_video(src, keep, cut)
    orig, kept = cc.probe_dur(src), cc.probe_dur(cut)
    print(f"  {orig:.0f} วิ → {kept:.0f} วิ (ตัดออก {orig - kept:.0f} วิ)", flush=True)
    E = edit_init.build(seg_json, cut, style, keep, opts["aspect"], cc.probe_wh(src))
    if p1.get("title"):  # ชื่องานตามเนื้อหา (หน้าแรก/คลังคลิป/ชื่อไฟล์ตอนโหลด)
        E["title"] = str(p1["title"]).strip()[:60]
    if speeds1:  # เวลาซับคิดจาก keep (= เวลาบน cut1) → เลื่อนตามช่วงที่เร่ง
        for it in E["items"]:
            it["start"] = round(speedup.out_time(it["start"], speeds1), 3)
            it["end"] = round(speedup.out_time(it["end"], speeds1), 3)
        E["speedups"] = speedup.items_for(speeds1)
    if clips:  # รอยต่อคลิป (เวลาหลังตัด) → เส้นบน timeline · รวมฉากฮา = ฟิ้ว+แฟลชตอนขึ้นฉากใหม่
        E["clips"] = [{"name": c["name"], "start": round(speedup.out_time(cc.remap(c["start"], keep), speeds1), 3)} for c in clips]
        if opts.get("kind") == "funny":
            for n, c in enumerate(E["clips"][1:], 1):
                t = c["start"]
                E["items"].append(edit_apply.fill({"id": f"a_sc{n}", "track": "sfx", "sfx": "whoosh_fast", "start": max(0, t - 0.12), "vol": 0.8}, E))
                E["items"].append(edit_apply.fill({"id": f"z_sc{n}", "track": "fx", "fx": "flash", "start": t, "end": t + 0.3, "amount": 0.55}, E))
    if not opts["subs"]:
        E["items"] = []
    if opts["music"] and p1.get("music") and ccfx.music_file(p1["music"]):
        E["music"] = {"src": p1["music"], "vol": ccfx.MUSIC_DEFAULT["vol"], "duck": True, "offset": 0}
    prog(60)

    # 4 แบบ Motion Explainer: AI กำกับฉาก (พื้นกระดาษ/หัวข้อ/ภาพพิกเซล/ตำแหน่งกล้อง) แทนการแปะเอฟเฟกต์
    if opts.get("mode") == "explainer":
        import explainer
        import face
        step(4, "AI กำกับฉาก + วาดไอคอนที่ยังไม่มี")
        if not E["items"]:  # explainer ใช้ซับเสมอ (ซับเต็มด้านล่าง + AI อ่านบทจากซับ)
            E["items"] = edit_init.build(seg_json, cut, style, keep, "9x16", cc.probe_wh(src))["items"]
        E["aspect"] = "9x16"
        E["face"] = face.find_face(cut)
        explainer.plan(E, outdir, opts["density"], opts["vibe"])
        step(5, "AI ดูภาพหาจุดที่ควรซูม (หน้าคนพูด / ของที่ยก / จุดที่ชี้)")
        explainer.add_focus(E, outdir)
        explainer.scene_sfx(E)
        prog(95)
        ccfx.save_edit(edit, E)
        print(f"  {len(E['scenes'])} ฉาก · หน้าคนพูด {'เจอ' if E['face'] else 'ไม่เจอ (กรอบจะโชว์ทั้งภาพ)'}", flush=True)
        n, tin, tout, usd = usage_summary(os.environ.get("CLIPCUT_JOB", ""))
        if n:
            print(f"  AI {n} ครั้ง · อ่าน {tin / 1000:.0f}k + เขียน {tout / 1000:.0f}k tokens (≈ ${usd:.2f} ถ้าคิดราคา API)", flush=True)
        prog(100)
        print("EDIT " + edit, flush=True)
        return

    # 4 AI รอบสอง: วางเอฟเฟกต์
    plan = []
    if any(opts.get(k) for k in ("sfx", "emoji", "broll", "gif", "fx")):
        step(4, "AI วางเอฟเฟกต์ตามบท")
        subs_for_ai = E["items"] or edit_init.build(seg_json, cut, style, keep, opts["aspect"], cc.probe_wh(src))["items"]
        import smartcam
        peaks = smartcam.voice_peaks(cut) if opts.get("fx") else []
        E["roles"] = roles(subs_for_ai, p1.get("chen"))
        plan = pass2(subs_for_ai, E["duration"], opts, opts["aspect"] == "9x16", peaks, E["roles"])
        json.dump(plan, open(os.path.join(outdir, "_ai_pass2.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    prog(85)

    # 5 ภาพพิกเซล + ตรวจของ AI แล้วเขียน edit.json
    step(5, "สร้างภาพประกอบพิกเซล + จัดลง timeline")
    ok, bad = 0, 0
    allowed = {k for k in ("sfx", "emoji", "broll", "fx") if opts.get(k)}
    # ไอคอนที่ AI อยากได้แต่ยังไม่มี → ให้ AI วาดพิกเซลเข้าคลังกลาง (ใช้ซ้ำคลิปหน้าได้)
    have = set(pixel.names()["icons"])
    wants = {}
    for it in plan:
        p = it.get("pixel") if it.get("track") == "broll" and isinstance(it.get("pixel"), dict) else {}
        nm = re.sub(r"[^a-z0-9_]", "_", str(p.get("icon") or "").lower()).strip("_")[:30]
        if nm and nm not in have:
            p["icon"] = nm
            if len(wants) < NEW_ICONS[opts["density"]]:
                wants[nm] = p.get("icon_desc") or nm
    if wants:
        import pixel_gen
        print(f"  วาดไอคอนใหม่ {len(wants)} ตัว: {', '.join(wants)}", flush=True)
        pixel_gen.ensure(wants)
    pxn = pixel.names()
    for it in plan:
        try:
            tr = it.get("track")
            if tr == "gif":  # place_gifs() ทำทีหลัง (ต้องเว้นช่องหยุดคลิป)
                continue
            if tr not in allowed or not isinstance(it.get("start"), (int, float)):
                raise ValueError(tr)
            if tr == "sfx" and it.get("sfx") not in SFX_DESC:
                raise ValueError(it.get("sfx"))
            if tr == "emoji":  # อีโมจิผสม (ZWJ/สีผิว) วาดแยกเป็นหลายตัว → เหลือตัวแรก
                it["emoji"] = re.split("[‍\U0001F3FB-\U0001F3FF]", str(it.get("emoji") or ""))[0] or "✨"
            if tr == "fx" and it.get("fx") not in ccfx.FX_TYPES:
                raise ValueError(it.get("fx"))
            if tr == "broll":
                spec = {k: v for k, v in (it.pop("pixel", None) or {}).items() if v and k in ("sprite", "icon", "brand")}
                # ตัวการ์ตูน = คนที่พูดตอนนั้น (เฉิน hoodie_ / แฟน girl_ / คนอื่น = ไม่มีตัว)
                sp = next((x.get("speaker") for x in E["items"] if x["track"] == "sub" and x["start"] <= it["start"] + 0.3 < x["end"] + 0.6), None)
                pre = CHAR.get(E.get("roles", {}).get(sp, "เฉิน"))
                pose = re.sub(r"^(hoodie|girl|tee|coat)_", "", str(spec.get("sprite") or ""))
                spec["sprite"] = pre + pose if pre and pose else None
                if spec.get("sprite") not in pxn["sprites"]:
                    spec.pop("sprite", None)
                if spec.get("icon") not in pxn["icons"]:
                    spec.pop("icon", None)
                if not spec:
                    raise ValueError("pixel ว่าง")
                try:
                    p = pixel.make(spec, os.path.join(outdir, "broll"))
                except Exception:  # ดึงโลโก้ไม่ได้ → เหลือแต่ตัวการ์ตูน/ไอคอน
                    spec.pop("brand", None)
                    if not spec:
                        raise
                    p = pixel.make(spec, os.path.join(outdir, "broll"))
                it["src"] = os.path.relpath(p, outdir).replace("\\", "/")
                it.setdefault("w", 0.6 if opts["aspect"] == "9x16" else 0.3)
            if it.get("end") is not None and it["end"] <= it["start"]:
                it.pop("end")
            pre = {"sub": "s", "broll": "b", "emoji": "e", "sfx": "a", "fx": "z"}[tr]
            n = 1
            while any(x["id"] == f"{pre}{n}" for x in E["items"]):
                n += 1
            E["items"].append(edit_apply.fill(dict(it, id=f"{pre}{n}"), E))
            ok += 1
        except Exception as ex:
            bad += 1
            print(f"  ข้าม {json.dumps(it, ensure_ascii=False)[:120]} ({ex})", flush=True)
    if opts.get("fx") or opts.get("cam"):  # ซูมอัจฉริยะ: กล้องตามหน้า + ซูมไปของที่ยก + ซูมช้ากันนิ่ง + จุดซูมของทุกเอฟเฟกต์
        import smartcam
        prog(90)
        cuts, acc = [], 0.0
        for s0, e0 in keep:
            acc += e0 - s0; cuts.append(round(speedup.out_time(acc, speeds1), 3))

        def new_id(tr):
            n = 1
            while any(x.get("id") == f"z{n}" for x in E["items"]):
                n += 1
            return f"z{n}"
        try:
            smartcam.run(E, outdir, opts, cuts[:-1], new_id)
            snap = smartcam.voice_peaks(cut)
            smartcam.snap_punches(E, snap)
            smartcam.refocus(E)
        except Exception as ex:
            print(f"  ! ซูมอัจฉริยะพัง ใช้ซูมกลางจอแทน: {ex}", flush=True)
    if vcmds:  # คำสั่งเสียง → เอฟเฟกต์ตอนพูดจบ (หลังกล้องตามหน้า — ตำแหน่งนิ้วต้องแปลงตามกล้อง)
        def vid(pre):
            n = 1
            while any(x.get("id") == f"{pre}{n}" for x in E["items"]):
                n += 1
            return f"{pre}{n}"
        try:
            voicecmd.apply(E, vcmds, outdir, src, lambda t: speedup.out_time(cc.remap(t, keep), speeds1), set(SFX_DESC), vid, ai, vspots)
        except Exception as ex:
            print(f"  ! ทำตามคำสั่งเสียงไม่ได้: {ex}", flush=True)
    if opts.get("gif"):
        try:
            place_gifs(E, plan, outdir, opts)
        except Exception as ex:
            print(f"  ! ใส่ GIF ไม่ได้: {ex}", flush=True)
    declutter(E)
    ccfx.save_edit(edit, E)
    cnt = {t: sum(1 for x in E["items"] if x["track"] == t) for t in ccfx.TRACKS}
    print(f"  ซับ {cnt['sub']} · ภาพ {cnt['broll']} · GIF {cnt['gif']} · อีโมจิ {cnt['emoji']} · เสียง {cnt['sfx']} · เอฟเฟกต์ {cnt['fx']}"
          + (f" (ข้าม {bad})" if bad else ""), flush=True)
    n, tin, tout, usd = usage_summary(os.environ.get("CLIPCUT_JOB", ""))
    if n:
        print(f"  AI {n} ครั้ง · อ่าน {tin / 1000:.0f}k + เขียน {tout / 1000:.0f}k tokens (≈ ${usd:.2f} ถ้าคิดราคา API)", flush=True)
    prog(100)
    print("EDIT " + edit, flush=True)


if __name__ == "__main__":
    main()
