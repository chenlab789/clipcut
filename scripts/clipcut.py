#!/usr/bin/env python
"""clipcut — AI auto-edit คลิป ChenLab
ตัด dead air + ซับไทยไวรัล (สี/ฟอนต์ตามธีมคลิป แยกสีคนพูด) + export 16:9 / 9:16

pipeline:
  1. transcribe.py  → segments.json (ElevenLabs+diarize → มี speaker / fallback whisper)
  2. keep-intervals (ตัดช่วงเงียบ + --keep ช่วงที่ต้องเก็บแม้ไม่มีเสียงพูด) + remap timestamps
  3. ตัดวิดีโอด้วย ffmpeg select filter
  4. สร้าง ASS — เด้งทีละวลี, สีตาม speaker, ไฮไลต์คำ (ตาม --style)
  5. render ด้วย filter ass + shaping=complex (วรรณยุกต์ไทยไม่ซ้อน)
     คลิปแนวนอน → 16:9 + 9:16 (blur bg) · คลิปแนวตั้ง → 9:16 อย่างเดียว

usage:
  python clipcut.py <input> [--out DIR] [--style style.json] [--keep "44.8-47.5,1:02-1:05"]
                     [--model medium] [--min-silence 0.6] [--pad 0.15]
                     [--only-16x9 | --only-9x16] [--skip-transcribe | --transcribe-only]
"""
import sys
import os
import re
import json
import subprocess
import argparse

import ccfx  # noqa: E402,F401  (ซ่อนหน้าต่างดำของ subprocess บน Windows)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(os.path.dirname(HERE), "fonts")
FF = os.environ.get("FFMPEG", "ffmpeg")
FFPROBE = os.environ.get("FFPROBE", "ffprobe")
BG = "#060606"
FPS = 30

# คำเทคที่ไฮไลต์ทองเป็น default (คลิป ChenLab สายสอน) — style "highlights" ทับได้
KEYWORDS = ["Chrome Remote Desktop", "Claude Code", "Remote Desktop",
            "Remote Control", "Search YouTube", "private network",
            "use case", "session", "Tailscale", "Termius", "Terminal",
            "GitHub", "iPhone", "Chrome", "Claude", "VPN", "SSH"]

# style default — Claude ควรส่ง --style ตามธีมคลิปทุกครั้ง (ดู SKILL.md)
DEFAULT_STYLE = {
    "font": "Mali",                 # ชื่อ family — ไฟล์อยู่ใน clipcut/fonts/ หรือในระบบ
    "size": 130,                    # px ที่ความกว้าง 1080 (9:16) — 16:9 ใช้ x0.62
    "fill": "#FFFFFF",              # สีคนพูดที่ไม่ได้กำหนดใน speakers
    "speakers": {},                 # {"speaker_1": "#9AD8FF"} — ว่าง+หลายคน = ใช้ PALETTE
    "outline": "#000000",
    "outline_w": 11,
    "shadow": 7,
    "shadow_color": "#000000",
    "highlights": {k: "#FFD700" for k in KEYWORDS},
    "margin_v": 330,                # ระยะจากขอบล่าง (9:16)
}
PALETTE = ["#FFFFFF", "#FFE066", "#9AD8FF", "#FF9AC8"]
POP = r"{\fad(80,60)\fscx70\fscy70\t(0,120,\fscx112\fscy112)\t(120,220,\fscx100\fscy100)}"


def ass_col(hexrgb, alpha=0):
    """#RRGGBB → &HAABBGGRR (Style)"""
    h = hexrgb.lstrip("#")
    return f"&H{alpha:02X}{h[4:6]}{h[2:4]}{h[0:2]}".upper()


def ass_tag(hexrgb):
    """#RRGGBB → {\\c&HBBGGRR&} (inline override — ต้อง 6 หลัก)"""
    h = hexrgb.lstrip("#")
    return "{\\c&H" + f"{h[4:6]}{h[2:4]}{h[0:2]}".upper() + "&}"


