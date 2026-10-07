---
name: clipcut
description: ตัดต่อคลิป ChenLab อัตโนมัติด้วย AI — ตัด dead air/ช่วงเงียบ + ใส่ซับไทยไวรัล (สี/ฟอนต์ตามธีมคลิป, แยกสีคนพูด) + SFX/อีโมจิเด้ง/ภาพประกอบ/ซูม-สั่น-แฟลช ตามจังหวะ ผ่านโปรแกรม editor (timeline + พรีวิวสด ที่เฉินเห็นและแก้ได้ทันที) + export 16:9 (YouTube) และ/หรือ 9:16 (Shorts/Reels). ใช้เมื่อเฉินสั่ง /clipcut, "ตัดคลิปให้", "ใส่เอฟเฟกต์/เสียง/อีโมจิในคลิป" หรือ "เปิด editor"
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

## โปรแกรม ClipCut (เฉินใช้เองไม่ต้องคุยกับกุ้ง) — ไอคอน "ClipCut" บน Desktop
ดับเบิลคลิก → หน้าแรก: ลากคลิปวาง (หรือลากใส่ไอคอน) → เลือกแบบ (ครบชุด / ตัด+ซับ / ตัดอย่างเดียว · อารมณ์ · 9:16/16:9 · ความแน่น) → `autopilot.py` ทำ 5 ขั้น (~1 นาทีต่อคลิป 45 วิ + เวลาตัด) → เปิด editor ให้เช็ค → เฉินกด Render เอง
- โปรเจกต์อยู่ที่ `D:\ChenLab-Recordings\clipcut\<ชื่อคลิป>\` (env `CLIPCUT_HOME` เปลี่ยนได้) · รายการล่าสุด `~/.clipcut/recent.json`
- AI = `claude -p --model sonnet` (claude.exe ตรงจาก npm — ใช้แพ็กเกจ Max ไม่ต้องมี key) · pass1 ดูภาพ `_frames.jpg` + แก้คำเพี้ยน + สไตล์ซับ + เพลง · pass2 วางเอฟเฟกต์ → ตรวจชื่อ sfx/fx/อีโมจิผสม ก่อนลง timeline
- ภาพประกอบ = **พิกเซลแนว animclip** (`pixel.py`): ตัวการ์ตูนเฉิน `<tee|hoodie|coat>_<ท่า>` + `icon` + `brand` (โดเมน → favicon → ลบพื้นหลัง → พิกเซล 20 ช่อง + ขอบครีม) — sprite ก๊อปจาก animclip ไว้ที่ `assets/pixel/` (ท่าใหม่: วาดที่ animclip แล้วก๊อปมา)
- เปิดซ้ำตอนรันอยู่ = ส่งไฟล์ให้ตัวเดิม (`/api/stage`) ไม่เปิด server ซ้อน · ติดตั้งไอคอนใหม่: `python scripts/install_shortcut.py`
- เฉินสั่งผ่านแชทก็ยังใช้ workflow ด้านล่างได้ตามเดิม

## แบบ Motion Explainer (2026-10-06 — เฉินเอาคลิป TikTok @warodomdotcom มาเป็นตัวอย่าง)
หน้าแรก ClipCut เลือก "แบบตัดต่อ: Motion Explainer" → จัดฉากใหม่ทุก 2-5 วิ: พื้นกระดาษ (ตาราง/เส้น/คราฟต์/กรมท่า…) + ป้ายหัวข้อ + ภาพพิกเซล 1-3 ชิ้น + ป้ายคำ + **ซับเต็มล่าง** + คนพูดย้ายกรอบ (full / polaroid / corner / circle / none)
- `remotion/src/Explainer.jsx` (ส่วนพื้นกระดาษ/ดาว/ท่าเด้ง/transition ยกมาจาก animclip) · `remotion/node_modules` = junction ไป animclip (ไม่โหลดซ้ำ 750MB) · `public/pixel` + `public/jobs/<hash>` = junction ไปคลัง/โปรเจกต์
- **แก้ Explainer.jsx แล้วต้อง build ตัวเล่นใหม่**: `cd remotion && node_modules/.bin/esbuild.cmd src/player-entry.jsx --bundle --minify --format=iife --jsx=automatic --loader:.jsx=jsx "--define:process.env.NODE_ENV=\"production\"" --outfile=../scripts/editor/player.js` — editor พรีวิวด้วย Remotion Player ตัวเดียวกับตอนเรนเดอร์ (ภาพตรงเป๊ะ)
- `explainer.py plan` = AI (opus) กำกับฉาก → ของเลือก "อะไร" แต่ตำแหน่งจัดเองตาม `SLOTS` ของแต่ละกล้อง (มีคู่ใน app.js แก้พร้อมกัน) · `explainer.py render` = Remotion ภาพเงียบ + `render_edit.audio_graph` ผสมเสียง
- `face.py` หาหน้า (OpenCV Haar ที่ 1280px — หน้าเล็กมุมจอจากคลิปอัดจอ) → กรอบ circle/corner ซูมเข้าหน้า
- **ไอคอนพิกเซลโตเองได้** (`pixel_gen.py`): AI (opus) วาดตาราง 16×16 ชุดสี animclip → `assets/pixel/icon_<ชื่อ>.png` + ตารางใน `icons.json` · AI กำกับฉากขอ `{"new": ..}` ได้ ≤12 ชิ้น/คลิป · editor มีช่อง "ให้ AI วาด" · วาด 8 ตัวขนาน ~2 นาที
- **พรีวิวภาพค้าง (แก้ 2026-10-07 — เฉินเจอ "ภาพค้างเป็นช่วง เสียงกับโมชั่นเล่นต่อ" เฉพาะใน editor)**: ① `View` ใน Explainer.jsx ต้องคืนโครงสร้างเดิมทุกฉาก (เปลี่ยนแค่ style) — เดิมคืน element ต่างแบบ → React สร้าง `<video>` ใหม่ทุกฉาก ② editor ใช้ `<cut>.proxy.mp4` (540 px, keyframe ทุก 15 เฟรม — server ทำเองตอนเปิดโปรเจกต์) ③ ซิงก์ตอนเล่นวัดจาก `<video>` จริงในตัวเล่น คลาดเกิน 0.1 วิค่อย seek ห่างกัน ≥1.5 วิ (seek ถี่ = ค้าง) · วัดผล: เล่น 20 วิ ไม่ค้าง คลาด ≤0.1 วิ
- **ซูมตามบริบท (2026-10-07 — เฉินด่า "ซูมโง่ ไม่มี subject ซูมเข้ากลางคลิป")** `focus.py`:
  ① ตามหน้าทุกคน YuNet (`assets/models/yunet.onnx`) ทุก 0.2 วิ → track · รวม track ที่หลุดเฟรม (เวลาไม่ซ้อน + ตำแหน่งเดียวกัน) ② จับคู่คนพูด = ปากใครขยับตอน speaker_X พูด (`E.faces.tracks[].speaker`) ③ AI (opus) ดูภาพนิ่ง 2 ภาพ/ช่วง + ตารางพิกัด + ประโยค → `focus: [{at, mode: speaker|box|wide, box}]`
  - Explainer: ต่อฉาก (`sc.focus`) → `focusRegion` ใน Explainer.jsx เฉลี่ย ±0.3 วิ ให้กล้องนุ่ม · กรอบเล็ก (circle/corner) = หน้าเต็มกรอบ · กรอบใหญ่ = หัวถึงอก · ซูม ≥ cover ≤ 4 เท่า
  - แปะเอฟเฟกต์: ซูม/สั่น → `fx_x, fx_y` (พิกัดเฟรมผลลัพธ์) → zoompan + พรีวิว canvas ใช้สูตรเดียวกัน
  - editor: Explainer แผงฉาก "กล้องมองที่" + ลากกรอบบนภาพ + ปุ่มสลับคนพูด · แปะเอฟเฟกต์ เป้าเล็งบนจอคลิกย้าย
  - `explainer.py focus <edit>` = ทำโฟกัสใหม่ให้โปรเจกต์ที่มีฉากแล้ว (~2 นาที/คลิป 50 วิ)
- **กันหน้าต่างเก่าเซฟทับ (บั๊กจริง 2026-10-07 — faces/focus หายหลังรีสตาร์ท server)**: rev เริ่มจากเวลา ไม่ใช่ 0 · server เติม field ที่หน้าเว็บส่งมาไม่ครบจากดิสก์ + `keep_focus` · หน้าเว็บ merge ฉากไม่ทิ้ง focus
- เรนเดอร์: คลิป 34 วิ ครึ่งความละเอียด ~2 นาที (ช้ากว่าแบบแปะเอฟเฟกต์มาก — คลิปยาวใช้ "เรนเดอร์ทดสอบ" ก่อน)

## ซูมอัจฉริยะ แบบแปะเอฟเฟกต์ (2026-10-07 — `smartcam.py`)
- **กล้องตามหน้า**: `E.cam = {mode follow|fit, zoom, w, h, path[[t,x0,y0]]}` กรอบครอปขนาดคงที่จากต้นฉบับ เลื่อนตามคนพูด (deadzone 12% · เลื่อนนุ่ม 1 วิ · ย้ายไกล >0.18 = ตัดฉับ) · แนวนอน→9:16 = zoom 1 (ครอปเต็มสูงแทนพื้นเบลอ) · สัดส่วนเดียวกัน = 1.15
  สูตรต้องตรงกัน 3 ที่: `smartcam.cam_at` · `camAt()` app.js · `cam_expr()` crop ใน render_edit
- **ซูมไปที่ของ**: AI (opus) ดูภาพทั้งคลิปช่วงละ ~4.5 วิ → mode box = fx ใหม่ `focus` (เข้า 0.35 วิ ค้าง ออก 0.35 วิ, amount ให้ของกว้าง ~60% จอ ไม่เกิน 2.2) + `box_src` ให้กล้องเลื่อนไปหาของ · ทับซูมที่ AI วาง = เอา focus
- **ซูมกระแทกตามจังหวะ**: `voice_peaks()` (dB สูงกว่า median เสียงพูด +5) ส่งให้ AI ใน pass2 + `snap_punches` ขยับ punch ±0.35 วิ เข้าจุดเน้น
- **กันภาพนิ่ง**: ช่วงว่าง ≥3 วิ ระหว่างรอยตัด → zoomin/zoomout สลับ amount 1.05-1.09 (`auto: drift`) จบตรงรอยตัด
- จุดซูม: `fx_src` = พิกัดต้นฉบับ → `refocus()` แปลงเป็น fx_x/fx_y ตามกล้อง · ลากเป้าเล็งใน editor = ลบ fx_src (ของมือ) · editor แท็บเอฟเฟกต์ เปิด/ปิดกล้อง + ซูมพื้นฐาน → POST /api/cam
- ไอคอนใหม่: pass2 ให้ AI ตั้งชื่อ snake_case + `icon_desc` → `pixel_gen.ensure` (density 1/2/3 = 2/4/6 ตัว)
- หน้าต่างดำเด้งตอน AI ทำงาน: server = pythonw → autopilot ไม่มี console → ffmpeg/claude/python ลูกเปิดหน้าต่างใหม่ทุกตัว · แก้ที่ `ccfx.py` บังคับ CREATE_NO_WINDOW ให้ subprocess ทุกตัว (clipcut.py import ccfx) · เทสด้วยตัวจับหน้าต่างใหม่: ทั้งงาน 0 หน้าต่าง
- UI v3: หน้าแรกการ์ดโปรเจกต์ (ภาพปก `_thumb.jpg`, ตั้งชื่อ = `E.title` ผ่าน /api/rename) · ตัวเลือกเป็นสวิตช์ + สรุปด้านขวา · editor timeline สูงตามจำนวนแถว, ภาพรวมโปรเจกต์ตอนไม่ได้เลือกอะไร

## GIF / meme + ตัวการ์ตูนตามคนพูด (2026-10-07)
- **คลัง GIF ในเครื่อง** `gif_lib.py` → `assets/gif/<หมวด>/<id>.mp4` + `library.json` (250 ตัว 25 หมวด ~48 MB, ไม่ขึ้น GitHub) · โหลดจาก GIPHY (key = env `GIPHY_API_KEY` ผู้ใช้ Windows) → AI (sonnet) ดูภาพ 3 เฟรม คัดตัวมีลายน้ำ/ตัวหนังสือเยอะ/ห่วยออก + เขียนคำอธิบาย
  เติม: `gif_lib.py build --cat x,y` · ไฟล์ของเฉินเอง: โยนใส่ `assets/gif/_mine/` แล้ว `gif_lib.py mine` · ไม่มีตัวตรง → `online()` ค้นสดแล้วเก็บเข้าคลัง · editor ปุ่ม × = ban
- **3 แบบ** (track `gif`): `overlay` แปะทับกรอบสติกเกอร์เอียง · `cut` คลิปหยุด ตัดไป GIF เต็มจอ (พื้นเบลอ+กรอบขาว+คำมุก) · `freeze` ภาพค้าง+ซูม+ข้อความ ("เดี๋ยวนะ...") — cut/freeze มีเสียง meme คู่ (`gap` id ผูกกัน)
- **ช่องหยุดคลิป** `gaps.py`: `E.gaps=[{id,at,dur}]` + `E.video_base` (คลิปไม่มีช่อง) → `E.video` = `*.gap<hash>.mp4` (tpad clone + apad) → editor/render ใช้เวลาเดียวกันหมด · ใส่/ลบช่อง = `_shift` เลื่อน items/gaps/faces/cam path · ช่องวางท้ายประโยค (`boundary`) · editor ใส่/ลบผ่าน POST /api/gap (สร้างคลิปใหม่ ~30-60 วิ)
- AI pass2 ได้ catalog คลัง + เป้าจำนวน (density 2: ตัดเข้า ~dur/20, แปะ ~dur/14) · `GIF_SPACING` กันถี่ · เทสคลิปแกะกล่อง 64 วิ: แปะ 4 ตัดเข้า 2 หยุดภาพ 1
- **ตัวการ์ตูนตามคนพูด**: `char_sprites.py` สร้าง `girl_<ท่า>` (แฟน: ผมยาวหน้าม้า แว่น เสื้อน้ำตาล) จากโครง animclip · `roles()` เฉิน=hoodie_ / คนพูดเยอะสุดที่ไม่ใช่เฉิน=girl_ / คนอื่น=ไม่มีตัว — autopilot บังคับ prefix ตามคนพูดตอนนั้นเอง (AI ส่งแค่ท่า)
- อีโมจิ: เลิกใช้ทั้งโปรแกรม (เฉินสั่ง "ไม่มียิ่งดี") — autopilot บังคับ emoji=0, editor ไม่มีแท็บ/แถว (โชว์แค่โปรเจกต์เก่าที่ค้าง)
- โควตาภาพ: เลือก GIF อย่างเดียว → แปะทับถี่ขึ้น (`gif_spacing` ×0.6) · ภาพพิกเซลอย่างเดียว → ~dur/4.8 ภาพ (density 2) · ทั้งคู่ → พิกเซลได้รอง ~dur/10.4
- พรีวิว GIF: โหลดทุกตัวล่วงหน้า (`preloadGifs`) + หยุดตัวที่ไม่อยู่บนจอ + watchdog คลิปหลักค้าง >0.4 วิ = seek ที่เดิม · พื้นเบลอตอนตัดเข้าใช้ canvas จิ๋ว 14×24 (ctx.filter blur ทั้งจอ = กระตุก)
- ลำดับความสำคัญ GIF > ภาพพิกเซล > อีโมจิ: `declutter()` เวลาชนกัน (±0.3 วิ) เอาตัวรองออก + เสียง whoosh/pop ที่วางคู่ · เสียง meme ใหม่ 9 ตัว (`build_sfx.py --meme`)

## ใช้ผ่านมือถือ (2026-10-07 — เฉินเครื่องเดียว)
- `tailscale serve --bg 8765` → https://<ชื่อเครื่อง>.<tailnet>.ts.net (วง Tailscale ของเจ้าของเท่านั้น · ห้ามใช้ funnel = สาธารณะ) · server ยังฟัง 127.0.0.1 ไม่ต้องเปิดไฟร์วอลล์
- คำขอที่มี header `Tailscale-User-Login`/`X-Forwarded-For` = มาจากนอกเครื่อง → ต้องมี cookie `cc_auth` (HMAC ของ PIN) · ใส่ PIN ที่ /login (PIN ใน `~/.clipcut/pin.txt`, ผิด 8 ครั้ง/15 นาที = ล็อก) — ในวงอาจมีเครื่องคนอื่น
- มือถือ: หน้าแรกเหมือนเดิม (แตะเลือกคลิป → อัปขึ้นคอม) · editor แบบย่อ `/m` = ดูคลิปที่เรนเดอร์ล่าสุด · ลบ/เปลี่ยน GIF · ลบภาพพิกเซล · แก้คำซับ · เรนเดอร์ (poll `/api/render/status`) · บันทึกผ่าน `/api/video?path=` (เฉพาะ mp4 ในโฟลเดอร์โปรเจกต์ในรายการ)
- `/m` เล่นเฉพาะคลิปที่เรนเดอร์ "แบบเดียวกับงานตอนนี้" (fx = `_edit_`/`_preview_`, explainer = `_explainer_`) — เคยหยิบ Explainer ตัวเก่ามาเล่นในงานที่ทำใหม่เป็นแปะเอฟเฟกต์ · เรนเดอร์เก่ากว่า edit.json = ป้าย "เรนเดอร์ก่อนแก้ครั้งล่าสุด"
- server เปิดงานได้ทีละงาน (ทุกเครื่องเห็นงานเดียวกัน): POST /api/edit ส่ง `file` มาด้วย ≠ งานที่เปิดอยู่ = 409 `switched` · event `edit` มี `file` → หน้าเว็บที่ถืองานอื่นโหลดใหม่ (กันเซฟของงาน A ทับงาน B)
- ไอคอนถาด (pystray, `tray()` ใน server.py): มีไอคอน = รันอยู่ · คลิก = เปิด ClipCut · ปิดโปรแกรมได้เฉพาะตอนไม่มีงานค้าง · เริ่มเองตอนล็อกอินผ่าน Startup\ClipCut.lnk (`install_shortcut.py`, ปิดด้วย `--no-startup`)
- งานหนักยังรันบนคอม → คอมต้องเปิดค้าง
- `/m` พรีวิวสด = iframe `/edit?embed=1` (editor ตัวจริง ซ่อนทุกอย่างเหลือจอ+ปุ่มเล่น, แตะจอไม่ลากของ) → เห็นเอฟเฟกต์โดยไม่ต้องเรนเดอร์ · แก้ใน /m → event edit → พรีวิววาดใหม่เอง · ปุ่มสลับ "ไฟล์ที่เรนเดอร์" (หยุดพรีวิวให้) · iPad (จอ ≥900px) ได้ editor เต็มอยู่แล้ว
- อัปจากมือถือ: ต้องอยู่หน้าเว็บจนครบ 100% (Safari หยุดส่งเมื่อสลับแอป/ล็อกจอ) → wakeLock กันจอดับ + beforeunload เตือน · server ได้ไม่ครบ Content-Length = ลบไฟล์ ไม่เข้าคลัง

## การใช้ AI (tokens)
- `ai()` เรียก `claude -p` แบบตัดของไม่ใช้: `--tools "Read"|""` `--strict-mcp-config` `--setting-sources project` `--disable-slash-commands` — วัดจริง "say ok" 30k → 5.4k tokens/ครั้ง (ที่เหลือ = CLAUDE.md/ความจำผู้ใช้ที่แพ็กเกจโหลดเสมอ) · `--bare` ลดได้อีกแต่ต้องใช้ API key ไม่ได้กับแพ็กเกจ claude.ai
- จดทุกครั้ง → `~/.clipcut/usage.jsonl` (job = env `CLIPCUT_JOB`) · ท้ายงานพิมพ์ "AI n ครั้ง · อ่าน Xk + เขียน Yk tokens (≈ $ ถ้าคิดราคา API)"

## หลายคลิป + ช่วงสาธิต (2026-10-07)
- **หลายคลิป** (`multiclip.py`): ลากหลายไฟล์ → หน้าเรียงคลิป (ลาก/▲▼/เรียงตามเวลาถ่าย) → `opts.clips` · server สร้างโฟลเดอร์ใหม่ `multi_<เวลา>` เสมอ (ไฟล์รวม = ชื่อโฟลเดอร์ ห้ามทับต้นฉบับ)
  ก่อนรวม: ขนาด/สัดส่วน (เสียงข้างมาก, ไม่ตรง = ภาพเต็มบนพื้นเบลอ) / 30fps / เสียง -16 LUFS ทุกคลิป → concat → ถอดเสียงครั้งเดียว
  - เล่าเรื่อง (`kind=story`): ตามลำดับที่เฉินเรียง ไม่ตัดหัวท้าย
  - รวมฉากฮา (`kind=funny`): AI (opus) ดู 3 เฟรม+บทแต่ละฉาก → ตัดหัวท้ายเหลือช่วงฮา + (order=ai) เรียงฮาสุดไว้ต้น / (order=random) สุ่ม · ขึ้นฉากใหม่ = whoosh_fast + flash · ตัดแล้วเลื่อนเวลาบทเอง ไม่ถอดเสียงซ้ำ
  - `E.clips` = เส้นรอยต่อบน timeline · `drop_retakes()` ประโยคซ้ำติดกัน (≥85%) เก็บเทคสุดท้าย (ทุกโหมด)
- **ช่วงสาธิต** (`speedup.py`, ขั้นที่ 3 ของตัด dead air): ช่วงเงียบ ≥1.5 วิ ที่ภาพขยับ ≥1.2× ของตอนพูด (เทียบในคลิปเอง — อัดจอขยับน้อยมาก) → AI (sonnet) ดู 4 เฟรม+ประโยครอบข้าง → demo: <4 วิ เก็บ · 4-24 วิ เร่ง ×2-4 (เสียงเงียบ เพลงคลอ) · ยาวกว่า = เก็บต้น+จบ 2.5 วิ
  `cut1.mp4` = ความเร็วปกติทุกช่วง (ไว้สลับ) → `cut.mp4` เร่งแล้ว · เวลาซับแปลงด้วย `out_time()` · ป้าย "เร่ง ×N" มุมขวาบน · editor แถบบนไม้บรรทัด → เร่ง/ปกติ/ตัดทิ้ง (POST /api/speed สร้างคลิปใหม่ ชื่อ `.cut.s<hash>.mp4`)
  - `gaps._shift` เลื่อน `E.clips` / `E.speedups` ด้วย — เคยลืม เส้นรอยต่อคลิปคลาด 4.5 วิหลังแทรก GIF

## คำสั่งเสียงตามบริบท (2026-10-07 — `voicecmd.py` + `photos.py`, opts.voice ค่าเริ่ม 1)
เฉินพูดสั่งคนตัดต่อในคลิปได้เลย ไม่มีคำปลุก ไม่ตัดประโยคที่สั่งออก — เคยทำแบบคำปลุก "กุ้งเต้น" + ตัดช่วงสั่งทิ้ง แล้วเฉินบอก "แปลก" เอาออก
- pass1 (AI อ่านบททั้งคลิปอยู่แล้ว) ตอบ `commands` เพิ่ม — ไม่เสียการเรียก AI · กติกาใน `PASS1_RULE`: ต้องสั่งตัดต่อชัดๆ (คุยกับคนในคลิป/เล่าเรื่องรูป ≠ คำสั่ง)
  `from_pass1()` หาเวลาจบคำสั่งจากเวลารายตัวอักษร `seg.wt` (transcribe.py เก็บแยกจาก `words` เพราะ `words` ใช้แบ่งซับ)
- image = **รูปถ่ายจริง** (เฉินไม่เอาภาพ AI วาด): Openverse + Wikimedia (ไม่ต้องใช้ key) ~12 รูป → แผ่นมีเลข → AI เลือกทุกคำสั่งในการเรียกเดียว → กรอบขาว `photos/photo_<id>.png` เป็น broll + เสียง pop · zoom = focus fx (ลบซูมอื่นที่ทับ) · sfx
- หาคำสั่ง = `detect()` AI ข้อความล้วนแยกต่างหาก (เคยฝากใน pass1 แล้วบางรอบตอบว่าง — AI คิดว่า "กุ้งเต้น" เป็นคนในคลิป) · ใช้บท**ดิบก่อน pass1 แก้คำ** (pass1 เคยเดาจากภาพแก้ "ขึ้นรูป…ส้ม" → "ซูมรูป…ขวด") + กติกา pass1: แก้ได้เฉพาะเสียงใกล้เดิม
- zoom มี `target` (ขวดน้ำ/หน้าเฉิน) + `later` (สั่งล่วงหน้า "ตอนกินน้ำ") → `locate()` AI (opus) ดูแผ่นเฟรมมีตาราง 0.1 ตีกรอบของ + เลือกช่องที่เกิดจริง · ทำ**ก่อนตัด dead air** แล้ว `protect()` กันช่วงนั้น (ช่วงกินน้ำเงียบ เคยโดนตัดทิ้ง) · `smartcam.hold_on()` เลื่อนกล้องจัดของกลางกรอบช่วงซูม + แรงซูม = ของกว้าง ~60%
- เอฟเฟกต์ขึ้นตอนพูดคำสั่งจบ · "ตรงนี้" + ชี้ → `fingertip()` MediaPipe HandLandmarker (`~/.clipcut/models/hand_landmarker.task` โหลดเอง) ไม่เจอท่าชี้ = รูปกลางบน / ซูมหน้าคนพูด
- item มี `cmd` ชนะ declutter · place_gifs เว้น ±2 วิรอบคำสั่ง · `E.commands` = ป้ายชมพูบนไม้บรรทัด editor (แดง = ทำไม่ได้) คลิก = ไปจุดนั้น+เลือกของ · `gaps._shift` เลื่อนป้ายด้วย

## คลังคลิป + ตั้งชื่ออัตโนมัติ (2026-10-07 — `library.py`)
- ทุกไฟล์ที่อัป → `<root>/_library/<YYYYMMDD>/` (ชื่อซ้ำต่อ _2) + `library.json` · หน้าแรกส่วน "คลังคลิป": "+ อัปเก็บไว้ก่อน" (ไม่เด้งไปตัด) · แตะเลือก (เลขลำดับ = ลำดับรวมคลิป) → "ตัดคลิปที่เลือก" · ลบ = ถังขยะ (VisualBasic SendToRecycleBin)
- เปิด server → `scan_old()` ดึงคลิปที่อัปก่อนมีคลัง (clips_*/ + ต้นฉบับชื่อเดียวกับโฟลเดอร์งาน) ไม่ย้ายไฟล์ · `_dedupe` ชื่อ+ความยาวเท่ากัน = ตัวเดียว (ขนาดไฟล์อาจต่าง) · `uses` = งานที่ตัดจากคลิปนี้
- ตัดคลิปเดิมซ้ำ = โฟลเดอร์งานใหม่ `<ชื่อ>_2` (เดิมทับงานเก่า) · คลิปในคลังถอดเสียงครั้งเดียว เก็บ `<คลิป>.segments.json` ข้างไฟล์ ตัดรอบหน้าไม่ถอดซ้ำ
- ชื่อ: อัปแล้ว AI ดู 4 เฟรม (`by=frames`) → ตัดเสร็จ pass1 ตั้ง `E.title` จากบท + ส่งกลับคลัง (`by=project`) → เฉินตั้งเอง (`by=user` ห้ามทับ) · งานเก่าไม่มีชื่อ = AI อ่านซับตั้ง (`title_project`) · คิวทีละอันเบื้องหลัง error ลง `_library/library.log`
- ชื่อไฟล์ตอนโหลดลงเครื่อง (`dl_name`) = ชื่องาน + (ทดสอบ) + สัดส่วน · ไฟล์จริงบนดิสก์ไม่เปลี่ยนชื่อ
- server รันด้วย pythonw = `sys.stdout` เป็น None → โมดูลที่ server import (autopilot/edit_apply) ต้องเช็คก่อน `reconfigure` (เคยทำตั้งชื่อพังเงียบทั้งคิว)

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

**4b. โหมด editor (ค่าเริ่มต้นเมื่อเฉินอยากได้ SFX/อีโมจิ/ภาพ/ซูม)** — แทนขั้น 4
```bash
python "$S/clipcut.py" "<คลิป>" --skip-transcribe --style style.json --keep "..." --edit   # → <ชื่อ>.edit.json
python "$S/editor/server.py" "<out>/<ชื่อ>.edit.json"     # รันแบบ background — เปิดหน้าต่าง Chrome --app ให้เฉิน
```
มี output clipcut เก่าอยู่แล้ว (มี .cut.mp4 + .segments.json) → `python "$S/edit_init.py" <ชื่อ>.segments.json [--style ...] [--keep ...]` แทน

แล้ว**ร่างแผนเอฟเฟกต์ระหว่างที่เฉินดู**: อ่านซับใน edit.json (เวลา = เวลาหลังตัดแล้ว) → เขียน plan.json → 
`python "$S/edit_apply.py" <edit.json> plan.json --stagger 0.4` (ของเด้งขึ้นจอเฉินทีละชิ้น · `--clear emoji,sfx,fx,broll` = ร่างใหม่ทั้งชุด)
- **ความแน่น "พอดี"** ≈ 1 จุดต่อ 5-10 วิ ใส่เฉพาะจังหวะที่มีเหตุผล: พีค/ปล่อยมุก/ช็อค/เปลี่ยนเรื่อง/พูดชื่อของ — อย่าโปรยทุกประโยค
- **SFX ตามจังหวะ**: เปลี่ยนเรื่อง/ภาพโผล่ = `whoosh`/`whoosh_fast` · พีค/reveal = `boom` + fx `punch` · มุก/งง = `boing`/`record_scratch` · ถูก/ได้ = `ding`/`confirm`/`tada` · ผิด/พัง = `buzzer`/`error` · คำถาม = `question` · บิ้วก่อนพีค = `riser` (จบตรงพีค) · อีโมจิโผล่ = `pop` · ทั้งหมด `ls assets/sfx` (36 ตัว) · vol 0.4-0.7 อย่าดังทับเสียงพูด
- **อีโมจิ** ตามอารมณ์ประโยค (pop = ทั่วไป, shake = ตกใจ/ขำ, float = ล่องลอย/งง) · สลับ x 0.72 / 0.28 ไม่ให้ซ้ำที่เดิมติดกัน
- **ภาพประกอบ (broll)** = ไฟล์รูปในโฟลเดอร์ output (`broll/`) ตอนพูดชื่อของ/แอป — ไม่มีรูป → gen ด้วย nanobanana ([[image-gen-mcp]]) เก็บใน `<out>/broll/`
- **fx**: `punch` (เน้นคำ, 0.45s) · `zoomin`/`zoomout` (บิ้ว 2-3s, amount 1.1-1.2) · `shake` (ช็อค) · `flash` (ตัดฉาก)
- จบแล้วบอกเฉินให้แก้ในหน้าจอได้เลย → เฉินกด **Render** เอง (หรือสั่งกุ้ง `python "$S/render_edit.py" <edit.json>`)
- ส่งให้เฉินดูจุดไหน: `http://127.0.0.1:<port>/?t=131.1&sel=e5`
- เฉินแก้ค้างในหน้าเว็บ + กุ้งแก้ไฟล์พร้อมกันได้ — หน้าเว็บ merge ให้ (ของที่เฉินแตะชนะ) แต่**อ่าน edit.json ใหม่ก่อนแก้ทุกครั้ง**

