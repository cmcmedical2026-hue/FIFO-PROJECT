# Flow ERP automation

Python-only automation for the company's Flow ERP tenant at
`https://erp.mcbs-global.com/` — create, inspect, reconcile and delete documents
through the API, without the browser.

Agents: start at [`AGENTS.md`](AGENTS.md).

## Quick start

Python 3.10+, no third-party packages.

```bash
cp .env.example .env        # then fill in FLOW_ACC / FLOW_USRID / FLOW_PASS
python tools/validate_repo.py
python scripts/flow_query.py whoami
```

Without a `.env` the toolkit falls back to reading the login out of a HAR
capture in `har/`. That works, but those files store the password in clear text,
so it prints a warning.

## What you can do

```bash
# look around
python scripts/flow_query.py doc SALORD 989
python scripts/flow_query.py downstream SALORD 989
python scripts/flow_query.py contacts --find "احمد جبر"

# create — preview first, then --commit
python scripts/create_document.py --op SALREQ --party 26 --agent 10 --line 75:18:1000
python scripts/create_document.py --op SALORD --source 997 --from-source --tax zero

# delete — soft delete, STS becomes D
python scripts/delete_document.py SALORD 987 --with-sources
```

Every write is a dry run until `--commit`.

## Documentation

| File | Contents |
|---|---|
| [`AGENTS.md`](AGENTS.md) | Entry point for any agent: layout, commands, conventions |
| [`CLAUDE.md`](CLAUDE.md) | Claude Code specifics |
| [`docs/safety-protocol.md`](docs/safety-protocol.md) | Why the scripts are shaped this way. Read before writing |
| [`docs/api-reference.md`](docs/api-reference.md) | Hosts, endpoints, commands, SQL dialect |
| [`docs/operations.md`](docs/operations.md) | All 40 operations, their chains, and how to add one |
| [`skills/`](skills/) | Per-operation playbooks |

## Layout

```
scripts/     the CLIs         │  tools/       maintenance
src/flow/    the library      │  templates/   captured ADDPOS payloads
skills/      playbooks        │  har/         raw captures (gitignored)
docs/        reference        │  legacy/      phase-1 scripts, reference only
```

## Security

HAR captures contain the tenant password in clear text. They are gitignored, and
`tools/validate_repo.py` fails if a secret reaches a tracked file. Once
`tools/extract_templates.py` has run, day-to-day work does not need them.
