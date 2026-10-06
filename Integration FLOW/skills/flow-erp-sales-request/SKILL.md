---
name: flow-erp-sales-request
description: Create and verify a new Sales Request (SALREQ, طلب بيع) in this company's Flow ERP tenant. Use for document creation, not Sales Order, inquiry-only, or generic sales reporting.
---

# Flow ERP Sales Request

Use alongside `flow-erp-sales`; read its document-entry and safety references. This skill covers one new `SALREQ` document, not a Sales Order or an edit of a saved document. The user must request the mutation; a HAR capture or earlier example is not authorization.

## Prepare

- Verify the live `SALREQ` operation configuration, company, store, active customer, agent, item, unit/packing/location requirements, date, quantity, unit price, discounts, shipping, and totals. Select company before store and dependent lookups. `SALREQ` has no source document; a new document uses `DOCNO=0` or a blank number in the UI.
- If the user has **not specified tax treatment for this particular document**, ask before Save: “هل تريد ضريبة الصنف الافتراضية أم أخلي الضرائب 0؟” Do not carry over the zero-tax choice from a previous Sales Order. If the user explicitly chose a rate or zero for this document, use that choice and review the resulting amount. This is a per-document choice, not a change to item or tenant tax setup.
- For “today,” use the tenant's Africa/Cairo date. Verify any live expiry/default fields rather than copying a date from a prior capture.

## Persist and verify

- Stage the lines, review the exact company/store/customer/agent/item/quantity/price/tax/totals, then Save once through the POS engine (`POSCMD/ADDPOS`). `Add Item` alone does not persist.
- If the user requests Python without a browser, a HAR can inform the request schema; use credentials from it only when the user explicitly authorizes that source. Authenticate freshly, keep credentials/API keys out of source files and output, and use the returned key for the API. Replace every stale customer, date, item, price, tax, and remark in a captured payload with live values. Do not hardcode example record IDs.
- A `CMDDNE,<number>` response identifies the saved document, but retrieve `GETDOC/SALREQ/<company>/<store>/<number>` and verify header, line, tax amounts, total, status, and `POST` separately. Do not issue a separate Post unless requested. If Save times out or returns an uncertain response, investigate read-only; never blindly resend and risk a duplicate.

## Run it

```bash
python scripts/flow_query.py op SALREQ                      # confirm SRCDOC is -1, check EXPDAY and tax flags
python scripts/flow_query.py contacts --find "<customer>"   # resolve the exact CNO
python scripts/flow_query.py agents                         # resolve the agent EMPNO
python scripts/flow_query.py items --find <item>            # price, tax rate, and any structured-field requirement

python scripts/create_document.py --op SALREQ \
    --party <CNO> --agent <EMPNO> --line <ITNO>:<QTY>:<PRICE> --tax default
# read the PREVIEW line, confirm the tax choice with the user, then re-run with --commit

python scripts/flow_query.py doc SALREQ <number>            # independent verification
```

`--tax default` uses the item's own rate; `--tax zero` zeroes VAT, trade and
table tax and clears the computed amounts. That choice belongs to this document
only — do not carry it into the next one.
