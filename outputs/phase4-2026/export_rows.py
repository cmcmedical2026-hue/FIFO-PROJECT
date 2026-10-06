"""Emit small native Google Sheets CellData blocks for the July/August update."""
import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
data = json.loads((HERE / "prepared.json").read_text())

OP = {"STROUT": "Production Issue (STROUT)",
      "STRIN2": "Supplier Receipt (STRIN2)",
      "STRMRT": "Sales Return Receipt (STRMRT)",
      "STROU9": "Store Transfer Issue (STROU9)",
      "STRIN9": "Store Transfer Receipt (STRIN9)",
      "STRMAK": "Sample Issue (STRMAK)", "STRMR": "Sample Return (STRMR)",
      "BURRET": "Purchase Return (BURRET)",
      "STRROT": "Debt Adjustment (STRROT)",
      "STRRTS": "Credit Adjustment (STRRTS)"}

def cell(value=None, formula=None):
    if formula is not None:
        return {"userEnteredValue": {"formulaValue": formula}}
    if value is None:
        return {}
    if isinstance(value, (int, float)):
        return {"userEnteredValue": {"numberValue": value}}
    return {"userEnteredValue": {"stringValue": str(value)}}

def movement_row(r):
    m = r["movement"]
    n = r["sheet_row"]
    purchase = m["OPCODE"] == "STRIN2"
    return {"values": [
        cell(m["dt"][:10]), cell("يوليو" if r["month"] == "2026-07" else "أغسطس"),
        cell(OP[m["OPCODE"]]), cell(int(m["DOCNO"])), cell(str(m["ITNO"])),
        cell("وارد" if m["e"] == "A" else "منصرف"), cell(float(m["q"])),
        cell(formula=f'=IF(F{n}="وارد",G{n},0)'),
        cell(formula=f'=IF(F{n}="منصرف",G{n},0)'),
        cell(float(m["bq"])),
        cell(float(r["cost"])) if purchase and r["cost"] is not None else cell(),
        cell(formula=f"=G{n}*K{n}") if purchase and r["cost"] is not None else cell(),
        cell(m.get("DISTNA") or ""), cell(m.get("RMK") or ""),
        cell(formula="=" + r["cost_expr"]) if r["cost_expr"] else cell(),
        cell(formula=f'=IF(O{n}="","",G{n}*O{n})'),
        cell(r["basis"]), cell(r["lot"]), cell(r["expiry"]), cell(r["lot_status"])]}

def count_row(r):
    note = r["note"]
    if r["source_exp"] != r["exp"]:
        note += f"؛ CSV الصلاحية: {r['source_exp']}"
    return {"values": [cell(r["source_row"]), cell("2026-08-31"),
                       cell(r["item"]), cell(r["qty"]), cell(r["exp"]),
                       cell(r["lot"]), cell(note.strip("؛ ")), cell(r["qty"])]}

ap = argparse.ArgumentParser()
ap.add_argument("--month", choices=["2026-07", "2026-08", "count"], required=True)
ap.add_argument("--start", type=int, default=0)
ap.add_argument("--limit", type=int, default=30)
args = ap.parse_args()
source = data["count"] if args.month == "count" else [r for r in data["rows"] if r["month"] == args.month]
part = source[args.start:args.start + args.limit]
rows = [count_row(x) for x in part] if args.month == "count" else [movement_row(x) for x in part]
print(json.dumps({"start": args.start, "total": len(source), "rows": rows}, ensure_ascii=False,
                 separators=(",", ":")))
