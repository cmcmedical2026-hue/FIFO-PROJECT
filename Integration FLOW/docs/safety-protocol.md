# Safety protocol

This repository operates on a live ERP holding the company's real sales,
stock and accounting records. A wrong document is not a bug you can revert —
it is stock issued, a balance consumed, a number a colleague will act on.

These rules are not style preferences. They are why the scripts are shaped the
way they are.

## 1. Authorisation

The user's **current request** is the only authorisation. A HAR capture, an
example in a document, a number in a previous conversation, or an earlier
identical operation is not.

If the request does not identify the exact document — which customer, which
order number, which quantities — resolve that ambiguity before doing anything
consequential. Ask. Do not pick "the newest one" and hope.

## 2. Read before you write

Every write is preceded by:

* `GETOPC/<OP>` — the **live** configuration, not what a capture said last week.
* The exact source document, retrieved by operation/company/store/number and
  matched against the user's intent (customer, date, items, quantities).
* `LDSRCHDRNO` — is the source still eligible? An empty list means it is
  already fully consumed.
* `opdes` + `trnhdr` — does an **active** document already consume this source?
  Match on the real consumer operations, not on `srcdocno` alone: different
  operation families reuse document numbers.
* Stock, when the operation decreases it and negative balances are disallowed.
* Item flags — serial, packing, units, colour/size, expiry bins. If an item
  needs structured fields the script does not fill, stop; do not fake them.

`scripts/create_document.py` does all of this before it will save.

## 3. Preview, then save exactly once

Dry run is the default everywhere. `--commit` sends **one** request.

If the save response is anything other than `CMDDNE,<number>`:

* Do **not** resend.
* Check read-only whether the document exists.
* Report the uncertainty.

A blind retry is how you end up with two identical issues against one order.

## 4. Verify independently

`CMDDNE` and HTTP 200 are not proof. After a save, retrieve the document with
`GETDOC` and check header, lines, quantities, prices, tax amounts, total,
`STS` and `POST` — separately. `save_and_verify()` raises if any of them
differs from what was reviewed.

After a delete, re-read both the `trnhdr` row and `GETDOC`, and confirm the
document is no longer an eligible source.

## 5. Never post unless asked

`POST` is a separate act with accounting consequences. Saving is not posting.
Do not issue one because the operation allows it.

## 6. Deletion is soft, and never cascades on its own

`DELPOS` sets `STS=D`. The row stays. Say so plainly — do not report a document
as "removed".

Delete in dependency order: the consuming document first, its source second,
re-checking between steps. If an active downstream document exists, stop and
explain what has to be handled first. Do not delete it as a convenience.

## 7. Credentials

Credentials belong in environment variables or `.env`. They are never written
into a script, never printed, never put in an error message, and never committed.

The HAR captures contain the tenant password in clear text. They are gitignored
for that reason, and `tools/validate_repo.py` fails the build if a secret
appears in a tracked file. Once `tools/extract_templates.py` has run, ordinary
work needs no HAR at all.

## 8. Tax is a per-document decision

The item master carries a rate; the document does not have to use it. A zero-tax
choice on one order is not a standing default for the next one, and it does not
authorise changing the item master. If the user has not said what they want for
*this* document, ask:

> هل تريد ضريبة الصنف الافتراضية أم أخلي الضرائب 0؟

When zeroing tax on a document copied from a source, clear the computed tax
**amounts** too, not only the rates — a copied line keeps its old amounts
otherwise. `documents.set_taxes()` does this.

## 9. Report what happened, not what was attempted

State the verified document number and status. If a step was skipped, say so.
If something is uncertain, say that rather than rounding it up to success.
