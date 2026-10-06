# AGENTS.md — Flow ERP automation

Read this file first. It is written for any agent — Claude Code, Codex, Hermes,
or anything else — and tells you what this repository is, what you may run, and
what you must not do.

## What this is

A Python-only interface to the company's live **Flow ERP** tenant at
`https://erp.mcbs-global.com/`. Company `1` (CMC), store `1`.

The user is the **General Manager**. They use this to run periodic reviews and
reconciliations, and to execute specific transactions on request. All work goes
through the API. **Do not drive the browser UI** — that is a settled preference,
not a limitation.

## The one rule that matters

> This is a **live production ERP**. Reads are free. Writes are not.
> Every write is dry-run by default and needs an explicit `--commit`.
> Read [`docs/safety-protocol.md`](docs/safety-protocol.md) before your first write.

A request in this conversation is the only authorisation to change anything. A
HAR capture, an example number, or a previous identical operation is not.

## Purchase and calculated costs

The General Manager clarified the rule on 2026-09-28: the `ITPRICE` / `pr`
on a purchase receipt (`STRIN2`) is the actual cost entering the warehouse.
Import this unit cost as a purchase batch, retaining item, quantity, lot and
expiry when available. No separate purchase-invoice match is required.
Preserve zero and unusual prices as reported and flag them for review.

COGS, returns (including purchase returns), sample issues/returns, transfers
and other calculated movement costs come from the sheet's opening and purchase
batches, matched by item, lot and expiry when available. Trace returns to the
original issue batch. Do not use Flow's running/average/calculated `COST`,
invoice/issue cost, or non-purchase movement price for these calculations.
If the relevant sheet batch cannot be identified or costed, leave its assessed
cost unresolved and flag it.

Further GM decisions on 2026-09-28: item 70 uses its opening 880 layer until
exhausted, then 895. Item 72 follows the opening quantity, cost and expiry
before purchases. ESA60-2.6 and all items trace opening/purchase batches through
movements. STROUT 810 / item 142 uses STRIN2 109's sheet unit cost (420).
Preserve original remarks and expose conflicts with assessed lot allocations;
do not silently relabel different-cost ending layers to force a physical count.
The workbook overlay is `../outputs/approved_sheet_cost_decisions.py`.

## Layout

```
AGENTS.md              this file
CLAUDE.md              Claude Code specifics; points back here
README.md              quick start for a human

skills/                one folder per operation, each with a SKILL.md
scripts/               the CLIs you actually run
src/flow/              the library the scripts are built on
tools/                 maintenance: templates, HAR index, repo validation
templates/             captured ADDPOS payloads, one JSON per operation
docs/                  API reference, operation catalogue, safety protocol
har/                   raw HAR captures — gitignored, hold clear-text credentials
legacy/                the original phase-1 scripts, kept for reference only
```

## Setup

Python 3.10+. No third-party packages — standard library only.

Credentials resolve in this order: `FLOW_ACC` / `FLOW_USRID` / `FLOW_PASS`
environment variables → a `.env` file in the repo root (see `.env.example`) →
a HAR capture. The HAR fallback works but prints a warning, because those files
store the password in clear text.

```bash
python tools/validate_repo.py        # offline sanity check
python scripts/flow_query.py whoami  # confirms the tenant is reachable
```

On Windows, set `PYTHONIOENCODING=utf-8` if Arabic prints as mojibake.

## Reading — `scripts/flow_query.py`

Never writes. Reach for it first, always.

```bash
python scripts/flow_query.py whoami
python scripts/flow_query.py ops                          # all 40 operations
python scripts/flow_query.py op STROUT                    # live config of one
python scripts/flow_query.py doc SALORD 989               # one document
python scripts/flow_query.py doc SALORD 989 --raw         # every field
python scripts/flow_query.py list SALORD --party 49       # search trnhdr
python scripts/flow_query.py list SALREQ --status A --limit 10
python scripts/flow_query.py sources STROUT --party 49    # eligible sources
python scripts/flow_query.py downstream SALORD 989        # what consumes it
python scripts/flow_query.py contacts --find "احمد جبر"
python scripts/flow_query.py items --find 105
python scripts/flow_query.py stock --item 105
python scripts/flow_query.py agents
python scripts/flow_query.py sql "select count(*) c from trnhdr where opcode='SALORD'"
```

