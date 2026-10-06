# CLAUDE.md

**Read [`AGENTS.md`](AGENTS.md) first** — it holds the layout, the commands, and
the rules. This file only covers what is specific to Claude Code.

## Before you touch anything

This repository drives a **live production ERP** for the company the user runs.
Reads are free; every write is dry-run by default and needs `--commit`.
[`docs/safety-protocol.md`](docs/safety-protocol.md) is required reading before
your first write.

## Working style here

* **Answer from the live system, not from memory.** Document numbers, balances
  and statuses in this repo's docs and in past conversations are snapshots.
  Run `scripts/flow_query.py` and quote what comes back.
* **Dry run, show the preview, then ask.** For anything that saves or deletes,
  run without `--commit`, show the user the `PREVIEW` line, and wait for their
  go-ahead. Do not chain preview and commit in one turn unless they asked for
  exactly that.
* **One save, then verify.** If a save response is not `CMDDNE,<number>`, stop
  and investigate read-only. Never retry a write to "make sure".
* **Prefer the existing CLIs.** `flow_query.py`, `create_document.py` and
  `delete_document.py` already carry the preflight logic. Writing a fresh
  one-off script skips the safety checks that are the point of this repo.
* **Never drive the browser for ERP work.** The user chose the API path
  deliberately. The browser tools are for other things.

## Skills

`skills/*/SKILL.md` are the per-operation playbooks. They are plain files here,
not installed skills — read the relevant one directly before a write for that
operation. Each one now ends with the exact commands to run.

When you build out a new operation, add a skill alongside the script: the script
carries the mechanics, the skill carries the judgement (which source to pick,
when to ask about tax, what counts as a duplicate, what to verify).

## Adding an operation

1. The user captures the operation once in the browser and drops the `.har` in `har/`.
2. `python tools/extract_templates.py <OPCODE>`
3. Dry-run `scripts/create_document.py --op <OPCODE> …` and read the preflight output.
4. If it needs anything the generic path does not do, extend `src/flow/` rather
   than writing a standalone script.
5. Add `skills/flow-erp-<name>/SKILL.md`.
6. `python tools/validate_repo.py`

## Language

The user writes Egyptian Arabic; reply in Arabic. Keep the `LABEL {json}` output
lines from the scripts verbatim when quoting results — they are the evidence.

## Things that will trip you up

* Windows console mangles Arabic unless `PYTHONIOENCODING=utf-8` is set. The
  scripts reconfigure their own streams; ad-hoc `python -c` calls do not.
* `getrec` is MySQL/MariaDB dialect. `TOP n`, `getdate()` and `sysdate` all
  silently return zero rows rather than erroring.
* The login response's `fsysdt` is `false`, not a date. Use
  `documents.tenant_today(client)`, which asks the database.
* `STROU1` also consumes `SALORD`. A duplicate check that only looks for
  `STROUT` is wrong — use `client.downstream()`, which resolves consumers from
  `opdes`.
* HAR files hold the tenant password in clear text. They are gitignored. Do not
  print their contents, and do not copy credentials into any file.
