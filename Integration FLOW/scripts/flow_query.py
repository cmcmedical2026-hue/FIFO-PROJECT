"""Read-only inspection of the Flow ERP tenant. Never writes anything.

This is the tool to reach for first: reviews, reconciliations, finding a
customer code, checking what a document became, proving a delete worked.

    python scripts/flow_query.py whoami
    python scripts/flow_query.py ops
    python scripts/flow_query.py op STROUT
    python scripts/flow_query.py doc SALORD 989
    python scripts/flow_query.py doc SALORD 989 --raw
    python scripts/flow_query.py list SALORD --party 49 --limit 10
    python scripts/flow_query.py list SALREQ --status A
    python scripts/flow_query.py sources STROUT --party 49
    python scripts/flow_query.py downstream SALORD 989
    python scripts/flow_query.py contacts --find "احمد جبر"
    python scripts/flow_query.py items --find 105
    python scripts/flow_query.py stock --item 105
    python scripts/flow_query.py agents
    python scripts/flow_query.py sql "select count(*) c from trnhdr where opcode='SALORD'"
"""

from __future__ import annotations

import argparse
import json
import sys

import _bootstrap  # noqa: F401  (puts src/ on the path)

from flow import FlowClient, FlowError, rows
from flow import lookup
from flow.documents import summarise

DOC_HEADER_FIELDS = ("OP", "DOCNO", "DOCDT", "CONO", "STRNO", "DISTNO", "DISTNA", "EMPNO",
                     "SRCDOCNO", "REFDOCNO", "EXPDT", "RMK", "DOCTOT", "DOCNET",
                     "TOTSALTAX", "TOTTRDTAX", "TOTDISC", "STS", "POST")
DOC_LINE_FIELDS = ("LN", "ITNO", "ITDES", "QTY", "EXEQTY", "ITPRICE", "DISC1", "SALTAX",
                   "ITSALTAX", "TRDTAX", "TBLTAXRTO", "ITMTOT", "ITMNET", "LOCID", "PCKID")
OPERATION_FIELDS = ("OP", "FORDES", "DOCDES", "MNU", "SRCDOC", "DISTTYP", "EFFECTITBAL",
                    "EFFECTSRCBAL", "NGBAL", "EXPDT", "EXPDAY", "ADDBIN", "RETBIN", "USESN",
                    "SALTAX", "TRDTAX", "ITPRICE", "MAXOVR", "POST", "CASH", "CREDIT")


def emit(label: str, value) -> None:
    print(label + " " + json.dumps(value, ensure_ascii=False, default=str), flush=True)


def pick(row: dict, fields) -> dict:
    return {field: row.get(field) for field in fields if field in row}


def cmd_whoami(client, args):
    client.login()
    emit("SESSION", client.session)
    emit("TENANT", {"company": client.cono, "store": client.strno})
    emit("COMPANY", pick(client.company(), ("CONO", "CONA", "FORDES", "CONNA", "CURCOD")))


def cmd_ops(client, args):
    found = client.getrec("select opcode,srcdoc,mnu from opdes order by mnu,opcode")
    emit("OPERATION_COUNT", len(found))
    for row in found:
        emit("OPERATION", row)


def cmd_op(client, args):
    emit("OPERATION", pick(client.operation(args.opcode), OPERATION_FIELDS))


def cmd_doc(client, args):
    document = client.getdoc(args.opcode, args.docno)
    if document is None:
        emit("NOT_FOUND", {"op": args.opcode.upper(), "docno": args.docno})
        return 1
    if args.raw:
        emit("DOCUMENT", document)
        return 0
    emit("HEADER", pick(document, DOC_HEADER_FIELDS))
    for line in rows(document.get("DTL")):
        emit("LINE", pick(line, DOC_LINE_FIELDS))
    return 0


def cmd_list(client, args):
    found = client.headers(args.opcode, docno=args.docno, srcdocno=args.source,
                           distno=args.party, status=args.status, limit=args.limit)
    emit("COUNT", len(found))
    for row in found:
        emit("ROW", row)


def cmd_sources(client, args):
    operation = client.operation(args.opcode)
    emit("OPERATION", pick(operation, ("OP", "SRCDOC", "EFFECTSRCBAL", "FRCSRC")))
    numbers = client.source_candidates(args.opcode, args.party)
    emit("ELIGIBLE_SOURCES", {"op": args.opcode.upper(), "source_op": operation.get("SRCDOC"),
                              "party": args.party, "count": len(numbers), "numbers": numbers})


def cmd_downstream(client, args):
    consumers = client.getrec(
        "select opcode,srcdoc from opdes where lower(srcdoc)='%s'" % args.opcode.lower())
    emit("CONSUMER_OPERATIONS", consumers)
    linked = client.downstream(args.docno, args.opcode)
    active = [row for row in linked if str(row.get("sts", "")).upper() != "D"]
    emit("LINKED", {"source": "%s/%s" % (args.opcode.upper(), args.docno),
                    "total": len(linked), "active": len(active)})
    for row in linked:
        emit("LINK", row)


