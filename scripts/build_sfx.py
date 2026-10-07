#!/usr/bin/env python
"""สร้างคลัง SFX ของ clipcut → assets/sfx/*.wav (48k stereo)

- สังเคราะห์เอง (numpy) : whoosh / boom / riser / ding / … — ของเราเอง ไม่ติดลิขสิทธิ์
- คัดจาก Kenney (CC0)   : punch / glass / click / error / glitch / …
  ใส่ path โฟลเดอร์ที่แตก zip Kenney ไว้เป็น argument (impact/interface/digital-audio)

usage: python build_sfx.py [KENNEY_DIR]
"""
import os
import sys
import glob
import wave
import subprocess
import numpy as np

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "assets", "sfx")
FF = os.environ.get("FFMPEG", "ffmpeg")
SR = 48000
rng = np.random.default_rng(7)


def save(name, x):
    x = np.asarray(x, dtype=np.float64)
    if x.ndim == 1:
        x = np.stack([x, x], 1)
    x = x / (np.abs(x).max() + 1e-9) * 0.89
    with wave.open(os.path.join(OUT, name + ".wav"), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((x * 32767).astype("<i2").tobytes())
    print("  +", name)


def t_(d):
    return np.arange(int(SR * d)) / SR


def lowpass_sweep(noise, f0, f1):
    """one-pole lowpass ที่ cutoff กวาดจาก f0→f1 (ทำเสียงลมวูบ)"""
    fc = np.geomspace(f0, f1, len(noise))
    a = np.exp(-2 * np.pi * fc / SR)
    y = np.zeros_like(noise); acc = 0.0
    for i, v in enumerate(noise):
        acc = a[i] * acc + (1 - a[i]) * v
        y[i] = acc
    return y


def env(n, att, rel_pow=2.0):
    k = np.linspace(0, 1, n)
    a = np.clip(k / max(att, 1e-4), 0, 1)
    return a * (1 - k) ** rel_pow


def whoosh(d, f0, f1, att=0.45):
    n = int(SR * d)
    l = lowpass_sweep(rng.standard_normal(n), f0, f1)
    r = lowpass_sweep(rng.standard_normal(n), f0, f1)
    e = np.sin(np.pi * np.clip(np.linspace(0, 1, n) / (2 * att), 0, 0.5)) * (1 - np.linspace(0, 1, n)) ** 1.5
    pan = np.linspace(-0.6, 0.6, n)  # วิ่งซ้าย→ขวา
    return np.stack([l * e * (1 - pan), r * e * (1 + pan)], 1)


def synth():
    save("whoosh", whoosh(0.55, 300, 4500))
    save("whoosh_fast", whoosh(0.28, 600, 7000, 0.6))
    save("swoosh_down", whoosh(0.6, 5000, 250, 0.2))
    # boom: sine ดิ่งเสียง + noise ต้นเสียง + saturation (แนว vine boom)
    t = t_(1.6)
    f = 75 * np.exp(-t * 1.4) + 38
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 2.2)
    click = rng.standard_normal(len(t)) * np.exp(-t * 60) * 0.5
    save("boom", np.tanh((body + click) * 3.0))
    t = t_(2.2)
    f = 55 * np.exp(-t * 0.8) + 30
    save("bass_drop", np.tanh(np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 1.2) * 2))
    # riser: noise สูงขึ้น + saw ไล่ pitch (บิ้วก่อนพีค)
    t = t_(2.0)
    nz = lowpass_sweep(rng.standard_normal(len(t)), 200, 9000)
    f = np.geomspace(180, 1400, len(t))
    tone = np.sin(2 * np.pi * np.cumsum(f) / SR) * 0.35
    save("riser", (nz + tone) * (t / t[-1]) ** 2)
    # ding: ระฆังใส (harmonics ไม่ลงตัว)
    t = t_(1.4)
    x = sum(a * np.sin(2 * np.pi * 1320 * m * t) * np.exp(-t * dk)
            for a, m, dk in [(1, 1, 3), (0.5, 2.76, 5), (0.3, 5.4, 8), (0.2, 8.9, 12)])
    save("ding", x * np.clip(t / 0.003, 0, 1))
    # pop: ฟองแตก
    t = t_(0.12)
    f = np.geomspace(900, 300, len(t))
    save("pop", np.sin(2 * np.pi * np.cumsum(f) / SR) * env(len(t), 0.02, 3))
    # boing: สปริง
    t = t_(0.7)
    f = 220 + 160 * np.sin(2 * np.pi * 9 * t) * np.exp(-t * 4)
    save("boing", np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 4.5))
    # tada-ish: arpeggio ขึ้น
    notes = [523, 659, 784, 1047]
    seg = []
    for i, fr in enumerate(notes):
        d = 0.09 if i < 3 else 0.6
        tt = t_(d)
        seg.append((np.sin(2 * np.pi * fr * tt) + 0.3 * np.sin(4 * np.pi * fr * tt)) * np.exp(-tt * (8 if i < 3 else 3)))
    save("tada", np.concatenate(seg))
    # buzzer ผิด (เกมโชว์)
    t = t_(0.7)
    sq = np.sign(np.sin(2 * np.pi * 110 * t)) + 0.5 * np.sign(np.sin(2 * np.pi * 116 * t))
    save("buzzer", sq * np.clip((0.7 - t) / 0.05, 0, 1) * 0.6)
    # record scratch (หยุดเรื่อง)
    t = t_(0.45)
    sp = np.concatenate([np.linspace(1.6, -1.2, len(t) // 2), np.linspace(-1.2, 0.2, len(t) - len(t) // 2)])
    ph = np.cumsum(sp) / SR
    src = rng.standard_normal(SR)
    idx = (np.abs(ph) * SR * 0.9).astype(int) % SR
    save("record_scratch", lowpass_sweep(src[idx], 2500, 1200) * np.hanning(len(t)) ** 0.3)
    # camera shutter
    t = t_(0.18)
    nz = rng.standard_normal(len(t))
    e = np.exp(-((t - 0.01) ** 2) / 1e-5) + 0.8 * np.exp(-((t - 0.09) ** 2) / 2e-5)
    save("shutter", nz * e)


def tone(fr, d, harm=((1, 1),), vib=0.0, vib_hz=5.5):
    t = t_(d)
    f = fr * (1 + vib * np.sin(2 * np.pi * vib_hz * t)) if np.isscalar(fr) else fr
    ph = 2 * np.pi * np.cumsum(np.broadcast_to(f, t.shape)) / SR
    return sum(a * np.sin(m * ph) for a, m in harm)


BRASS = ((1, 1), (0.7, 2), (0.5, 3), (0.35, 4), (0.2, 5), (0.12, 6))


def synth_meme():
    """เสียงแนว meme (ใช้ตอนตัดเข้า GIF) — สังเคราะห์เอง ไม่ติดลิขสิทธิ์"""
    # vine boom: กระแทกต่ำหนัก + หางก้อง
    t = t_(1.8)
    f = 95 * np.exp(-t * 3) + 42
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 1.6)
    thump = lowpass_sweep(rng.standard_normal(len(t)), 900, 120) * np.exp(-t * 25) * 2
    save("vine_boom", np.tanh((body + thump) * 4))
    # จิ้งหรีด (เงียบกริบ/อึดอัด)
    t = t_(2.4)
    car = np.sin(2 * np.pi * 4600 * t)
    chirp = (np.sin(2 * np.pi * 30 * t) > 0.2) * (np.sin(2 * np.pi * 1.6 * t) > -0.1)
    save("crickets", car * chirp * 0.6 * np.clip((2.4 - t) / 0.3, 0, 1))
    # ดั่น ดั่น ดั๊นนน (ดราม่า)
    seg = []
    for fr, d in ((147, 0.32), (147, 0.32), (110, 1.4)):
        tt = t_(d)
        seg.append(tone(fr, d, BRASS, 0.004) * np.clip(tt / 0.02, 0, 1) * np.exp(-tt * (2.5 if d < 1 else 1.1)))
        seg.append(np.zeros(int(SR * 0.05)))
    save("dun_dun", np.tanh(np.concatenate(seg) * 1.5))
    # ทรอมโบนเศร้า (วา วา วา วาาา)
    seg = []
    for fr, d in ((233, 0.42), (220, 0.42), (208, 0.42), (196, 1.3)):
        tt = t_(d)
        seg.append(tone(fr, d, BRASS[:4], 0.012 if d > 1 else 0.003) * np.clip(tt / 0.04, 0, 1) * np.clip((d - tt) / 0.08, 0, 1))
    save("sad_trombone", np.concatenate(seg))
    # นกหวีดสไลด์ลง (ล้ม/เฟล) / ขึ้น
    t = t_(0.8)
    save("slide_down", np.sin(2 * np.pi * np.cumsum(np.geomspace(2200, 500, len(t))) / SR) * env(len(t), 0.05, 0.6))
    save("slide_up", np.sin(2 * np.pi * np.cumsum(np.geomspace(450, 2000, len(t))) / SR) * env(len(t), 0.05, 0.6))
    # bonk (โดนเคาะหัว)
    t = t_(0.35)
    f = 520 * np.exp(-t * 6) + 180
    save("bonk", (np.sin(2 * np.pi * np.cumsum(f) / SR) + 0.4 * rng.standard_normal(len(t)) * np.exp(-t * 80)) * np.exp(-t * 11))
    # ตึ่งงง (plot twist / เผย)
    t = t_(1.6)
    x = sum(a * np.sin(2 * np.pi * fr * t) for a, fr in ((1, 98), (0.6, 147), (0.5, 196), (0.3, 233)))
    save("reveal_sting", np.tanh(x * np.exp(-t * 1.8) * 2) + 0.3 * whoosh(1.6, 4000, 300, 0.05)[:, 0])
    # ฟิ้ววว (ผ่านไปไว/หายตัว)
    save("zoom_out", whoosh(0.5, 6000, 400, 0.15))


KENNEY = {  # ชื่อใน clipcut ← ไฟล์ Kenney (CC0)
    "punch": "impactPunch_heavy_000", "punch_light": "impactPunch_medium_001",
    "hit_soft": "impactSoft_heavy_001", "metal_clang": "impactMetal_heavy_000",
    "bell": "impactBell_heavy_000", "glass": "impactGlass_medium_000",
    "wood_knock": "impactWood_heavy_002",
    "click": "click_002", "tick": "tick_002", "drop": "drop_002",
    "confirm": "confirmation_002", "error": "error_006", "question": "question_001",
    "glitch": "glitch_002", "glitch_2": "glitch_004", "scratch": "scratch_001",
    "pluck": "pluck_001", "open": "maximize_006",
    "powerup": "powerUp2", "laser": "laser4", "zap": "zap1",
    "phaser_up": "phaserUp3", "coin": "highUp",
}


def kenney(root):
    files = {os.path.splitext(os.path.basename(p))[0]: p
             for p in glob.glob(os.path.join(root, "**", "*.ogg"), recursive=True)}
    for name, src in KENNEY.items():
        if src not in files:
            print("  ! ไม่เจอ", src); continue
        subprocess.run([FF, "-y", "-v", "error", "-i", files[src], "-ar", str(SR), "-ac", "2",
                        "-af", "loudnorm=I=-14:TP=-1", os.path.join(OUT, name + ".wav")], check=True)
        print("  +", name, "(kenney)")


def level_all(target_db=-20.0, peak_db=-3.0):
    """ทุกไฟล์ดังเท่ากัน: RMS ช่วง 300ms ที่ดังสุด = target_db (เสียงพูดหลัง render ≈ -16 LUFS → SFX เบากว่า ~6-8 dB)
    ห้าม normalize แบบ LUFS/peak — เสียงสั้น (pop/click) โดน gate วัดผิด, boom peak ต่ำแต่ดังมาก"""
    for f in sorted(os.listdir(OUT)):
        p = os.path.join(OUT, f)
        with wave.open(p) as w:
            sr, ch = w.getframerate(), w.getnchannels()
            x = np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(np.float64).reshape(-1, ch) / 32768
        mono = x.mean(1)
        win = max(1, int(sr * 0.3))
        rms = np.sqrt(np.convolve(mono ** 2, np.ones(win) / win, "valid").max() if len(mono) > win else (mono ** 2).mean())
        g = 10 ** (target_db / 20) / max(rms, 1e-6)
        g = min(g, 10 ** (peak_db / 20) / max(np.abs(x).max(), 1e-6))
        y = x * g
        with wave.open(p, "wb") as w:
            w.setnchannels(ch); w.setsampwidth(2); w.setframerate(sr)
            w.writeframes((np.clip(y, -1, 1) * 32767).astype("<i2").tobytes())
        print(f"  = {f[:-4]:16} x{g:.2f}")


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    if sys.argv[1:] == ["--meme"]:  # เพิ่มเฉพาะชุด meme ไม่ทับของเดิม
        print("สังเคราะห์เสียง meme…"); synth_meme(); print("ปรับระดับ…"); level_all(); sys.exit()
    print("สังเคราะห์ SFX…"); synth(); synth_meme()
    if len(sys.argv) > 1:
        print("คัดจาก Kenney…"); kenney(sys.argv[1])
    print("ปรับระดับ…"); level_all()
    print("✓", OUT, len(os.listdir(OUT)), "ไฟล์")
