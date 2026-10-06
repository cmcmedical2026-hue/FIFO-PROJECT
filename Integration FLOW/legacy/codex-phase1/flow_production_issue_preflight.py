"""Read-only source, item, stock and lot checks for two proposed Production Issues."""

import json
from pathlib import Path

from flow_sales_request import ERP_HOST, api_get, getrec, har_request, http_json, login


HAR_PATH = Path(r"C:\Users\hp\Downloads\Sales Order.har")
TARGETS = (("Ahmed", 989, 49, {"105": 2, "107": 2, "108": 1}),
           ("Mohamed", 988, 346, {"6": 5}))


def rows(value):
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    return []


def source_candidates(entries, key, customer):
    req = har_request(entries, "/api/srvcmd/getrec")
    body = json.loads(req["postData"]["text"])
    body["CMDTXT"] = "LDSRCHDRNO"
    body["CMDPAR"] = f"OPCODE=STROUT\vCONO=1\vSTRNO=1\vDISTNO={customer}\v"
    body["APIKEY"] = key
    return rows(http_json(f"https://{ERP_HOST}/", method="POST", body=body, api_key=key)[1])


def main():
    entries = json.loads(HAR_PATH.read_text(encoding="utf-8-sig"))["log"]["entries"]
    key = login(entries)
    op = api_get("/api/SRVCMD/GETOPC/STROUT", key)
    print("OP=" + json.dumps({k: op.get(k) for k in ("OP", "SRCDOC", "EFFECTITBAL",
        "EFFECTSRCBAL", "NGBAL", "EXPDT", "ADDBIN", "RETBIN", "DISTTYP", "ITPRICE",
        "SALTAX", "TRDTAX", "FRCSRC", "MAXOVR", "SISCO", "SISST")}, ensure_ascii=True))
    if op.get("OP") != "STROUT" or op.get("SRCDOC") != "SALORD":
        raise RuntimeError("Unexpected Production Issue configuration")
    balances = rows(api_get("/api/POSCMD/GETBAL/1/1", key))
    print("BALANCE_COUNT=" + str(len(balances)) + " KEYS=" +
          json.dumps(list(balances[0]) if balances else [], ensure_ascii=True))
    items = rows(api_get("/api/POSCMD/GETITM/-1", key))
    print("ITEM_COUNT=" + str(len(items)))
    downstream = rows(getrec(entries,
        "select opcode,docno,cono,strno,distno,sts,srcdocno from trnhdr "
        "where cono=1 and strno='1' and opcode in ('STROUT','STROU1') "
        "and srcdocno in (988,989)", key))
    print("DOWNSTREAM_BY_ORDER=" + json.dumps(downstream, ensure_ascii=True))
    for reqno in (996, 998):
        request = api_get(f"/api/POSCMD/GETDOC/SALREQ/1/1/{reqno}", key)
        print("SOURCE_REQUEST=" + json.dumps({"docno": reqno,
            "status": request.get("STS") if isinstance(request, dict) else None,
            "customer": request.get("DISTNO") if isinstance(request, dict) else None},
            ensure_ascii=True))
    for itemno in ("105", "107", "108", "6"):
        found = [row for row in items if isinstance(row, dict) and str(row.get("ITNO")) == itemno]
        print("ITEM=" + json.dumps({"code": itemno, "matches": [{k: row.get(k) for k in (
            "ITNO", "ITDES", "TOTBAL", "USESN", "USEWEG", "USECZ", "USEUNT", "HASPCK",
            "OPNITM", "ITVALD", "SALTAX", "TRDTAX", "UNIT", "EXPDT", "USEEXP",
            "USELOC", "HOLD", "STS") } for row in found]}, ensure_ascii=True))
        matches = [row for row in balances if isinstance(row, dict) and
                   str(row.get("ITNO", row.get("itno", ""))) == itemno]
        print("STOCK=" + json.dumps({"code": itemno, "rows": matches}, ensure_ascii=True))
    for name, docno, customer, expected in TARGETS:
        order = api_get(f"/api/POSCMD/GETDOC/SALORD/1/1/{docno}", key)
        if (not isinstance(order, dict) or order.get("OP") != "SALORD" or
                str(order.get("DISTNO")) != str(customer) or order.get("STS") != "A"):
            raise RuntimeError(f"Target Sales Order {docno} changed")
        lines = rows(order.get("DTL"))
        got = {str(row.get("ITNO")): float(row.get("QTY", 0)) - float(row.get("EXEQTY", 0))
               for row in lines}
        print("ORDER=" + json.dumps({"name": name, "docno": docno, "date": order.get("DOCDT"),
            "company": order.get("CONO"), "store": order.get("STRNO"), "customer": order.get("DISTNO"),
            "status": order.get("STS"), "post": order.get("POST"), "expiry": order.get("EXPDT"),
            "source": order.get("SRCDOCNO"), "remaining": got, "expected_full": expected,
            "line_fields": [{k: row.get(k) for k in ("ITNO", "QTY", "EXEQTY", "CUBAL",
                "NWBAL", "ITPRICE", "ITMTOT", "ITMNET", "SALTAX", "ITSALTAX", "TotalTaxes",
                "BINDTL", "EXPDT", "LOCID", "PCKID", "UNTID", "USESN", "USECSZ")}
                for row in lines]}, ensure_ascii=True))
        choices = source_candidates(entries, key, customer)
        numbers = [str(row.get("DOCNO", "")).split("SRCDOCNO=")[-1].split("\v")[0]
                   for row in choices if isinstance(row, dict)]
        print("SOURCE_CHOICE=" + json.dumps({"name": name, "target": docno,
            "listed": str(docno) in numbers, "count": len(numbers), "numbers": numbers[:20],
            "choice_rows": [{k: row.get(k) for k in ("DOCNO", "DOCDT", "DISTNO", "FORDES")}
                            for row in choices[:5]]},
            ensure_ascii=True))


if __name__ == "__main__":
    main()
