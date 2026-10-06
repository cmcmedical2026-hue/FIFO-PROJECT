"""Prepare July/August stock lines from Flow and the existing sheet cost layers."""
import csv
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "Integration FLOW" / "src"))
from flow.lots import Catalog, DATE_RE, lots_in_segment, norm_lot, split_remark

PRIOR = json.loads((ROOT / "outputs/phase3-2026/prepared.json").read_text())
STAGE2 = json.loads((ROOT / "outputs/01a0df6e-opening/stage2_costs.json").read_text())
RAW = json.loads((HERE / "flow_raw.json").read_text())
MOVES = RAW["movements"]
CAT = Catalog(ROOT / "Integration FLOW/data/inventory/lot_catalog.json")
OVERRIDES = json.loads((ROOT / "Integration FLOW/data/inventory/overrides.json").read_text())["overrides"]
MONTHS = {"2026-07": ("حركات يوليو", "يوليو"), "2026-08": ("حركات أغسطس", "أغسطس")}

def actual_purchase_cost(m):
    """Actual incoming Flow purchase price, per user instruction 2026-09-28."""
    return float(m["pr"]) if m.get("pr") is not None else None

def canonical_lot(item, lot):
    found = CAT.canonical(item, lot)
    if found:
        return found
    if str(lot).isdigit():
        for known in CAT.items.get(item, {}):
            if known.isdigit() and int(known) == int(lot):
                return known
    return lot

# The count file uses an empty code to continue the previous item's lots.
count_path = ROOT / "Source file/جرد 31-08-2026.csv"
count_csv = list(csv.reader(count_path.open(encoding="utf-8-sig", newline="")))
assert count_csv[0][:4] == ["COD", "EXP", "IOT", "QTY"]
count = []
item = ""
for source_row, r in enumerate(count_csv[1:], 2):
    if not any(r):
        item = ""
        continue
    if r[0].strip():
        item = r[0].strip()
    if not item:
        raise ValueError(("blank item", source_row))
    adopted = {"QEIC": "QELC", "QEIC6035B": "QELC 6035B"}.get(item, item)
    lot = r[2].strip()
    canonical = canonical_lot(adopted, lot)
    note = r[4].strip() if len(r) > 4 else ""
    if item != adopted:
        note = "؛ ".join(filter(None, [note, f"تصحيح كود معتمد: {item} ← {adopted}"]))
    if lot != canonical:
        note = "؛ ".join(filter(None, [note, f"توحيد كتابة اللوط: {lot} ← {canonical}"]))
    adopted_exp = r[1].strip()
    if adopted == "108" and adopted_exp == "17/3/2028":
        note = "؛ ".join(filter(None, [note, "تصحيح معتمد سابقاً: الصلاحية 7/1/2028 لكل الرصيد"]))
        adopted_exp = "7/1/2028"
    count.append({"source_row": source_row, "source_item": item, "item": adopted,
                  "qty": float(r[3]), "exp": adopted_exp, "source_exp": r[1].strip(), "lot": canonical,
                  "source_lot": lot, "note": note})

by_count = defaultdict(dict)
for r in PRIOR["count"]:
    if r["qty"] > 0 and r["lot"] not in ("", "بدون"):
        lot = canonical_lot(str(r["item"]), r["lot"])
        by_count[str(r["item"])][lot] = r["exp"]
for r in count:
    if r["qty"] > 0 and r["lot"] not in ("", "بدون"):
        by_count[r["item"]][r["lot"]] = r["exp"]

def exp_for(item, lot):
    return by_count[item].get(lot) or CAT.expiry(item, lot)

doc_items = defaultdict(list)
doc_remark = {}
for m in MOVES:
    k = (m["OPCODE"], int(m["DOCNO"]))
    if str(m["ITNO"]) not in doc_items[k]:
        doc_items[k].append(str(m["ITNO"]))
    doc_remark[k] = m.get("RMK") or ""
segments = {k: split_remark(doc_remark[k], items) for k, items in doc_items.items()}

def parse_prior_lots(text):
    return [(m.group(1), float(m.group(2))) for m in re.finditer(r"([^؛()]+)\s*\((\d+(?:\.\d+)?)\)", text or "")]

issue = {}
issue_lots = {}
for r in STAGE2["rows"]:
    if r["op"] in ("STROUT", "STROU9", "STRMAK", "BURRET", "STRRTS"):
        key = (r["op"], int(r["doc"]), str(r["item"]))
        issue[key] = {"qty": float(r["qty"]), "cost": r["cost"],
                      "expr": f"'{r['sheet']}'!O{r['row']}" if r["cost"] is not None else None}
