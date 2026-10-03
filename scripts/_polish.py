import sys
import os
import json
import subprocess

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
video, plan_path, whoosh, w, h, out = sys.argv[1:7]
FF = os.environ.get("FFMPEG", "ffmpeg")

plan = json.load(open(plan_path, encoding="utf-8"))
starts = sorted(set(round(p["start"], 2) for p in plan))
merged = []
for s in starts:
    if not merged or s - merged[-1] > 1.5:
        merged.append(s)
n = len(merged)

# video: slow Ken Burns zoom (subtle, อยู่ระหว่าง 1.0–1.06)
vf = (f"[0:v]zoompan=z='min(pzoom+0.0007,1.06)':"
      f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={w}x{h}:fps=30[v]")

# audio: ผสม whoosh เบา ๆ ตอน b-roll โผล่
ap = ["[1:a]asplit=" + str(n) + "".join(f"[w{i}]" for i in range(n))]
mix = ["[0:a]"]
for i, t in enumerate(merged):
    ms = int(t * 1000)
    ap.append(f"[w{i}]adelay={ms}|{ms}[d{i}]")
    mix.append(f"[d{i}]")
ap.append("".join(mix) + f"amix=inputs={n+1}:normalize=0:dropout_transition=0[a]")

fc = vf + ";" + ";".join(ap)
cmd = [FF, "-y", "-i", video, "-i", whoosh, "-filter_complex", fc,
       "-map", "[v]", "-map", "[a]",
       "-c:v", "libx264", "-preset", "medium", "-crf", "19",
       "-c:a", "aac", "-b:a", "192k", out]
subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
print(f"✓ polished ({n} whoosh cues) → {out}")
