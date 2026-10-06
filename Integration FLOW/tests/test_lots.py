from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from flow.lots import Catalog, Ledger, load_count, reanchor, split_remark, lots_in_segment

CATALOG = {
    "items": {"105": {"36112025001": "3-1-2028", "36112025003": "15-3-2028"},
              "108": {"36142025001": "7-1-2028"}},
    "aliases": {"105": {"3611202500": "36112025001"}},
}


def mv(op, doc, item, e, q, pr=700.0, rmk="", dt="2026-06-01"):
    return {"OPCODE": op, "DOCNO": doc, "dt": dt, "ITNO": item, "e": e, "q": q, "pr": pr,
            "RMK": rmk, "DISTNA": ""}


class LotLedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "cat.json").write_text(json.dumps(CATALOG), encoding="utf-8")
        self.cat = Catalog(self.tmp / "cat.json")

    def test_remark_split_by_item_marker(self):
        seg = split_remark("(105) 15/3/2028 36112025003 (108) 7/1/2028", ["105", "108"])
        self.assertEqual(lots_in_segment(self.cat, "105", seg["105"]), ["36112025003"])
        self.assertEqual(lots_in_segment(self.cat, "108", seg["108"]), ["36142025001"])

    def test_lot_found_by_expiry_when_number_missing(self):
        self.assertEqual(lots_in_segment(self.cat, "105", " 3/1/2028 "), ["36112025001"])

    def test_partial_return_from_mixed_price_source_stays_unresolved(self):
        led = Ledger(self.cat)
        led.return_sources = {3: {"out": 2, "cost": {"105": 1400}}}
        led.lot("105", "36112025003").batches.append(__import__("flow.lots", fromlist=["Batch"]).Batch(5, 600, "old"))
        led.run([mv("STRIN2", 1, "105", "A", 5, 800, "(105) 36112025003"),
                 mv("STROUT", 2, "105", "S", 6, rmk="(105) 36112025003", dt="2026-06-02"),
                 mv("STRMRT", 3, "105", "A", 1, 1400, "(105) 36112025003", dt="2026-06-03")])
        batches = [(b.qty, b.cost) for b in led.lot("105", "36112025003").batches]
        self.assertEqual(batches, [(4, 800), (1, None)])

    def test_actual_purchase_price_is_imported_without_invoice_match(self):
        led = Ledger(self.cat)
        receipt = mv("STRIN2", 1, "105", "A", 5, 800, "(105) 36112025003")
        receipt["cost"] = 9999  # calculated Flow COST must not replace ITPRICE/pr
        led.run([receipt])
        self.assertEqual(led.lot("105", "36112025003").value, 4000)

    def test_return_uses_source_lot_instead_of_flow_cost(self):
        led = Ledger(self.cat, return_sources={4: {"out": 3, "cost": {"105": 9999}}})
        led.run([mv("STRIN2", 1, "105", "A", 5, 600, "(105) 36112025001"),
                 mv("STRIN2", 2, "105", "A", 5, 800, "(105) 36112025003"),
                 mv("STROUT", 3, "105", "S", 2, 9999, "(105) 36112025003", dt="2026-06-02"),
                 mv("STRMRT", 4, "105", "A", 1, 9999, "(105) 36112025003", dt="2026-06-03")])
        self.assertEqual(led.log[-1]["value"], 800)

    def test_missing_receipt_price_does_not_fall_back_to_flow_cost(self):
        led = Ledger(self.cat)
        receipt = mv("STRIN2", 1, "105", "A", 5, None, "(105) 36112025003")
        receipt["cost"] = 9999
        led.run([receipt])
        self.assertIsNone(led.lot("105", "36112025003").value)

    def test_count_relabels_only_when_item_total_agrees(self):
        led = Ledger(self.cat)
        led.run([mv("STRIN2", 1, "105", "A", 10, rmk="(105) 36112025001"),
                 mv("STRIN2", 2, "108", "A", 5, rmk="(108) 36142025001")])
        (self.tmp / "c.json").write_text(json.dumps({"as_of": "2026-06-30", "lines": [
            ["105", "36112025001", 4], ["105", "36112025003", 6], ["108", "36142025001", 3]]}),
            encoding="utf-8")
        moves = reanchor(led, load_count(self.tmp / "c.json"), "2026-06-30")
        self.assertEqual([(m["item"], m["to"], m["qty"]) for m in moves], [("105", "36112025003", 6)])
        self.assertEqual(led.lot("108", "36142025001").qty, 5)   # total differs: left alone


if __name__ == "__main__":
    unittest.main()