for r in PRIOR["rows"]:
    m = r["movement"]
    if m["e"] == "S":
        key = (m["OPCODE"], int(m["DOCNO"]), str(m["ITNO"]))
        issue[key] = {"qty": float(m["q"]), "cost": r["cost"],
                      "expr": f"'{r['sheet']}'!O{r['sheet_row']}" if r["cost"] is not None else None}
        issue_lots[key] = parse_prior_lots(r["lot"])

base_layers = defaultdict(list)
for item, arr in PRIOR["ending_layers"].items():
    for layer in arr:
        v = dict(layer)
        if v.get("lot") is None and len(by_count[item]) == 1:
            v["lot"] = next(iter(by_count[item]))
        base_layers[item].append(v)

def choose_lot(m, known_issues):
    item, op, doc, qty = str(m["ITNO"]), m["OPCODE"], int(m["DOCNO"]), float(m["q"])
    key = f"{op}:{doc}:{item}"
    seg = (segments[(op, doc)].get(item) or segments[(op, doc)].get("*") or "").strip()
    override = OVERRIDES.get(key, {})
    if override.get("lots"):
        pairs = [(canonical_lot(item, l), float(q)) for l, q in override["lots"]]
        if abs(sum(q for _, q in pairs) - qty) > 1e-8:
            raise ValueError(("override qty mismatch", key, qty, pairs))
        return pairs, "ملاحظة المستند وتقسيم موثق" if seg else "تقسيم موثق من الجرد"
    found = list(dict.fromkeys(lots_in_segment(CAT, item, seg))) if seg else []
    explicit = [l for l in found if norm_lot(l) in norm_lot(seg)]
    if len(found) == 1 and (explicit or DATE_RE.search(seg)):
        return [(found[0], qty)], "ملاحظة المستند" if explicit else "ملاحظة المستند والصلاحية"
    if len(found) > 1:
        return [], "أكثر من لوط؛ الكمية غير محددة"
    if op in ("STRMRT", "STRMR", "STRROT"):
        if op == "STRMRT":
            src = RAW["return_sources"].get(str(doc), {}).get("out")
            oldkey = ("STROUT", int(src), item) if src is not None else None
        elif op == "STRMR":
            src = RAW["sample_return_links"].get(str(doc))
            oldkey = ("STRMAK", int(src), item) if src is not None else None
        else:
            oldkey = None
        old = known_issues.get(oldkey, []) if oldkey else []
        if len(old) == 1 and old[0][1] >= qty:
            return [(old[0][0], qty)], "لوط إذن الصرف الأصلي"
    known = set(by_count[item])
    if len(known) == 1:
        return [(next(iter(known)), qty)], "مستنتج من الجرد"
    if not known and len(CAT.items.get(item, {})) == 1:
        return [(next(iter(CAT.items[item])), qty)], "مستنتج من سجل اللوطات"
    return [], "غير محدد"

def consume(layers, item, qty, key, target_lot=None):
    left, parts = qty, []
    arr = layers[item]
    if target_lot:
        arr = [x for x in arr if x.get("lot") == target_lot] + [x for x in arr if x.get("lot") is None] + [x for x in arr if x.get("lot") not in (target_lot, None)]
    for l in arr:
        if left <= 1e-8:
            break
        take = min(left, l["qty"])
        if take > 1e-8:
            l["qty"] -= take
            left -= take
            parts.append(dict(l, qty=take))
    if left > 1e-8:
        raise ValueError(("negative item stock", key, item, qty, left))
    return parts

def common_cost(parts):
    if not parts or any(x["cost"] is None for x in parts):
        return None
    return sum(x["qty"] * x["cost"] for x in parts) / sum(x["qty"] for x in parts)

def prior_known_lot_cost(layers, item, lot):
    xs = [l for l in layers[item] if l["qty"] > 1e-8 and l["cost"] is not None
          and (not lot or l.get("lot") in (lot, None))]
    costs = {round(l["cost"], 8) for l in xs}
    if len(costs) == 1:
        x = next(l for l in xs if l["expr"] is not None)
        return x["cost"], x["expr"]
    return None, None

def historical_cost_expr(item, cost):
    for l in base_layers[item]:
        if l["cost"] is not None and abs(l["cost"] - cost) < 1e-8 and l.get("expr"):
            return l["expr"]
    return None

seed_issue = dict(issue)
seed_lots = dict(issue_lots)
current_issue_position = {}
position_counts = Counter()
for m in MOVES:
    month = m["dt"][:7]
    position_counts[month] += 1
    if m["e"] == "S":
        current_issue_position[(m["OPCODE"], int(m["DOCNO"]), str(m["ITNO"]))] = (
            MONTHS[month][0], position_counts[month] + 1)
