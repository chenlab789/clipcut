import json
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
d = json.load(open(sys.argv[1], encoding="utf-8"))
for i, s in enumerate(d["segments"]):
    print(f'{i}\t{s["start"]:.2f}\t{s["end"]:.2f}\t{s["text"]}')
