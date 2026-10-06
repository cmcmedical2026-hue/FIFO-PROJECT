# Approved costs and lot investigation — 2026-09-28

The GM supplied follow-up decisions for the 18 unresolved lines. The existing
Google Sheet was updated in place through the connected Google Sheets API.
No Flow transaction, source CSV, source quantity or document remark was edited.

16 original unresolved lines are now costed. The two remaining lines are item
75 in STROUT 921 (July, row 82) and STROUT 949 (August, row 71). There is a
10-unit old/new lot discrepancy. Assuming all other records are correct, 921
must be 8 old / 122 new instead of the remark's 18 old / 112 new. This is a
conditional inference awaiting resolution; it was not written as a fact.

Follow-up on 2026-10-04: the approved June CSV, August zero balance, source
remarks and batch sequence resolved these two lines. The current decision and
verification are in `../item75-lot-resolution-2026-10-04/audit.json`. This
28-September audit remains the historical pre-resolution record.

Item 75's only explicitly documented 0469-E3 purchase in Jan-Aug is receipt
114: 10 units on 20 April at 850. Receipt 104 has no lot in its remark. All
stock was exhausted by May end. Purchases 124, 126, 128 and 133 explicitly
name 0505-E2. The live purchase extract confirms all six receipts.
Returns 137 and 146 trace to 2025 issues 538 and 644, and are assessed against
the same-lot/expiry opening sheet batch at 560. No invoice or Flow COST input
was used. Issue 948's unit cost is 560 under every feasible July lot split;
source-layer allocation retains a review flag.

Item 144's June issues 872 and 220 each use 335 from opening lot 20241213031,
expiry 12 December 2027. The approved June count reconciles 7 - 1 - 1 - 2 = 3
old units. Their original conflicting remarks remain intact. August records
leave 3 old and 69 new units, whereas the count says 0 old and 72 new. This
lot discrepancy is recorded; old-cost layers are not silently relabelled.

The GM's item 72 rule yields 70 at 760 and 10 at 790 in issue 822: value
61,100, unit cost 763.75. Subsequent issue 826 takes the remaining 5 at 790.
Item 70's 880 layer has not been exhausted: 685 units remain at August end;
the higher-cost 895 layers retain 2,001 units.

`../approved_sheet_cost_decisions.py` applies these decisions by stable movement
identity and quantity. The main rebuild calls this overlay before producing
requests. `audit.json` and `native_verification.json` record the result.
`live_before.json`, `prewrite.json`, `live_after.json` and the `before_*` files
retain the evidence and prior state. Never replay stored requests against a
changed sheet; refresh the affected live cells and source inputs first.

Verification covered 20 changed cost formulas and amounts, all 80 monthly
summary values/document counts, source preservation and unchanged formatting,
validation and notes. Browser capture is prohibited for this project; visual
fit was not verified by browser capture. This was a content-only edit.
