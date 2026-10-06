# Operation catalogue

The tenant defines **40 operations**. `TEMPLATE` marks the 15 we have a captured
`ADDPOS` payload for — those can be created by `scripts/create_document.py`
today. The rest need a HAR capture first (see "Adding an operation" below).

Read the live configuration before acting on any of them:

```bash
python scripts/flow_query.py op STROUT
```

## Sales — menu `SALDOC`

| Code | Source | Template | Arabic / meaning |
|---|---|---|---|
| `SALREQ` | standalone | TEMPLATE | طلب بيع — Sales Request |
| `SALORD` | `SALREQ` | TEMPLATE | أمر بيع — Sales Order |
| `SALINV` | `STROUT` | TEMPLATE | فاتورة مبيعات — Sales Invoice |
| `SALRT2` | `SALINV` | TEMPLATE | طلب مرتجع عميل — Customer Return Request |
| `SALRTN` | `STRMRT` | TEMPLATE | مرتجع مبيعات — Sales Return |
| `SALRE` | standalone | TEMPLATE | طلب عينات — Samples Request |
| `SALCON` | — | — | Sales contract |
| `SALIN1` | standalone | — | Direct invoice variant |
| `SALIN3` | `STROU3` | — | Invoice variant 3 |
| `SALRT1` | standalone | — | Return variant 1 |
| `SALRT3` | `SALIN3` | — | Return variant 3 |
| `STROU2` | — | — | Issue variant 2 |

## Inventory / stores — menu `STRDOC`

| Code | Source | Template | Arabic / meaning |
|---|---|---|---|
| `STROUT` | `SALORD` | TEMPLATE | إذن صرف — Production Issue |
| `STROU1` | `SALORD` | — | Second issue operation on the same source |
| `STRMAK` | `SALRE` | TEMPLATE | إذن صرف عينات — Sample Issue |
| `STRMRS` | `STRMAK` | TEMPLATE | طلب مرتجع عينات — Samples Return Request |
| `STRMR` | `STRMRS` | TEMPLATE | مرتجع عينات — Samples Return |
| `STRMRT` | `SALRT2` | — | **Gap**: feeds `SALRTN`, not yet captured |
| `PRCREV` | `PRCORD` | TEMPLATE | تقرير فحص — Inspection Report |
| `STRIN2` | `PRCREV` | TEMPLATE | إذن إضافة موردين — Supplier Additions |
| `BURRET` | standalone | — | Feeds `PRCRTN` |
| `RTNRQS` | `PRCREQ` | — | Purchase request return |
| `RTNSAL` | `SALINV` | — | Sales invoice return |
| `STRIN3`, `STRIN9`, `STRMAM`, `STRMAN`, `STROU3`, `STROU9`, `STRROT`, `STRRTE`, `STRRTN`, `STRRTS`, `TRNORD` | various | — | Transfers, adjustments, other stock movements |

## Purchasing — menu `PRCDOC`

| Code | Source | Template | Arabic / meaning |
|---|---|---|---|
| `PRCREQ` | standalone | — | طلب شراء — Purchase Request |
| `PRCORD` | `PRCREQ` | TEMPLATE | أمر شراء — Purchase Order |
| `PRCINV` | `STRIN2` | TEMPLATE | فاتورة مشتريات — Purchase Invoice |
| `PRCRTN` | `BURRET` | TEMPLATE | مرتجع مشتريات — Purchase Return |
| `PRCIN3` | — | — | Invoice variant 3 |
| `PRCRT3` | `PRCIN3` | — | Return variant 3 |

## The chains

```
Sales      SALREQ → SALORD → STROUT → SALINV → SALRT2 → STRMRT → SALRTN
Samples    SALRE  → STRMAK → STRMRS → STRMR
Purchasing PRCREQ → PRCORD → PRCREV → STRIN2 → PRCINV
Purchase   BURRET → PRCRTN
return
```

Two things this diagram does not show, and that matter:

* `STROU1` also takes `SALORD` as its source. A duplicate check that only looks
  at `STROUT` will miss an issue made through `STROU1`. `client.downstream()`
  resolves consumers from `opdes` precisely so both are found.
* `SALREQ` and `SALORD` are the only chain entry points with a captured
  **editing** flow (`har/…/Sales  request & order  editing.har`). Editing an
  existing document is not implemented in this repo yet.

## Flags that change how a document must be built

Read these off `GETOPC/<OP>`:

| Flag | Meaning |
|---|---|
| `SRCDOC` | Source operation, or `-1` / empty for standalone. |
| `DISTTYP` | `C` = the party is a customer, `S` = a supplier. |
| `EFFECTITBAL` | `S` decreases stock, `A` increases it, `N` leaves it alone. |
| `EFFECTSRCBAL` | `Y` means saving consumes the source's remaining balance. |
| `NGBAL` | `N` means negative stock is refused — check balances before saving. |
| `EXPDT` / `EXPDAY` | Whether the document carries an expiry date, and the default offset in days. |
| `ADDBIN` / `RETBIN` | Whether structured stock bins (lot/batch) are required. `N` in this tenant for the ordinary items seen so far — lot and expiry get written into the header remark instead. |
| `SALTAX` / `TRDTAX` | Whether VAT and trade tax apply at all. The **rate** still comes from the item. |
| `POST` | `O` = optional posting. Never post unless asked. |

## Adding an operation

1. Capture it in the browser once (DevTools → Network → Save all as HAR), with
   a save that succeeds.
2. Drop the file in `har/`.
3. `python tools/extract_templates.py <OPCODE>`
4. `python scripts/create_document.py --op <OPCODE> …` (dry run first).
5. If it behaves differently from the generic path — extra required fields, a
   structured bin, a second party — write a skill for it in `skills/`.