for pass_no in range(2):
    layers = defaultdict(list, {item: [dict(l) for l in arr] for item, arr in base_layers.items()})
    known_issue = dict(issue)
    known_lots = dict(seed_lots)
    rows, cost_flags, lot_flags, conflicts = [], [], [], []
    month_row = Counter()
    for m in MOVES:
        month = m["dt"][:7]
        sheet, month_ar = MONTHS[month]
        month_row[month] += 1
        sheet_row = month_row[month] + 1
        item, op, doc, qty = str(m["ITNO"]), m["OPCODE"], int(m["DOCNO"]), float(m["q"])
        key = (op, doc, item)
        pairs, lot_status = choose_lot(m, known_lots)
        if pairs:
            known_lots[key] = pairs
        cost, expr, basis = None, None, ""
        parts = []
        if m["e"] == "S":
            row_conflicts = []
            if pairs and len(pairs) == 1:
                parts = consume(layers, item, qty, key, pairs[0][0])
                row_conflicts = [p for p in parts if p.get("lot") not in (None, pairs[0][0])]
            elif pairs:
                for lot, q in pairs:
                    taken = consume(layers, item, q, key, lot)
                    row_conflicts += [p for p in taken if p.get("lot") not in (None, lot)]
                    parts += taken
            else:
                parts = consume(layers, item, qty, key)
            cost = common_cost(parts)
            basis = "؛ ".join(dict.fromkeys(p["basis"] for p in parts))
            if len(parts) > 1:
                basis = f"{len(parts)} دفعات: " + basis
            if row_conflicts:
                for p in row_conflicts:
                    conflicts.append({"op": op, "doc": doc, "item": item,
                                      "wanted": pairs, "used": p.get("lot"), "qty": p["qty"]})
                if len({p["cost"] for p in parts}) > 1:
                    cost = None
                    basis += "؛ تعارض لوط مع دفعات بتكلفة مختلفة"
            if cost is not None and all(p.get("expr") for p in parts):
                if len(parts) == 1:
                    expr = parts[0]["expr"]
                else:
                    expr = "(" + "+".join(f'{p["qty"]:g}*{p["expr"]}' for p in parts) + f")/G{sheet_row}"
            else:
                cost = None
            known_issue[key] = {"qty": qty, "cost": cost,
                                "expr": f"'{sheet}'!O{sheet_row}" if cost is not None else None}
        else:
            if op == "STRIN2":
                cost = actual_purchase_cost(m)
                if cost is not None:
                    expr = f"K{sheet_row}"
                    basis = f"تكلفة شراء فعلية واردة من Flow؛ إذن إضافة موردين {doc}"
                else:
                    basis = "سعر الشراء الفعلي غير موجود في حركة المشتريات"
            elif op in ("STRMRT", "STRMR"):
                if op == "STRMRT":
                    src = RAW["return_sources"].get(str(doc), {}).get("out")
                    oldkey = ("STROUT", int(src), item) if src is not None else None
                else:
                    src = RAW["sample_return_links"].get(str(doc))
                    oldkey = ("STRMAK", int(src), item) if src is not None else None
                old = known_issue.get(oldkey) or seed_issue.get(oldkey)
                later_source = (oldkey in current_issue_position and
                                current_issue_position[oldkey][0] == sheet and
                                current_issue_position[oldkey][1] >= sheet_row)
                if old and old["cost"] is not None and not later_source:
                    cost, expr = old["cost"], old["expr"]
                    basis = f"تكلفة صرف {oldkey[0]} {oldkey[1]}"
                else:
                    approved = OVERRIDES.get(f"{op}:{doc}:{item}", {}).get("cost")
                    if approved is not None:
                        cost = float(approved)
                        expr = historical_cost_expr(item, cost)
                        invoice = RAW["return_sources"].get(str(doc), {}).get("inv")
                        basis = f"تكلفة فاتورة المرتجع {invoice or 'القديمة'} المعتمدة"
                    else:
                        lot = pairs[0][0] if len(pairs) == 1 else None
                        cost, expr = prior_known_lot_cost(layers, item, lot)
                        if cost is None:
                            cost, expr = prior_known_lot_cost(base_layers, item, lot)
                        basis = ("تكلفة دفعة موثقة للصنف في الشيت؛ الصرف الأصلي خارج الفترة"
                                 if cost is not None else
                                 f"تكلفة الصرف الأصلي {src or 'غير محدد'} غير متاحة من الشيت")
            else:
                if not pairs and op == "STRROT":
                    basis = "اللوط وتكلفة التسوية المدينة غير موثقين بالمستند"
                else:
                    lot = pairs[0][0] if len(pairs) == 1 else None
                    cost, expr = prior_known_lot_cost(layers, item, lot)
                    if cost is None and pairs:
                        cost, expr = prior_known_lot_cost(base_layers, item, lot)
                    basis = "تكلفة دفعة موثقة باللوط في الشيت" if cost is not None else "تكلفة التحويل الوارد غير محددة من الشيت"
            if cost is not None and expr is None:
                cost = None
            if pairs:
                for lot, q in pairs:
                    layers[item].append({"qty": q, "cost": cost,
                        "expr": f"'{sheet}'!O{sheet_row}" if cost is not None else None,
                        "basis": basis, "lot": lot})
            else:
                layers[item].append({"qty": qty, "cost": cost,
                    "expr": f"'{sheet}'!O{sheet_row}" if cost is not None else None,
                    "basis": basis, "lot": None})
        if cost is None:
            cost_flags.append({"month": month, "op": op, "doc": doc, "item": item,
                               "qty": qty, "basis": basis})
        if not pairs:
            lot_flags.append({"month": month, "op": op, "doc": doc, "item": item,
                              "qty": qty, "reason": lot_status})
        lot_text = "؛ ".join(f"{l} ({q:g})" for l, q in pairs)
        exp_text = "؛ ".join(f"{exp_for(item, l)} ({q:g})" for l, q in pairs)
        rows.append({"month": month, "sheet": sheet, "sheet_row": sheet_row,
                     "movement": m, "cost": cost, "cost_expr": expr,
                     "value": None if cost is None else cost * qty, "basis": basis,
                     "cost_parts": parts, "lot": lot_text, "expiry": exp_text,
                     "lot_status": lot_status})
    seed_issue.update(known_issue)
    seed_lots.update(known_lots)

