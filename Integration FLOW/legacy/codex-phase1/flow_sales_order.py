"""Create a zero-tax Sales Order from Sales Request 997 via Python only."""

import argparse
import copy
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from flow_sales_request import API_HOST, ERP_HOST, api_get, har_request, http_json, login


HAR_PATH = Path(r"C:\Users\hp\Downloads\Sales Order.har")
SOURCE_DOCNO = 997


def load_entries():
    return json.loads(HAR_PATH.read_text(encoding="utf-8-sig"))["log"]["entries"]


def source_candidates(entries, api_key, customer):
    captured = har_request(entries, "/api/srvcmd/getrec")
    body = json.loads(captured["postData"]["text"])
    body["CMDTXT"] = "LDSRCHDRNO"
    body["APIKEY"] = api_key
    body["CMDPAR"] = f"OPCODE=SALORD\vCONO=1\vSTRNO=1\vDISTNO={customer}\v"
    response = http_json(f"https://{ERP_HOST}/", method="POST", body=body, api_key=api_key)[1]
    return response if isinstance(response, list) else [response]


def probe(entries, api_key, *, verbose=True):
    operation = api_get("/api/SRVCMD/GETOPC/SALORD", api_key)
    if operation.get("OP") != "SALORD" or operation.get("SRCDOC") != "SALREQ":
        raise RuntimeError("Sales Order source configuration is not Sales Request")
    source = api_get(f"/api/POSCMD/GETDOC/SALREQ/1/1/{SOURCE_DOCNO}", api_key)
    if not isinstance(source, dict) or str(source.get("DOCNO")) != str(SOURCE_DOCNO):
        raise RuntimeError("Source Sales Request 997 was not retrieved")
    details = source.get("DTL") or []
    if len(details) != 1:
        raise RuntimeError(f"Source line count differs: {len(details)}")
    line = details[0]
    if verbose:
        print("OPERATION=" + json.dumps({k: operation.get(k) for k in ("OP", "SRCDOC", "SALTAX", "TRDTAX", "EFFECTSRCBAL", "FRCSRC", "EXPDT", "EXPDAY", "ITPRICE", "MAXOVR")}, ensure_ascii=False))
        print("SOURCE_HEADER=" + json.dumps({k: source.get(k) for k in ("OP", "DOCNO", "CONO", "STRNO", "DISTNO", "EMPNO", "DOCDT", "EXPDT", "DOCTOT", "DOCNET", "TOTSALTAX", "STS", "POST")}, ensure_ascii=False))
        print("SOURCE_LINE=" + json.dumps({k: line.get(k) for k in ("ITNO", "QTY", "EXEQTY", "CUBAL", "NWBAL", "ITPRICE", "SALTAX", "TRDTAX", "TBLTAXRTO", "ITMTOT", "ITMTOTVAL", "ITMNET", "ITVALD", "ITSALTAX", "TotalTaxes", "ITMTOTVAL", "ITMVALACC", "ITMDISACC", "ITSPAY")}, ensure_ascii=False))
        print("SOURCE_TAX_FIELDS=" + json.dumps({k: v for k, v in line.items() if ("TAX" in k.upper() or "NET" in k.upper() or "VAL" in k.upper()) and isinstance(v, (str, int, float, type(None)))}, ensure_ascii=False))
    candidates = source_candidates(entries, api_key, source["DISTNO"])
    encoded = [row.get("DOCNO", "") for row in candidates if isinstance(row, dict)]
    if verbose:
        print("SOURCE_CHOICES=" + json.dumps({"count": len(encoded), "contains_997": any("SRCDOCNO=997\v" in str(value) for value in encoded), "source_keys": [str(value).split("SRCDOCNO=")[-1].split("\v")[0] for value in encoded]}, ensure_ascii=False))
    if not any("SRCDOCNO=997\v" in str(value) for value in encoded):
        raise RuntimeError("Sales Request 997 is not eligible as a source")
    return operation, source


