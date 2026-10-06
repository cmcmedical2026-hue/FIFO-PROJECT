"""Lot / expiry / cost ledger for one store, rebuilt from Flow movements.

Flow keeps quantity per item but not per lot, and its running cost is an
average. The General Manager wants neither: every purchase batch keeps its own
purchase price, and every lot is tracked by the lot/expiry written in the
document remark. This module replays Flow's stock movements on top of a counted
opening balance and applies those rules.

Rules (agreed with the user; see skills/flow-erp-inventory-lots/SKILL.md):

* Quantity comes from Flow: ``trndtl`` rows with ``STS='A'`` and
  ``EFFECTITBAL`` ``A`` (in) or ``S`` (out); the quantity is ``STRQTY``,
  which includes bonus units.
* Lot, in this order: an explicit override → the lot written in the remark →
  the earliest-expiring lot that still has stock (flagged as a guess).
* Cost: Flow's purchase receipt (``STRIN2``) ``pr`` / ``ITPRICE`` is the actual
  incoming cost, as clarified by the user on 2026-09-28. A purchase creates a
  batch at that price. An issue consumes the oldest batch of its lot. A return
  uses reconstructed sheet-batch cost; Flow's calculated invoice/issue cost
  is retained as raw reference data only. A transfer follows its source batch.

Read-only: nothing here writes to Flow.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

PURCHASE_OPS = {"STRIN2"}          # new batch at purchase price
RETURN_OPS = {"STRMRT", "STRIN9", "STRMR", "STRROT"}   # back at cost it left with

DATE_RE = re.compile(r"(?<![\d])(\d{1,2})\s*[/\-]\s*(\d{1,2})\s*[/\-]\s*(20\d\d)(?![\d])"
                     r"|(?<![\d/\-])(\d{1,2})\s*[/\-]\s*(20\d\d)(?![\d])")
MARK_RE = re.compile(r"\(\s*([A-Za-z0-9.\- ]{1,12}?)\s*\)")


def norm_lot(s: str) -> str:
    return re.sub(r"\s+", "", str(s)).upper()


def norm_date(s: str) -> str:
    m = DATE_RE.search(s)
    if not m:
        return ""
    if m.group(1):
        return f"{int(m.group(1))}-{int(m.group(2))}-{m.group(3)}"
    return f"{int(m.group(4))}-{m.group(5)}"


@dataclass
class Batch:
    qty: float
    cost: float | None
    src: str


@dataclass
class Lot:
    item: str
    lot: str
    batches: list = field(default_factory=list)
    consumed: list = field(default_factory=list)   # (qty, cost) most recent last

    @property
    def qty(self) -> float:
        return sum(b.qty for b in self.batches)

    @property
    def value(self) -> float | None:
        if any(b.cost is None for b in self.batches):
            return None
        return sum(b.qty * b.cost for b in self.batches)


class Catalog:
    def __init__(self, path: Path):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        self.items: dict[str, dict[str, str]] = data["items"]
        self.aliases: dict[str, dict[str, str]] = data.get("aliases", {})

    def expiry(self, item: str, lot: str) -> str:
        return self.items.get(item, {}).get(lot, "")

    def canonical(self, item: str, token: str) -> str | None:
        t = norm_lot(token)
        for lot in self.items.get(item, {}):
            if norm_lot(lot) == t:
                return lot
        for alias, lot in self.aliases.get(item, {}).items():
            if norm_lot(alias) == t:
                return lot
        return None

    def by_date(self, item: str, date: str) -> list[str]:
        return [lot for lot, exp in self.items.get(item, {}).items() if exp == date]


def split_remark(rmk: str, doc_items: list[str]) -> dict[str, str]:
    """Cut a header remark into per-item segments keyed by item code."""
    text = (rmk or "").replace("\n", " ")
    marks = []
    wanted = {norm_lot(i): i for i in doc_items}
    wanted.update({"BATTRY": "BATTERY", "ES60-2.6": "ESA60-2.6"})
    for m in MARK_RE.finditer(text):
        key = norm_lot(m.group(1))
        if key in wanted and wanted[key] in doc_items:
            marks.append((m.start(), m.end(), wanted[key]))
    for m in re.finditer(r"(?:كود\s*)?(?<![\w/\-])(\d{1,5})\s*\(", text):
        if m.group(1) in doc_items and not any(s <= m.start() < e for s, e, _ in marks):
            marks.append((m.start(), m.end() - 1, m.group(1)))
    for m in re.finditer(r"كود\s*(\d{1,5})", text):
        if m.group(1) in doc_items and not any(s <= m.start() < e for s, e, _ in marks):
            marks.append((m.start(), m.end(), m.group(1)))
    marks.sort()
    if not marks:
        return {i: text for i in doc_items} if len(doc_items) == 1 else {"*": text}
    out: dict[str, str] = {}
    for n, (s, e, item) in enumerate(marks):
        end = marks[n + 1][0] if n + 1 < len(marks) else len(text)
        out[item] = out.get(item, "") + " " + text[e:end]
    return out


def lots_in_segment(cat: Catalog, item: str, seg: str) -> list[str]:
    """Distinct canonical lots named in a segment, by lot number first, then by expiry."""
    found: list[str] = []
    for tok in re.findall(r"[A-Za-z0-9][A-Za-z0-9\-]{3,}", seg.replace(" 0", " 0")):
        if DATE_RE.fullmatch(tok):
            continue
        lot = cat.canonical(item, tok)
        if lot and lot not in found:
            found.append(lot)
    joined = re.sub(r"(\d{8})\s+(\d{3})\b", r"\1\2", seg)   # "36112025 017"
    if joined != seg:
        for tok in re.findall(r"[A-Za-z0-9]{4,}", joined):
            lot = cat.canonical(item, tok)
            if lot and lot not in found:
                found.append(lot)
    if not found:
        for m in DATE_RE.finditer(seg):
            d = norm_date(m.group(0))
            for lot in cat.by_date(item, d):
                if lot not in found:
                    found.append(lot)
    if not found and len(cat.items.get(item, {})) == 1:
        found = list(cat.items[item])
    return found


class Ledger:
    def __init__(self, catalog: Catalog, overrides: dict | None = None,
                 return_sources: dict | None = None, purchase_costs: dict | None = None):
        self.cat = catalog
        self.return_sources = return_sources or {}
        self.issue_cost: dict[tuple, list] = {}     # (op, doc, item) -> [qty, value]
        self.known_issue_cost: dict[tuple, list] = {}   # from a previous pass (same-day returns)
        self.issue_batches: dict[tuple, list] = {}
        self.known_issue_batches: dict[tuple, list] = {}
        self.lots: dict[tuple[str, str], Lot] = {}
        self.overrides = overrides or {}
        self.purchase_costs = purchase_costs or {}
        self.log: list[dict] = []
        self.flags: list[dict] = []

    def lot(self, item: str, lot: str) -> Lot:
        key = (item, lot)
        if key not in self.lots:
            self.lots[key] = Lot(item, lot)
        return self.lots[key]

    def load_opening(self, path: Path) -> str:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        for item, lot, qty, cost, src in data["batches"]:
            self.lot(str(item), lot).batches.append(Batch(qty, cost, src))
        return data["date"]

    # -- lot choice ------------------------------------------------------------
    def fefo(self, item: str, qty: float, exclude=()) -> list[tuple[str, float]]:
        def key(l):
            e = self.cat.expiry(item, l.lot)
            p = [int(x) for x in re.findall(r"\d+", e)] if e else []
            if len(p) == 3:
                return (p[2], p[1], p[0])
            if len(p) == 2:
                return (p[1], p[0], 28)
            return (9999, 0, 0)
        cands = sorted((l for (i, _), l in self.lots.items()
                        if i == item and l.qty > 0 and l.lot not in exclude), key=key)
        out, left = [], qty
        for l in cands:
            take = min(left, l.qty)
            if take > 0:
                out.append((l.lot, take))
                left -= take
            if left <= 0:
                break
        if left > 0:
            first = cands[0].lot if cands else next(iter(self.cat.items.get(item, {"?": ""})))
            out.append((first, left))
        return out

    def choose(self, mv: dict, seg: dict[str, str]) -> tuple[list[tuple[str, float]], str]:
        key = f"{mv['OPCODE']}:{mv['DOCNO']}:{mv['ITNO']}"
        item, qty = mv["ITNO"], float(mv["q"])
        if "lots" in self.overrides.get(key, {}):
            o = self.overrides[key]
            return [(l, float(q)) for l, q in o["lots"]], "override"
        text = seg.get(item) or seg.get("*", "")
        lots = lots_in_segment(self.cat, item, text) if text.strip() else []
        if len(lots) == 1:
            return [(lots[0], qty)], "remark"
        if len(lots) > 1:
            self.flags.append({"key": key, "why": "several lots in remark, split by FEFO among them",
                               "lots": lots})
            if mv["e"] == "S":
                picked, left = [], qty
                for l in lots:
                    have = self.lot(item, l).qty
                    take = min(left, have)
                    if take > 0:
                        picked.append((l, take)); left -= take
                if left > 0:
                    picked.append((lots[0], left))
                return picked, "remark-split"
            return [(lots[0], qty)], "remark-split"
        if mv["e"] == "S":
            return self.fefo(item, qty), "fefo"
        known = list(self.cat.items.get(item, {}))
        return [(known[0] if known else "?", qty)], "default"

    # -- movement --------------------------------------------------------------
    def apply(self, mv: dict, seg: dict[str, str]):
        item, op = mv["ITNO"], mv["OPCODE"]
        key = f"{op}:{int(mv['DOCNO'])}:{item}"
        picks, how = self.choose(mv, seg)
        if how in ("fefo", "default"):
            self.flags.append({"key": f"{op}:{mv['DOCNO']}:{item}", "why": f"no lot in remark ({how})",
                               "lots": [p[0] for p in picks]})
        ov = self.overrides.get(f"{op}:{mv['DOCNO']}:{item}", {})
        for lot_name, q in picks:
            lot = self.lot(item, lot_name)
            if mv["e"] == "A":
                if op in PURCHASE_OPS:
                    cost = float(mv["pr"]) if mv.get("pr") is not None else None
                    if cost is None:
                        self.flags.append({"key": key,
                            "why": "actual incoming purchase price ITPRICE/pr is missing"})
                    elif cost <= 1:
                        self.flags.append({"key": key, "why": "zero or unusual actual purchase price retained",
                                           "purchase_unit_cost": cost})
                elif "cost" in ov:
                    cost = float(ov["cost"])
                elif op == "STRMRT" and int(mv["DOCNO"]) in self.return_sources:
                    cost = self.invoice_cost(mv["DOCNO"], item, lot_name, q)
                    if cost is None:
                        self.flags.append({"key": key, "why": "source return batch unresolved by lot; Flow COST ignored"})
                else:
                    cost = self.return_cost(item, lot)
                lot.batches.append(Batch(q, cost, f"{op} {mv['DOCNO']}"))
                val = q * cost if cost is not None else None
            else:
                consumed_before = len(lot.consumed)
                val = self.consume(lot, q, f"{op} {mv['DOCNO']}")
                parts = self.issue_batches.setdefault((op, mv["DOCNO"], item), [])
                parts.extend({"lot": lot_name, "qty": amount, "cost": cost}
                             for amount, cost in lot.consumed[consumed_before:])
                ic = self.issue_cost.setdefault((op, mv["DOCNO"], item), [0.0, 0.0])
                ic[0] += q
                if val is None:
                    ic[1] = None
                elif ic[1] is not None:
                    ic[1] += val
            self.log.append({"date": mv["dt"][:10], "op": op, "doc": mv["DOCNO"], "item": item,
                             "lot": lot_name, "exp": self.cat.expiry(item, lot_name),
                             "dir": mv["e"], "qty": q,
                             "value": round(val, 2) if val is not None else None, "how": how,
                             "party": (mv.get("DISTNA") or "").strip(),
                             "remark": (mv.get("RMK") or "").replace("\n", " ").strip()})

    def invoice_cost(self, mrt_doc, item: str, lot_name: str | None = None,
                     qty: float | None = None) -> float | None:
        """A sales return uses its reconstructed source issue, never Flow COST."""
        src = self.return_sources.get(int(mrt_doc))
        if not src:
            return None
        key = ("STROUT", src["out"], item)
        batches = self.issue_batches.get(key) or self.known_issue_batches.get(key)
        if batches:
            matching = [b for b in batches if lot_name is None or b["lot"] == lot_name]
            costs = {b["cost"] for b in matching}
            if matching and len(costs) == 1 and None not in costs and (
                    qty is None or qty <= sum(b["qty"] for b in matching) + 1e-9):
                return next(iter(costs))
            return None
        if lot_name is not None:
            return None
        issued = self.issue_cost.get(key) or self.known_issue_cost.get(key)
        if issued and issued[0] > 0 and issued[1] is not None:
            return issued[1] / issued[0]
        # Flow's invoice COST is calculated; keep it out of batch valuation.
        return None

    def return_cost(self, item: str, lot: Lot) -> float | None:
        costs = {cost for _, cost in lot.consumed} | {b.cost for b in lot.batches}
        return next(iter(costs)) if len(costs) == 1 else None

    def consume(self, lot: Lot, qty: float, src: str) -> float | None:
        left, val = qty, 0.0
        while left > 1e-9 and lot.batches:
            b = lot.batches[0]
            take = min(left, b.qty)
            b.qty -= take
            left -= take
            if b.cost is None:
                val = None
            elif val is not None:
                val += take * b.cost
            lot.consumed.append((take, b.cost))
            if b.qty <= 1e-9:
                lot.batches.pop(0)
        if left > 1e-9:
            cost = lot.consumed[-1][1] if lot.consumed else self.return_cost(lot.item, lot)
            lot.batches.insert(0, Batch(-left, cost, "NEGATIVE " + src))
            self.flags.append({"key": src + ":" + lot.item, "why": f"lot {lot.lot} went negative by {left:g}",
                               "lots": [lot.lot]})
            if cost is None:
                val = None
            elif val is not None:
                val += left * cost
        return val

    def run(self, movements: list[dict], upto: str | None = None, since: str | None = None):
        bydoc: dict[tuple, list] = defaultdict(list)
        for mv in movements:
            bydoc[(mv["OPCODE"], mv["DOCNO"])].append(mv)
        done = set()
        for mv in movements:
            if upto and mv["dt"][:10] > upto:
                break
            if since and mv["dt"][:10] < since:
                continue
            k = (mv["OPCODE"], mv["DOCNO"])
            if k in done:
                continue
            done.add(k)
            lines = bydoc[k]
            seg = split_remark(lines[0].get("RMK") or "", [x["ITNO"] for x in lines])
            for x in lines:
                self.apply(x, seg)

    def snapshot(self) -> list[dict]:
        rows = []
        for (item, lot), l in sorted(self.lots.items(), key=lambda kv: (kv[0][0].zfill(8), kv[0][1])):
            for b in l.batches:
                if abs(b.qty) > 1e-9:
                    rows.append({"item": item, "lot": lot, "exp": self.cat.expiry(item, lot),
                                 "qty": b.qty, "cost": b.cost,
                                 "value": round(b.qty * b.cost, 2) if b.cost is not None else None,
                                 "batch": b.src})
        return rows


def _read(client, sql: str, attempts: int = 3) -> list:
    """getrec with a short retry. Only for SELECTs: a read is safe to repeat."""
    import time
    for n in range(attempts):
        try:
            return client.getrec(sql)
        except Exception as exc:          # FlowError on a reset connection
            if n == attempts - 1 or "Network error" not in str(exc):
                raise
            time.sleep(2 * (n + 1))
    return []


def fetch_return_sources(client, date_from: str, cono: str = "1", strno: str = "1") -> dict:
    """STRMRT -> SALRT2 -> SALINV -> STROUT, with the invoice's per-item cost."""
    sql = ("select m.DOCNO mrt, i.DOCNO inv, i.SRCDOCNO outdoc, d.ITNO, d.COST cost "
           "from trnhdr m join trnhdr r on r.CONO=m.CONO and r.OPCODE='SALRT2' and r.DOCNO=m.SRCDOCNO "
           "join trnhdr i on i.CONO=m.CONO and i.OPCODE='SALINV' and i.DOCNO=r.SRCDOCNO "
           "join trndtl d on d.CONO=i.CONO and d.OPCODE='SALINV' and d.DOCNO=i.DOCNO and d.STRNO=i.STRNO "
           f"where m.CONO={int(cono)} and m.STRNO={int(strno)} and m.OPCODE='STRMRT' and m.STS='A' "
           f"and r.STS='A' and i.STS='A' and d.STS='A' and m.DOCDT>='{date_from}'")
    out: dict = {}
    for row in _read(client, sql):
        src = out.setdefault(int(row["mrt"]), {"inv": row["inv"], "out": row["outdoc"], "cost": {}})
        src["cost"].setdefault(str(row["ITNO"]), float(row["cost"]))
    return out


