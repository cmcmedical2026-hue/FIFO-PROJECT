# Purchase and sheet batch costs — 2026-09-28

The General Manager explicitly authorized Flow STRIN2 ITPRICE/pr as the actual
incoming purchase unit cost. No separate invoice match is required. All other
movement costs use the sheet's opening and purchase batches by item, lot and
expiry. Flow calculated COST and non-purchase prices are not cost inputs.

`../rebuild_sheet_costs.py` is the authoritative correction pass for the current
January–August workbook. It verifies live row identities from `live_before.json`,
imports purchase prices, preserves existing Jan/Feb cost formulas, retains
explicit purchase lot/expiry data, and reconstructs later cost formulas from
source sheet cells. Receipt metadata splits are used only when quantities are
stated in the source or already documented in project overrides.

`correction.json` records the cost inputs, batch allocations, formulas, review
flags and ending layers. `requests-*.json` contain bounded, content-only native
Google Sheets updates. `before/` and `live_before.json` preserve previous state.

For future edits, refresh live reads before running the correction; do not replay
old requests against changed row identities. The phase preparation scripts remain
data preparation inputs; run the correction pass after them before publishing
cost formulas. Unresolved batch costs remain blank; zero/unusual incoming prices
are retained as reported with review flags.

Where a lot allocation is unclear but every available documented batch has the
same price, the unit cost is unambiguous; the basis explicitly retains the lot
allocation review flag. Different-price ambiguity stays unresolved. No assertion
of a complete lot-level ending valuation is made for unresolved allocations.

Later on the same date, the GM's follow-up batch decisions were applied to
16 of the 18 unresolved movement lines. The remaining two are item 75 issues
921 and 949, pending a 10-unit lot split discrepancy. The rebuild now applies
`../approved_sheet_cost_decisions.py` before generating cost requests. See
`../approved-batch-decisions-2026-09-28/README.md` and its audit/verification
files for the current decisions, source evidence and unresolved lot findings.
