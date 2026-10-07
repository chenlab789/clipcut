#!/usr/bin/env python
"""render edit.json → mp4 จริง (ffmpeg) — ซับ + ภาพประกอบ + อีโมจิเด้ง + SFX + ซูม/สั่น/แฟลช

  python render_edit.py <ชื่อ>.edit.json [--aspect 9x16|16x9] [--preview] [--out FILE]

--preview = ครึ่งความละเอียด + encode เร็ว ไว้เช็คของจริงก่อนเรนเดอร์เต็ม
ลำดับเลเยอร์: คลิป(+blur bg) → ซูม/สั่น → แฟลช → ภาพประกอบ → อีโมจิ → ซับ
"""
import os
import sys
import math
import shutil
import argparse
import tempfile
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import clipcut as cc  # noqa: E402
import ccfx  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
FF = cc.FF
FPS = 30


CAP_FONT = {"Mali": ("Mali-Bold.ttf", 1000 / 2122), "Kanit": ("Kanit-Bold.ttf", 1000 / 1580), "Itim": ("Itim-Regular.ttf", 1000 / 1200)}


def fx_exprs(fx, T, k):
    """สูตรเดียวกับ ccfx.zoom_at แต่เป็น expr ของ ffmpeg (T = ตัวแปรเวลา, k = สเกลความละเอียด)"""
    z, sx, sy, fl = [], [], [], []
    for it in fx:
        s, e = it["start"], it["end"]
        a = it.get("amount", ccfx.FX_DEFAULT[it["fx"]])
        d = max(e - s, 1e-3)
        on = f"between({T},{s:.3f},{e:.3f})"
        if it["fx"] == "punch":
            z.append(f"{a - 1:.4f}*{on}*min(1,min(({T}-{s:.3f})/0.08,({e:.3f}-{T})/0.15))")
        elif it["fx"] == "zoomin":
            z.append(f"{a - 1:.4f}*{on}*({T}-{s:.3f})/{d:.3f}")
        elif it["fx"] == "zoomout":
            z.append(f"{a - 1:.4f}*{on}*(1-({T}-{s:.3f})/{d:.3f})")
        elif it["fx"] == "focus":
            z.append(f"{a - 1:.4f}*{on}*min(1,min(({T}-{s:.3f})/0.35,({e:.3f}-{T})/0.35))")
        elif it["fx"] == "shake":
            z.append(f"0.06*{on}")
            sx.append(f"{a * k:.2f}*{on}*sin({T}*47)")
            sy.append(f"{a * k:.2f}*{on}*sin({T}*61+1)")
        elif it["fx"] == "flash":
            fl.append(f"{a:.3f}*{on}*exp(-({T}-{s:.3f})*4/{d:.3f})")
    j = lambda xs: "+".join(xs) if xs else "0"  # noqa: E731
    return "1+" + j(z), j(sx), j(sy), j(fl)


def cam_expr(path, col, size):
    """เส้นทางกล้อง [[t, x0, y0]] → expr เวลา t (พิกเซล) — เส้นตรงระหว่าง key · ต้นไม้สมดุล (ffmpeg parse ยาวๆ พัง)"""
    v = lambda k: path[k][col] * size  # noqa: E731
    terms = [f"lt(t,{path[0][0]:.3f})*{v(0):.1f}", f"gte(t,{path[-1][0]:.3f})*{v(-1):.1f}"]
    for k in range(len(path) - 1):
        a, b = path[k][0], path[k + 1][0]
        if b <= a:
            continue
        terms.append(f"gte(t,{a:.3f})*lt(t,{b:.3f})*({v(k):.1f}+{v(k + 1) - v(k):.1f}*(t-{a:.3f})/{b - a:.3f})")
    return cc.sum_tree(terms)