- **เพลง**: ตั้ง `"music": {"src": "<id>", "vol": 0.35, "duck": true, "offset": 0}` ใน edit.json (หรือแท็บ "เพลง" ใน editor) — เลือกตามอารมณ์คลิปจาก `assets/music/music.json` (เทค/สอน = wallpaper, ตลก = fluffing_a_duck, vlog = carefree …) · ไม่มีเพลง → `python "$S/fetch_music.py"` · เพลง CC BY → **บอกเฉินให้ก๊อปเครดิตใส่ใต้คลิป** (render พิมพ์ให้)
- **ระดับเสียง (อย่าถอย — เฉินด่าแล้ว "เอฟเฟกเสียงดังไป")**: เสียงพูดยกด้วย gain คงที่ไป -16 LUFS (`voice_lufs` ใน edit.json วัดตอนสร้าง) · SFX ทั้งคลังปรับ RMS ช่วงดังสุด = -20 dBFS (`build_sfx.py` → `level_all`) → ×vol×`mix.sfx` (0.8) ≈ เบากว่าเสียงพูด 4-6 dB · เพลง -20 LUFS ×0.35 ≈ เบากว่าเสียงพูด 12 dB + duck อีก 10 dB ตอนพูด · เพิ่ม SFX ใหม่ต้องรัน `level_all` ด้วย ไม่งั้นดังทับเสียงพูด