def highlight_kw(text, highlights, base):
    if not highlights:
        return text
    words = sorted(highlights, key=len, reverse=True)
    pat = re.compile("|".join(re.escape(k) for k in words), re.IGNORECASE)

    def sub(m):
        col = next(v for k, v in highlights.items() if k.lower() == m.group(0).lower())
        return ass_tag(col) + m.group(0) + ass_tag(base)
    return pat.sub(sub, text)


def run(cmd, **kw):
    print("›", " ".join(str(c) for c in cmd[:6]), "…")
    subprocess.run(cmd, check=True, **kw)


def probe_dur(path):
    out = subprocess.check_output(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", path], text=True)
    return float(out.strip())


def probe_wh(path):
    out = subprocess.check_output(
        [FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height:stream_side_data=rotation", "-of", "json", path], text=True)
    s = json.loads(out)["streams"][0]
    w, h = s["width"], s["height"]
    rot = next((abs(int(d.get("rotation", 0))) for d in s.get("side_data_list", []) if "rotation" in d), 0)
    return (h, w) if rot in (90, 270) else (w, h)


def parse_keep(spec):
    """'44.8-47.5,1:02-1:05' → [(44.8,47.5),(62,65)]"""
    def sec(t):
        p = [float(x) for x in t.strip().split(":")]
        v = 0.0
        for x in p:
            v = v * 60 + x
        return v
    out = []
    for part in (spec or "").split(","):
        if part.strip():
            a, b = part.split("-")
            out.append((sec(a), sec(b)))
    return out


# ---------- 1. keep intervals + remap ----------
def compute_keep(segments, pad, min_silence, min_keep=0.25, extra=None):
    """รวม segments ที่พูด (+ extra ช่วงบังคับเก็บ) → keep intervals, ตัด gap เงียบ > min_silence"""
    spans = []
    for s in segments:
        if not s["text"].strip():
            continue
        spans.append([max(0.0, s["start"] - pad), s["end"] + pad])
    spans += [[a, b] for a, b in (extra or [])]
    spans.sort()
    merged = []
    for st, en in spans:
        if merged and st - merged[-1][1] < min_silence:
            merged[-1][1] = max(merged[-1][1], en)
        else:
            merged.append([st, en])
    # ปัดขอบให้ตรงเฟรม 30fps — ไม่งั้นภาพ (ตัดทีละเฟรม) กับเสียง (ตัดตามเวลาจริง) คลาดสะสมทุกรอยตัด → ปากไม่ตรงเสียงท้ายคลิป
    snap = lambda t: round(t * FPS) / FPS  # noqa: E731
    return [(snap(s), snap(e)) for s, e in merged if snap(e) - snap(s) >= min_keep]


def tighten_keep(src, keep, protect=None, min_gap=0.3, hold=0.08, min_island=0.12):
    """ตัด dead air รอบสองด้วย "ความดังเสียงจริง" (ทุก 10ms) — ตัดตามบทอย่างเดียวรอดเยอะ:
    เงียบ < min_silence ระหว่างประโยค + pad หัวท้าย + เว้นจังหวะกลางประโยค + เวลาท้ายคำของ EL ลากทับช่วงหายใจ
    ช่วงเงียบ >= min_gap → เหลือหายใจ hold วิ ต่อฝั่ง · ระดับเงียบปรับตามเสียงพื้นของคลิปนั้น
    protect = ช่วงที่ห้ามแตะ (--keep ช่วงโชว์ของเงียบๆ)"""
    import numpy as np
    raw = subprocess.run([FF, "-v", "error", "-i", src, "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    x = np.frombuffer(raw, "<i2").astype(np.float32) / 32768
    hop = 160  # 10ms
    n = len(x) // hop
    if n < 10:
        return keep
    db = 20 * np.log10(np.sqrt((x[: n * hop].reshape(n, hop) ** 2).mean(1)) + 1e-6)
    # ไม่นับเงียบสนิท (-120 dB จาก noise gate/ไมค์ตัด) ไม่งั้นพื้นต่ำเกิน เกณฑ์เงียบหลุดไปที่ -90 dB ไม่เจออะไรเลย
    live = db[db > -90]
    speech = np.percentile(live, 95) if len(live) else -20
    noise = np.percentile(live, 15) if len(live) else -60
    thr = min(speech - 22, max(speech - 30, noise + 0.35 * (speech - noise)))
    quiet = db < thr
    out = []
    for s, e in keep:
        a, b = int(s * 100), min(n, int(e * 100))
        cuts, i = [], a
        while i < b:
            if quiet[i]:
                j = i
                while j < b and quiet[j]:
                    j += 1
                gs, ge = i / 100, j / 100
                inside = any(ps < ge and pe > gs for ps, pe in (protect or []))
                if ge - gs >= min_gap and not inside:
                    lo = gs if i == a else gs + hold  # เงียบหัวช่วง = ตัดจากขอบช่วงเลย เหลือแค่ hold ก่อนคำแรก
                    hi = ge if j >= b else ge - hold  # เงียบท้ายช่วง = ตัดถึงขอบช่วงเลย เหลือแค่ hold หลังคำสุดท้าย
                    if hi > lo:
                        cuts.append((lo, hi))
                i = j
            else:
                i += 1
        cur = s
        for lo, hi in cuts:
            if lo - cur >= min_island:
                out.append((cur, lo))
            cur = hi
        if e - cur >= min_island:
            out.append((cur, e))
    snap = lambda t: round(t * FPS) / FPS  # noqa: E731
    return [(snap(s), snap(e)) for s, e in out if snap(e) > snap(s)]


def remap(t, keep):
    """เวลาเก่า → เวลาใหม่ (หลังตัด dead air)"""
    acc = 0.0
    for s, e in keep:
        if t < s:
            return acc
        if t <= e:
            return acc + (t - s)
        acc += e - s
    return acc


# ---------- 2. ตัดวิดีโอ ----------
def sum_tree(terms):
    """a+b+c+… แบบต้นไม้สมดุล — ffmpeg parse บวกยาวเป็นเส้นตรงเกิน ~100 ตัวแล้วพัง (Cannot allocate memory)"""
    if len(terms) == 1:
        return terms[0]
    m = len(terms) // 2
    return f"({sum_tree(terms[:m])}+{sum_tree(terms[m:])})"


def cut_video(src, keep, out):
    """ตัด dead air — ภาพ select ทีละเฟรม, เสียง atrim+concat ระดับ sample (aselect ตัดเป็นก้อน ~21ms → คลาดสะสม)
    ขอบ keep อยู่บนกริดเฟรมแล้ว (compute_keep) → ภาพ (e-s)*30 เฟรม = เสียง (e-s) วิ เป๊ะทุกช่วง ปากตรงเสียงถึงท้ายคลิป
    รอยต่อเสียง fade 6ms กันเสียง "ปึ๊ก" ตรงรอยตัด"""
    import tempfile
    h = 0.5 / FPS  # ภาพเลื่อนครึ่งเฟรม = ได้เฟรมช่วง [s, e) พอดี
    vexpr = sum_tree([f"between(t,{s - h:.4f},{e - h:.4f})" for s, e in keep])
    # fps=30 ก่อน select: คลิปอัดจอ iPhone เป็น VFR (r_frame_rate โกหก) → N/FRAME_RATE ยืดภาพ ไม่ตรงเสียง
    g = [f"[0:v]fps={FPS},select='{vexpr}',setpts=N/{FPS}/TB[v]", "[0:a]asplit=" + str(len(keep)) + "".join(f"[i{i}]" for i in range(len(keep)))]
    for i, (s, e) in enumerate(keep):
        f = min(0.006, (e - s) / 4)
        g.append(f"[i{i}]atrim={s:.6f}:{e:.6f},asetpts=PTS-STARTPTS,"
                 f"afade=t=in:d={f:.4f},afade=t=out:st={e - s - f:.4f}:d={f:.4f}[a{i}]")
    g.append("".join(f"[a{i}]" for i in range(len(keep))) + f"concat=n={len(keep)}:v=0:a=1[a]")
    if out.endswith(".cut.mp4"):
        json.dump([[round(s, 4), round(e, 4)] for s, e in keep], open(out[:-8] + ".keep.json", "w"))
    gf = os.path.join(tempfile.gettempdir(), "clipcut_cut_graph.txt")
    open(gf, "w", encoding="utf-8").write(";\n".join(g))
    run([FF, "-y", "-i", src, "-/filter_complex", gf, "-map", "[v]", "-map", "[a]", "-r", str(FPS),
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
         "-c:a", "aac", "-b:a", "192k", out],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ---------- 3. ASS subtitle ----------
def fmt_t(t):
    h = int(t // 3600); m = int((t % 3600) // 60)
    s = t % 60
    return f"{h:d}:{m:02d}:{s:05.2f}"


def phrase_chunks(segments, keep, max_words=6):
    """แตก segment เป็นวลีสั้น ๆ ตาม word timestamps + remap เวลา → (st, en, text, speaker)"""
    chunks = []
    for seg in merge_midword(segments):
        sp = seg.get("speaker")
        words = seg.get("words") or []
        if not words:
            st = remap(seg["start"], keep); en = remap(seg["end"], keep)
            if en > st and seg["text"].strip():
                chunks.append((st, en, seg["text"], sp))
            continue
        buf = []
        for w in words:
            buf.append(w)
            if len(buf) >= max_words or w["word"].strip().endswith((".", "!", "?", "ๆ")):
                st = remap(buf[0]["start"], keep); en = remap(buf[-1]["end"], keep)
                txt = "".join(x["word"] for x in buf).strip()
                if en > st and txt:
                    chunks.append((st, en, txt, sp))
                buf = []
        if buf:
            st = remap(buf[0]["start"], keep); en = remap(buf[-1]["end"], keep)
            txt = "".join(x["word"] for x in buf).strip()
            if en > st and txt:
                chunks.append((st, en, txt, sp))
    return chunks


_MARKS = re.compile("[ัิ-ฺ็-๎]")


def text_w(t):
    """ความกว้างโดยประมาณ (หน่วย = ตัวไทย 1 ตัว) — สระบน/ล่าง+วรรณยุกต์ไม่กินที่, ละติน ~1.6"""
    t = _MARKS.sub("", t)
    return sum(1.6 if c.isascii() and c.isalpha() else 1 for c in t)


# คำพูดกันเองที่พจนานุกรม pythainlp ไม่มี → ไม่ใส่ = โดนหั่นกลางคำ ("แม่ | ง", "แม่ | งอ | ยู่")
SLANG = ["แม่ง", "เหี้ย", "เชี่ย", "สัส", "ไอสัส", "ไอ้สัส", "ไอสัตว์", "เว้ย", "ว่ะ", "ป่ะ", "ปะ", "มั้ง",
         "เนี่ย", "เงี้ย", "อย่างเงี้ย", "งี้", "อย่างงี้", "ยังไง", "ไง", "โคตร", "เจ๋ง", "ปึ๊บ", "อ่ะ", "อะ",
         "กู", "มึง", "พวกมึง", "เวิร์ค", "เวิร์ก", "โอเค", "ชิล", "แป๊บ", "เดี๋ยว", "ตะกี้", "เมื่อกี้"]
_TOK = None


def thai_tok():
    """ตัวตัดคำไทย (newmm + คำแสลง) — ไม่มี pythainlp = ตัดได้แค่ที่ช่องว่าง"""
    global _TOK
    if _TOK is None:
        try:
            from pythainlp.tokenize import word_tokenize
            from pythainlp.corpus.common import thai_words
            from pythainlp.util import dict_trie
            trie = dict_trie(set(thai_words()) | set(SLANG))
            _TOK = lambda t: word_tokenize(t, custom_dict=trie, engine="newmm", keep_whitespace=True)  # noqa: E731
        except ImportError:
            _TOK = lambda t: re.split(r"(\s+)", t)  # noqa: E731
    return _TOK


def merge_midword(segments, max_gap=1.5):
    """ElevenLabs ตัด segment กลางคำได้ ("เห" | "มือนกับ", "โ" | "อเค") → ต่อกลับถ้าตัดคำแล้วมีคำคร่อมรอยต่อ"""
    tok = thai_tok()
    out = []
    for s in segments:
        p = out[-1] if out else None
        if (p and s["start"] - p["end"] <= max_gap and p.get("speaker") == s.get("speaker")
                and p["text"] and s["text"] and not p["text"][-1].isspace() and not s["text"][0].isspace()
                and "฀" <= p["text"][-1] <= "๿" and "฀" <= s["text"][0] <= "๿"):
            joined, cut, pos = p["text"] + s["text"], len(p["text"]), 0
            for w in tok(joined):
                if pos < cut < pos + len(w):  # มีคำคร่อมรอยต่อ = ตัดกลางคำ
                    out[-1] = dict(p, text=joined, end=s["end"], words=(p.get("words") or []) + (s.get("words") or []))
                    break
                pos += len(w)
            else:
                out.append(s)
            continue
        out.append(s)
    return out


def split_long(chunks, maxw):
    """ไทยไม่มีเว้นวรรค libass ตัดบรรทัดไม่ได้ → ท่อนยาวเกินจอแตกเป็นหลายท่อนต่อกัน (ตัดตามคำ)"""
    tok = thai_tok()
    out = []
    for st, en, txt, sp in chunks:
        tw = text_w(txt)
        if tw <= maxw:
            out.append((st, en, txt, sp)); continue
        n = int(-(-tw // maxw))
        target, parts, cur = tw / n, [], ""
        for w in tok(txt):
            if cur.strip() and text_w(cur + w) > target * 1.15 and len(parts) < n - 1:
                parts.append(cur.strip()); cur = w.lstrip()
            else:
                cur += w
        if cur.strip():
            parts.append(cur.strip())
        tot = sum(text_w(x) for x in parts) or 1
        t = st
        for x in parts:
            d = (en - st) * text_w(x) / tot
            out.append((t, t + d, x, sp)); t += d
    return out


def speaker_colors(style, chunks):
    cols = dict(style["speakers"])
    found = sorted({c[3] for c in chunks if c[3]})
    if not cols and len(found) > 1:  # ไม่ได้กำหนด แต่มีหลายคน → แจกสี default
        cols = {sp: PALETTE[i % len(PALETTE)] for i, sp in enumerate(found)}
    return cols


def build_ass(chunks, style, w, h, out):
    scale = 1.0 if w <= h else 0.62
    size = round(style["size"] * scale)
    ow = max(2, round(style["outline_w"] * scale))
    sh = max(0, round(style["shadow"] * scale))
    mv = style["margin_v"] if w <= h else max(50, round(style["margin_v"] * 0.2))
    chunks = split_long(chunks, int((w - 160) / (0.34 * size)))
    cols = speaker_colors(style, chunks)
    styles = {"Default": style["fill"], **cols}
    sline = []
    for name, col in styles.items():
        sline.append(
            f"Style: {name},{style['font']},{size},{ass_col(col)},{ass_col(col)},"
            f"{ass_col(style['outline'])},{ass_col(style['shadow_color'], 0x70)},"
            f"1,0,0,0,100,100,0,0,1,{ow},{sh},2,60,60,{mv},1")  # Spacing=0 เสมอ — ≠0 ทำวรรณยุกต์หลุด
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
{chr(10).join(sline)}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    for st, en, txt, sp in chunks:
        name = sp if sp in cols else "Default"
        txt = highlight_kw(txt.replace("\n", " ").strip(), style["highlights"], styles[name])
        lines.append(f"Dialogue: 0,{fmt_t(st)},{fmt_t(en)},{name},,0,0,0,,{POP}{txt}")
    with open(out, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(lines) + "\n")
    return cols


def esc(p):
    """escape path สำหรับ filter บน Windows"""
    return p.replace("\\", "/").replace(":", "\\:")


def ass_filter(ass):
    # filter ass (ไม่ใช่ subtitles) เพราะต้อง shaping=complex — ไม่งั้นวรรณยุกต์ไทยซ้อน/หาย
    return f"ass='{esc(ass)}':fontsdir='{esc(FONTS)}':shaping=complex"


# ---------- 4. render ----------
def render_16x9(cut, ass, out):
    run([FF, "-y", "-i", cut, "-vf", ass_filter(ass),
         "-c:v", "libx264", "-preset", "medium", "-crf", "19",
         "-c:a", "copy", out],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def render_9x16(cut, ass, out, vertical):
    if vertical:  # ต้นฉบับแนวตั้งอยู่แล้ว → fit 1080x1920 ตรงๆ
        fc = (f"[0:v]scale=1080:1920:force_original_aspect_ratio=decrease,"
              f"pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color={BG},setsar=1,{ass_filter(ass)}[final]")
    else:  # 16:9 → พื้นหลัง = คลิป zoom เต็ม+เบลอ, หน้า = คลิปชัดวางกลาง
        fc = (f"[0:v]split=2[bg][fg];"
              f"[bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=26:2[bgb];"
              f"[fg]scale=1080:-2[fgs];"
              f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2[base];"
              f"[base]{ass_filter(ass)}[final]")
    run([FF, "-y", "-i", cut, "-filter_complex", fc, "-map", "[final]", "-map", "0:a",
         "-c:v", "libx264", "-preset", "medium", "-crf", "19",
         "-c:a", "copy", out],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def load_style(path):
    st = dict(DEFAULT_STYLE)
    if path:
        st.update(json.load(open(path, encoding="utf-8-sig")))
    return st


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("--out", default=None, help="โฟลเดอร์ output")
    ap.add_argument("--style", default=None, help="style.json — ฟอนต์/สี/สีต่อคนพูด/ไฮไลต์")
    ap.add_argument("--keep", default=None,
                    help="ช่วงที่ต้องเก็บแม้ไม่มีเสียงพูด (เวลาคลิปต้นฉบับ) เช่น '44.8-47.5,1:02-1:05'")
    ap.add_argument("--model", default="medium", help="whisper model (ใช้เมื่อไม่มี ElevenLabs)")
    ap.add_argument("--min-silence", type=float, default=0.6)
    ap.add_argument("--pad", type=float, default=0.15)
    ap.add_argument("--loose", action="store_true", help="ไม่ตัดเงียบรอบสอง (ตัดตามบทอย่างเดียว แบบ v2)")
    ap.add_argument("--only-16x9", action="store_true")
    ap.add_argument("--only-9x16", action="store_true")
    ap.add_argument("--skip-transcribe", action="store_true",
                    help="ใช้ segments.json เดิม (ข้ามถอดเสียงซ้ำ)")
    ap.add_argument("--transcribe-only", action="store_true",
                    help="ถอดเสียงแล้วหยุด — ให้ตรวจ/แก้ segments.json + ทำ style ก่อน render")
    ap.add_argument("--edit", action="store_true",
                    help="ตัด dead air แล้วสร้าง <ชื่อ>.edit.json (ไม่ render) — ใส่ SFX/อีโมจิ/ภาพ/ซูม ใน editor แล้ว render_edit.py")
    args = ap.parse_args()

    src = os.path.abspath(args.input)
    base = os.path.splitext(os.path.basename(src))[0]
    outdir = os.path.abspath(args.out) if args.out else os.path.join(os.path.dirname(src), "clipcut_out")
    os.makedirs(outdir, exist_ok=True)
    seg_json = os.path.join(outdir, f"{base}.segments.json")

    # 1. transcribe
    if not (args.skip_transcribe and os.path.exists(seg_json)):
        run([sys.executable, os.path.join(HERE, "transcribe.py"), src, seg_json, args.model])
    data = json.load(open(seg_json, encoding="utf-8-sig"))
    segments = data["segments"]
    if not segments:
        print("!! ไม่พบเสียงพูด — หยุด"); sys.exit(2)
    if args.transcribe_only:
        print(f"\n✓ transcript → {seg_json} (speakers: {data.get('speakers', '-')})"); return

    # 2. keep intervals
    extra = parse_keep(args.keep)
    keep = compute_keep(segments, args.pad, args.min_silence, extra=extra)
    if not args.loose:  # รอบสอง: ตัดเงียบด้วยความดังเสียงจริง (ตัดตามบทอย่างเดียวรอดเงียบ ~13% ของคลิป)
        keep = tighten_keep(src, keep, protect=extra)
    orig = probe_dur(src)
    kept = sum(e - s for s, e in keep)
    print(f"\n⏱  เดิม {orig:.1f}s → ตัดเหลือ {kept:.1f}s "
          f"(ตัดออก {orig-kept:.1f}s / {100*(orig-kept)/orig:.0f}%) | {len(keep)} ช่วง"
          + (f" | บังคับเก็บ {len(extra)} ช่วง" if extra else ""))

    # 3. cut
    cut = os.path.join(outdir, f"{base}.cut.mp4")
    cut_video(src, keep, cut)

    # 4a. โหมด editor → เขียน edit.json แล้วจบ (render ทีหลังด้วย render_edit.py)
    if args.edit:
        import edit_init
        import ccfx
        ed = os.path.join(outdir, f"{base}.edit.json")
        aspect = "16x9" if args.only_16x9 else "9x16"
        ccfx.save_edit(ed, edit_init.build(seg_json, cut, load_style(args.style), keep, aspect, probe_wh(src)))
        server = os.path.join(HERE, "editor", "server.py")
        print(f'\n✓ edit → {ed}\n  เปิด editor: python "{server}" "{ed}"')
        return

    # 4. captions + render
    style = load_style(args.style)
    chunks = phrase_chunks(segments, keep)
    w, h = probe_wh(src)
    vertical = h > w
    do16 = not args.only_9x16 and not vertical
    do9 = not args.only_16x9 or vertical
    if vertical and not args.only_9x16:
        print("↕  คลิปแนวตั้ง → export 9:16 อย่างเดียว")

    if do16:
        ass16 = os.path.join(outdir, f"{base}.16x9.ass")
        build_ass(chunks, style, 1920, 1080, ass16)
        out16 = os.path.join(outdir, f"{base}_16x9.mp4")
        render_16x9(cut, ass16, out16)
        print(f"✓ 16:9 → {out16}")

    if do9:
        ass9 = os.path.join(outdir, f"{base}.9x16.ass")
        cols = build_ass(chunks, style, 1080, 1920, ass9)
        if cols:
            print("🎨 สีคนพูด:", ", ".join(f"{k}={v}" for k, v in cols.items()))
        out9 = os.path.join(outdir, f"{base}_9x16.mp4")
        render_9x16(cut, ass9, out9, vertical)
        print(f"✓ 9:16 → {out9}")

    print("\n🦞 clipcut เสร็จ —", outdir)


if __name__ == "__main__":
    main()
