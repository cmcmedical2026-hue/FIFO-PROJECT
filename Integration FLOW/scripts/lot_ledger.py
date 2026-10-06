"""Lot / expiry / cost ledger for one store, rebuilt from Flow. Read-only.

Replays every stock movement since a counted opening balance, assigns each
line to a lot from its remark, re-anchors lots at each physical count, and
prints the balance by lot with the cost of every batch.

    python scripts/lot_ledger.py                       # balance as of today
    python scripts/lot_ledger.py --to 2026-08-31       # as of a date
    python scripts/lot_ledger.py --since 2026-09-01    # also list that period's lines
    python scripts/lot_ledger.py --json out.json       # full result for a report
    python scripts/lot_ledger.py --xlsx out.xlsx       # workbook (needs openpyxl)

The rules (lot from remark, cost per purchase batch, no averages) are in
skills/flow-erp-inventory-lots/SKILL.md. Inputs live in data/inventory/.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import _bootstrap  # noqa: F401  (puts src/ on the path)

from flow import FlowClient
from flow.lots import (Catalog, Ledger, compare, fetch_movements, fetch_return_sources,
                       load_count, reanchor)

DATA = Path(__file__).resolve().parents[1] / "data" / "inventory"


def emit(label: str, obj) -> None:
    print(label, json.dumps(obj, ensure_ascii=False, default=str))


def _build(client, to: str | None, data_dir: Path = DATA, movements: list | None = None,
          names: dict | None = None, returns: dict | None = None,
          known_issue_cost: dict | None = None, known_issue_batches: dict | None = None) -> dict:
    plan = json.loads((data_dir / "plan.json").read_text(encoding="utf-8"))
    cat = Catalog(data_dir / plan["catalog"])
    overrides = json.loads((data_dir / plan["overrides"]).read_text(encoding="utf-8"))["overrides"]
    ledger = Ledger(cat, overrides)
    opening = ledger.load_opening(data_dir / plan["opening"])
    start = str((__import__("datetime").date.fromisoformat(opening)
                 + __import__("datetime").timedelta(days=1)))
    if returns is None:
        returns = fetch_return_sources(client, start, plan["cono"], plan["strno"])
    ledger.return_sources = returns
    ledger.known_issue_cost = known_issue_cost or {}
    ledger.known_issue_batches = known_issue_batches or {}
    if movements is None:
        movements = fetch_movements(client, start, None, plan["cono"], plan["strno"])
    mv = [m for m in movements if not to or m["dt"][:10] <= to]
    checkpoints = []
    since = None
    for name in plan["checkpoints"]:
        count = load_count(data_dir / name)
        if to and count["as_of"] > to:
            break
        ledger.run(mv, since=since, upto=count["as_of"])
        before = compare(ledger, count)
        moves = reanchor(ledger, count, count["as_of"])
        after = compare(ledger, count)
        checkpoints.append({"count": name, "count_path": str(data_dir / name),
                            "as_of": count["as_of"], "diffs_before": before,
                            "relabels": moves, "diffs_after": after})
        since = str(__import__("datetime").date.fromisoformat(count["as_of"])
                    + __import__("datetime").timedelta(days=1))
    ledger.run(mv, since=since, upto=to)
    if names is None:
        names = {str(i["ITNO"]): i.get("ITDES", "") for i in client.items()}
    return {"issue_cost": ledger.issue_cost, "issue_batches": ledger.issue_batches, "all_movements": movements, "all_returns": returns, "opening": opening, "to": to or (mv[-1]["dt"][:10] if mv else opening),
            "movements": len(mv), "checkpoints": checkpoints, "balance": ledger.snapshot(),
            "log": ledger.log, "flags": ledger.flags, "names": names}


def build(client, to: str | None, data_dir: Path = DATA, movements: list | None = None,
          names: dict | None = None, returns: dict | None = None) -> dict:
    """Two passes: a sales return is costed at its issue voucher's cost, and a
    voucher dated the same day as its return is only known after one pass."""
    first = _build(client, to, data_dir, movements, names, returns)
    res = _build(client, to, data_dir, first["all_movements"], first["names"],
                 first["all_returns"], first["issue_cost"], first["issue_batches"])
    res.pop("issue_cost")
    res.pop("issue_batches")
    return res


def by_lot(balance: list[dict]) -> list[dict]:
    agg: dict = defaultdict(lambda: {"qty": 0.0, "value": 0.0, "unknown_cost": False})
    for r in balance:
        a = agg[(r["item"], r["lot"], r["exp"])]
        a["qty"] += r["qty"]
        if r["value"] is None:
            a["unknown_cost"] = True
        elif not a["unknown_cost"]:
            a["value"] += r["value"]
    return [{"item": k[0], "lot": k[1], "exp": k[2], "qty": v["qty"],
             "value": None if v["unknown_cost"] else round(v["value"], 2)}
            for k, v in agg.items() if abs(v["qty"]) > 1e-9]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--to", help="last movement date to include (YYYY-MM-DD); default today")
    ap.add_argument("--since", help="print every movement line from this date")
    ap.add_argument("--json", help="write the full result to this file")
    ap.add_argument("--xlsx", help="write a workbook to this file (needs openpyxl)")
    ap.add_argument("--data", default=str(DATA), help="inputs folder (default data/inventory)")
    args = ap.parse_args()

    client = FlowClient()
    client.login()
    res = build(client, args.to, Path(args.data))

    for cp in res["checkpoints"]:
        emit("CHECKPOINT", {"count": cp["count"], "as_of": cp["as_of"],
                            "relabels": len(cp["relabels"]), "open_diffs": cp["diffs_after"]})
    if args.since:
        for row in res["log"]:
            if row["date"] >= args.since:
                emit("LINE", row)
    for row in by_lot(res["balance"]):
        emit("LOT", dict(row, name=res["names"].get(row["item"], "")))
    tot_q = sum(r["qty"] for r in res["balance"])
    tot_v = None if any(r["value"] is None for r in res["balance"]) else sum(r["value"] for r in res["balance"])
    emit("TOTAL", {"to": res["to"], "qty": tot_q, "value": round(tot_v, 2),
                   "movements": res["movements"],
                   "guessed_lines": sum(1 for f in res["flags"] if "no lot" in f["why"])})
    if args.json:
        Path(args.json).write_text(json.dumps({k: v for k, v in res.items() if not k.startswith("all_")}, ensure_ascii=False, default=str, indent=1),
                                   encoding="utf-8")
    if args.xlsx:
        from flow.lots_report import write_xlsx   # openpyxl only needed here
        data_dir = Path(args.data)
        plan = json.loads((data_dir / "plan.json").read_text(encoding="utf-8"))
        at = None
        if res["checkpoints"]:
            at = build(client, res["checkpoints"][-1]["as_of"], data_dir,
                       movements=res["all_movements"], names=res["names"],
                       returns=res["all_returns"])
        qfile = data_dir / "questions.json"
        questions = json.loads(qfile.read_text(encoding="utf-8"))["open"] if qfile.exists() else None
        write_xlsx(res, args.xlsx, snapshot_at=at, questions=questions,
                   opening_path=str(data_dir / plan["opening"]))
        emit("WROTE", {"xlsx": args.xlsx})
    return 0


if __name__ == "__main__":
    sys.exit(main())
