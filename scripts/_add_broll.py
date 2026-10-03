import sys
import os
import json
import subprocess
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
video, plan_path, brolldir, mode, out = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5]
FF = os.environ.get("FFMPEG", "ffmpeg")

BROLL_MAP = {
    "tailscale": "tailscale", "vpn": "tailscale",
    "termius": "terminal", "terminal": "terminal",
    "claude code": "claude_code", "claude": "claude_code",
    "session": "claude_code", "use case": "claude_code",
    "github": "github", "iphone": "iphone",
    "chrome remote desktop": "remote", "remote desktop": "remote",
    "remote control": "remote", "chrome": "remote", "search youtube": "remote",
}

plan = json.load(open(plan_path, encoding="utf-8"))
ranges = defaultdict(list)
for p in plan:
    img = BROLL_MAP.get(p["kw"].lower())
    if img:
        ranges[img].append((p["start"], p["end"]))

imgs = [i for i in ["tailscale", "terminal", "claude_code", "github", "iphone", "remote"] if i in ranges]
if not imgs:
    print("no broll")
    sys.exit(0)

if mode == "9x16":
    iw, x, y = 760, "(W-w)/2", 70           # บนกลาง เติมพื้นที่ดำ
else:
    iw, x, y = 360, "W-w-70", 70            # มุมบนขวา

inputs = ["-i", video]
for img in imgs:
    inputs += ["-i", os.path.join(brolldir, img + ".png")]

parts, cur = [], "[0:v]"
for i, img in enumerate(imgs):
    enable = "+".join(f"between(t,{s:.2f},{e:.2f})" for s, e in ranges[img])
    parts.append(f"[{i+1}:v]scale={iw}:-1[i{i}]")
    parts.append(f"{cur}[i{i}]overlay={x}:{y}:enable='{enable}'[v{i}]")
    cur = f"[v{i}]"
fc = ";".join(parts)

cmd = ([FF, "-y"] + inputs +
       ["-filter_complex", fc, "-map", cur, "-map", "0:a?",
        "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-c:a", "copy", out])
subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
print(f"✓ b-roll ({len(imgs)} ภาพ, {sum(len(v) for v in ranges.values())} จุด) → {out}")
