"""Delete one Flow ERP document, or a linked chain of them, with a full preflight.

Deletion in this tenant is **soft**: the row stays and ``STS`` becomes ``D``.
That is not the same as the document never having existed, and it is not a
guarantee that it can be restored.

Dry run by default.

    python scripts/delete_document.py SALORD 987                 # preflight only
    python scripts/delete_document.py SALORD 987 --commit        # delete one
    python scripts/delete_document.py SALREQ 997 --with-sources --commit

``--with-sources`` walks up the chain (order -> its request) and deletes from the
newest document backwards, re-checking dependencies before each step.

Refuses to run while any **active** downstream document consumes the target.
Deal with those first, deliberately; this script will not cascade for you.
"""

from __future__ import annotations

import argparse
import json
import sys

import _bootstrap  # noqa: F401

from flow import FlowClient, FlowError

DESCRIBE = ("OP", "DOCNO", "CONO", "STRNO", "DISTNO", "DISTNA", "EMPNO", "SRCDOCNO",
            "DOCDT", "DOCTOT", "STS", "POST")


def emit(label: str, value) -> None:
    print(label + " " + json.dumps(value, ensure_ascii=False, default=str), flush=True)


def describe(document: dict) -> dict:
    summary = {field: document.get(field) for field in DESCRIBE if field in document}
    summary["lines"] = [{"item": line.get("ITNO"), "qty": line.get("QTY"),
                         "price": line.get("ITPRICE")}
                        for line in (document.get("DTL") or [])]
    return summary


def header_row(client: FlowClient, op: str, docno: int):
    found = client.headers(op, docno=docno, limit=2)
    if len(found) != 1:
        raise FlowError("%s/%s matched %d header rows; refusing to act on an ambiguous target"
                        % (op, docno, len(found)))
    return found[0]


def preflight(client: FlowClient, op: str, docno: int, *, expect_party=None) -> dict:
    document = client.getdoc(op, docno)
    if document is None:
        raise FlowError("%s/%s was not found" % (op, docno))
    emit("TARGET", describe(document))
    row = header_row(client, op, docno)
    emit("TARGET_ROW", row)
    status = str(row.get("sts", "")).upper()
    if status == "D":
        emit("ALREADY_DELETED", {"op": op, "docno": docno})
        return {"document": document, "status": status, "skip": True}
    if expect_party is not None and str(document.get("DISTNO")) != str(expect_party):
        raise FlowError("%s/%s belongs to party %s, not %s"
                        % (op, docno, document.get("DISTNO"), expect_party))

    linked = client.downstream(int(docno), op)
    active = [entry for entry in linked if str(entry.get("sts", "")).upper() != "D"]
    emit("DOWNSTREAM", {"total": len(linked), "active": len(active), "rows": linked})
    if active:
        raise FlowError(
            "%d active document(s) still consume %s/%s: %s. Handle them first; this script "
            "does not cascade." % (len(active), op, docno,
                                   ", ".join("%s/%s" % (e.get("opcode"), e.get("docno"))
                                             for e in active)))
    return {"document": document, "status": status, "skip": False}


def delete_one(client: FlowClient, op: str, docno: int, *, commit: bool,
               expect_party=None) -> bool:
    checked = preflight(client, op, docno, expect_party=expect_party)
    if checked["skip"]:
        return False
    if not commit:
        emit("DRY_RUN", {"would_delete": "%s/%s/%s/%s" % (op, client.cono, client.strno, docno)})
        return False

    status, text = client.delpos_write(op, int(docno), confirm=True)
    emit("DELETE_RESPONSE", {"op": op, "docno": docno, "http": status, "text": text})

    # A 200 is not proof. Re-read both the header row and the document.
    row = header_row(client, op, docno)
    after = client.getdoc(op, docno)
    row_status = str(row.get("sts", "")).upper()
    doc_status = str((after or {}).get("STS", "")).upper()
    emit("VERIFIED", {"op": op, "docno": docno, "row_status": row_status,
                      "document_status": doc_status, "soft_deleted": row_status == "D"})
    if row_status != "D":
        raise FlowError(
            "%s/%s did not reach status D. Do not resend the delete; investigate read-only."
            % (op, docno))
    return True


def chain_up(client: FlowClient, op: str, document: dict) -> list:
    """The source documents above this one, nearest first."""
    steps = []
    current_op, current = op, document
    while True:
        operation = client.operation(current_op)
        source_op = str(operation.get("SRCDOC") or "")
        source_no = current.get("SRCDOCNO")
        if source_op in ("", "-1", "N") or not source_no or str(source_no) in ("0", ""):
            break
        parent = client.getdoc(source_op, source_no)
        if parent is None:
            emit("CHAIN_MISSING", {"op": source_op, "docno": source_no})
            break
        steps.append((source_op, int(source_no)))
        current_op, current = source_op, parent
    return steps


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("opcode")
    parser.add_argument("docno", type=int)
    parser.add_argument("--company", dest="cono", default=None)
    parser.add_argument("--store", dest="strno", default=None)
    parser.add_argument("--party", help="assert the document belongs to this customer/supplier")
    parser.add_argument("--with-sources", action="store_true",
                        help="also delete the source documents above this one")
    parser.add_argument("--commit", action="store_true", help="actually delete")
    args = parser.parse_args()

    client = FlowClient(cono=args.cono, strno=args.strno)
    client.login()
    op = args.opcode.upper()

    document = client.getdoc(op, args.docno)
    if document is None:
        raise FlowError("%s/%s was not found" % (op, args.docno))

    targets = [(op, args.docno)]
    if args.with_sources:
        targets.extend(chain_up(client, op, document))
    emit("PLAN", {"order": ["%s/%s" % (o, n) for o, n in targets],
                  "mode": "commit" if args.commit else "dry-run"})

    deleted = []
    for index, (target_op, target_no) in enumerate(targets):
        emit("STEP", {"position": index + 1, "of": len(targets),
                      "target": "%s/%s" % (target_op, target_no)})
        if delete_one(client, target_op, target_no, commit=args.commit,
                      expect_party=args.party if index == 0 else None):
            deleted.append("%s/%s" % (target_op, target_no))

    emit("RESULT", {"deleted": deleted, "count": len(deleted),
                    "note": "soft deletion: rows are retained with STS=D"})
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except FlowError as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        raise SystemExit(1)
