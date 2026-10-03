#!/usr/bin/env python
"""ถอดเสียงไทยจากคลิป → segments JSON
engine:
  elevenlabs (default ถ้ามี ELEVENLABS_API_KEY) — แม่น+เร็ว + แยกคนพูด (diarize) → segment มี "speaker"
  whisper   (fallback) — faster-whisper CPU ช้า ไทยเพี้ยน ไม่มี speaker

usage: python transcribe.py <input> <out.json> [model_size] [initial_prompt]
env:   CLIPCUT_ENGINE=auto|elevenlabs|whisper   CLIPCUT_SPEAKERS=<n> (ถ้ารู้จำนวนคนพูด)
       FW_DEVICE=cuda|cpu   FW_COMPUTE=float16|int8|int8_float16
"""
import sys
import os
import json
import subprocess
import tempfile
import urllib.request
import urllib.error
import uuid

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

FF = os.environ.get("FFMPEG", "ffmpeg")
EL_URL = "https://api.elevenlabs.io/v1/speech-to-text"
EL_MODEL = "scribe_v2"


def el_key():
    k = os.environ.get("ELEVENLABS_API_KEY")
    if k:
        return k
    # setx แล้วแต่ session เปิดก่อน → อ่านจาก registry ตรง
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as h:
            return winreg.QueryValueEx(h, "ELEVENLABS_API_KEY")[0]
    except Exception:
        return None


# ---------- ElevenLabs ----------
def el_request(src, key, speakers):
    tmp = os.path.join(tempfile.mkdtemp(prefix="clipcut_"), "a.mp3")
    subprocess.run([FF, "-v", "error", "-y", "-i", src, "-vn", "-ac", "1", "-ar", "16000",
                    "-c:a", "libmp3lame", "-b:a", "64k", tmp], check=True)
    fields = {"model_id": EL_MODEL, "language_code": "tha", "diarize": "true",
              "timestamps_granularity": "word"}
    if speakers:
        fields["num_speakers"] = str(speakers)
    b = uuid.uuid4().hex
    body = b""
    for k, v in fields.items():
        body += f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
    body += (f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="a.mp3"\r\n'
             f"Content-Type: audio/mpeg\r\n\r\n").encode() + open(tmp, "rb").read() + f"\r\n--{b}--\r\n".encode()
    req = urllib.request.Request(EL_URL, data=body, method="POST", headers={
        "xi-api-key": key, "Content-Type": f"multipart/form-data; boundary={b}"})
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"ElevenLabs HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}")


def el_phrases(words, gap=0.45, min_chars=8):
    """คำไทยจาก EL มาเป็นรายตัวอักษร → รวมเป็นวลี
    ตัดวลีที่: ช่องว่าง (ถ้าวลียาวพอ), เปลี่ยนคนพูด, เงียบ > gap"""
    segs, cur = [], None

    def flush():
        if cur and cur["text"].strip():
            cur["text"] = cur["text"].strip()
            segs.append(cur)

    for w in words:
        if w.get("type") == "spacing":
            if cur and len(cur["text"].strip()) >= min_chars:
                flush(); cur = None
            elif cur:
                cur["text"] += " "
            continue
        if w.get("type") != "word":
            continue  # audio_event เช่น (หัวเราะ)
        sp = w.get("speaker_id") or "speaker_0"
        if cur and (sp != cur["speaker"] or w["start"] - cur["end"] > gap):
            flush(); cur = None
        if cur is None:
            cur = {"start": w["start"], "end": w["end"], "text": "", "speaker": sp, "words": []}
        cur["text"] += w["text"]
        cur["end"] = w["end"]
    flush()
    for s in segs:
        s["start"], s["end"] = round(s["start"], 3), round(s["end"], 3)
    return segs


def run_elevenlabs(src, out, key):
    sp = os.environ.get("CLIPCUT_SPEAKERS")
    print(f"[engine=elevenlabs model={EL_MODEL} diarize speakers={sp or 'auto'}]", flush=True)
    d = el_request(src, key, sp)
    segs = el_phrases(d.get("words", []))
    for s in segs:
        print(f"{s['start']:7.2f} {s['speaker']}: {s['text']}", flush=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"engine": "elevenlabs", "language": d.get("language_code"),
                   "speakers": sorted({s["speaker"] for s in segs}),
                   "segments": segs}, f, ensure_ascii=False, indent=1)
    print(f"\n✓ {len(segs)} segments → {out}")


# ---------- faster-whisper (fallback) ----------
def run_whisper(src, out, model_size, prompt):
    device = os.environ.get("FW_DEVICE", "cpu")
    compute = os.environ.get("FW_COMPUTE", "float16" if device == "cuda" else "int8")

    from faster_whisper import WhisperModel
    print(f"[engine=whisper device={device} compute={compute} model={model_size}]", flush=True)
    model = WhisperModel(model_size, device=device, compute_type=compute)

    segments, info = model.transcribe(
        src,
        language="th",
        word_timestamps=True,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=400),
        beam_size=5,
        initial_prompt=prompt,
        condition_on_previous_text=True,
    )

    dur = info.duration or 1
    print(f"duration {dur:.0f}s — start...", flush=True)
    data = []
    for seg in segments:
        words = [{"start": round(w.start, 3), "end": round(w.end, 3), "word": w.word}
                 for w in (seg.words or [])]
        text = seg.text.strip()
        if not text:
            continue
        data.append({"start": round(seg.start, 3), "end": round(seg.end, 3),
                     "text": text, "words": words})
        pct = min(100.0, seg.end / dur * 100)
        filled = int(pct // 5)
        bar = "#" * filled + "-" * (20 - filled)
        print(f"[{bar}] {pct:5.1f}%  {text}", flush=True)

    with open(out, "w", encoding="utf-8") as f:
        json.dump({"engine": "whisper", "language": info.language,
                   "duration": round(info.duration, 2), "segments": data},
                  f, ensure_ascii=False, indent=1)
    print(f"\n✓ {len(data)} segments → {out}")


def main():
    if len(sys.argv) < 3:
        print("usage: transcribe.py <input> <out.json> [model_size] [initial_prompt]")
        sys.exit(1)
    src = sys.argv[1]
    out = sys.argv[2]
    model_size = sys.argv[3] if len(sys.argv) > 3 else "medium"
    prompt = sys.argv[4] if len(sys.argv) > 4 else None

    engine = os.environ.get("CLIPCUT_ENGINE", "auto")
    key = el_key() if engine in ("auto", "elevenlabs") else None
    if key:
        try:
            return run_elevenlabs(src, out, key)
        except Exception as e:
            if engine == "elevenlabs":
                raise
            print(f"!! ElevenLabs ล้ม ({e}) → ใช้ whisper แทน", flush=True)
    elif engine == "elevenlabs":
        sys.exit("!! ไม่มี ELEVENLABS_API_KEY")
    run_whisper(src, out, model_size, prompt)


if __name__ == "__main__":
    main()
