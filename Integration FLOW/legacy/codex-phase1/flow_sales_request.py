"""Create one Flow ERP Sales Request using HAR-derived credentials, never a browser."""

import argparse
import copy
import json
import re
import sys
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


HAR_PATH = Path(r"C:\Users\hp\Downloads\Sales request.har")
LOGIN_HOST = "login.mcbs-global.com"
API_HOST = "api.mcbs-global.com"
ERP_HOST = "erp.mcbs-global.com"
ORIGIN = "https://erp.mcbs-global.com"


def normalized(value):
    value = unicodedata.normalize("NFKC", str(value or ""))
    value = re.sub(r"[\u064b-\u065f\u0670\u0640\s]", "", value)
    return value.translate(str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه"})).lower()


def load_har():
    return json.loads(HAR_PATH.read_text(encoding="utf-8-sig"))["log"]["entries"]


def har_request(entries, path, method="POST"):
    for entry in entries:
        req = entry["request"]
        if req["method"] == method and req["url"].split("?")[0].endswith(path):
            return req
    raise RuntimeError(f"HAR request missing: {method} {path}")


def http_json(url, *, method="GET", body=None, api_key=None):
    if not (url.startswith(f"https://{LOGIN_HOST}/") or url.startswith(f"https://{API_HOST}/") or url.startswith(f"https://{ERP_HOST}/")):
        raise RuntimeError("Unexpected destination")
    headers = {"Accept": "application/json, text/plain, */*", "Origin": ORIGIN}
    if api_key:
        headers["apikey"] = api_key
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json; charset=UTF-8"
        data = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=25) as response:
            raw = response.read().decode("utf-8-sig")
            status = response.status
    except HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} at {url.split('?')[0]}") from None
    except URLError as exc:
        raise RuntimeError(f"Network error at {url.split('?')[0]}: {type(exc.reason).__name__}") from None
    try:
        content = json.loads(raw)
    except ValueError:
        content = raw
    return status, content


def login(entries):
    req = har_request(entries, "/api/chkusr/login")
    body = json.loads(req["postData"]["text"])
    status, result = http_json(f"https://{LOGIN_HOST}/api/chkusr/login", method="POST", body=body)
    if status != 200 or not isinstance(result, dict) or not result.get("apiKey"):
        raise RuntimeError("Fresh login did not return an API key")
    print(f"LOGIN_OK auth={result.get('auth')} err={bool(result.get('errMsg'))}")
    return result["apiKey"]


def api_get(path, api_key):
    return http_json(f"https://{API_HOST}{path}", api_key=api_key)[1]


def getrec(entries, sql, api_key):
    req = har_request(entries, "/api/srvcmd/getrec")
    body = json.loads(req["postData"]["text"])
    body["CMDTXT"] = "GETREC"
    body["CMDPAR"] = sql
    body["APIKEY"] = api_key
    return http_json(f"https://{API_HOST}/api/srvcmd/getrec", method="POST", body=body, api_key=api_key)[1]


def as_rows(value):
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    return []


def matching(rows, target):
    needle = normalized(target)
    return [row for row in rows if isinstance(row, dict) and any(normalized(v) == needle for v in row.values() if isinstance(v, str))]


