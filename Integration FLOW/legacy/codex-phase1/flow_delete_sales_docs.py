"""Read-only preflight and scoped deletion for Sales Order 987 and Request 997."""

import argparse
import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from flow_sales_request import api_get, getrec, har_request, login


HAR_PATH = Path(r"C:\Users\hp\Downloads\Sales Order.har")


def rows(value):
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    return []


def get_header_rows(entries, api_key, sql):
    result = getrec(entries, sql, api_key)
    if isinstance(result, str) and result.startswith("CMDERR"):
        raise RuntimeError("Read-only link query failed")
    return rows(result)


def preflight(entries, api_key, *, verbose=True):
    order = api_get("/api/POSCMD/GETDOC/SALORD/1/1/987", api_key)
    request = api_get("/api/POSCMD/GETDOC/SALREQ/1/1/997", api_key)
    if not isinstance(order, dict) or not isinstance(request, dict):
        raise RuntimeError("One or both documents are no longer retrievable")
    if (order.get("OP") != "SALORD" or str(order.get("DOCNO")) != "987" or
            str(order.get("CONO")) != "1" or str(order.get("STRNO")) != "1" or
            str(order.get("SRCDOCNO")) != "997" or str(order.get("DISTNO")) != "26" or
            len(order.get("DTL") or []) != 1 or str(order["DTL"][0].get("ITNO")) != "75" or
            float(order["DTL"][0].get("QTY", 0)) != 18):
        raise RuntimeError("Sales Order 987 differs from the document we created")
    if (request.get("OP") != "SALREQ" or str(request.get("DOCNO")) != "997" or
            str(request.get("CONO")) != "1" or str(request.get("STRNO")) != "1" or
            str(request.get("DISTNO")) != "26" or len(request.get("DTL") or []) != 1 or
            str(request["DTL"][0].get("ITNO")) != "75" or float(request["DTL"][0].get("QTY", 0)) != 18):
        raise RuntimeError("Sales Request 997 differs from the document we created")
    if verbose:
        print("ORDER=" + json.dumps({key: order.get(key) for key in (
            "OP", "DOCNO", "CONO", "STRNO", "DISTNO", "SRCDOCNO", "DOCDT", "STS", "POST", "DOCTOT")}, ensure_ascii=False))
        print("REQUEST=" + json.dumps({key: request.get(key) for key in (
            "OP", "DOCNO", "CONO", "STRNO", "DISTNO", "DOCDT", "STS", "POST", "DOCTOT")}, ensure_ascii=False))

    source_order_ops = get_header_rows(entries, api_key,
        "select opcode,srcdoc from opdes where lower(srcdoc)='salord'")
    source_request_ops = get_header_rows(entries, api_key,
        "select opcode,srcdoc from opdes where lower(srcdoc)='salreq'")
    if verbose:
        print("SOURCE_ORDER_OPS=" + json.dumps(source_order_ops, ensure_ascii=False))
        print("SOURCE_REQUEST_OPS=" + json.dumps(source_request_ops, ensure_ascii=False))
    if not any(str(row.get("opcode", "")).upper() == "STROUT" for row in source_order_ops):
        raise RuntimeError("Cannot identify operations sourced from Sales Orders")
    order_codes = [str(row["opcode"]) for row in source_order_ops]
    request_codes = [str(row["opcode"]) for row in source_request_ops]
    order_filter = ",".join("'" + code.replace("'", "''") + "'" for code in order_codes)
    request_filter = ",".join("'" + code.replace("'", "''") + "'" for code in request_codes)
    links_from_order = get_header_rows(entries, api_key,
        "select opcode,docno,srcdocno from trnhdr where cono=1 and strno='1' and srcdocno=987 and opcode in (" + order_filter + ")")
    links_from_request = get_header_rows(entries, api_key,
        "select opcode,docno,srcdocno from trnhdr where cono=1 and strno='1' and srcdocno=997 and opcode in (" + request_filter + ")")
    if verbose:
        print("ORDER_DOWNSTREAM=" + json.dumps(links_from_order, ensure_ascii=False))
        print("REQUEST_DOWNSTREAM=" + json.dumps(links_from_request, ensure_ascii=False))
    if links_from_order:
        raise RuntimeError("Sales Order 987 has downstream documents; do not delete blindly")
    if not any(str(row.get("opcode", "")).lower() == "salord" and str(row.get("docno")) == "987" for row in links_from_request):
        raise RuntimeError("Sales Request 997 is not linked to the expected order")
    if len(links_from_request) != 1:
        raise RuntimeError("Sales Request 997 has additional downstream documents")
    return order, request