def fetch_movements(client, date_from: str, date_to: str | None = None,
                    cono: str = "1", strno: str = "1") -> list[dict]:
    """Every active in/out line for one store, oldest first, with its header remark."""
    to = f" and d.DOCDT<='{date_to}'" if date_to else ""
    sql = ("select d.OPCODE,d.DOCNO,d.DOCDT dt,d.ITNO,d.EFFECTITBAL e,d.STRQTY q,d.BQTY bq,"
           "d.ITPRICE pr,d.COST cost,h.DISTNA,h.RMK from trndtl d join trnhdr h on "
           "h.CONO=d.CONO and h.STRNO=d.STRNO and h.OPCODE=d.OPCODE and h.DOCNO=d.DOCNO "
           f"where d.CONO={int(cono)} and d.STRNO={int(strno)} and d.STS='A' "
           f"and d.EFFECTITBAL in ('A','S') and d.DOCDT>='{date_from}'{to} "
           "order by d.DOCDT, case d.EFFECTITBAL when 'A' then 0 else 1 end, d.OPCODE, d.DOCNO")
    return [dict(r, dt=str(r["dt"])) for r in _read(client, sql)]


def load_count(path: Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    lines: dict[tuple[str, str], float] = defaultdict(float)
    for row in data["lines"]:
        lines[(str(row[0]), row[1])] += float(row[2])
    return {"as_of": data["as_of"], "lines": dict(lines),
            "not_counted": set(data.get("not_counted", []))}


def compare(ledger: Ledger, count: dict) -> list[dict]:
    """Lot-level and item-level differences between the ledger and a count."""
    sim: dict[tuple[str, str], float] = defaultdict(float)
    for (item, lot), l in ledger.lots.items():
        sim[(item, lot)] += l.qty
    items = {k[0] for k in sim if abs(sim[k]) > 1e-9} | {k[0] for k in count["lines"]}
    out = []
    for item in sorted(items, key=lambda i: i.zfill(8)):
        if item in count["not_counted"]:
            continue
        keys = sorted({k for k in list(sim) + list(count["lines"]) if k[0] == item})
        s_tot = sum(sim.get(k, 0) for k in keys)
        c_tot = sum(count["lines"].get(k, 0) for k in keys)
        for k in keys:
            s, c = sim.get(k, 0), count["lines"].get(k, 0)
            if abs(s - c) > 1e-9:
                out.append({"item": item, "lot": k[1], "ledger": s, "count": c, "diff": c - s,
                            "item_ledger": s_tot, "item_count": c_tot})
    return out


def reanchor(ledger: Ledger, count: dict, date: str) -> list[dict]:
    """Move quantity between lots of an item so the ledger matches a count.

    Only where the item's total already agrees: a lot mix-up is a relabel, but
    a total difference is a real gain or loss and is left for the user.
    Batches move with their own cost, so a relabel never changes value; the
    returned rows say when the moved cost differs from the target lot's.
    """
    moves = []
    diffs = compare(ledger, count)
    by_item: dict[str, list] = defaultdict(list)
    for d in diffs:
        by_item[d["item"]].append(d)
    for item, rows in by_item.items():
        if abs(rows[0]["item_ledger"] - rows[0]["item_count"]) > 1e-9:
            continue
        need = [(r["lot"], r["diff"]) for r in rows if r["diff"] > 0]
        spare = [[r["lot"], -r["diff"]] for r in rows if r["diff"] < 0]
        for lot_to, q in need:
            while q > 1e-9 and spare:
                lot_from, have = spare[0]
                take = min(q, have)
                src = ledger.lot(item, lot_from)
                dst = ledger.lot(item, lot_to)
                left = take
                while left > 1e-9:
                    b = src.batches[0] if src.batches else Batch(0, 0, "")
                    if b.qty <= 1e-9:
                        # negative or empty source: carry the target's own cost
                        cost = dst.batches[0].cost if dst.batches else ledger.return_cost(item, dst)
                        src.batches.insert(0, Batch(-left, cost, "RELABEL " + date))
                        dst.batches.append(Batch(left, cost, "RELABEL " + date))
                        left = 0
                        break
                    t = min(left, b.qty)
                    b.qty -= t
                    if b.qty <= 1e-9:
                        src.batches.pop(0)
                    dst.batches.append(Batch(t, b.cost, f"RELABEL {date} from {lot_from}"))
                    left -= t
                src.batches = [x for x in src.batches if abs(x.qty) > 1e-9]
                # net out a negative batch against positives in the same lot
                neg = [x for x in src.batches if x.qty < 0]
                for n in neg:
                    for x in src.batches:
                        if x.qty > 0 and n.qty < 0:
                            t = min(x.qty, -n.qty); x.qty -= t; n.qty += t
                src.batches = [x for x in src.batches if abs(x.qty) > 1e-9]
                moves.append({"date": date, "item": item, "from": lot_from, "to": lot_to, "qty": take})
                ledger.log.append({"date": date, "op": "RELABEL", "doc": "", "item": item, "lot": lot_to,
                                   "exp": ledger.cat.expiry(item, lot_to), "dir": "A", "qty": take,
                                   "value": 0, "how": "count", "party": f"from lot {lot_from}",
                                   "remark": f"مطابقة لوطات على جرد {count['as_of']}"})
                spare[0][1] -= take
                q -= take
                if spare[0][1] <= 1e-9:
                    spare.pop(0)
    settle(ledger, date)
    return moves


def settle(ledger: Ledger, date: str) -> list[dict]:
    """Net a lot's negative batch (an over-issue) against the stock that later
    covered it. The quantity nets to what it should; any cost difference between
    what the over-issue was valued at and the batch that really covered it is a
    correction to cost of goods issued, logged as COST-ADJ."""
    adj = []
    for (item, name), lot in ledger.lots.items():
        for n in [b for b in lot.batches if b.qty < 0]:
            for b in lot.batches:
                if b.qty > 0 and n.qty < 0:
                    t = min(b.qty, -n.qty)
                    delta = None if b.cost is None or n.cost is None else t * (b.cost - n.cost)
                    b.qty -= t
                    n.qty += t
                    if delta is None:
                        ledger.flags.append({"key": f"COST-ADJ:{date}:{item}:{name}",
                                             "why": "cost adjustment unresolved because one or both batches lack purchase-backed cost"})
                    elif abs(delta) > 0.005:
                        adj.append({"item": item, "lot": name, "qty": t, "delta": round(delta, 2)})
                        ledger.log.append({"date": date, "op": "COST-ADJ", "doc": "", "item": item,
                                           "lot": name, "exp": ledger.cat.expiry(item, name), "dir": "S",
                                           "qty": 0, "value": round(delta, 2), "how": "settle", "party": "",
                                           "remark": f"{t:g} اتصرفوا بتكلفة {n.cost:g} وكانوا فعلياً من دفعة {b.cost:g}"})
        lot.batches = [b for b in lot.batches if abs(b.qty) > 1e-9]
    return adj
