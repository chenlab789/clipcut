#!/usr/bin/env python
"""สร้าง <ชื่อ>.edit.json — แผนตัดต่อที่ editor (server.py) กับ render_edit.py ใช้ร่วมกัน

ปกติ clipcut.py --edit เรียกให้เอง · ใช้ตรงได้กับ output clipcut เดิม (มี .cut.mp4 + .segments.json):
  python edit_init.py <clipcut_out>/<ชื่อ>.segments.json [--style style.json] [--keep ...] [--aspect 9x16|16x9]

เวลาใน edit.json = เวลาของ .cut.mp4 (หลังตัด dead air แล้ว)
items: {id, track: sub|broll|emoji|sfx|fx, start, end, ...}
  sub   : text, speaker
  broll : src (path เทียบโฟลเดอร์ edit.json), x, y (กลางภาพ 0-1), w (กว้าง/จอ 0-1)
  emoji : emoji, x, y, size (กว้าง/จอ), anim: pop|float|shake
  sfx   : sfx (ชื่อไฟล์ใน assets/sfx ไม่มี .wav), vol
  fx    : fx: punch|zoomin|zoomout|shake|flash, amount
"""
import os
import json
import sys
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import clipcut as cc  # noqa: E402
import ccfx  # noqa: E402


def build(seg_json, cut_mp4, style, keep, aspect, src_wh):
    data = ccfx.load_edit(seg_json)
    w, h = ccfx.out_size(aspect)
    st = dict(style)
    size = st["size"] * (1.0 if w <= h else 0.62)
    chunks = cc.split_long(cc.phrase_chunks(data["segments"], keep), int((w - 160) / (0.34 * size)))
    cols = cc.speaker_colors(st, chunks)
    st["speakers"] = cols
    items = [{"id": f"s{i}", "track": "sub", "start": round(a, 3), "end": round(b, 3),
              "text": t.replace("﻿", "").strip(), "speaker": sp}
             for i, (a, b, t, sp) in enumerate(chunks, 1)]
    return {
        "version": 1,
        "video": os.path.basename(cut_mp4),
        "source_wh": list(src_wh),
        "aspect": aspect,
        "duration": round(cc.probe_dur(cut_mp4), 3),
        "style": st,
        "voice_lufs": round(ccfx.measure_lufs(cut_mp4), 1),
        "mix": dict(ccfx.MIX_DEFAULT),
        "music": None,
        "items": items,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("segments")
    ap.add_argument("--style")
    ap.add_argument("--keep")
    ap.add_argument("--pad", type=float, default=0.15)
    ap.add_argument("--min-silence", type=float, default=0.6)
    ap.add_argument("--aspect", choices=["9x16", "16x9"], default=None)
    ap.add_argument("--force", action="store_true", help="ทับ edit.json เดิม")
    a = ap.parse_args()

    seg = os.path.abspath(a.segments)
    base = os.path.basename(seg)[: -len(".segments.json")]
    outdir = os.path.dirname(seg)
    cut = os.path.join(outdir, base + ".cut.mp4")
    out = os.path.join(outdir, base + ".edit.json")
    if os.path.exists(out) and not a.force:
        print("มี edit.json อยู่แล้ว (ใช้ --force ถ้าจะทับ):", out); return
    segs = ccfx.load_edit(seg)["segments"]
    kj = os.path.join(outdir, base + ".keep.json")
    if os.path.exists(kj):  # ช่วงที่ cut_video ใช้จริง (รวมตัดเงียบรอบสอง) — ต้องตรงกับ cut.mp4
        keep = [tuple(x) for x in json.load(open(kj))]
    else:
        keep = cc.compute_keep(segs, a.pad, a.min_silence, extra=cc.parse_keep(a.keep))
    wh = cc.probe_wh(cut)
    aspect = a.aspect or "9x16"
    ccfx.save_edit(out, build(seg, cut, cc.load_style(a.style), keep, aspect, wh))
    print("✓", out)


if __name__ == "__main__":
    main()
