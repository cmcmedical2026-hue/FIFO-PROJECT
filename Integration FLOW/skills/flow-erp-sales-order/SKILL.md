---
name: flow-erp-sales-order
description: Create and verify a Sales Order (SALORD, أمر بيع) from an eligible Sales Request in this company's Flow ERP tenant. Use for order creation, not standalone Sales Request, inquiry-only, or invoices.
---

# Flow ERP Sales Order

Use alongside `flow-erp-sales`; read its document-entry and safety references. This skill covers one new `SALORD` document. Do not treat a source number or example in a HAR as the user's instruction to create an order.

## Source and tax review

- Verify the live operation has `SRCDOC=SALREQ`, then retrieve the exact Sales Request by operation/company/store/document number. Confirm its customer, agent, status, eligible positive remaining quantity, item, price, and expiry. Check the live source choices or balance before using it; if no balance remains, stop instead of recreating lines independently.
- Confirm the intended quantity and price against the source and current pricing policy. When the user asks for an order following a just-created request without specifying a subset, review the full remaining quantity and state that assumption before Save. Do not substitute another source silently.
- If tax treatment is **not explicit in the current order request**, ask before Save: “هل تريد ضريبة الصنف الافتراضية أم أخلي الضرائب 0؟” A previous order's zero-tax choice is not a permanent default. The order's tax may differ from its source request; changing it in the order does not authorize editing the request or the item master.
- For zero tax, review every applicable line rate and tax amount (VAT, trade/table tax, shipping tax if relevant) and recompute line/total values consistently. A captured source line may contain tax amounts even after its rate is set to zero. Verify payment, discounts, shipping, location, and total before Save.

## Save once, then retrieve

- Save the new order (`DOCNO=0`) through `POSCMD/ADDPOS` once, with the exact `SRCDOCNO`. If Python/no browser is requested, use a HAR only for schema and credentials only with explicit current authorization; authenticate freshly and never embed or print credentials/API keys. Build from the **live source**, not stale example customer/line data, and recalculate fields affected by tax or price changes.
- Capture `CMDDNE,<number>`, then retrieve `GETDOC/SALORD/<company>/<store>/<number>` and verify source number, customer, agent, date, lines, quantities, prices, zero or selected tax amounts, total, status, and `POST` separately. Check the source's remaining eligibility/balance after the order. Do not issue a separate Post or modify the source request unless requested. On an uncertain Save response, investigate read-only and never blindly retry.

## Run it

```bash
python scripts/flow_query.py op SALORD                      # confirm SRCDOC=SALREQ and EFFECTSRCBAL
python scripts/flow_query.py doc SALREQ <source>            # the exact source: customer, agent, lines, remaining qty
python scripts/flow_query.py sources SALORD --party <CNO>   # is that request still eligible?
python scripts/flow_query.py downstream SALREQ <source>     # does an order already consume it?

python scripts/create_document.py --op SALORD --source <SALREQ number> --from-source --tax zero
# --from-source takes each source line's remaining quantity at its source price.
# For a partial order, use explicit --line ITEM:QTY:PRICE instead.
# Read the PREVIEW line, confirm the tax choice, then re-run with --commit

python scripts/flow_query.py doc SALORD <number>            # verify source, lines, tax amounts, total, STS, POST
python scripts/flow_query.py sources SALORD --party <CNO>   # the source should no longer be listed
```

The preflight refuses to build an order when the request is not listed as
eligible, or when an active order already consumes it. Both refusals are real
findings — report them rather than working around them with `--allow-duplicate`.
