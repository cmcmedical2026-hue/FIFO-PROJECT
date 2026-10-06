# har/

Raw HAR captures of the Flow ERP browser session, used for two things only:

1. the **request schema** of each operation — the captured `ADDPOS` payload is
   the only real description of the 29–135 fields a document line carries;
2. a **credential fallback**, when no environment variable is configured.

## These files contain the tenant password in clear text

They are gitignored (`*.har`, `har/*.zip`). Do not commit one, do not paste
their contents anywhere, and prefer `.env` over the credential fallback.

## Using them

```bash
python tools/har_index.py --detail        # what each capture covers
python tools/extract_templates.py         # rebuild templates/ from them
```

Once `templates/` is built, ordinary work needs no HAR at all.

## Adding a capture

In the browser: DevTools → Network → perform the operation through to a
successful save → *Save all as HAR with content* → drop the file here → run
`python tools/extract_templates.py <OPCODE>`.

A capture is only useful if the save **succeeded** — a failed attempt has no
`CMDDNE` response and its payload may be malformed.