def emoji_frames(it, px, tmp):
    """วาดอีโมจิทีละเฟรม (pop/float/shake) → โฟลเดอร์ PNG — canvas คงที่ให้ overlay ไม่เปลี่ยนขนาด"""
    from PIL import Image
    src = Image.open(ccfx.emoji_png(it["emoji"])).convert("RGBA")
    S = int(math.ceil(px * 1.25 * 1.45)) // 2 * 2
    dur = it["end"] - it["start"]
    d = tempfile.mkdtemp(prefix=f"emo_{it['id']}_", dir=tmp)
    for n in range(max(1, int(math.ceil(dur * FPS)))):
        s, rot, a, _ = ccfx.emoji_anim(it.get("anim", "pop"), n / FPS, dur)
        fr = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        sz = int(px * s)
        if sz >= 2 and a > 0:
            e = src.resize((sz, sz), Image.LANCZOS).rotate(-rot, Image.BICUBIC, expand=True)
            if a < 1:
                e.putalpha(e.getchannel("A").point(lambda v: int(v * a)))
            fr.alpha_composite(e, ((S - e.width) // 2, (S - e.height) // 2))
        fr.save(os.path.join(d, f"{n:04d}.png"), compress_level=1)
    return d, S


def audio_graph(E, voice, n_in, sfx):
    """เสียงทั้งหมด → (inputs เพิ่ม, บรรทัด filter) ออกที่ [aout] — voice = index input ที่มีเสียงพูด (cut.mp4)
    ใช้ทั้ง render_edit (แปะเอฟเฟกต์) และ explainer (ภาพจาก Remotion)"""
    inputs = []
    #    เสียงพูด: ยกด้วย gain คงที่ไปที่ VOICE_LUFS (ไม่ใช้ loudnorm แบบ dynamic — พรีวิวต้องคำนวณตามได้)
    #    SFX: คลังปรับ RMS = -20 dBFS ไว้แล้ว × vol × mix.sfx · เพลง: -20 LUFS × vol แล้วกดลงตอนพูด (sidechain)
    dur = E["duration"]
    vgain = ccfx.VOICE_LUFS - E.get("voice_lufs", ccfx.VOICE_LUFS)
    master = E.get("mix", {}).get("sfx", ccfx.MIX_DEFAULT["sfx"])
    music = E.get("music")
    mfile = music and ccfx.music_file(music["src"])
    amix = [f"[{voice}:a]aresample=48000,volume={vgain:.2f}dB" + (",asplit=2[a0][vsc]" if mfile and music.get("duck", True) else "[a0]")]
    parts = ["[a0]"]
    for i, it in enumerate(sfx):
        inputs += ["-i", os.path.join(ccfx.SFX_DIR, it["sfx"] + ".wav")]
        ms = int(it["start"] * 1000)
        amix.append(f"[{n_in}:a]aresample=48000,volume={it.get('vol', 0.8) * master:.3f},adelay={ms}:all=1[s{i}]")
        parts.append(f"[s{i}]"); n_in += 1
    if mfile:
        inputs += ["-stream_loop", "-1", "-i", mfile]
        off = music.get("offset", 0)
        chain = (f"[{n_in}:a]aresample=48000,atrim={off:.2f}:{off + dur:.2f},asetpts=PTS-STARTPTS,"
                 f"volume={music.get('vol', ccfx.MUSIC_DEFAULT['vol']):.3f},"
                 f"afade=t=in:d=1,afade=t=out:st={max(0, dur - 2.5):.2f}:d=2.5")
        if music.get("duck", True):
            amix.append(chain + "[mraw]")
            # กดเพลงลง ~10 dB ตอนมีเสียงพูด ปล่อยกลับช้าๆ ตอนเงียบ
            amix.append("[mraw][vsc]sidechaincompress=threshold=0.015:ratio=8:attack=40:release=600:makeup=1[m]")
        else:
            amix.append(chain + "[m]")
        parts.append("[m]"); n_in += 1
    if len(parts) > 1:
        amix.append("".join(parts) + f"amix=inputs={len(parts)}:normalize=0:duration=first:dropout_transition=0,"
                    f"alimiter=limit=0.89:level=false[aout]")
    else:
        amix.append("[a0]alimiter=limit=0.89:level=false[aout]")
    return inputs, amix


def build(E, proj, aspect, preview, tmp):
    W, H = ccfx.out_size(aspect)
    k = 0.5 if preview else 1.0
    w, h = int(W * k) // 2 * 2, int(H * k) // 2 * 2
    sw, sh = E["source_wh"]
    items = sorted(E["items"], key=lambda x: x["start"])
    by = lambda tr: [x for x in items if x["track"] == tr]  # noqa: E731

    inputs = ["-i", os.path.join(proj, E["video"])]
    fc = []
    # 1. base
    cam = E.get("cam") or {}
    if cam.get("mode") == "follow" and cam.get("path"):
        # กล้องตามหน้า (smartcam): ครอปขนาดคงที่จากต้นฉบับ เลื่อนตาม path → ขยายเต็มจอ (= camAt ใน app.js)
        cw, ch = int(cam["w"] * sw) // 2 * 2, int(cam["h"] * sh) // 2 * 2
        fc.append(f"[0:v]fps={FPS},crop={cw}:{ch}:x='{cam_expr(cam['path'], 1, sw)}':y='{cam_expr(cam['path'], 2, sh)}',"
                  f"scale={w}:{h}:flags=lanczos,setsar=1[v0]")
    elif aspect == "9x16" and sw > sh:
        fc.append(f"[0:v]fps={FPS},split=2[bg][fg];"
                  f"[bg]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},boxblur={int(26*k)}:2[bgb];"
                  f"[fg]scale={w}:-2[fgs];[bgb][fgs]overlay=(W-w)/2:(H-h)/2,setsar=1[v0]")
    else:
        fc.append(f"[0:v]fps={FPS},scale={w}:{h}:force_original_aspect_ratio=decrease,"
                  f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color={cc.BG},setsar=1[v0]")
    cur = "v0"
    # 2. ซูม/สั่น
    fx = by("fx")
    if any(x["fx"] != "flash" for x in fx):
        z, sx, sy, _ = fx_exprs([x for x in fx if x["fx"] != "flash"], "it", k)
        # จุดโฟกัสของแต่ละ item (fx_x/fx_y จาก focus.py — หน้าคนพูด/ของที่ยก) · ไม่มี = กลางจอ · zoompan clip ขอบให้เอง
        fxe, fye = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
        for it in reversed([x for x in fx if x["fx"] != "flash" and x.get("fx_x") is not None]):
            on = f"between(it,{it['start']:.3f},{it['end']:.3f})"
            fxe = f"if({on},{it['fx_x']:.4f}*iw-iw/zoom/2,{fxe})"
            fye = f"if({on},{it['fx_y']:.4f}*ih-ih/zoom/2,{fye})"
        fc.append(f"[{cur}]zoompan=z='{z}':x='{fxe}+({sx})':y='{fye}+({sy})'"
                  f":d=1:s={w}x{h}:fps={FPS}[vz]")
        cur = "vz"
    # 3. แฟลช
    if any(x["fx"] == "flash" for x in fx):
        _, _, _, fl = fx_exprs([x for x in fx if x["fx"] == "flash"], "t", k)
        fc.append(f"[{cur}]eq=brightness='min(1,{fl})':eval=frame[vf]")
        cur = "vf"
    n_in = 1
    # 4. ภาพประกอบ
    for i, it in enumerate(by("broll")):
        s, e = it["start"], it["end"]; d = e - s; fd = min(0.15, d / 3)
        inputs += ["-loop", "1", "-framerate", str(FPS), "-t", f"{d:.3f}", "-i", os.path.join(proj, it["src"])]
        bw = int(it.get("w", 0.8) * w) // 2 * 2
        fc.append(f"[{n_in}:v]scale={bw}:-2,format=rgba,fade=t=in:st=0:d={fd:.3f}:alpha=1,"
                  f"fade=t=out:st={d - fd:.3f}:d={fd:.3f}:alpha=1,setpts=PTS-STARTPTS+{s:.3f}/TB[b{i}];"
                  f"[{cur}][b{i}]overlay=x={it['x'] * w:.1f}-w/2:y={it['y'] * h:.1f}-h/2:eof_action=pass:"
                  f"enable='between(t,{s:.3f},{e:.3f})'[vb{i}]")
        cur = f"vb{i}"; n_in += 1
    # 4b. GIF แปะทับ: กรอบขาวแบบสติกเกอร์ เอียงนิดๆ (เข้าชุดกับภาพพิกเซล) · เล่นวนถ้าสั้นกว่าช่วง
    import gif_lib
    GL = gif_lib.lib()
    for i, it in enumerate(x for x in by("gif") if x.get("mode", "overlay") == "overlay" and x.get("gif") in GL):
        s, e = it["start"], it["end"]; d = e - s
        inputs += ["-stream_loop", "-1", "-i", gif_lib.path(it["gif"], GL)]
        bw = int(it.get("w", 0.55) * w) // 2 * 2
        bd = max(4, int(bw * 0.035))
        rot = it.get("rot", -3)
        fc.append(f"[{n_in}:v]trim=duration={d:.3f},setpts=PTS-STARTPTS,fps={FPS},scale={bw}:-2,"
                  f"pad=iw+{bd * 2}:ih+{bd * 2}:{bd}:{bd}:color=#fcfaf4,format=rgba,"
                  f"rotate={rot}*PI/180:c=none:ow=rotw({rot}*PI/180):oh=roth({rot}*PI/180),"
                  f"fade=t=in:st=0:d=0.12:alpha=1,fade=t=out:st={max(0, d - 0.12):.3f}:d=0.12:alpha=1,"
                  f"setpts=PTS-STARTPTS+{s:.3f}/TB[g{i}];"
                  f"[{cur}][g{i}]overlay=x={it.get('x', 0.5) * w:.1f}-w/2:y={it.get('y', 0.3) * h:.1f}-h/2:eof_action=pass:"
                  f"enable='between(t,{s:.3f},{e:.3f})'[vg{i}]")
        cur = f"vg{i}"; n_in += 1
    # 5. อีโมจิ
    emo = by("emoji")
    if emo:
        print(f"วาดอีโมจิ {len(emo)} ตัว…", flush=True)
    for i, it in enumerate(emo):
        s, e = it["start"], it["end"]
        d, S = emoji_frames(it, it.get("size", 0.22) * w, tmp)
        inputs += ["-framerate", str(FPS), "-i", os.path.join(d, "%04d.png")]
        dy = f"-{0.08 * h:.1f}*(t-{s:.3f})/{e - s:.3f}" if it.get("anim") == "float" else "0"
        fc.append(f"[{n_in}:v]setpts=PTS-STARTPTS+{s:.3f}/TB[e{i}];"
                  f"[{cur}][e{i}]overlay=x={it['x'] * w:.1f}-w/2:y='{it['y'] * h:.1f}-h/2+{dy}':eof_action=pass:"
                  f"enable='between(t,{s:.3f},{e:.3f})'[ve{i}]")
        cur = f"ve{i}"; n_in += 1
    # 5b. ตัดเข้า GIF เต็มจอ (ช่องหยุดคลิป) — พื้น = GIF ตัวเดียวกันขยายเต็ม+เบลอ · ตัวจริงเต็มกว้างกรอบขาว
    for i, it in enumerate(x for x in by("gif") if x.get("mode") == "cut" and x.get("gif") in GL):
        s, e = it["start"], it["end"]; d = e - s
        inputs += ["-stream_loop", "-1", "-i", gif_lib.path(it["gif"], GL)]
        fw = int(w * 0.92) // 2 * 2
        bd = max(4, int(w * 0.012))
        fc.append(f"[{n_in}:v]trim=duration={d:.3f},setpts=PTS-STARTPTS,fps={FPS},split=2[cb{i}][cf{i}];"
                  f"[cb{i}]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},boxblur={int(30 * k)}:2,"
                  f"eq=brightness=-0.18,setsar=1[cbb{i}];"
                  f"[cf{i}]scale='min({fw},iw*{h * 0.62:.0f}/ih)':-2,pad=iw+{bd * 2}:ih+{bd * 2}:{bd}:{bd}:color=#fcfaf4[cff{i}];"
                  f"[cbb{i}][cff{i}]overlay=(W-w)/2:(H-h)/2,setpts=PTS-STARTPTS+{s:.3f}/TB[cg{i}];"
                  f"[{cur}][cg{i}]overlay=0:0:eof_action=pass:enable='between(t,{s:.3f},{e - 0.001:.3f})'[vc{i}]")
        cur = f"vc{i}"; n_in += 1
    # 6. ซับ + คำมุกบน GIF/หยุดภาพ
    subs = [(x["start"], x["end"], x["text"], x.get("speaker")) for x in by("sub") if x["text"].strip()]
    caps = [x for x in by("gif") if (x.get("caption") or "").strip()]
    if subs or caps:
        ass = os.path.join(tmp, "subs.ass")
        st = cc.load_style(None) | E["style"]
        cc.build_ass(subs, st, W, H, ass)
        if caps:  # ตัวใหญ่ด้านบน (เต็มจอ) / เหนือ GIF (แปะทับ) · สไตล์เดียวกับซับ
            lines = []
            for x in caps:
                y = H * (0.14 if x.get("mode") in ("cut", "freeze") else max(0.06, x.get("y", 0.3) - 0.17))
                fs = st["size"] * (1.25 if W <= H else 0.8)
                try:  # ยาว = ย่อให้พอดีกว้าง 90% (= drawCaption ใน app.js) · libass fs → em = fs × CAP_EM
                    from PIL import ImageFont
                    fn, em = CAP_FONT.get(st["font"], CAP_FONT["Mali"])
                    tw = ImageFont.truetype(os.path.join(cc.FONTS, fn), max(8, int(fs * em))).getlength(x["caption"])
                    fs = fs * min(1, W * 0.9 / tw) if tw else fs
                except Exception:
                    pass
                fs = int(fs)
                txt = x["caption"].replace("\n", " ").replace("{", "(").replace("}", ")")
                lines.append(f"Dialogue: 1,{cc.fmt_t(x['start'])},{cc.fmt_t(x['end'])},Default,,0,0,0,,"
                             f"{{\\an8\\pos({W / 2:.0f},{y:.0f})\\fs{fs}}}{txt}")
            open(ass, "a", encoding="utf-8").write("\n".join(lines) + "\n")
        fc.append(f"[{cur}]{cc.ass_filter(ass)}[vs]")
        cur = "vs"
    fc.append(f"[{cur}]format=yuv420p[vout]")
    # 7. เสียง
    ain, amix = audio_graph(E, 0, n_in, by("sfx"))
    inputs += ain
    return inputs, ";\n".join(fc + amix), (w, h)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("edit")
    ap.add_argument("--aspect", choices=["9x16", "16x9"])
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--out")
    ap.add_argument("--to", type=float, help="เรนเดอร์แค่ถึงวินาทีนี้ (ไว้เทส)")
    ap.add_argument("--keep-tmp", action="store_true")
    a = ap.parse_args()

    path = os.path.abspath(a.edit)
    proj = os.path.dirname(path)
    E = ccfx.load_edit(path)
    aspect = a.aspect or E["aspect"]
    base = os.path.basename(path)[: -len(".edit.json")]
    out = a.out or os.path.join(proj, f"{base}_{'preview' if a.preview else 'edit'}_{aspect}.mp4")
    tmp = tempfile.mkdtemp(prefix="clipcut_render_")
    try:
        inputs, graph, (w, h) = build(E, proj, aspect, a.preview, tmp)
        gfile = os.path.join(tmp, "graph.txt")
        open(gfile, "w", encoding="utf-8").write(graph)
        enc = (["-preset", "ultrafast", "-crf", "27"] if a.preview else ["-preset", "medium", "-crf", "19"])
        cmd = [FF, "-y", "-hide_banner", "-loglevel", "error", "-progress", "pipe:1", "-nostats",
               *inputs, "-/filter_complex", gfile, "-map", "[vout]", "-map", "[aout]",
               "-r", str(FPS), "-c:v", "libx264", *enc, "-c:a", "aac", "-b:a", "192k",
               "-t", f"{min(a.to or 1e9, E['duration']):.3f}", "-movflags", "+faststart", out]
        cnt = {t: sum(1 for x in E["items"] if x["track"] == t) for t in ccfx.TRACKS}
        print(f"เรนเดอร์ {aspect} {w}x{h} · ซับ {cnt['sub']} ภาพ {cnt['broll']} อีโมจิ {cnt['emoji']} "
              f"เสียง {cnt['sfx']} เอฟเฟกต์ {cnt['fx']}", flush=True)
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                             encoding="utf-8", errors="replace")
        last = -10
        for line in p.stdout:
            if line.startswith("out_time_us="):
                try:
                    t = int(line.split("=")[1]) / 1e6
                except ValueError:
                    continue
                pct = min(100, 100 * t / min(a.to or 1e9, E["duration"]))
                if pct - last >= 5:
                    print(f"  {pct:5.1f}%  ({t:.0f}/{E['duration']:.0f}s)", flush=True); last = pct
        err = p.stderr.read()
        if p.wait() != 0:
            print(err[-3000:]); print("กราฟ:", gfile); a.keep_tmp = True; sys.exit(1)
        vd, ad = (float(subprocess.check_output([cc.FFPROBE, "-v", "error", "-select_streams", s,
                  "-show_entries", "stream=duration", "-of", "csv=p=0", out], text=True).strip() or 0)
                  for s in ("v:0", "a:0"))
        print(f"✓ video {vd:.2f}s / audio {ad:.2f}s" + ("" if abs(vd - ad) < 0.2 else "  !! ไม่เท่ากัน"))
        m = E.get("music") and next((x for x in ccfx.music_list() if x["id"] == E["music"]["src"]), None)
        if m and m["credit"]:
            print("\nเครดิตเพลง (ก๊อปใส่ใต้คลิป — CC BY บังคับ):\n" + m["credit"] + "\n")
        print("OUTPUT " + out, flush=True)
    finally:
        if not a.keep_tmp:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
