# legacy/

The phase-1 scripts, written against the tenant with Codex before this structure
existed. Kept because they are the record of what was actually executed, and
because their HAR-inspection code documents how the API was reverse-engineered.

**Do not run them.** They hardcode document numbers (997, 987, 989, 988),
customer codes, quantities and prices, they read HAR files from absolute
`C:\Users\hp\Downloads\` paths, and `validate_flow_skills.py` points at a Codex
working directory that no longer exists.

Everything they did is now covered by:

| Legacy script | Replaced by |
|---|---|
| `flow_sales_request.py` | `scripts/create_document.py --op SALREQ` |
| `flow_sales_order.py` | `scripts/create_document.py --op SALORD --source N` |
| `flow_production_issue_*.py` | `scripts/create_document.py --op STROUT --source N` + `scripts/flow_query.py` |
| `flow_delete_sales_docs.py` | `scripts/delete_document.py` |
| `inspect_flow_*.py` | `tools/har_index.py`, `tools/extract_templates.py` |
| `validate_flow_skills.py` | `tools/validate_repo.py` |

What they executed, for the record: Sales Request 997 and Sales Order 987 were
created and later soft-deleted (`STS=D`). Production Issues 975 (from order 989)
and 976 (from order 988) were created and posted, and still exist — never
recreate them.