def create(entries, api_key, *, commit=False):
    operation, source = probe(entries, api_key, verbose=False)
    line = source["DTL"][0]
    if (str(source.get("CONO")) != "1" or str(source.get("STRNO")) != "1" or
            str(source.get("DISTNO")) != "26" or str(source.get("EMPNO")) != "10" or
            str(line.get("ITNO")) != "75" or float(line.get("QTY", 0)) != 18 or
            float(line.get("EXEQTY", 0)) != 0 or float(line.get("ITPRICE", 0)) != 1000 or
            float(line.get("ITMNET", 0)) != 18000):
        raise RuntimeError("Sales Request 997 changed from the values reviewed for this order")
    if operation.get("SALTAX") != "Y" or operation.get("EFFECTSRCBAL") != "Y":
        raise RuntimeError("Sales Order VAT/source-balance configuration changed")

    example = json.loads(entries[124]["request"]["postData"]["text"])
    if example.get("OP") != "SALORD" or len(example.get("DTL", [])) != 1:
        raise RuntimeError("HAR Sales Order template is not the expected operation")
    today = datetime.now().date().isoformat()
    payload = copy.deepcopy(example)
    for field in ("SDISTNO", "DISTNA", "SDISTNA", "FRMORD", "EXPDOC", "RGNO", "FORDES", "DISTADD", "TEL1", "TEL2", "EMAIL", "SALRET", "TOTDISC", "EMPNO", "RMK", "DLVLOC", "TOTSHPVAL", "EXPDT", "TOTDISC5"):
        payload[field] = source.get(field)
    payload.update({
        "OP": "SALORD",
        "DOCNO": 0,
        "DOCDT": today,
        "CONO": "1",
        "STRNO": "1",
        "DISTNO": str(source["DISTNO"]),
        "REFDOCNO": str(source.get("REFDOCNO") or "0"),
        "SRCDOCNO": str(SOURCE_DOCNO),
        "PY": "-1",  # Recorded Sales Order default, not an inferred payment.
        "EMPNO": int(source["EMPNO"]),
    })
    payload["DTL"] = copy.deepcopy(source["DTL"])
    order_line = payload["DTL"][0]
    order_line.update({
        "SALTAX": 0,
        "ITSALTAX": 0,
        "TotalTaxes": 0,
        "TRDTAX": 0,
        "ITTRDTAX": 0,
        "TBLTAXRTO": 0,
        "TBLTAXVAL": 0,
        "TBLTAX": 0,
        "ITMTOT": 18000,
        "ITMTOTVAL": 18000,
        "ITMNET": 18000,
        "NetPrice": 1000,
    })
    if any(float(order_line.get(field, 0) or 0) != 0 for field in ("SALTAX", "ITSALTAX", "TotalTaxes", "TRDTAX", "ITTRDTAX", "TBLTAXRTO", "TBLTAXVAL", "TBLTAX")):
        raise RuntimeError("Order tax fields are not all zero")
    if (payload["DOCNO"] != 0 or payload["SRCDOCNO"] != "997" or
            len(payload["DTL"]) != 1 or float(order_line["QTY"]) != 18 or
            float(order_line["ITPRICE"]) != 1000 or float(order_line["ITMTOT"]) != 18000):
        raise RuntimeError("Final Sales Order review failed")
    print(f"PREVIEW op=SALORD company=1 store=1 customer={payload['DISTNO']} agent={payload['EMPNO']} source=997 date={today} item=75 qty=18 price=1000 vat=0 taxes=0 total=18000", flush=True)
    if not commit:
        return

    status, result = http_json(f"https://{API_HOST}/api/POSCMD/ADDPOS", method="POST", body=payload, api_key=api_key)
    if status != 200 or not isinstance(result, str) or not re.fullmatch(r"CMDDNE,\d+", result):
        raise RuntimeError(f"Order save response was uncertain: status={status}; do not retry automatically")
    docno = int(result.split(",")[1])
    print(f"SAVE_RESPONSE={result}", flush=True)
    saved = api_get(f"/api/POSCMD/GETDOC/SALORD/1/1/{docno}", api_key)
    if not isinstance(saved, dict) or str(saved.get("DOCNO")) != str(docno) or saved.get("OP") != "SALORD":
        raise RuntimeError(f"Sales Order {docno} could not be retrieved after save")
    lines = saved.get("DTL") or []
    if len(lines) != 1 or str(saved.get("SRCDOCNO")) != "997" or str(saved.get("DISTNO")) != "26" or str(saved.get("EMPNO")) != "10" or str(saved.get("CONO")) != "1" or str(saved.get("STRNO")) != "1" or saved.get("DOCDT", "")[:10] != today:
        raise RuntimeError(f"Sales Order {docno} header/line count differs from the review")
    saved_line = lines[0]
    if str(saved_line.get("ITNO")) != "75" or float(saved_line.get("QTY", 0)) != 18 or float(saved_line.get("ITPRICE", 0)) != 1000 or float(saved_line.get("SALTAX", -1)) != 0 or float(saved_line.get("ITSALTAX", -1)) != 0 or float(saved.get("TOTSALTAX", -1)) != 0 or float(saved.get("DOCTOT", 0)) != 18000:
        raise RuntimeError(f"Sales Order {docno} saved, but tax/amount or item differs")
    print("VERIFIED=" + json.dumps({
        "docno": docno, "source": saved.get("SRCDOCNO"), "date": saved.get("DOCDT"),
        "company": saved.get("CONO"), "store": saved.get("STRNO"), "customer": saved.get("DISTNO"),
        "agent": saved.get("EMPNO"), "item": saved_line.get("ITNO"), "qty": saved_line.get("QTY"),
        "price": saved_line.get("ITPRICE"), "vat_rate": saved_line.get("SALTAX"),
        "vat_amount": saved.get("TOTSALTAX"), "trade_tax": saved.get("TOTTRDTAX"),
        "table_tax": saved.get("TOTTBLTAX"), "total": saved.get("DOCTOT"),
        "net": saved.get("DOCNET"), "status": saved.get("STS"), "post": saved.get("POST"),
    }, ensure_ascii=False), flush=True)
    candidates_after = source_candidates(entries, api_key, saved["DISTNO"])
    still_eligible = any("SRCDOCNO=997\v" in str(row.get("DOCNO", "")) for row in candidates_after if isinstance(row, dict))
    print(f"SOURCE_997_STILL_ELIGIBLE={still_eligible}", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["probe", "preview", "save"])
    args = parser.parse_args()
    entries = load_entries()
    api_key = login(entries)
    if args.mode == "probe":
        probe(entries, api_key)
    elif args.mode in ("preview", "save"):
        create(entries, api_key, commit=args.mode == "save")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