def exact_header_rows(entries, api_key, opcode, docno):
    sql = ("select opcode,docno,sts from trnhdr where cono=1 and strno='1' and "
           f"opcode='{opcode}' and docno={docno}")
    return get_header_rows(entries, api_key, sql)


def send_delpos(entries, api_key, opcode, docno):
    if (opcode, docno) not in (("SALORD", 987), ("SALREQ", 997)):
        raise RuntimeError("Delete target outside the two requested documents")
    captured = har_request(entries, "/api/srvcmd/getrec")
    wrapper = json.loads(captured["postData"]["text"])
    if any(not wrapper.get(key) for key in ("acc", "usrid", "pass")):
        raise RuntimeError("Captured lowercase authentication fields are missing")
    command = (f"DELPOS,OPCODE={opcode}\fCONO=1\fSTRNO=1\fDOCNO={docno}\f\v")
    body = {
        "acc": wrapper.get("acc"),
        "usrid": wrapper.get("usrid"),
        "pass": wrapper.get("pass"),
        "lng": wrapper.get("lng"),
        "thm": wrapper.get("thm"),
        "APIKEY": api_key,
        "cmdtxt": "EXECMD",
        "cmdpar": command,
        "srcapp": "FLOW",
        "srcver": 0,
    }
    data = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    request = Request("https://erp.mcbs-global.com/", data=data, method="POST", headers={
        "Accept": "text/plain, */*", "Content-Type": "text/json", "Origin": "https://erp.mcbs-global.com",
        "XAPIKEY": api_key,
    })
    try:
        with urlopen(request, timeout=25) as response:
            text = response.read().decode("utf-8-sig")
            status = response.status
    except HTTPError as exc:
        raise RuntimeError(f"Delete command returned HTTP {exc.code}; do not resend blindly") from None
    except URLError as exc:
        raise RuntimeError("Delete command had a network error; check status read-only before any retry") from None
    print(f"DELETE_RESPONSE {opcode}/{docno}: HTTP={status} TEXT={text[:150]}", flush=True)
    return status, text


def delete_order(entries, api_key):
    preflight(entries, api_key, verbose=False)
    if len(exact_header_rows(entries, api_key, "SALORD", 987)) != 1:
        raise RuntimeError("Sales Order 987 row was not uniquely present before delete")
    print("DELETE_PREVIEW order=SALORD/1/1/987 source_request=SALREQ/1/1/997 downstream=0", flush=True)
    status, result = send_delpos(entries, api_key, "SALORD", 987)
    remaining = exact_header_rows(entries, api_key, "SALORD", 987)
    if remaining:
        raise RuntimeError("Sales Order 987 still exists after delete response; do not retry blindly")
    if status != 200:
        raise RuntimeError("Sales Order row disappeared but HTTP response was not normal")
    source = api_get("/api/POSCMD/GETDOC/SALREQ/1/1/997", api_key)
    print("ORDER_DELETED VERIFIED source_request_exists=" + str(isinstance(source, dict) and str(source.get("DOCNO")) == "997") +
          " source_executed_qty=" + str((source.get("DTL") or [{}])[0].get("EXEQTY") if isinstance(source, dict) else None), flush=True)


