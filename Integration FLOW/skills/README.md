# Skills

One folder per Flow ERP operation. Each `SKILL.md` carries what the script flags
cannot: which source document to pick, when to stop and ask, what counts as a
duplicate, and what has to be verified after the save.

Read the relevant skill **before** running a write for that operation. The
scripts enforce the mechanical checks; the skill covers the judgement.

| Skill | Operation | Covers |
|---|---|---|
| [`flow-erp-sales-request`](flow-erp-sales-request/SKILL.md) | `SALREQ` | طلب بيع — creating a standalone sales request |
| [`flow-erp-sales-order`](flow-erp-sales-order/SKILL.md) | `SALORD` | أمر بيع — creating an order from an eligible request |
| [`flow-erp-production-issue`](flow-erp-production-issue/SKILL.md) | `STROUT` | إذن صرف — issuing stock against an order, with lot/expiry remarks |
| [`flow-erp-sales-delete`](flow-erp-sales-delete/SKILL.md) | `SALORD` / `SALREQ` | Deleting an order, a request, or a linked pair |
| [`flow-erp-inventory-lots`](flow-erp-inventory-lots/SKILL.md) | read-only | رصيد باللوط والصلاحية والتكلفة، ومطابقة الجرد |

## Not yet covered

Twelve more operations have captured templates and can be driven by
`scripts/create_document.py` today, but have no skill written for them —
`SALINV`, `SALRT2`, `SALRTN`, `SALRE`, `STRMAK`, `STRMRS`, `STRMR`, `PRCORD`,
`PRCREV`, `STRIN2`, `PRCINV`, `PRCRTN`. See [`../docs/operations.md`](../docs/operations.md).

## Writing a new one

Keep the existing shape:

1. **Frontmatter** — exactly `name` (matching the folder) and `description`
   (what it does, and what it is *not* for, so it does not fire on the wrong task).
2. **Prepare** — what to verify live before building anything.
3. **Build and save** — the decisions, the ambiguities to resolve, save once.
4. **Verify** — what to retrieve and compare afterwards.
5. **Run it** — the exact commands, with placeholders rather than real numbers.

Never put a real document number, customer code or date in a skill: it reads as
an example to copy, and the next agent will copy it. Run
`python ../tools/validate_repo.py` after editing.
