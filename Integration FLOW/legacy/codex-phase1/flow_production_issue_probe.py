"""Read-only preflight for STROUT from Sales Order 987; no document save."""

import json
import sys
from pathlib import Path

from flow_sales_request import ERP_HOST, api_get, har_request, http_json, login


HAR_PATH = Path(r"C:\Users\hp\Downloads\Sales Order.har")


def rows(value):
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    return []


def main():
    entries = json.loads(HAR_PATH.read_text(encoding="utf-8-sig"))["log"]["entries"]
    api_key = login(entries)
    operation = api_get("/api/SRVCMD/GETOPC/STROUT", api_key)
    print("OPERATION=" + json.dumps({key: operation.get(key) for key in (
        "OP", "DOCDES", "MNU", "SRCDOC", "DISTTYP", "EFFECTITBAL", "EFFECTSRCBAL",
        "NGBAL", "USESN", "EXPDT", "ADDBIN", "RETBIN", "SISCO", "SISST", "ITPRICE",
        "SALTAX", "TRDTAX", "POST", "LNKSTR")}, ensure_ascii=False))
    if operation.get("OP") != "STROUT" or operation.get("SRCDOC") != "SALORD":
        raise RuntimeError("STROUT is not configured to source Sales Orders")
    order = api_get("/api/POSCMD/GETDOC/SALORD/1/1/987", api_key)
    details = rows(order.get("DTL")) if isinstance(order, dict) else []
    print("ORDER=" + json.dumps({key: order.get(key) for key in (
        "OP", "DOCNO", "DOCDT", "CONO", "STRNO", "DISTNO", "EMPNO", "SRCDOCNO",
        "STS", "POST", "RMK", "DOCTOT")}, ensure_ascii=False))
    print("ORDER_LINES=" + json.dumps([{key: line.get(key) for key in (
        "ITNO", "QTY", "EXEQTY", "ITPRICE", "SALTAX", "LOCID", "PCKID", "UNTID",
        "USESN", "USECSZ", "BINDTL", "EXPDT") } for line in details], ensure_ascii=False))
    lookup = json.loads(har_request(entries, "/api/srvcmd/getrec")["postData"]["text"])
    lookup["CMDTXT"] = "LDSRCHDRNO"
    lookup["CMDPAR"] = "OPCODE=STROUT\vCONO=1\vSTRNO=1\vDISTNO=26\v"
    lookup["APIKEY"] = api_key
    available = http_json(f"https://{ERP_HOST}/", method="POST", body=lookup, api_key=api_key)[1]
    available_rows = rows(available)
    source_keys = [str(row.get("DOCNO", "")).split("SRCDOCNO=")[-1].split("\v")[0] for row in available_rows if isinstance(row, dict)]
    print("SOURCE_ORDERS=" + json.dumps({"count": len(source_keys), "order_987_listed": "987" in source_keys, "keys": source_keys}, ensure_ascii=False))
    balances = rows(api_get("/api/POSCMD/GETBAL/1/1", api_key))
    print(f"BALANCE_ROWS={len(balances)} KEYS={list(balances[0]) if balances else []}")
    item_balances = [row for row in balances if isinstance(row, dict) and any(str(row.get(key, "")) == "75" for key in ("ITNO", "itno"))]
    print("ITEM75_BALANCE=" + json.dumps(item_balances, ensure_ascii=False))
    items = rows(api_get("/api/POSCMD/GETITM/-1", api_key))
    item = [row for row in items if isinstance(row, dict) and str(row.get("ITNO")) == "75"]
    print("ITEM75_FLAGS=" + json.dumps([{key: row.get(key) for key in (
        "ITNO", "ITDES", "TOTBAL", "USESN", "USEWEG", "USECZ", "HASPCK", "OPNITM",
        "ITVALD", "SALTAX", "TRDTAX", "UNIT") } for row in item], ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
