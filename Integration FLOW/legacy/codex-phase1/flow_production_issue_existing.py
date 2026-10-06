"""Read-only verification of Production Issues already linked to the requested orders."""

import json
from pathlib import Path

from flow_sales_request import api_get, getrec, login


HAR_PATH = Path(r"C:\Users\hp\Downloads\Sales Order.har")
TARGETS = ((989, 49, 975, {"105", "107", "108"}),
           (988, 346, 976, {"6"}))


def rows(value):
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    return []


def main():
    entries = json.loads(HAR_PATH.read_text(encoding="utf-8-sig"))["log"]["entries"]
    key = login(entries)
    for orderno, customer, issueno, items in TARGETS:
        links = rows(getrec(entries,
            "select opcode,docno,cono,strno,distno,sts,post,srcdocno,docdt "
            "from trnhdr where opcode='STROUT' and cono=1 and strno='1' "
            f"and srcdocno={orderno}", key))
        issue = api_get(f"/api/POSCMD/GETDOC/STROUT/1/1/{issueno}", key)
        order = api_get(f"/api/POSCMD/GETDOC/SALORD/1/1/{orderno}", key)
        if not isinstance(issue, dict) or not isinstance(order, dict):
            raise RuntimeError("Linked issue/order retrieval failed")
        lines = rows(issue.get("DTL"))
        print("ISSUE=" + json.dumps({"target_order": orderno, "expected_customer": customer,
            "expected_items": sorted(items), "links": links,
            "header": {k: issue.get(k) for k in ("OP", "DOCNO", "CONO", "STRNO", "DISTNO",
                "SRCDOCNO", "DOCDT", "RMK", "STS", "POST", "DOCTOT", "DOCNET")},
            "lines": [{k: line.get(k) for k in ("ITNO", "QTY", "EXEQTY", "ITPRICE",
                "SALTAX", "ITSALTAX", "TotalTaxes", "LOCID", "PCKID", "UNTID",
                "BINDTL", "EXPDT", "RMK", "LOTNO", "LOT", "BATCHNO")}
                for line in lines],
            "order_line_balances": [{k: line.get(k) for k in ("ITNO", "QTY", "EXEQTY")}
                for line in rows(order.get("DTL"))]}, ensure_ascii=True))


if __name__ == "__main__":
    main()