def cmd_contacts(client, args):
    contacts = client.contacts(args.kind)
    emit("CONTACT_COUNT", len(contacts))
    if not args.find:
        return 0
    buckets = lookup.find_contacts(contacts, args.find)
    for bucket, found in buckets.items():
        for row in found[:args.limit]:
            emit("MATCH_" + bucket.upper(),
                 pick(row, ("CNO", "CNAME", "FORDES", "CONO", "STS", "CADD", "TEL1", "RGNO")))
    if not any(buckets.values()):
        emit("NO_MATCH", {"query": args.find})
    return 0


def cmd_items(client, args):
    items = client.items()
    emit("ITEM_COUNT", len(items))
    if not args.find:
        return 0
    needle = lookup.normalized(args.find)
    found = [row for row in items if str(row.get("ITNO")) == str(args.find)
             or needle in lookup.normalized(row.get("ITDES"))]
    emit("MATCHES", len(found))
    for row in found[:args.limit]:
        summary = pick(row, ("ITNO", "ITDES", "TOTBAL", "SALTAX", "TRDTAX", "UNIT", "STS"))
        summary["requires"] = lookup.item_requirements(row)
        emit("ITEM", summary)
    return 0


def cmd_stock(client, args):
    balances = client.balances()
    emit("BALANCE_ROWS", len(balances))
    if not args.item:
        return 0
    found = lookup.stock_for(balances, args.item)
    emit("STOCK", {"item": args.item, "rows": found})
    return 0


def cmd_agents(client, args):
    found = client.agents(args.job)
    emit("AGENT_COUNT", len(found))
    for row in found:
        emit("AGENT", row)


def cmd_sql(client, args):
    found = client.getrec(args.query)
    emit("ROWS", len(found))
    for row in found[:args.limit]:
        emit("ROW", row)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--company", dest="cono", default=None, help="company number (default 1)")
    parser.add_argument("--store", dest="strno", default=None, help="store number (default 1)")
    parser.add_argument("--quiet", action="store_true", help="suppress the credential/session banner")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("whoami", help="log in and show the session").set_defaults(func=cmd_whoami)
    sub.add_parser("ops", help="every operation code and its source").set_defaults(func=cmd_ops)

    one = sub.add_parser("op", help="live configuration of one operation")
    one.add_argument("opcode")
    one.set_defaults(func=cmd_op)

    doc = sub.add_parser("doc", help="retrieve one document")
    doc.add_argument("opcode")
    doc.add_argument("docno")
    doc.add_argument("--raw", action="store_true", help="print every field")
    doc.set_defaults(func=cmd_doc)

    listing = sub.add_parser("list", help="search trnhdr for documents")
    listing.add_argument("opcode")
    listing.add_argument("--docno", type=int)
    listing.add_argument("--source", type=int, help="filter by SRCDOCNO")
    listing.add_argument("--party", type=int, help="filter by customer/supplier code")
    listing.add_argument("--status", help="A active, D deleted")
    listing.add_argument("--limit", type=int, default=25)
    listing.set_defaults(func=cmd_list)

    sources = sub.add_parser("sources", help="source documents still eligible for an operation")
    sources.add_argument("opcode")
    sources.add_argument("--party", required=True, help="customer/supplier code")
    sources.set_defaults(func=cmd_sources)

    down = sub.add_parser("downstream", help="documents consuming a source document")
    down.add_argument("opcode", help="the SOURCE operation, e.g. SALORD")
    down.add_argument("docno", type=int)
    down.set_defaults(func=cmd_downstream)

    contacts = sub.add_parser("contacts", help="customers (C) or suppliers (S)")
    contacts.add_argument("--kind", default="C", choices=["C", "S", "c", "s"])
    contacts.add_argument("--find", help="name or code")
    contacts.add_argument("--limit", type=int, default=10)
    contacts.set_defaults(func=cmd_contacts)

    items = sub.add_parser("items", help="item master")
    items.add_argument("--find", help="item code or part of a description")
    items.add_argument("--limit", type=int, default=15)
    items.set_defaults(func=cmd_items)

    stock = sub.add_parser("stock", help="store balances")
    stock.add_argument("--item")
    stock.set_defaults(func=cmd_stock)

    agents = sub.add_parser("agents", help="sales agents")
    agents.add_argument("--job", type=int, default=100)
    agents.set_defaults(func=cmd_agents)

    sql = sub.add_parser("sql", help="run a read-only SELECT")
    sql.add_argument("query")
    sql.add_argument("--limit", type=int, default=50)
    sql.set_defaults(func=cmd_sql)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    client = FlowClient(verbose=not args.quiet, cono=args.cono, strno=args.strno)
    return args.func(client, args) or 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except FlowError as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        raise SystemExit(1)