**render_edit.py**: `[--preview]` (ครึ่งจอ เร็ว) `[--aspect 16x9]` `[--to 30]` (ถึงวินาทีที่ 30 ไว้เทส) → `<ชื่อ>_edit_9x16.mp4` · ~1.5x realtime ที่ 1080x1920

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

## ตัด dead air 2 รอบ (อย่าถอย — เฉินด่า "ยังรู้สึกถึง dead air หลายจุด" 2026-10-06)
- รอบ 1 `compute_keep` ตามบท (segment EL + pad 0.15 + รวม gap < 0.6) — **รอดเงียบ ~13% ของคลิป** (73 จุด ≥0.35 วิ)
- รอบ 2 `tighten_keep` ความดังจริงทุก 10ms: เงียบ ≥ 0.3 วิ → เหลือหายใจ 0.08 วิต่อฝั่ง · เกณฑ์ = เสียงพูด(p95) −22..−30 dB **ไม่นับเงียบสนิท -120 dB** (ไม่งั้นเกณฑ์หลุดไป -90 ไม่ตัดอะไรเลย) → เหลือ 14 จุด ไม่มีเกิน 0.5 วิ
- `--loose` = ปิดรอบ 2 · `<ชื่อ>.keep.json` เก็บช่วงที่ตัดจริง (edit_init ใช้ตัวนี้ ห้ามคำนวณใหม่ ไม่งั้นซับเลื่อน)
- ห้ามให้ AI เดาช่วง keep จากภาพนิ่ง — มันกันช่วงยาวไม่ให้ตัด เงียบกลับมา 17 วิ
- วัดผล: `ffmpeg -i X.cut.mp4 -af silencedetect=n=-38dB:d=0.35 -f null -`
- select ของภาพต้องเป็น `sum_tree` (บวกแบบต้นไม้) — บวกเรียงเกิน ~100 ช่วง ffmpeg พัง "Cannot allocate memory"

