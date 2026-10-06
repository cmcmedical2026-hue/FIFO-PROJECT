"""Compare the August count with the June count plus Flow item movements."""
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
prior = json.loads((ROOT / "outputs/phase3-2026/prepared.json").read_text())
movements = json.loads((HERE / "flow_raw.json").read_text())["movements"]
count_rows = list(csv.reader((ROOT / "Source file/جرد 31-08-2026.csv").open(encoding="utf-8-sig")))
jun = defaultdict(float)
for r in prior["count"]:
    jun[str(r["item"])] += float(r["qty"])
aug = defaultdict(float)
aug_lots = defaultdict(list)
last_item = ""
for i, r in enumerate(count_rows[1:], 2):
    if not any(r):
        last_item = ""
        continue
    if r[0].strip():
        last_item = r[0].strip()
    item = last_item
    if not item:
        print("COUNT_ROW_WITHOUT_ITEM", i, r)
        continue
    q = float(r[3]) if r[3].strip() else 0.0
    aug[item] += q
    aug_lots[item].append({"row": i, "qty": q, "expiry": r[1], "lot": r[2], "note": r[4]})
flow = defaultdict(float)
by_month = defaultdict(lambda: defaultdict(float))
for r in movements:
    q = float(r["q"]) * (1 if r["e"] == "A" else -1)
    flow[str(r["ITNO"])] += q
    by_month[r["dt"][:7]][str(r["ITNO"])] += q
diffs = []
for item in sorted(set(jun) | set(aug) | set(flow)):
    expected = jun[item] + flow[item]
    if abs(aug[item] - expected) > 1e-8:
        diffs.append({"item": item, "june": jun[item], "flow_delta": flow[item],
                      "flow_aug": expected, "aug_count": aug[item], "diff": aug[item] - expected,
                      "aug_lots": aug_lots[item]})
print(json.dumps({"june_items": len([x for x in jun.values() if x]), "june_qty": sum(jun.values()),
                  "aug_items": len([x for x in aug.values() if x]), "aug_qty": sum(aug.values()),
                  "flow_delta": sum(flow.values()), "expected_aug_qty": sum(jun.values()) + sum(flow.values()),
                  "diff_count": len(diffs), "diffs": diffs}, ensure_ascii=False, indent=2))
