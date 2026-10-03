---
name: clipcut
description: ตัดต่อคลิป ChenLab อัตโนมัติด้วย AI — ตัด dead air/ช่วงเงียบ + ใส่ซับไทยไวรัล (สี/ฟอนต์ตามธีมคลิป, แยกสีคนพูด) + export 16:9 (YouTube) และ/หรือ 9:16 (Shorts/Reels). ใช้เมื่อเฉินสั่ง /clipcut หรือ "ตัดคลิปให้" กับไฟล์วิดีโอ
---

# /clipcut — AI Video Auto-Editor (ChenLab)

ตัดคลิปดิบให้เป็น content พร้อมลง — ตัดจังหวะอืด ใส่ซับ export ตามสัดส่วนคลิป

## เครื่องมือ
- **ElevenLabs scribe_v2** — ถอดเสียงไทย + แยกคนพูด (diarize) — key `ELEVENLABS_API_KEY` (user env / registry อ่านเองได้)
- **faster-whisper** — fallback ถ้าไม่มี key (CPU ช้า ไทยเพี้ยน ไม่มี speaker)
- **ffmpeg** 8.x — ตัด/ซับ/reframe
- **pythainlp** — ตัดคำไทย แตกซับยาวเกินจอ (ไม่มี = ตัดได้แค่ที่ช่องว่าง)
- **video-understand** skill — ดูคลิปก่อนตัด (เลือกธีม + หาช่วงไคลแมกซ์ที่ไม่มีเสียงพูด)
- ฟอนต์ใน `clipcut/fonts/`: **Mali** (น่ารัก/ชิล), **Kanit** (หนา เทค/จริงจัง), **Itim** (กลม สบายๆ)

## Workflow (ทำตามลำดับ — อย่าข้ามขั้นดูคลิป)

```bash
export FFMPEG=... FFPROBE=...   # หรือ PowerShell $env:FFMPEG (ดูท้ายไฟล์)
export PYTHONIOENCODING=utf-8
S="$HOME/.claude/skills/clipcut/scripts"
```

**1. ดูคลิปก่อน** — รัน video-understand `index.py` + `frames.py --index <dir>/index.json` แล้วอ่าน grid:
- ธีมคลิป (สีของในคลิป, อารมณ์) → ใช้เลือกสี/ฟอนต์
- **ช่วงสำคัญที่ไม่มีเสียงพูด** (แกะเจอของ, reveal, ท่าเด็ด) → จดเวลาไว้ใส่ `--keep` — ไม่งั้นโดนตัดเป็น dead air

**2. ถอดเสียงแล้วหยุด**
```bash
python "$S/clipcut.py" "<คลิป>" --transcribe-only
```
อ่าน `<out>/<ชื่อ>.segments.json` แล้ว:
- **ใครคือเฉิน** — เฉินเป็นผู้ชาย. ดูคำลงท้าย (ค่ะ/คะ = ผู้หญิง, ครับ = ผู้ชาย) + บริบท. ไม่ชัด → ถามเฉิน
- **คำที่ฟังไม่ออก/มั่ว** (ชื่อแบรนด์เพี้ยน, อังกฤษผิดๆ) → **ถามเฉินก่อน** (เขามักฟังออก) — ถ้าเฉินก็ไม่รู้ ใส่มั่วตลกๆ แบบ "หฟวสกาด่รก" ได้ (เฉินอนุญาต) ห้ามปล่อยคำผิดที่ดูเหมือนจริง
- แก้ text / `speaker` ใน json ได้ตรงๆ (diarize จัดผิดได้ — เฉินยืนยันแล้วเชื่อเฉิน)

**3. เขียน style.json ตามธีมคลิป** (ไม่ล็อกเขียวแบรนด์ — เฉินสั่ง "เอาตามธีมคลิป")
```json
{
 "font": "Mali",
 "size": 130,
 "speakers": {"speaker_0": "#FFE066", "speaker_1": "#9AD8FF"},
 "outline": "#4A2E1A",
 "shadow_color": "#4A2E1A",
 "highlights": {"น่ารัก": "#FF4F9A"}
}
```
- `size` = px ที่ความกว้าง 1080 (9:16) — **130 คือขนาดที่เฉินโอเค** (92 = "เล็กไปมาก") — 16:9 ย่อ x0.62 ให้เอง
- สีตัวอักษรอ่อน + ขอบเข้มโทนเดียวกับคลิป (ขอบดำ = default) · คนละคนต้องต่างกันชัด
- `highlights` = คำ → สี (คำเด่นของคลิป) — **สีไฮไลต์ต้องตัดกับพื้นหลัง** (ชมพูพาสเทลบนผิวคน = กลืน → ใช้ชมพูเข้ม)
- ไม่ใส่ `highlights` = ใช้คำเทค ChenLab (Claude, GitHub, SSH...) สีทองตาม default
- ใส่เฉพาะ key ที่ต่างจาก default ได้ (default: Mali 130, ขาว, ขอบดำ 11, เงา 7, margin_v 330)