## ตัด dead air ให้ปากตรงเสียง (อย่าถอย — แก้ 2026-10-06)
- `compute_keep` ปัดขอบทุกช่วงลงกริดเฟรม 30fps · `cut_video` ภาพ = select เลื่อนครึ่งเฟรม `[s, e)` · เสียง = **atrim+concat** (ห้าม aselect — ตัดเป็นก้อน ~21ms) + fade 6ms ที่รอยต่อ
- ผล: video = audio = ผลรวม keep เป๊ะ (เดิมคลาดสะสม 0.28 วิ ใน 70 รอยตัด → ท้ายคลิปปากไม่ตรงเสียง)

## กติกาซับไทย (อย่าถอย — บั๊กเก่าที่แก้แล้ว)
- ตัดคำด้วย `thai_tok()` = newmm + `SLANG` (แม่ง/เหี้ย/เว้ย/ป่ะ…) — ไม่ใส่ คำแสลงโดนหั่น "แม่ | ง" · เจอคำแสลงใหม่โดนหั่น → เติมใน `SLANG`
- `merge_midword()` ต่อ segment ที่ ElevenLabs ตัดกลางคำ ("เห" | "มือนกับ", "โ" | "อเค" — ห่างกันได้ถึง 1.5 วิ) อัตโนมัติใน `phrase_chunks`
- **เทส editor/เอฟเฟกต์ต้องใช้ output ที่รัน v2+ ใหม่** — อย่าหยิบ clipcut_out เก่า (whisper ไม่มีเวลารายคำ ซับค้างจอ 10 วิ) มาเทส (พลาดมาแล้ว 2026-10-06 เฉินด่า "แบบเก่ายังทำได้ดีกว่า")
- render ด้วย filter **`ass` + `shaping=complex`** — `subtitles=` จัดวรรณยุกต์แบบ simple → ซ้อน/หาย (ดู [[libass-thai-shaping-complex]])
- Style **Spacing = 0** เสมอ · ฟอนต์ต้องมี GPOS (ห้าม Tahoma)
- สี inline `{\c&HBBGGRR&}` 6 หลัก
- ไทยไม่มีเว้นวรรค → libass ตัดบรรทัดไม่ได้ → `split_long` แตกท่อนยาวเป็นหลาย pop ต่อกัน (ตัดตามคำด้วย pythainlp)