def probe(entries, api_key):
    operation = api_get("/api/SRVCMD/GETOPC/SALREQ", api_key)
    print(f"OP={operation.get('OP')} source={operation.get('SRCDOC')} expiry={operation.get('EXPDT')} expiry_days={operation.get('EXPDAY')} vat={operation.get('SALTAX')} trade_tax={operation.get('TRDTAX')} cash={operation.get('CASH')} credit={operation.get('CREDIT')}")

    company = api_get("/api/SRVCMD/GETCOM/1", api_key)
    print(f"COMPANY_TYPE={type(company).__name__} COMPANY_KEYS={list(company) if isinstance(company, dict) else []}")
    if isinstance(company, dict):
        print("COMPANY_FIELDS=" + json.dumps({k: v for k, v in company.items() if k.lower() in ("cono", "cona", "fordes", "conna", "companyname", "cmpna")}, ensure_ascii=False))

    stores = as_rows(getrec(entries, "select cono,strno,fordes from stores where cono=1 and strno='1'", api_key))
    print(f"STORE={json.dumps(stores, ensure_ascii=False)}")

    contacts = as_rows(api_get("/api/CONCMD/GETCON/C", api_key))
    print(f"CONTACT_ROWS={len(contacts)} KEYS={list(contacts[0]) if contacts else []}")
    found_contacts = matching(contacts, "هانى المصري")
    print(f"CUSTOMER_MATCH_COUNT={len(found_contacts)}")
    for row in found_contacts:
        print("CUSTOMER_MATCH=" + json.dumps({k: v for k, v in row.items() if k.upper() in ("CNO", "CNAME", "FORDES", "CONO", "CONGRP", "PRICECODE", "SUBCON", "TOTDISC", "RGNO", "TAXFAC", "TRDTAX", "CONTYP", "EMPNO", "CADD")}, ensure_ascii=False))

    agents = as_rows(getrec(entries, "select empno,empnm from empmas where sts='a' and jobid=100 order by empnm", api_key))
    print(f"AGENT_ROWS={len(agents)} AGENT_MATCH={json.dumps(matching(agents, 'احمد الصعيدى'), ensure_ascii=False)}")

    items = as_rows(api_get("/api/POSCMD/GETITM/-1", api_key))
    print(f"ITEM_ROWS={len(items)} KEYS={list(items[0]) if items else []}")
    item_match = [row for row in items if isinstance(row, dict) and any(str(row.get(key, "")) == "75" for key in ("ITNO", "itno", "ITCODE", "itcode"))]
    print(f"ITEM_MATCH_COUNT={len(item_match)}")
    for row in item_match:
        print("ITEM_MATCH=" + json.dumps({k: v for k, v in row.items() if k.upper() in ("ITNO", "ITCODE", "ITDES", "ITNA", "STS", "SALTAX", "TRDTAX", "TBLTAXRTO", "ITPRICE", "UNITPRC", "ITMPRICE", "HASCLR", "HASSIZ", "HASPCK", "USEUNT", "USESN", "USEWEG", "USECZ", "UNIT", "OPNITM")}, ensure_ascii=False))


def exact_one(rows, name):
    found = matching(rows, name)
    if len(found) != 1:
        raise RuntimeError(f"Expected one match for {name}, found {len(found)}")
    return found[0]


