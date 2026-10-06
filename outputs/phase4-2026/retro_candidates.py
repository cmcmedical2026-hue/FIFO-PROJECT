"""Find only well-supported lot/expiry fills in March–June rows."""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "Integration FLOW" / "src"))
from flow.lots import Catalog, DATE_RE, lots_in_segment, norm_lot, split_remark

prior = json.loads((ROOT / "outputs/phase3-2026/prepared.json").read_text())
feb = json.loads((ROOT / "outputs/01a0df6e-opening/stage2_data.json").read_text())
aug = json.loads((HERE / "prepared.json").read_text())
cat = Catalog(ROOT / "Integration FLOW/data/inventory/lot_catalog.json")

def canon(item, lot):
    found = cat.canonical(item, lot)
    if found:
        return found
    if str(lot).isdigit():
        for known in cat.items.get(item, {}):
            if known.isdigit() and int(known) == int(lot):
                return known
    return lot

counts = defaultdict(lambda: defaultdict(set))
for r in feb["count"]:
    if r["qty"] > 0 and r["lot"] not in ("", "بدون"):
        counts["feb"][str(r["item"])].add(canon(str(r["item"]), r["lot"]))
for r in prior["count"]:
    if r["qty"] > 0 and r["lot"] not in ("", "بدون"):
        counts["jun"][str(r["item"])].add(canon(str(r["item"]), r["lot"]))
for r in aug["count"]:
    if r["qty"] > 0 and r["lot"] not in ("", "بدون"):
        counts["aug"][str(r["item"])].add(canon(str(r["item"]), r["lot"]))

doc_items = defaultdict(list)
for r in prior["rows"]:
    m = r["movement"]
    key = (m["OPCODE"], int(m["DOCNO"]))
    if str(m["ITNO"]) not in doc_items[key]:
        doc_items[key].append(str(m["ITNO"]))

candidates = []
still_open = []
for r in prior["rows"]:
    if r["lot"]:
        continue
    m = r["movement"]
    item = str(m["ITNO"])
    key = (m["OPCODE"], int(m["DOCNO"]))
    segs = split_remark(m.get("RMK") or "", doc_items[key])
    seg = (segs.get(item) or segs.get("*") or "").strip()
    found = list(dict.fromkeys(lots_in_segment(cat, item, seg))) if seg else []
    explicit = [l for l in found if norm_lot(l) in norm_lot(seg)]
    chosen = None
    why = ""
    if len(found) == 1 and (explicit or DATE_RE.search(seg)):
        chosen, why = found[0], "ملاحظة المستند بعد توحيد اللوط"
    elif len(counts["feb"][item]) == len(counts["jun"][item]) == len(counts["aug"][item]) == 1:
        same = counts["feb"][item] | counts["jun"][item] | counts["aug"][item]
        if len(same) == 1:
            chosen, why = next(iter(same)), "لوط وحيد متطابق في جرد فبراير ويونيو وأغسطس"
    if chosen and key not in [("STROUT", 872), ("STRMAK", 220)]:
        exp = cat.expiry(item, chosen)
        if exp:
            candidates.append({"sheet": r["sheet"], "row": r["sheet_row"],
                               "op": m["OPCODE"], "doc": m["DOCNO"], "item": item,
                               "qty": m["q"], "lot": chosen, "exp": exp, "why": why})
            continue
    still_open.append({"sheet": r["sheet"], "row": r["sheet_row"],
                       "op": m["OPCODE"], "doc": m["DOCNO"], "item": item,
                       "qty": m["q"], "remark": seg[:100]})

out = {"candidates": candidates, "still_open": still_open}
(HERE / "retro_candidates.json").write_text(json.dumps(out, ensure_ascii=False, indent=2))
print(json.dumps({"candidate_count": len(candidates), "still_open": len(still_open),
                  "candidates": candidates[:25]}, ensure_ascii=False))
