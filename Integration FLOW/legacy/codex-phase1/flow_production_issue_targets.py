"""Read-only discovery of the two named Sales Orders and Production Issue prerequisites."""

import json
from pathlib import Path

from flow_sales_request import api_get, getrec, login, normalized


HAR_PATH = Path(r"C:\Users\hp\Downloads\Sales Order.har")
NAMES = ("احمد جبر", "محمد علاء")
EXPECTED = {"احمد جبر": {"105", "107", "108"}, "محمد علاء": {"6"}}


def rows(value):
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    return []


def main():
    entries = json.loads(HAR_PATH.read_text(encoding="utf-8-sig"))["log"]["entries"]
    key = login(entries)
    op = api_get("/api/SRVCMD/GETOPC/STROUT", key)
    print("ISSUE_OPERATION=" + json.dumps({k: op.get(k) for k in (
        "OP", "SRCDOC", "EFFECTITBAL", "EFFECTSRCBAL", "NGBAL", "EXPDT", "ADDBIN",
        "USESN", "USELOC", "POST", "ITPRICE", "SALTAX", "TRDTAX")}, ensure_ascii=False))
    if op.get("OP") != "STROUT" or op.get("SRCDOC") != "SALORD":
        raise RuntimeError("Production Issue is not currently sourced from Sales Orders")
    contacts = rows(api_get("/api/CONCMD/GETCON/C", key))
    print("CUSTOMER_LOOKUP_SIZE=" + str(len(contacts)) + " KEYS=" +
          json.dumps(list(contacts[0]) if contacts else [], ensure_ascii=True))
    agents = rows(getrec(entries, "select empno,empnm from empmas where sts='a' order by empnm", key))
    for name in NAMES:
        matches = [c for c in contacts if isinstance(c, dict) and any(
            normalized(c.get(field)) == normalized(name) for field in ("CNAME", "FORDES"))]
        partial = [c for c in contacts if isinstance(c, dict) and any(
            normalized(name) in normalized(c.get(field)) or normalized(c.get(field)) in normalized(name)
            for field in ("CNAME", "FORDES") if c.get(field))]
        agent_matches = [a for a in agents if isinstance(a, dict) and (
            normalized(name) in normalized(a.get("empnm")) or
            normalized(a.get("empnm")) in normalized(name))]
        print("CUSTOMER_MATCH=" + json.dumps({"name": name, "matches": [
            {k: c.get(k) for k in ("CNO", "CNAME", "FORDES", "CONO", "STS")}
            for c in matches], "partial": [{k: c.get(k) for k in ("CNO", "CNAME", "FORDES")}
                for c in partial[:10]], "agent_matches": agent_matches[:10]}, ensure_ascii=True))
        if not matches and len(partial) == 1 and normalized(partial[0].get("CNAME", "")).endswith(normalized(name)):
            matches = partial
        for customer in matches:
            cno = customer.get("CNO")
            if cno is None or not str(cno).isdigit():
                continue
            sql = ("select opcode,docno,cono,strno,distno,empno,sts,post,docdt,srcdocno "
                   "from trnhdr where opcode='SALORD' and distno=" + str(cno) +
                   " order by docno desc")
            order_rows = rows(getrec(entries, sql, key))
            print("ORDERS_BY_CUSTOMER=" + json.dumps({"name": name, "customer": cno,
                "count": len(order_rows), "orders": order_rows[:20]}, ensure_ascii=False))
            for header in order_rows[:20]:
                if str(header.get("sts", "")).upper() == "D":
                    continue
                co, st, no = (header.get("cono"), header.get("strno"), header.get("docno"))
                if not all(str(value).isdigit() for value in (co, st, no)):
                    continue
                doc = api_get(f"/api/POSCMD/GETDOC/SALORD/{co}/{st}/{no}", key)
                if not isinstance(doc, dict):
                    continue
                details = rows(doc.get("DTL"))
                items = {str(line.get("ITNO")) for line in details}
                print("ORDER_DETAIL=" + json.dumps({"name": name, "docno": no, "company": co,
                    "store": st, "status": doc.get("STS"), "customer": doc.get("DISTNO"),
                    "agent": doc.get("EMPNO"), "items": sorted(items),
                    "expected_items_present": EXPECTED[name].issubset(items),
                    "lines": [{k: line.get(k) for k in ("ITNO", "QTY", "EXEQTY", "ITPRICE",
                        "LOCID", "PCKID", "UNTID", "BINDTL", "EXPDT")} for line in details]
                    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
