"""Create one Flow ERP document of any operation, with a full preflight.

Dry run by default. Nothing is sent until ``--commit`` is passed, and even then
exactly one save is attempted -- never a retry.

    # a standalone request (no source document)
    python scripts/create_document.py --op SALREQ --party 26 --agent 10 \
        --line 75:18:1000 --tax default

    # an order that consumes a request, taking its remaining lines as they are
    python scripts/create_document.py --op SALORD --source 997 --from-source --tax zero

    # an inventory issue from an order, with lot/expiry recorded as a remark
    python scripts/create_document.py --op STROUT --source 989 --from-source \
        --remark "(105) 22/3/2028 36112025004"

Preflight always checks: the operation's live configuration, that the source is
still eligible, that no active document already consumes it, that each item can
be sold as a plain line, and that stock covers the quantity when the operation
decreases stock and negative balances are disallowed.
"""

from __future__ import annotations

import argparse
import json
import sys

import _bootstrap  # noqa: F401

from flow import FlowClient, FlowError, rows
from flow import documents, lookup


def emit(label: str, value) -> None:
    print(label + " " + json.dumps(value, ensure_ascii=False, default=str), flush=True)


def parse_line_spec(spec: str) -> dict:
    """``ITEM:QTY[:PRICE[:DISCOUNT]]``"""
    parts = spec.split(":")
    if len(parts) < 2:
        raise FlowError("--line needs at least ITEM:QTY, got %r" % spec)
    entry = {"item": parts[0].strip(), "qty": float(parts[1])}
    if len(parts) > 2 and parts[2] != "":
        entry["price"] = float(parts[2])
    if len(parts) > 3 and parts[3] != "":
        entry["discount"] = float(parts[3])
    return entry


def resolve_tax(choice: str, item: dict):
    """``default`` = the item's own rate, ``zero`` = 0, or an explicit number."""
    if choice == "default":
        return float(item.get("SALTAX") or 0)
    if choice == "zero":
        return 0.0
    return float(choice)


def check_source(client: FlowClient, operation: dict, source_no, party,
                 *, allow_duplicate: bool) -> dict:
    source_op = str(operation.get("SRCDOC") or "")
    if source_op in ("", "-1", "N"):
        raise FlowError("Operation %s takes no source document, but --source was given"
                        % operation.get("OP"))
    source = client.getdoc(source_op, source_no)
    if source is None:
        raise FlowError("Source %s/%s was not found" % (source_op, source_no))
    if str(source.get("STS", "")).upper() == "D":
        raise FlowError("Source %s/%s is deleted" % (source_op, source_no))
    emit("SOURCE", {"op": source_op, "docno": source.get("DOCNO"), "party": source.get("DISTNO"),
                    "party_name": source.get("DISTNA"), "agent": source.get("EMPNO"),
                    "date": source.get("DOCDT"), "status": source.get("STS"),
                    "post": source.get("POST"), "total": source.get("DOCTOT")})
    if party is not None and str(source.get("DISTNO")) != str(party):
        raise FlowError("Source belongs to party %s, not %s" % (source.get("DISTNO"), party))

    eligible = client.source_candidates(operation["OP"], source.get("DISTNO"))
    emit("SOURCE_ELIGIBILITY", {"target": str(source_no), "listed": str(source_no) in eligible,
                                "eligible_count": len(eligible), "eligible": eligible[:25]})
    if str(source_no) not in eligible:
        raise FlowError(
            "Source %s/%s is not listed as available for a new %s. It may already be fully "
            "consumed. Check with: flow_query.py downstream %s %s"
            % (source_op, source_no, operation["OP"], source_op, source_no))

    linked = client.downstream(int(source_no), source_op)
    active = [row for row in linked if str(row.get("sts", "")).upper() != "D"]
    emit("EXISTING_DOWNSTREAM", {"total": len(linked), "active": len(active), "rows": linked})
    same_op = [row for row in active if str(row.get("opcode", "")).upper() == operation["OP"]]
    if same_op and not allow_duplicate:
        raise FlowError(
            "%d active %s document(s) already consume %s/%s: %s. Retrieve them instead of "
            "creating a duplicate, or pass --allow-duplicate if a second one is genuinely wanted."
            % (len(same_op), operation["OP"], source_op, source_no,
               ", ".join(str(row.get("docno")) for row in same_op)))
    return source


def lines_from_source(source: dict, items_by_code: dict) -> list:
    """Remaining (unexecuted) quantity of every source line."""
    built = []
    for line in rows(source.get("DTL")):
        remaining = float(line.get("QTY") or 0) - float(line.get("EXEQTY") or 0)
        if remaining <= 0:
            continue
        built.append({"item": str(line.get("ITNO")), "qty": remaining,
                      "price": float(line.get("ITPRICE") or 0),
                      "discount": float(line.get("DISC1") or 0)})
    if not built:
        raise FlowError("Source document has no remaining quantity on any line")
    return built


