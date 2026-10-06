---
name: flow-erp-inventory-lots
description: Read-only lot / expiry / cost balance for a Flow ERP store (مخزون المقطم 1), rebuilt from Flow movements on top of a counted opening balance, reconciled to physical counts (جرد). Use for "رصيد باللوط", "مطابقة الجرد", "صلاحيات", the daily movement pull, and valuing stock at purchase-batch cost. Not for creating or deleting documents, and not Flow's own average cost.
---

# Flow ERP inventory by lot

Flow tracks quantity per item only, and values it at a running average. The
General Manager wants each purchase batch kept at its own price and each lot
tracked by what the documents say. `scripts/lot_ledger.py` rebuilds that from
Flow; this skill is the judgement around it. Nothing here writes to Flow.

## Inputs (`data/inventory/`)

- `plan.json` — store, opening file, and the counts to reconcile against, in date order.
- `opening_*.json` — the counted opening balance, one row per cost batch.
- `lot_catalog.json` — every known lot per item with its expiry, plus aliases for
  the spellings that appear in remarks (truncated or mistyped lot numbers, relabelled lots).
- `overrides.json` — lot splits and costs decided by hand, keyed `OPCODE:DOCNO:ITEM`, each with a `why`.
- `count_*.json` — each physical count, lot by lot, with `as_of` set to the day of
  Flow movements it actually reflects (a count taken in the morning reflects the previous evening).
- `questions.json` — what is waiting on the user. Keep it current; it goes into the workbook.

## Rules that are settled

- Quantity is Flow's: `trndtl` `STS='A'`, `EFFECTITBAL` `A`/`S`, `STRQTY` (bonus included). The ledger total per item must equal Flow per item — check it every run.
- Lot, in order: override → the lot in the remark (number first, then expiry) → earliest expiry with stock, which is a guess and is shown in amber.
- Cost (clarified by the user on 2026-09-28): purchase receipts (`STRIN2`) create batches at Flow's actual incoming `ITPRICE` / `pr`, retaining item, quantity, lot and expiry when available. No separate invoice match is required. Issues and all returns, including purchase returns, are calculated from the sheet's opening/purchase batches by item, lot and expiry; trace a return to the original issue batch. Never use Flow's running/average/calculated `COST`, invoice/issue cost, or a non-purchase price for these calculations. If the sheet batch cannot be established, leave cost unresolved and flag it. Preserve zero/unusual purchase receipt prices and flag them without stopping the authorized import.
- When the user says a count's lots are right and the documents disagree, alias the documents' lot to the counted one in `lot_catalog.json` rather than overriding line by line.
- At each count: if the item total agrees, lots are relabelled to the count and batches move with their own cost (no value change). If the total differs, it stays an open difference — never force it; ask.

## When to stop and ask

- Any item total that differs from a count.
- A proposed value change beyond importing the actual purchase receipt price: a return whose source batch is unclear, or an expired lot that may need writing off. Authorized receipt prices are imported as reported; unusual prices are review flags.
- A remark whose lot contradicts the count or the receipt, when the lots have different costs. When costs are equal, relabel and mention it.
- A lot or expiry that appears nowhere in the catalogue: add it only once the user confirms it.

## Daily run

1. Run the ledger to today and confirm `TOTAL` qty equals Flow's store balance.
2. Read the new `LINE`s since the last run. Any `fefo`/`default` line means the remark had no usable lot: fix with an override if the documents make it clear, otherwise ask.
3. Report per item: quantity, lots with expiry, value; flag expired and near-expiry lots.
4. Regenerate the workbook and hand it over.

## Run it

```bash
python scripts/lot_ledger.py                                  # balance by lot as of today
python scripts/lot_ledger.py --since <YYYY-MM-DD>             # plus every line since that date
python scripts/lot_ledger.py --to <YYYY-MM-DD>                # as of a past date
python scripts/lot_ledger.py --xlsx <out.xlsx>                # workbook (pip install openpyxl)
python scripts/flow_query.py sql "select ITNO, sum(case when EFFECTITBAL='A' then STRQTY else -STRQTY end) q from trndtl where CONO=1 and STRNO=1 and STS='A' and EFFECTITBAL in ('A','S') group by ITNO having q<>0"
```