assert dict(month_row) == {"2026-07": 119, "2026-08": 136}
june = defaultdict(float)
for r in PRIOR["count"]:
    june[str(r["item"])] += float(r["qty"])
aug = defaultdict(float)
for r in count:
    aug[r["item"]] += r["qty"]
flow = defaultdict(float)
for m in MOVES:
    flow[str(m["ITNO"])] += float(m["q"]) * (1 if m["e"] == "A" else -1)
assert all(abs(june[i] + flow[i] - aug[i]) < 1e-8 for i in set(june) | set(flow) | set(aug))

lot_roll = defaultdict(float)
for r in PRIOR["count"]:
    lot_roll[(str(r["item"]), canonical_lot(str(r["item"]), r["lot"]))] += float(r["qty"])
unassigned = defaultdict(float)
for r in rows:
    m = r["movement"]
    sign = 1 if m["e"] == "A" else -1
    found = parse_prior_lots(r["lot"])
    if found:
        for lot, q in found:
            lot_roll[(str(m["ITNO"]), lot.strip())] += sign * q
    else:
        unassigned[str(m["ITNO"])] += sign * float(m["q"])
aug_lot = defaultdict(float)
for r in count:
    aug_lot[(r["item"], r["lot"])] += r["qty"]
lot_diffs = []
for key in sorted(set(lot_roll) | set(aug_lot)):
    if abs(lot_roll[key] - aug_lot[key]) > 1e-8:
        lot_diffs.append({"item": key[0], "lot": key[1],
                          "ledger": lot_roll[key], "count": aug_lot[key],
                          "diff": aug_lot[key] - lot_roll[key]})

out = {"source": {"flow_lines": len(MOVES), "count_file": count_path.name,
                  "count_sha256": hashlib.sha256(count_path.read_bytes()).hexdigest()},
       "cost_methodology": ("Purchase receipts use actual Flow ITPRICE/pr as authorized on 2026-09-28. "
                            "movement.cost is retained as Flow-reported raw data only and is never "
                            "used for calculated movement costs, which follow sheet batches by lot/expiry."),
       "rows": rows, "count": count, "cost_flags": cost_flags, "lot_flags": lot_flags,
       "lot_cost_conflicts": conflicts, "month_rows": dict(month_row),
       "lot_diffs": lot_diffs, "unassigned_net_qty": dict(unassigned),
       "june_qty": sum(june.values()), "aug_qty": sum(aug.values()),
       "ending_layers": {i: [l for l in arr if l["qty"] > 1e-8] for i, arr in layers.items()}}
(HERE / "prepared.json").write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str))
print(json.dumps({"rows": len(rows), "month_rows": dict(month_row),
                  "june_qty": out["june_qty"], "aug_qty": out["aug_qty"],
                  "missing_cost": len(cost_flags), "missing_lot": len(lot_flags),
                  "lot_cost_conflicts": len(conflicts), "lot_diffs": len(lot_diffs),
                  "cost_flags": cost_flags[:25],
                  "conflicts": conflicts[:15]}, ensure_ascii=False))