## PowerShell
```powershell
$env:FFMPEG  = (Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\Gyan.FFmpeg*" -Recurse -Filter ffmpeg.exe  | Select -First 1).FullName
$env:FFPROBE = (Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\Gyan.FFmpeg*" -Recurse -Filter ffprobe.exe | Select -First 1).FullName
```

## Editor — โครงสร้าง
- `edit.json` = แหล่งความจริงตัวเดียว: `items[{id, track: sub|broll|emoji|sfx|fx, start, end, ...}]` (schema ใน `edit_init.py`)
- `editor/server.py` (Python stdlib) + `index.html/app.js/app.css` — พรีวิว canvas, SSE sync 2 ทาง, ปุ่ม Render
- `render_edit.py` — ffmpeg: blur bg → zoompan (zoom/shake) → eq (flash) → overlay ภาพ → overlay อีโมจิ (เฟรม PNG จาก PIL) → ass ซับ · เสียง adelay+amix+alimiter
- `ccfx.py` — สูตร anim/zoom ที่ต้อง**ตรงกับ app.js** (แก้ฝั่งหนึ่งต้องแก้อีกฝั่ง ไม่งั้นพรีวิวไม่ตรงของจริง)
- ซับพรีวิว: libass คิด Fontsize = winAscent+winDescent ของ OS/2 → `FONT_METRIC` ใน app.js (Mali em = 0.471×size) — เพิ่มฟอนต์ใหม่ต้องเติมค่า
- อีโมจิ = Segoe UI Emoji วาดเป็นสติกเกอร์ขอบขาว แคชที่ `assets/emoji/` (gitignore — ฟอนต์ MS ห้ามแจก)
- SFX `assets/sfx/` = สังเคราะห์เอง + Kenney CC0 → `build_sfx.py [kenney_dir]` สร้างใหม่ได้

## Phase 2 (ยังไม่ทำ)
- intro/outro: video-as-code (Hyperframe) ธีม ChenLab
- 9:16 reframe แบบ smart (track หน้า/จอ แทน blur bg)

## หมายเหตุ
- backup ก่อนแก้ 2026-10-03: `scripts.bak-2026-10-03/`
- คลิปยาว = transcribe ช้า (whisper) → รัน background · ElevenLabs คลิป 1 นาที ~6 วิ
- ดู [[gui-capture-launch-context]] ถ้าเกี่ยวกับการอัด
