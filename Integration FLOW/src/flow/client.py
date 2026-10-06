"""HTTP client for the Flow ERP API.

Three surfaces, all reached through one class:

* https://login.mcbs-global.com/api/chkusr/login -- returns the session apiKey.
* https://api.mcbs-global.com/api/...            -- the REST surface.
* https://erp.mcbs-global.com/                   -- the legacy command surface
  (cmdtxt=EXECMD), which needs the key in an XAPIKEY header.

Every method that changes data is named ``*_write`` and takes ``confirm=True``,
so a write can never happen by accident while reading.
"""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from . import config
from .credentials import Credentials, redact, resolve

SAVE_OK = re.compile(r"^CMDDNE,(\d+)$")


class FlowError(RuntimeError):
    """Any failure that must stop the caller rather than be retried blindly."""


class UncertainWrite(FlowError):
    """A write whose outcome is unknown. Never retry; check read-only first."""


def rows(value: Any) -> list:
    """Normalise the API's list/dict/None result shapes into a list."""
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    return []


class FlowClient:
    def __init__(self, credentials: Credentials | None = None, *, verbose: bool = True,
                 cono: str | None = None, strno: str | None = None):
        self.credentials = credentials or resolve(verbose=verbose)
        self.verbose = verbose
        self.cono = str(cono or config.DEFAULT_CONO)
        self.strno = str(strno or config.DEFAULT_STRNO)
        self.apikey: str | None = None
        self.session: dict = {}

    # -- transport -----------------------------------------------------------
    def _request(self, url: str, *, method: str = "GET", body: Any = None,
                 headers: dict | None = None, timeout: int | None = None) -> tuple[int, Any]:
        host = url.split("/")[2]
        if host not in config.ALLOWED_HOSTS:
            raise FlowError("Refusing to contact unexpected host: " + host)
        merged = {"Accept": "application/json, text/plain, */*", "Origin": config.ORIGIN}
        merged.update(headers or {})
        data = None
        if body is not None:
            if isinstance(body, str):
                merged.setdefault("Content-Type", "text/plain; charset=UTF-8")
                data = body.encode("utf-8")
            else:
                merged.setdefault("Content-Type", "application/json; charset=UTF-8")
                data = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        request = Request(url, data=data, headers=merged, method=method)
        path = url.split("?")[0].replace("https://" + host, "")
        try:
            with urlopen(request, timeout=timeout or config.HTTP_TIMEOUT) as response:
                raw = response.read().decode("utf-8-sig")
                status = response.status
        except HTTPError as exc:
            raise FlowError("HTTP %s at %s%s" % (exc.code, host, path)) from None
        except URLError as exc:
            raise FlowError("Network error at %s%s: %s" % (host, path, type(exc.reason).__name__)) from None
        try:
            return status, json.loads(raw)
        except ValueError:
            return status, raw

    # -- session -------------------------------------------------------------
    def login(self) -> str:
        """Authenticate through the tenant's working login surface.

        The dedicated login host currently rejects otherwise valid requests
        before reading their JSON bodies.  Prefer the ERP compatibility
        endpoint so every new CLI process does not repeat that known-bad
        request; retain the dedicated endpoint as a fallback in case the
        compatibility surface is temporarily unavailable.
        """
        try:
            result = self._legacy_login()
        except FlowError:
            result = self._api_login()
        self.apikey = result["apiKey"]
        self.session = {k: result.get(k) for k in
                        ("acc", "usrid", "usrna", "empno", "dcono", "auth", "applvl", "fsysdt", "lng")}
        if self.verbose:
            print("LOGIN_OK " + json.dumps(self.session, ensure_ascii=False), flush=True)
        return self.apikey

    def _api_login(self) -> dict:
        """Authenticate through the dedicated JSON login API."""
        status, result = self._request(
            "https://%s/api/chkusr/login" % config.LOGIN_HOST,
            method="POST", body=self.credentials.login_body())
        if status != 200 or not isinstance(result, dict) or not result.get("apiKey"):
            raise FlowError("Login did not return an API key")
        if result.get("errMsg"):
            raise FlowError("Login reported an error: " + redact(str(result["errMsg"]), self.credentials))
        return result

    def _legacy_login(self) -> dict:
        """Use Flow's original login surface.

        The tenant's web client retains this protocol as its own compatibility
        path.  Parse only the authentication/session fields we need: the raw
        response also contains unrelated server configuration and must never be
        logged or retained.
        """
        body = "\f".join((self.credentials.acc, self.credentials.usrid,
                           self.credentials.password, config.DEFAULT_LNG, "")) + "\f"
        status, response = self._request(
            "https://%s/?OP=CHKUSR" % config.ERP_HOST,
            method="POST", body=body, headers={"Accept": "text/plain, */*"})
        if status != 200 or not isinstance(response, str) or not response.startswith("LOGIN"):
            raise FlowError("Legacy login was rejected")

        fields = {}
        for part in response[len("LOGIN"):].split(";"):
            key, separator, value = part.partition("=")
            if separator:
                fields[key.upper()] = value
        if fields.get("LOGINERR", "0") != "0" or not fields.get("APIKEY"):
            raise FlowError("Legacy login was rejected")
        result = {
            "apiKey": fields["APIKEY"],
            "errMsg": "",
            "acc": self.credentials.acc,
            "usrid": fields.get("USRID", self.credentials.usrid),
            "usrna": fields.get("USRNA"),
            "empno": fields.get("EMPNO"),
            "dcono": fields.get("DCONO"),
            "auth": fields.get("AUTH"),
            "applvl": fields.get("APPLVL"),
            "fsysdt": fields.get("FSYSDT"),
            "lng": config.DEFAULT_LNG,
        }
        return result

    def _key(self) -> str:
        if not self.apikey:
            self.login()
        return self.apikey  # type: ignore[return-value]

    # -- REST reads ----------------------------------------------------------
    def api_get(self, path: str) -> Any:
        return self._request("https://%s%s" % (config.API_HOST, path),
                             headers={"apikey": self._key()})[1]

    def srvcmd(self, endpoint: str, cmdtxt: str, cmdpar: str = "") -> Any:
        """POST a command through the api host (getrec, GETFIL, ...)."""
        body = self.credentials.command_wrapper(self._key())
        body.update({"cmdtxt": cmdtxt, "cmdpar": cmdpar})
        return self._request("https://%s/api/srvcmd/%s" % (config.API_HOST, endpoint),
                             method="POST", body=body, headers={"apikey": self._key()})[1]

    def getrec(self, sql: str) -> list:
        """Run a read-only SQL query. Refuses anything that is not a SELECT."""
        if not sql.lstrip().lower().startswith("select"):
            raise FlowError("getrec accepts SELECT statements only")
        result = self.srvcmd("getrec", "GETREC", sql)
        if isinstance(result, str) and result.startswith("CMDERR"):
            raise FlowError("Query rejected by the server: " + result[:120])
        return rows(result)

    def legacy(self, cmdtxt: str, cmdpar: str) -> tuple[int, Any]:
        """POST a legacy command to the ERP root (LDSRCHDRNO, EXECMD, ...)."""
        body = self.credentials.command_wrapper(self._key())
        body.update({"cmdtxt": cmdtxt, "cmdpar": cmdpar})
        return self._request("https://%s/" % config.ERP_HOST, method="POST", body=body,
                             headers={"XAPIKEY": self._key(), "Accept": "text/plain, */*"})

    # -- domain reads --------------------------------------------------------
    def operation(self, op: str) -> dict:
        """Live configuration of one operation (SRCDOC, tax flags, bins...)."""
        result = self.api_get("/api/SRVCMD/GETOPC/" + op.upper())
        if not isinstance(result, dict) or str(result.get("OP", "")).upper() != op.upper():
            raise FlowError("Operation %s could not be read" % op)
        return result

    def company(self, cono: str | None = None) -> dict:
        return self.api_get("/api/SRVCMD/GETCOM/" + str(cono or self.cono))

    def contacts(self, kind: str = "C") -> list:
        """C = customers, S = suppliers."""
        return rows(self.api_get("/api/CONCMD/GETCON/" + kind.upper()))

    def items(self) -> list:
        return rows(self.api_get("/api/POSCMD/GETITM/-1"))

    def balances(self, cono: str | None = None, strno: str | None = None) -> list:
        return rows(self.api_get("/api/POSCMD/GETBAL/%s/%s" % (cono or self.cono, strno or self.strno)))

    def agents(self, job_id: int = 100) -> list:
        return self.getrec(
            "select empno,empnm from empmas where sts='a' and jobid=%d order by empnm" % int(job_id))

    def getdoc(self, op: str, docno, cono: str | None = None, strno: str | None = None):
        result = self.api_get("/api/POSCMD/GETDOC/%s/%s/%s/%s" % (
            op.upper(), cono or self.cono, strno or self.strno, docno))
        return result if isinstance(result, dict) and result.get("DOCNO") is not None else None

    def headers(self, op: str, *, docno=None, srcdocno=None, distno=None,
                status: str | None = None, limit: int = 50) -> list:
        """Query trnhdr for documents of one operation. Read-only."""
        where = ["cono=%d" % int(self.cono), "strno='%s'" % self.strno, "opcode='%s'" % op.upper()]
        if docno is not None:
            where.append("docno=%d" % int(docno))
        if srcdocno is not None:
            where.append("srcdocno=%d" % int(srcdocno))
        if distno is not None:
            where.append("distno=%d" % int(distno))
        if status is not None:
            where.append("sts='%s'" % status.upper())
        sql = ("select opcode,docno,cono,strno,distno,empno,sts,post,docdt,srcdocno "
               "from trnhdr where " + " and ".join(where) + " order by docno desc")
        return self.getrec(sql)[:limit]

    def source_candidates(self, op: str, distno) -> list:
        """Source document numbers still eligible to feed a new ``op`` document."""
        cmdpar = "OPCODE=%s\vCONO=%s\vSTRNO=%s\vDISTNO=%s\v" % (
            op.upper(), self.cono, self.strno, distno)
        status, response = self.legacy("LDSRCHDRNO", cmdpar)
        if status != 200:
            raise FlowError("Source lookup for %s returned HTTP %s" % (op, status))
        numbers = []
        for row in rows(response):
            if not isinstance(row, dict):
                continue
            encoded = str(row.get("DOCNO", ""))
            if "SRCDOCNO=" in encoded:
                numbers.append(encoded.split("SRCDOCNO=")[-1].split("\v")[0])
        return numbers

    def downstream(self, srcdocno: int, source_op: str) -> list:
        """Active documents that consume ``srcdocno``, found by real dependency.

        A bare srcdocno match is not enough: a different operation family can
        reuse the same number. ``opdes.srcdoc`` names the operations that really
        take ``source_op`` as their source.
        """
        consumers = self.getrec(
            "select opcode,srcdoc from opdes where lower(srcdoc)='%s'" % source_op.lower())
        codes = [str(row.get("opcode")) for row in consumers if row.get("opcode")]
        if not codes:
            return []
        quoted = ",".join("'" + code.replace("'", "''") + "'" for code in codes)
        return self.getrec(
            "select opcode,docno,cono,strno,distno,sts,post,srcdocno from trnhdr "
            "where cono=%d and strno='%s' and srcdocno=%d and opcode in (%s)" % (
                int(self.cono), self.strno, int(srcdocno), quoted))

    # -- writes --------------------------------------------------------------
    def addpos_write(self, payload: dict, *, confirm: bool = False) -> int:
        """Save one document. Returns the new number. Never call twice."""
        if not confirm:
            raise FlowError("addpos_write requires confirm=True")
        if str(payload.get("DOCNO", "")) not in ("0", ""):
            raise FlowError("A new document must carry DOCNO=0")
        status, result = self._request("https://%s/api/POSCMD/ADDPOS" % config.API_HOST,
                                       method="POST", body=payload,
                                       headers={"apikey": self._key()})
        if isinstance(result, str) and result.startswith("CMDERR"):
            raise FlowError("Server rejected the document: " + result[:200])
        match = SAVE_OK.match(result) if isinstance(result, str) else None
        if status != 200 or not match:
            raise UncertainWrite(
                "Save response was not a confirmed number (status=%s). "
                "Check read-only whether the document exists before any retry." % status)
        return int(match.group(1))

    def delpos_write(self, op: str, docno: int, *, confirm: bool = False):
        """Soft-delete one document (STS becomes D; the row is retained)."""
        if not confirm:
            raise FlowError("delpos_write requires confirm=True")
        command = "DELPOS,OPCODE=%s\fCONO=%s\fSTRNO=%s\fDOCNO=%d\f\v" % (
            op.upper(), self.cono, self.strno, int(docno))
        status, response = self.legacy("EXECMD", command)
        text = response if isinstance(response, str) else json.dumps(response, ensure_ascii=False)
        return status, redact(text, self.credentials)[:300]
