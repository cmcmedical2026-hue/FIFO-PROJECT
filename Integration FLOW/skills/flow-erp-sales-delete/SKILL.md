---
name: flow-erp-sales-delete
description: Delete and verify an existing Sales Order (SALORD) or Sales Request (SALREQ) in this company's Flow ERP tenant. Use for authorized deletion of these documents, including a linked order/request pair; not for creation, editing, or other Sales operations.
---

# Delete Flow ERP Sales Order or Sales Request

Use alongside `flow-erp-sales`; read its document and safety references. A captured HAR, an example number, or an earlier deletion is not authorization. Require a current user request that identifies the exact document(s). If the identity or intended scope is ambiguous, resolve it before the consequential delete.

## Preflight

1. Retrieve each target with `GETDOC/<OPCODE>/<CONO>/<STRNO>/<DOCNO>` (under `api/POSCMD`) and match operation, company, store, document number, customer, source, and distinctive lines against the user's intended record. Do not rely on document number alone: different operation types can reuse numbers.
2. Check current `STS` and the operation's live dependency configuration. Find *active* downstream documents by the correct source operation and exact company/store/source number, not just `SRCDOCNO`: another operation may coincidentally refer to the same number. If stock, invoice, or other downstream effects exist, stop and explain what must be handled first; do not cascade-delete them without the user's instruction.
3. For a linked `SALORD` → `SALREQ` pair, delete the order first. Before deleting the request, confirm the order is `STS=D`, no other active order remains linked, and the request is still the exact intended active document. A deleted order's retained database row is not an active dependency.
4. Review the exact target and impact immediately before each delete. If an intended target is already `D`, treat it as deleted and do not send `DELPOS` again.

## Delete once and verify

- In the POS UI, retrieve the target by operation/company/store/document number, use **Delete**, and confirm. If the user requests Python/no browser, use captured HAR material only for request schema and credentials when explicitly authorized; authenticate freshly, never hardcode or print credentials/API keys, and use the current returned key. The observed legacy command is `DELPOS,OPCODE=<OPCODE>\fCONO=<CONO>\fSTRNO=<STRNO>\fDOCNO=<DOCNO>\f\v`, sent as `cmdtxt=EXECMD` and `cmdpar` to the Flow root endpoint with the session's auth and `XAPIKEY`. Do not replay an old HAR delete request verbatim.
- Send a delete command only once for each exact target. `CMDDNE,`/HTTP 200 is not sufficient proof. Retrieve the same `GETDOC` and, where available, the exact `trnhdr` row to verify `STS=D`; this tenant retains deleted rows (soft deletion). Check that the deleted request is no longer an eligible order source. An existing row alone is not a deletion failure.
- On timeout, HTTP error, or contradictory status, perform read-only status checks before considering any retry. Never blindly resend. Report each document's verified status and explain that `D` does not prove physical removal or guaranteed recoverability. Do not claim that related stock/accounting documents were deleted unless separately requested and verified.

## Run it

```bash
python scripts/flow_query.py doc SALORD <number>            # confirm it is the intended record
python scripts/flow_query.py downstream SALORD <number>     # any active document consuming it?

python scripts/delete_document.py SALORD <number>                  # preflight, nothing sent
python scripts/delete_document.py SALORD <number> --commit         # one delete
python scripts/delete_document.py SALORD <number> --with-sources --commit
# --with-sources walks up the chain (order -> its request) and deletes newest first,
# re-checking dependencies before each step.

python scripts/flow_query.py list SALORD --docno <number>   # confirm sts=D on the header row
python scripts/flow_query.py sources SALORD --party <CNO>   # a deleted request must no longer be an eligible source
```

The script refuses to run while an active downstream document exists and it
never cascades. `--party <CNO>` asserts the target belongs to the customer you
expect — use it whenever the number came from the user rather than from a query
you just ran.

Deletion is soft. Report `STS=D`, and state plainly that the row is retained and
that this is not a guarantee of recoverability.
