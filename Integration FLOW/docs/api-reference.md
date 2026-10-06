# Flow ERP API reference

Everything here was derived from authorised HAR captures of the company's own
browser sessions and confirmed against the live tenant.

## Hosts

| Host | Purpose |
|---|---|
| `login.mcbs-global.com` | `POST /api/chkusr/login` — the only place credentials go. Returns `apiKey`. |
| `api.mcbs-global.com` | The REST surface. Key travels in an `apikey` header. |
| `erp.mcbs-global.com` | The legacy command surface (root `/`). Key travels in an `XAPIKEY` header. |

`flow.config.ALLOWED_HOSTS` refuses any other destination.

## Login

```
POST https://login.mcbs-global.com/api/chkusr/login
{"ACC": "...", "USRID": "...", "PASS": "...", "LNG": "ENG", "CMDTXT": "CHKUSR", "CMDPAR": "", "SRCAPP": "FLOW"}
```

The response carries `apiKey` plus the session (`usrid`, `usrna`, `auth`,
`applvl`, `empno`). A non-empty `errMsg` means the login failed even with HTTP 200.

The dedicated login service currently rejects valid JSON requests before
reading their bodies. The client therefore uses the ERP web client's legacy
`POST /?OP=CHKUSR` compatibility endpoint first and automatically falls back to
the dedicated service if that endpoint is unavailable. The compatibility
response contains more server configuration than authentication needs; the
client retains only the API key and the documented session fields.

Note: `fsysdt` comes back as `false` in this tenant — it is **not** a usable
server date. Use `select current_date` through `getrec` instead.

## REST reads

| Endpoint | Returns |
|---|---|
| `GET /api/SRVCMD/GETOPC/<OP>` | One operation's configuration — `SRCDOC`, tax flags, `EFFECTITBAL`, `NGBAL`, `EXPDAY`, `ADDBIN`. **Always read this before building a document.** |
| `GET /api/SRVCMD/GETCOM/<cono>` | Company record (`CONO`, `CONA`). |
| `GET /api/CONCMD/GETCON/C` | All customers. `…/S` for suppliers. Key field is `CNO`. |
| `GET /api/POSCMD/GETITM/-1` | The item master. Key field is `ITNO`. |
| `GET /api/POSCMD/GETBAL/<cono>/<strno>` | Store balances. |
| `GET /api/POSCMD/GETDOC/<OP>/<cono>/<strno>/<docno>` | One saved document, header plus `DTL` lines. |
| `GET /api/SRVCMD/GETPRCLST` | Price lists. |
| `GET /api/SRVCMD/GetGroup/ITM` `…/ITC` | Item groups and categories. |

## Command surface

Both command endpoints take the same lowercase wrapper — `acc`, `usrid`,
`pass`, `lng`, `thm`, `srcapp`, `srcver`, `APIKEY` — plus `cmdtxt` and `cmdpar`.

### `POST api.mcbs-global.com/api/srvcmd/getrec` — `cmdtxt=GETREC`

`cmdpar` is a **read-only SQL SELECT**. The dialect is MySQL/MariaDB: `LIMIT n`
works, `TOP n` and `FIRST n` do not; `current_date` works, `getdate()` and
`sysdate` do not. A rejected query comes back as a `CMDERR…` string, not an
HTTP error.

Tables worth knowing:

| Table | Holds |
|---|---|
| `trnhdr` | Every document header. `opcode`, `docno`, `cono`, `strno`, `distno`, `empno`, `sts`, `post`, `docdt`, `srcdocno`. |
| `opdes` | Operation definitions. `opcode`, `srcdoc`, `mnu`. This is how you find which operations consume a given source. |
| `empmas` | Employees. Sales agents are `jobid=100`, `sts='a'`. |
| `stores` | Stores per company. |

### `POST erp.mcbs-global.com/` — legacy commands

`cmdpar` uses `\v` between fields and `\f` inside `EXECMD` payloads.

| Command | `cmdpar` | Purpose |
|---|---|---|
| `LDSRCHDRNO` | `OPCODE=<OP>\vCONO=<n>\vSTRNO=<n>\vDISTNO=<party>\v` | Source documents **still eligible** to feed a new `<OP>`. The real remaining-balance check. |
| `EXECMD` | `DELPOS,OPCODE=<OP>\fCONO=<n>\fSTRNO=<n>\fDOCNO=<n>\f\v` | Soft-delete a document. |
| `PRTDOC` / `PRTPOS` | operation/company/store/document | Render a document for printing. |

`LDSRCHDRNO` returns rows whose `DOCNO` field is an encoded string containing
`SRCDOCNO=<number>\v`; the source number has to be parsed out of it. An empty
list means the source is fully consumed — this is the authoritative duplicate
check, stronger than reading `EXEQTY` off the source line.

## Writing

```
POST https://api.mcbs-global.com/api/POSCMD/ADDPOS
<the full document payload, DOCNO = 0>
```

* Success: the body is the plain string `CMDDNE,<new document number>`.
* Rejection: `CMDERR,<reason>` with HTTP 200.
* Anything else: the outcome is **unknown**. Do not resend — check read-only
  whether the document exists.

A payload carries roughly 30 header fields and between 29 and 135 line fields
depending on the operation. They are not documented anywhere and are not worth
guessing: `templates/<OP>.json` holds the real captured payload for each of the
15 operations we have, and `flow.documents.new_draft()` builds from it.

## Deleting

Deletion is **soft**. `DELPOS` sets `sts='D'`; the row stays in `trnhdr` and
`GETDOC` still returns the document. `STS=D` is proof the delete registered — it
is not proof of physical removal and not a guarantee of recoverability.

## Encoding

Responses are UTF-8 with a BOM; decode as `utf-8-sig`. On Windows, set
`PYTHONIOENCODING=utf-8` or the Arabic data prints as mojibake. The scripts here
already reconfigure their own streams.