def check_stock(client: FlowClient, operation: dict, requested: list) -> None:
    """Refuse to issue more than the store holds when the tenant disallows negatives."""
    if str(operation.get("EFFECTITBAL", "")).upper() != "S":
        return
    if str(operation.get("NGBAL", "N")).upper() == "Y":
        emit("STOCK_CHECK", {"skipped": "operation allows negative balances"})
        return
    balances = client.balances()
    problems = []
    for entry in requested:
        found = lookup.stock_for(balances, entry["item"])
        available = sum(float(row.get("TOTBAL", row.get("BAL", 0)) or 0) for row in found)
        emit("STOCK", {"item": entry["item"], "needed": entry["qty"],
                       "available": available, "rows": len(found)})
        if found and available < entry["qty"]:
            problems.append("item %s needs %s but the store holds %s"
                            % (entry["item"], entry["qty"], available))
    if problems:
        raise FlowError("Insufficient stock: " + "; ".join(problems))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--op", required=True, help="operation code, e.g. SALREQ, SALORD, STROUT")
    parser.add_argument("--company", dest="cono", default=None)
    parser.add_argument("--store", dest="strno", default=None)
    parser.add_argument("--party", help="customer/supplier code, or a name to resolve")
    parser.add_argument("--agent", help="sales agent code or name")
    parser.add_argument("--source", help="source document number")
    parser.add_argument("--from-source", action="store_true",
                        help="take the remaining quantity of every source line")
    parser.add_argument("--line", action="append", default=[], metavar="ITEM:QTY[:PRICE[:DISC]]")
    parser.add_argument("--tax", default="default",
                        help="'default' (item rate), 'zero', or an explicit rate such as 14")
    parser.add_argument("--date", help="document date YYYY-MM-DD (default: the tenant's today)")
    parser.add_argument("--remark", default="", help="header RMK, e.g. lot/expiry notes")
    parser.add_argument("--reference", default="", help="header REFDOCNO")
    parser.add_argument("--allow-duplicate", action="store_true",
                        help="proceed even if an active document already consumes the source")
    parser.add_argument("--commit", action="store_true", help="actually save (one attempt)")
    args = parser.parse_args()

    if not args.line and not args.from_source:
        parser.error("give at least one --line, or --from-source")
    if args.from_source and not args.source:
        parser.error("--from-source needs --source")

    client = FlowClient(cono=args.cono, strno=args.strno)
    client.login()
    op = args.op.upper()

    operation = client.operation(op)
    emit("OPERATION", {k: operation.get(k) for k in
                       ("OP", "FORDES", "SRCDOC", "DISTTYP", "EFFECTITBAL", "EFFECTSRCBAL",
                        "NGBAL", "EXPDT", "EXPDAY", "ADDBIN", "SALTAX", "TRDTAX", "POST")})

    kind = str(operation.get("DISTTYP") or "C").upper()
    contacts = client.contacts(kind)
    items = client.items()
    items_by_code = {str(row.get("ITNO")): row for row in items if isinstance(row, dict)}

    source = None
    party = args.party
    if args.source:
        source = check_source(client, operation, args.source, party,
                              allow_duplicate=args.allow_duplicate)
        party = source.get("DISTNO")
    if party is None:
        raise FlowError("--party is required when there is no source document")

    contact = lookup.resolve_contact(contacts, party)
    emit("PARTY", {"code": contact.get("CNO"), "name": contact.get("CNAME"),
                   "kind": kind, "company": contact.get("CONO")})

    requested = ([parse_line_spec(spec) for spec in args.line] if args.line
                 else lines_from_source(source, items_by_code))

    docdt = documents.parse_date(args.date) if args.date else documents.tenant_today(client)
    payload = documents.new_draft(client, op, docdt=docdt, srcdocno=args.source)
    documents.apply_contact(payload, contact)
    if args.remark and "RMK" in payload:
        payload["RMK"] = args.remark
    if args.reference and "REFDOCNO" in payload:
        payload["REFDOCNO"] = args.reference
    if "EXPDT" in payload and str(operation.get("EXPDT", "N")).upper() == "Y":
        payload["EXPDT"] = documents.expiry_from_operation(operation, docdt)

    if args.agent and "EMPNO" in payload:
        agent = lookup.resolve_agent(client.agents(), args.agent)
        payload["EMPNO"] = int(agent["empno"])
        emit("AGENT", {"code": agent.get("empno"), "name": agent.get("empnm")})
    elif source is not None and "EMPNO" in payload and source.get("EMPNO") is not None:
        payload["EMPNO"] = int(source["EMPNO"])

    expected_lines = []
    for index, entry in enumerate(requested, start=1):
        item = lookup.resolve_item(items, entry["item"])
        requires = lookup.item_requirements(item)
        if requires:
            raise FlowError("Item %s needs structured fields this script does not fill: %s"
                            % (entry["item"], "; ".join(requires)))
        price = entry.get("price")
        if price is None:
            raise FlowError("No price for item %s; give it as ITEM:QTY:PRICE" % entry["item"])
        rate = resolve_tax(args.tax, item)
        line = documents.new_line(op, item, qty=entry["qty"], price=price, line_no=index,
                                  vat_rate=rate, discount=entry.get("discount", 0),
                                  template=documents.load_template(op))
        documents.add_line(payload, line)
        expected_lines.append({"item": str(item.get("ITNO")), "qty": entry["qty"],
                               "price": price, "vat_rate": rate})

    check_stock(client, operation, requested)

    expect = {"OP": op, "CONO": client.cono, "STRNO": client.strno,
              "DISTNO": contact.get("CNO"), "lines": expected_lines}
    if args.source and "SRCDOCNO" in payload:
        expect["SRCDOCNO"] = args.source

    result = documents.save_and_verify(client, payload, confirm=args.commit, expect=expect)
    if result.get("saved") and args.source:
        after = client.source_candidates(op, contact.get("CNO"))
        emit("SOURCE_STILL_ELIGIBLE", {"source": args.source, "listed": str(args.source) in after})
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except FlowError as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        raise SystemExit(1)
