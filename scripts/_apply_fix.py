import json
import sys

raw_path, fixed_path, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
raw = json.load(open(raw_path, encoding="utf-8"))
lines = open(fixed_path, encoding="utf-8").read().split("\n")
while lines and lines[-1].strip() == "":
    lines.pop()
segs = raw["segments"]
if len(lines) != len(segs):
    print(f"MISMATCH: fixed lines={len(lines)} vs segments={len(segs)}")
    sys.exit(1)
for s, t in zip(segs, lines):
    s["text"] = t.strip()
    s["words"] = []          # ลบ word เพี้ยน → caption ใช้ text ที่แก้ (segment-level)
json.dump(raw, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"OK {len(segs)} segments → {out_path}")