def create(entries, api_key, *, commit=False):
    operation = api_get("/api/SRVCMD/GETOPC/SALREQ", api_key)
    if operation.get("OP") != "SALREQ" or str(operation.get("SRCDOC")) != "-1":
        raise RuntimeError("Sales Request operation differs from expected configuration")
    company = api_get("/api/SRVCMD/GETCOM/1", api_key)
    if str(company.get("CONO")) != "1" or normalized(company.get("CONA")) != "cmc":
        raise RuntimeError("Company 1 is not CMC")
    stores = as_rows(getrec(entries, "select cono,strno,fordes from stores where cono=1 and strno='1'", api_key))
    if len(stores) != 1 or str(stores[0].get("strno")) != "1":
        raise RuntimeError("Store 1 was not verified for company 1")

    customer = exact_one(as_rows(api_get("/api/CONCMD/GETCON/C", api_key)), "هانى المصري")
    if str(customer.get("CONO")) not in ("0", "1"):
        raise RuntimeError("Customer is not available for company 1")
    agent = exact_one(as_rows(getrec(entries, "select empno,empnm from empmas where sts='a' and jobid=100 order by empnm", api_key)), "احمد الصعيدى")
    item_rows = as_rows(api_get("/api/POSCMD/GETITM/-1", api_key))
    found_items = [row for row in item_rows if str(row.get("ITNO")) == "75"]
    if len(found_items) != 1:
        raise RuntimeError(f"Expected one item 75, found {len(found_items)}")
    item = found_items[0]
    if any(str(item.get(flag, "N")) == "Y" for flag in ("USEUNT", "USESN", "USEWEG", "USECZ")) or item.get("HASPCK"):
        raise RuntimeError("Item 75 requires extra unit/serial/weight/size/pack fields")
    if str(operation.get("SALTAX")) != "Y":
        raise RuntimeError("VAT configuration differs from the observed operation")

    today = datetime.now().date()
    expiry_days = int(operation.get("EXPDAY", 30))
    expiry = today + timedelta(days=expiry_days)
    vat_rate = float(item.get("SALTAX", 0))
    if vat_rate != 14.0 or float(item.get("TRDTAX", 0)) != 0.0:
        raise RuntimeError("Item tax policy changed after review")

    example = har_request(entries, "/api/POSCMD/ADDPOS")
    payload = copy.deepcopy(json.loads(example["postData"]["text"]))
    if payload.get("OP") != "SALREQ" or len(payload.get("DTL", [])) != 1:
        raise RuntimeError("HAR save template is not a one-line Sales Request")

    payload.update({
        "DOCNO": 0,
        "DOCDT": today.isoformat(),
        "CONO": "1",
        "STRNO": "1",
        "DISTNO": str(customer["CNO"]),
        "SDISTNO": 0,
        "DISTNA": customer["CNAME"],
        "SDISTNA": "",
        "FORDES": customer["FORDES"],
        "DISTADD": customer.get("CADD") or "",
        "TEL1": customer.get("TEL1") or "",
        "TEL2": "",
        "EMAIL": customer.get("EMAIL") or "",
        "EMPNO": int(agent["empno"]),
        "RGNO": str(customer.get("RGNO") or 0),
        "REFDOCNO": "",
        "TOTDISC": 0,
        "RMK": "",
        "DLVLOC": 0,
        "TOTSHPVAL": 0,
        "EXPDT": expiry.isoformat(),
    })
    line = payload["DTL"][0]
    line.update({
        "ITNO": "75",
        "ITDES": item["ITDES"],
        "ITPRICE": "1000",
        "SALTAX": "14",
        "TRDTAX": 0,
        "TBLTAXRTO": 0,
        "DISC1": "0",
        "ITMTOT": 18000,
        "QTY": 18,
        "BQTY": 0,
        "HASPCK": item.get("HASPCK") or "",
        "USEUNT": item.get("USEUNT") or "N",
        "USEWEG": item.get("USEWEG") or "N",
        "USESN": item.get("USESN") or "N",
        "USECSZ": item.get("USECZ") or "N",
    })

    if not (payload["OP"] == "SALREQ" and payload["DOCNO"] == 0 and payload["DISTNO"] == str(customer["CNO"]) and payload["EMPNO"] == int(agent["empno"]) and line["ITNO"] == "75" and line["QTY"] == 18 and float(line["ITPRICE"]) == 1000):
        raise RuntimeError("Final payload review failed")
    print(f"PREVIEW op=SALREQ company=CMC/1 store=1 customer={payload['DISTNO']} agent={payload['EMPNO']} date={payload['DOCDT']} item=75 qty=18 unit_price=1000 base=18000 vat_rate=14 expiry={payload['EXPDT']}", flush=True)
    if not commit:
        return

    status, save_result = http_json(f"https://{API_HOST}/api/POSCMD/ADDPOS", method="POST", body=payload, api_key=api_key)
    if status != 200 or not isinstance(save_result, str) or not re.fullmatch(r"CMDDNE,\d+", save_result):
        raise RuntimeError(f"Save response was not a confirmed document number: status={status}")
    docno = int(save_result.split(",")[1])
    print(f"SAVE_RESPONSE={save_result}", flush=True)

    saved = api_get(f"/api/POSCMD/GETDOC/SALREQ/1/1/{docno}", api_key)
    if not isinstance(saved, dict) or str(saved.get("DOCNO")) != str(docno) or saved.get("OP") != "SALREQ":
        raise RuntimeError(f"Document {docno} could not be verified after save")
    details = as_rows(saved.get("DTL"))
    if len(details) != 1 or str(details[0].get("ITNO")) != "75" or float(details[0].get("QTY", 0)) != 18 or float(details[0].get("ITPRICE", 0)) != 1000:
        raise RuntimeError(f"Document {docno} saved but its line differs from the requested values")
    if str(saved.get("DISTNO")) != str(customer["CNO"]) or str(saved.get("EMPNO")) != str(agent["empno"]) or str(saved.get("CONO")) != "1" or str(saved.get("STRNO")) != "1" or saved.get("DOCDT", "")[:10] != today.isoformat():
        raise RuntimeError(f"Document {docno} saved but its header differs from the requested values")
    print("VERIFIED=" + json.dumps({
        "docno": docno,
        "date": saved.get("DOCDT"),
        "company": saved.get("CONO"),
        "store": saved.get("STRNO"),
        "customer": saved.get("DISTNO"),
        "agent": saved.get("EMPNO"),
        "item": details[0].get("ITNO"),
        "qty": details[0].get("QTY"),
        "unit_price": details[0].get("ITPRICE"),
        "vat_rate": details[0].get("SALTAX"),
        "total": saved.get("DOCTOT"),
        "vat": saved.get("TOTSALTAX"),
        "net": saved.get("DOCNET"),
        "status": saved.get("STS"),
        "post": saved.get("POST"),
    }, ensure_ascii=False), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["probe", "preview", "save"])
    args = parser.parse_args()
    entries = load_har()
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
