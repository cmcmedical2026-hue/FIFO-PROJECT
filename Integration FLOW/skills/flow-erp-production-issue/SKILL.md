---
name: flow-erp-production-issue
description: Create or verify a Production Issue (STROUT, صرف بضاعة) sourced from a Sales Order in this company's Flow ERP tenant, with item-specific lot/expiry remarks and optional print. Use for inventory issue from an order, not Sales Order creation, invoices, or unrelated stock adjustments.
---

# Flow ERP Production Issue

Use with `flow-erp-inventory` and its document and safety references. `Production Issue` is Inventory `#POS,OPCODE=STROUT`; verify live `GETOPC/STROUT` still says `SRCDOC=SALORD` and inspect stock/source/expiry rules. A prior example or captured document does not authorize a new issue.

## Identify the exact source

- Resolve the Sales Order by operation **SALORD**, company, store, number, customer, date, and item lines. Names may have prefixes such as `د.`; match the actual customer record. If a name/code yields multiple orders, do not pick a historical order solely because it is newest. Use an unambiguous current context or ask for the order number.
- Check the live `STROUT` source choices/remaining balance and active issues already linked to that exact order (`STROUT`, company, store, `SRCDOCNO`, customer). Do this again just before Save because another user may issue stock during preparation. `GETDOC/SALORD` line `EXEQTY` alone may still show zero even when a linked active issue exists; never use it as the sole duplicate check.
- If an existing issue covers the intended items, quantities, and lot/expiry remarks, retrieve and report its exact document/status instead of saving a duplicate. If it partially covers them or the source has no remaining balance, stop and explain the mismatch rather than bypassing the source.

## Build and save

- Select the exact eligible Sales Order as source; carry only positive remaining quantities. If quantities are omitted and a full issue is implied, review the full remaining quantity per line and state that assumption before Save. Confirm store/location stock is sufficient when negative balance is disallowed, plus any active item packing, unit, serial, or expiry requirements. Do not invent a different store or quantity.
- Map each supplied item code to its own lot and expiry. In this tenant, observed ordinary items had `EXPDT=N`/`ADDBIN=N` on `STROUT`, and the lot/expiry were recorded in header `RMK` as separate item-labelled lines. That is a text remark, **not** a structured stock-batch assignment. If the live item/operation requires a structured expiry bin, use its verified fields and stock batch, not remarks as a substitute. Do not guess an unprovided lot/date; resolve any ambiguous mapping first.
- Review operation, company/store, date, source order, customer, each item/quantity/price/tax, location, lot/expiry text, and total. Adding lines only stages them. Global Save persists through `POSCMD/ADDPOS` once; do not issue a separate Post unless requested. If Python/no browser is explicitly requested, authenticate freshly with an authorized credential source, keep secrets out of files/output, and derive the current `STROUT` payload/schema from live evidence rather than copying a stale `SALORD` save verbatim. Do not assume an untested API payload is valid.

## Verify and print

- Capture the saved number, retrieve `GETDOC/STROUT/<company>/<store>/<number>`, and confirm source order, customer, all items/quantities, exact `RMK` mapping, status and `POST` separately. Confirm the stock/source effect through the relevant source eligibility, linked-document, and store-balance checks; do not rely on a success response alone. On uncertain Save, investigate read-only before any retry.
- When the requested workflow includes Print, invoke the configured `PRTPOS` for the **verified** operation/company/store/document and inspect the generated result. Do not claim a physical printer produced paper from a report preview alone.

## Run it

```bash
python scripts/flow_query.py op STROUT                      # confirm SRCDOC=SALORD, EFFECTITBAL=S, NGBAL, ADDBIN
python scripts/flow_query.py doc SALORD <order>             # the exact order: customer, items, remaining qty
python scripts/flow_query.py downstream SALORD <order>      # STROUT *and* STROU1 both consume SALORD
python scripts/flow_query.py sources STROUT --party <CNO>   # empty list = the order is already fully issued
python scripts/flow_query.py stock --item <ITNO>            # NGBAL=N means stock must cover the quantity

python scripts/create_document.py --op STROUT --source <order> --from-source \
    --remark "(105) 22/3/2028 36112025004
(107) 8/1/2028 36122025001"
# Read the PREVIEW line, then re-run with --commit

python scripts/flow_query.py doc STROUT <number>            # verify source, every line, the exact RMK text, STS, POST
```

Lot and expiry go in the header `RMK` as one labelled line per item, because
this tenant's ordinary items have `ADDBIN=N` on `STROUT`. That is a **text
remark, not a structured batch assignment** — say so when reporting. If a live
item or operation turns out to require a real expiry bin, stop and use its
verified fields instead of the remark.

Never guess a lot number or an expiry date that was not supplied.