def delete_request(entries, api_key):
    order_rows = exact_header_rows(entries, api_key, "SALORD", 987)
    if len(order_rows) != 1 or str(order_rows[0].get("sts", "")).upper() != "D":
        raise RuntimeError("Sales Order 987 is not uniquely confirmed with deleted status D")
    request = api_get("/api/POSCMD/GETDOC/SALREQ/1/1/997", api_key)
    if (not isinstance(request, dict) or request.get("OP") != "SALREQ" or
            str(request.get("DOCNO")) != "997" or str(request.get("CONO")) != "1" or
            str(request.get("STRNO")) != "1" or str(request.get("DISTNO")) != "26" or
            len(request.get("DTL") or []) != 1 or str(request["DTL"][0].get("ITNO")) != "75" or
            float(request["DTL"][0].get("QTY", 0)) != 18):
        raise RuntimeError("Sales Request 997 no longer matches our saved document")
    linked_orders = get_header_rows(entries, api_key,
        "select opcode,docno,sts from trnhdr where cono=1 and strno='1' and srcdocno=997 and opcode='SALORD' and sts<>'D'")
    if linked_orders:
        raise RuntimeError("Sales Request 997 still has linked Sales Orders")
    request_rows = exact_header_rows(entries, api_key, "SALREQ", 997)
    if len(request_rows) != 1 or str(request_rows[0].get("sts", "")).upper() != "A":
        raise RuntimeError("Sales Request 997 was not uniquely active before delete")
    print("DELETE_PREVIEW request=SALREQ/1/1/997 linked_sales_orders=0", flush=True)
    status, result = send_delpos(entries, api_key, "SALREQ", 997)
    after_rows = exact_header_rows(entries, api_key, "SALREQ", 997)
    after_doc = api_get("/api/POSCMD/GETDOC/SALREQ/1/1/997", api_key)
    if (status != 200 or len(after_rows) != 1 or
            str(after_rows[0].get("sts", "")).upper() != "D" or
            not isinstance(after_doc, dict) or str(after_doc.get("STS", "")).upper() != "D"):
        raise RuntimeError("Sales Request delete was not confirmed as status D; do not retry blindly")
    print("REQUEST_DELETED VERIFIED status=D (soft deletion)", flush=True)


def status_probe(entries, api_key):
    order_rows = exact_header_rows(entries, api_key, "SALORD", 987)
    request_rows = exact_header_rows(entries, api_key, "SALREQ", 997)
    print(f"STATUS_ROWS order_987={len(order_rows)} request_997={len(request_rows)}", flush=True)
    if order_rows:
        detailed = get_header_rows(entries, api_key,
            "select opcode,docno,sts,post,srcdocno from trnhdr where cono=1 and strno='1' and opcode='SALORD' and docno=987")
        print("ORDER_DATABASE_STATUS=" + json.dumps(detailed, ensure_ascii=False), flush=True)
        order = api_get("/api/POSCMD/GETDOC/SALORD/1/1/987", api_key)
        print("ORDER_GETDOC_STATUS=" + json.dumps({
            "docno": order.get("DOCNO") if isinstance(order, dict) else None,
            "status": order.get("STS") if isinstance(order, dict) else None,
            "post": order.get("POST") if isinstance(order, dict) else None,
            "source": order.get("SRCDOCNO") if isinstance(order, dict) else None,
        }, ensure_ascii=False), flush=True)
    if request_rows:
        detailed = get_header_rows(entries, api_key,
            "select opcode,docno,sts,post from trnhdr where cono=1 and strno='1' and opcode='SALREQ' and docno=997")
        print("REQUEST_DATABASE_STATUS=" + json.dumps(detailed, ensure_ascii=False), flush=True)
        request = api_get("/api/POSCMD/GETDOC/SALREQ/1/1/997", api_key)
        print("REQUEST_GETDOC_STATUS=" + json.dumps({
            "docno": request.get("DOCNO") if isinstance(request, dict) else None,
            "status": request.get("STS") if isinstance(request, dict) else None,
        }, ensure_ascii=False), flush=True)
        print("REQUEST_SOURCE_BALANCE=" + json.dumps({
            "docno": request.get("DOCNO"),
            "executed_qty": (request.get("DTL") or [{}])[0].get("EXEQTY"),
            "qty": (request.get("DTL") or [{}])[0].get("QTY"),
        }, ensure_ascii=False), flush=True)
        from flow_sales_order import source_candidates
        candidates = source_candidates(entries, api_key, request["DISTNO"])
        source_numbers = [str(row.get("DOCNO", "")).split("SRCDOCNO=")[-1].split("\v")[0]
                          for row in candidates if isinstance(row, dict)]
        print("REQUEST_997_ELIGIBLE_FOR_NEW_ORDER=" + str("997" in source_numbers), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["probe", "status", "delete-order", "delete-request"])
    args = parser.parse_args()
    entries = json.loads(HAR_PATH.read_text(encoding="utf-8-sig"))["log"]["entries"]
    api_key = login(entries)
    if args.mode == "probe":
        preflight(entries, api_key)
    elif args.mode == "status":
        status_probe(entries, api_key)
    elif args.mode == "delete-order":
        delete_order(entries, api_key)
    elif args.mode == "delete-request":
        delete_request(entries, api_key)


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