**4. render**
```bash
python "$S/clipcut.py" "<คลิป>" --skip-transcribe --style style.json --keep "44.8-47.6"
```

**5. เช็คก่อนส่ง** — ffprobe ความยาว video vs audio ของ output ต้องเท่ากัน (≈ ที่ log บอก "ตัดเหลือ Xs") — เคยหลุดคลิป iPhone VFR ภาพยืด 2 เท่า (แก้แล้วด้วย fps=30 ก่อน select) · ทำ contact sheet ส่องซับ (`fps=2,crop=...,tile=`) + ซูม crop เต็มความละเอียดคำที่มีวรรณยุกต์ซ้อน (ที่/ซึ่ง/น้ำ) — thumbnail เล็กมองสีผิดได้

## Options
| flag | default | ความหมาย |
|---|---|---|
| `--out DIR` | `<คลิป>\clipcut_out` | โฟลเดอร์ output |
| `--style FILE` | — | ฟอนต์/สี/สีต่อคนพูด/ไฮไลต์ (ด้านบน) |
| `--keep "a-b,c-d"` | — | ช่วงที่ต้องเก็บแม้ไม่มีเสียงพูด (เวลา**คลิปต้นฉบับ**, รับ `1:02` ได้) |
| `--transcribe-only` | — | ถอดเสียงแล้วหยุด (ขั้น 2) |
| `--skip-transcribe` | — | ใช้ segments.json เดิม |
| `--model` | `medium` | whisper model (เฉพาะ fallback) |
| `--min-silence` | `0.6` | ตัด gap เงียบที่ยาวเกินกี่วินาที |
| `--pad` | `0.15` | เผื่อหัว/ท้ายช่วงพูด (กันคำขาด) |
| `--only-16x9` / `--only-9x16` | — | export สัดส่วนเดียว |

env: `CLIPCUT_ENGINE=auto|elevenlabs|whisper`, `CLIPCUT_SPEAKERS=<n>` (ถ้ารู้จำนวนคนพูด — diarize แม่นขึ้น)

## Output
- คลิปแนวนอน → `<ชื่อ>_16x9.mp4` + `<ชื่อ>_9x16.mp4` (พื้นหลังคลิปเบลอ)
- คลิปแนวตั้ง → `<ชื่อ>_9x16.mp4` อย่างเดียว (จับเองจาก ffprobe)
- `.segments.json` (แก้มือได้) · `.cut.mp4` (หลังตัด dead air) · `.9x16.ass` / `.16x9.ass`

## กติกาซับไทย (อย่าถอย — บั๊กเก่าที่แก้แล้ว)
- render ด้วย filter **`ass` + `shaping=complex`** — `subtitles=` จัดวรรณยุกต์แบบ simple → ซ้อน/หาย (ดู [[libass-thai-shaping-complex]])
- Style **Spacing = 0** เสมอ · ฟอนต์ต้องมี GPOS (ห้าม Tahoma)
- สี inline `{\c&HBBGGRR&}` 6 หลัก
- ไทยไม่มีเว้นวรรค → libass ตัดบรรทัดไม่ได้ → `split_long` แตกท่อนยาวเป็นหลาย pop ต่อกัน (ตัดตามคำด้วย pythainlp)

## PowerShell
```powershell
$env:FFMPEG  = (Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\Gyan.FFmpeg*" -Recurse -Filter ffmpeg.exe  | Select -First 1).FullName
$env:FFPROBE = (Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\Gyan.FFmpeg*" -Recurse -Filter ffprobe.exe | Select -First 1).FullName
```

## Phase 2 (ยังไม่ทำ)
- b-roll: gen ภาพตาม keyword ด้วย nanobanana → overlay timestamp
- intro/outro: video-as-code (Hyperframe) ธีม ChenLab
- 9:16 reframe แบบ smart (track หน้า/จอ แทน blur bg)

## หมายเหตุ
- backup ก่อนแก้ 2026-10-03: `scripts.bak-2026-10-03/`
- คลิปยาว = transcribe ช้า (whisper) → รัน background · ElevenLabs คลิป 1 นาที ~6 วิ
- ดู [[gui-capture-launch-context]] ถ้าเกี่ยวกับการอัด
