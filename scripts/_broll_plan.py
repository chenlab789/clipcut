import sys
import os
import json
import re
sys.path.insert(0, os.path.dirname(__file__))
import clipcut as cc
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

segs = json.load(open(sys.argv[1], encoding="utf-8"))["segments"]
keep = cc.compute_keep(segs, 0.15, 0.6)
pat = re.compile("|".join(re.escape(k) for k in cc.KEYWORDS), re.IGNORECASE)

plan = []
for s in segs:
    m = pat.search(s["text"])
    if not m:
        continue
    kw = m.group(0)
    st = cc.remap(s["start"], keep)
    en = cc.remap(s["end"], keep)
    if en > st:
        plan.append({"kw": kw, "start": round(st, 2), "end": round(en, 2)})

json.dump(plan, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
for p in plan:
    print(f'{p["start"]:7.2f}-{p["end"]:7.2f}  {p["kw"]}')
uniq = sorted(set(p["kw"].lower() for p in plan))
print("\nUNIQUE KEYWORDS:", ", ".join(uniq))