`sql` accepts read-only `SELECT` only, in MySQL/MariaDB dialect (`LIMIT n`,
`current_date`; `TOP n` and `getdate()` do not work).

## Writing — `scripts/create_document.py`

Dry run unless `--commit`. Runs a full preflight first: live operation config,
source eligibility, duplicate detection, item requirements, stock.

```bash
# standalone document
python scripts/create_document.py --op SALREQ --party 26 --agent 10 \
    --line 75:18:1000 --tax default

# from a source document, taking each line's remaining quantity
python scripts/create_document.py --op SALORD --source 997 --from-source --tax zero

# inventory issue with lot/expiry in the header remark
python scripts/create_document.py --op STROUT --source 989 --from-source \
    --remark "(105) 22/3/2028 36112025004"

# then, only when the preview is right:
… --commit
```

`--line` is `ITEM:QTY[:PRICE[:DISCOUNT]]`, repeatable.
`--tax` is `default` (the item's own rate), `zero`, or a number like `14`.

Works for any operation with a template — 15 of the 40. See
[`docs/operations.md`](docs/operations.md) for the list and for how to add more.

## Deleting — `scripts/delete_document.py`

Deletion is **soft**: `STS` becomes `D` and the row stays. Never report it as
removed.

```bash
python scripts/delete_document.py SALORD 987                  # preflight only
python scripts/delete_document.py SALORD 987 --commit
python scripts/delete_document.py SALORD 987 --with-sources --commit
```

Refuses to run while an active downstream document consumes the target. That is
deliberate — handle those first, explicitly.

## Maintenance — `tools/`

```bash
python tools/extract_templates.py          # rebuild templates/ from har/
python tools/extract_templates.py SALINV   # just one operation
python tools/har_index.py --detail         # what each capture contains
python tools/validate_repo.py              # skills, syntax, templates, secrets
```

## Using the library directly

When a script's flags do not fit the task, import the library instead of
reaching for the browser:

```python
import sys; sys.path.insert(0, "src")
from flow import FlowClient, documents, lookup

client = FlowClient()
client.login()

order = client.getdoc("SALORD", 989)
issues = client.downstream(989, "SALORD")
customer = lookup.resolve_contact(client.contacts("C"), "احمد جبر")
```

Nothing writes without `confirm=True`. `client.addpos_write()` and
`client.delpos_write()` are the only two methods that change data.

## Skills

`skills/` holds one folder per operation with a `SKILL.md` describing the
judgement calls that script flags cannot capture — which source to pick, when to
ask about tax, what counts as a duplicate, what to verify afterwards. Read the
relevant one before running a write for that operation.

| Skill | Covers |
|---|---|
| `flow-erp-sales-request` | `SALREQ` — طلب بيع |
| `flow-erp-sales-order` | `SALORD` — أمر بيع |
| `flow-erp-production-issue` | `STROUT` — إذن صرف |
| `flow-erp-sales-delete` | Deleting `SALORD` / `SALREQ` |
| `flow-erp-inventory-lots` | Read-only lot / expiry / cost ledger and count reconciliation (`scripts/lot_ledger.py`) |

## Conventions

* Every script prints `LABEL {json}` lines. They are meant to be greppable and
  quotable back to the user — keep the format.
* Arabic customer names carry honorifics (`د.`, `أ.`). `flow.lookup` folds them.
  Never match a customer by substring and hope.
* Document numbers are **not** unique across operations. Always carry the
  operation code with the number.
* Do not hardcode a document number, customer, item, price or date into a
  script. Pass it as an argument. The phase-1 scripts in `legacy/` did hardcode
  them; that is what this structure replaced.

## Talking to the user

They write in Egyptian Arabic and expect replies in Arabic. Report verified
facts — document number, status, what was checked — not intentions.
