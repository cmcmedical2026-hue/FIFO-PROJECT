"""Building, saving and verifying Flow ERP documents.

A saved document carries ~30 header fields and ~90 line fields. Inventing them
is not an option, so every draft starts from a **captured template** -- the real
``ADDPOS`` payload the browser sent for that operation -- and then replaces the
business values with live ones. See ``tools/extract_templates.py``.
"""

from __future__ import annotations

import copy
import json
import re
from datetime import date, datetime, timedelta

from . import config
from .client import FlowClient, FlowError, rows

# Header fields that carry identity/contact data and must be re-derived from the
# live customer or supplier rather than inherited from a template.
IDENTITY_FIELDS = ("DISTNO", "SDISTNO", "DISTNA", "SDISTNA", "FORDES", "DISTADD",
                   "TEL1", "TEL2", "EMAIL", "RGNO")

TAX_FIELDS = ("SALTAX", "ITSALTAX", "TRDTAX", "ITTRDTAX", "TBLTAX", "TBLTAXRTO",
              "TBLTAXVAL", "TotalTaxes", "GRNSALTAX", "GRNTRDTAX", "INSSALTAX",
              "INSTRDTAX", "SHPSALTAX", "SHPTRDRAX")

AMOUNT_FIELDS = ("ITMTOT", "ITMTOTVAL", "ITMNET", "NetPrice", "UNITPRC")


# --- templates ---------------------------------------------------------------
def template_path(op: str):
    return config.TEMPLATES_DIR / (op.upper() + ".json")


def load_template(op: str) -> dict:
    """Return the captured ADDPOS payload for ``op``.

    Prefers ``templates/<OP>.json`` (fast, no HAR needed). Falls back to parsing
    the HAR archive, which is slow but always authoritative.
    """
    path = template_path(op)
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))["payload"]
    from .har import HarLibrary

    _, payload = HarLibrary().find_operation(op)
    return payload


def available_templates() -> list:
    if not config.TEMPLATES_DIR.is_dir():
        return []
    return sorted(p.stem for p in config.TEMPLATES_DIR.glob("*.json") if p.stem.isupper())


# --- dates -------------------------------------------------------------------
def tenant_today(client: FlowClient | None = None) -> date:
    """Today according to the tenant's database, not the local machine.

    The machine running a script may sit in a different timezone than the ERP,
    which would date a document a day off. ``select current_date`` asks the
    server. Falls back to the local date only if that query fails.
    """
    if client is not None:
        try:
            found = client.getrec("select current_date as today")
            if found:
                parsed = parse_date(str(list(found[0].values())[0]))
                if parsed:
                    return parsed
        except Exception:  # a date check must never block a read-only run
            pass
    return datetime.now().date()


def parse_date(raw: str):
    raw = (raw or "").strip()
    if not raw:
        return None
    match = re.match(r"^(\d{4})-(\d{2})-(\d{2})", raw)
    if match:
        return date(*(int(g) for g in match.groups()))
    match = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})", raw)
    if match:
        day, month, year = (int(g) for g in match.groups())
        return date(year, month, day)
    return None


# --- drafting ----------------------------------------------------------------
def new_draft(client: FlowClient, op: str, *, docdt: date | None = None,
              srcdocno=None, template: dict | None = None) -> dict:
    """A blank, template-shaped payload for a new ``op`` document."""
    payload = copy.deepcopy(template if template is not None else load_template(op))
    payload["OP"] = op.upper()
    payload["DOCNO"] = 0
    payload["CONO"] = str(client.cono)
    payload["STRNO"] = str(client.strno)
    payload["DOCDT"] = (docdt or tenant_today(client)).isoformat()
    payload["DTL"] = []
    for field in IDENTITY_FIELDS:
        if field in payload:
            payload[field] = 0 if field in ("SDISTNO", "DLVLOC") else ""
    for field in ("RMK", "REFDOCNO"):
        if field in payload:
            payload[field] = ""
    if "TOTDISC" in payload:
        payload["TOTDISC"] = 0
    if "TOTSHPVAL" in payload:
        payload["TOTSHPVAL"] = 0
    if srcdocno is not None and "SRCDOCNO" in payload:
        payload["SRCDOCNO"] = str(srcdocno)
    return payload


def apply_contact(payload: dict, contact: dict) -> dict:
    """Fill the customer/supplier block from a live ``GETCON`` row."""
    payload["DISTNO"] = str(contact.get("CNO"))
    if "DISTNA" in payload:
        payload["DISTNA"] = contact.get("CNAME") or ""
    if "FORDES" in payload:
        payload["FORDES"] = contact.get("FORDES") or ""
    if "DISTADD" in payload:
        payload["DISTADD"] = contact.get("CADD") or ""
    if "TEL1" in payload:
        payload["TEL1"] = contact.get("TEL1") or ""
    if "EMAIL" in payload:
        payload["EMAIL"] = contact.get("EMAIL") or ""
    if "RGNO" in payload:
        payload["RGNO"] = str(contact.get("RGNO") or 0)
    return payload


def new_line(op: str, item: dict, *, qty: float, price: float, line_no: int = 1,
             vat_rate=None, trade_rate=0, table_rate=0, discount=0,
             template: dict | None = None) -> dict:
    """One detail line, shaped like the captured template for ``op``."""
    source = template if template is not None else load_template(op)
    details = rows(source.get("DTL"))
    if not details:
        raise FlowError("Template for %s has no DTL line to copy" % op)
    line = copy.deepcopy(details[0])
    line["LN"] = line_no
    line["ITNO"] = str(item.get("ITNO"))
    if "ITDES" in line:
        line["ITDES"] = item.get("ITDES") or ""
    if "ITCODE" in line:
        line["ITCODE"] = item.get("ITCODE") or str(item.get("ITNO"))
    line["QTY"] = qty
    if "ITQTY" in line:
        line["ITQTY"] = qty
    line["ITPRICE"] = price
    for flag in ("HASPCK", "USEUNT", "USEWEG", "USESN"):
        if flag in line:
            line[flag] = item.get(flag) or ("" if flag == "HASPCK" else "N")
    if "USECSZ" in line:
        line["USECSZ"] = item.get("USECZ") or "N"
    if "DISC1" in line:
        line["DISC1"] = discount
    rate = float(item.get("SALTAX") or 0) if vat_rate is None else float(vat_rate)
    set_taxes(line, vat_rate=rate, trade_rate=trade_rate, table_rate=table_rate)
    recompute_line(line)
    return line


def set_taxes(line: dict, *, vat_rate: float, trade_rate: float = 0, table_rate: float = 0) -> dict:
    """Set the tax **rates** on a line and clear any inherited tax amounts.

    A line copied from a source document keeps its computed tax values even
    after its rate changes; leaving them is how a "zero tax" order ends up with
    tax on it. Amounts are recomputed by ``recompute_line``.
    """
    if "SALTAX" in line:
        line["SALTAX"] = vat_rate
    if "TRDTAX" in line:
        line["TRDTAX"] = trade_rate
    if "TBLTAXRTO" in line:
        line["TBLTAXRTO"] = table_rate
    for field in TAX_FIELDS:
        if field in line and field not in ("SALTAX", "TRDTAX", "TBLTAXRTO"):
            line[field] = 0
    return line


def recompute_line(line: dict) -> dict:
    """Recompute the line totals that depend on quantity, price and discount."""
    qty = float(line.get("QTY") or 0)
    price = float(line.get("ITPRICE") or 0)
    discount = float(line.get("DISC1") or 0)
    gross = qty * price
    net = gross - discount
    for field in ("ITMTOT", "ITMTOTVAL", "ITMNET"):
        if field in line:
            line[field] = net
    if "NetPrice" in line:
        line["NetPrice"] = price
    if "UNITPRC" in line:
        line["UNITPRC"] = price
    return line


def add_line(payload: dict, line: dict) -> dict:
    line = copy.deepcopy(line)
    line["LN"] = len(payload.get("DTL") or []) + 1
    payload.setdefault("DTL", []).append(line)
    return payload


def expiry_from_operation(operation: dict, start: date, default_days: int = 30) -> str:
    days = operation.get("EXPDAY")
    try:
        days = int(days)
    except (TypeError, ValueError):
        days = default_days
    return (start + timedelta(days=days)).isoformat()


# --- review, save, verify ----------------------------------------------------
def summarise(payload: dict) -> dict:
    """The few fields a human actually reviews before authorising a save."""
    lines = rows(payload.get("DTL"))
    return {
        "op": payload.get("OP"),
        "company": payload.get("CONO"),
        "store": payload.get("STRNO"),
        "date": payload.get("DOCDT"),
        "party": payload.get("DISTNO"),
        "party_name": payload.get("DISTNA"),
        "agent": payload.get("EMPNO"),
        "source": payload.get("SRCDOCNO"),
        "remark": payload.get("RMK"),
        "lines": [{"ln": line.get("LN"), "item": line.get("ITNO"), "desc": line.get("ITDES"),
                   "qty": line.get("QTY"), "price": line.get("ITPRICE"),
                   "vat_rate": line.get("SALTAX"), "trade_rate": line.get("TRDTAX"),
                   "table_rate": line.get("TBLTAXRTO"), "discount": line.get("DISC1"),
                   "total": line.get("ITMTOT")} for line in lines],
        "grand_total": sum(float(line.get("ITMTOT") or 0) for line in lines),
    }


def preview(payload: dict) -> dict:
    review = summarise(payload)
    print("PREVIEW " + json.dumps(review, ensure_ascii=False), flush=True)
    return review


def save_and_verify(client: FlowClient, payload: dict, *, confirm: bool = False,
                    expect: dict | None = None) -> dict:
    """Save once, then retrieve the document and check it independently.

    ``expect`` is a dict of ``GETDOC`` header fields to compare, plus an optional
    ``lines`` list of per-line ``{item, qty, price}`` checks.
    """
    review = preview(payload)
    if not confirm:
        print("DRY_RUN nothing was sent; re-run with --commit to save", flush=True)
        return {"saved": False, "review": review}

    docno = client.addpos_write(payload, confirm=True)
    print("SAVE_RESPONSE CMDDNE,%d" % docno, flush=True)

    saved = client.getdoc(payload["OP"], docno)
    if saved is None:
        raise FlowError("Document %s/%d was saved but cannot be retrieved; verify manually, do not resend"
                        % (payload["OP"], docno))
    problems = verify(saved, expect or {}, payload)
    result = {
        "saved": True,
        "docno": docno,
        "op": saved.get("OP"),
        "date": saved.get("DOCDT"),
        "party": saved.get("DISTNO"),
        "source": saved.get("SRCDOCNO"),
        "total": saved.get("DOCTOT"),
        "net": saved.get("DOCNET"),
        "vat": saved.get("TOTSALTAX"),
        "status": saved.get("STS"),
        "post": saved.get("POST"),
        "lines": [{"item": line.get("ITNO"), "qty": line.get("QTY"), "price": line.get("ITPRICE"),
                   "vat_rate": line.get("SALTAX"), "total": line.get("ITMTOT")}
                  for line in rows(saved.get("DTL"))],
    }
    print("VERIFIED " + json.dumps(result, ensure_ascii=False), flush=True)
    if problems:
        raise FlowError("Document %d saved but differs from the reviewed values: %s"
                        % (docno, "; ".join(problems)))
    return result


def verify(saved: dict, expect: dict, sent: dict | None = None) -> list:
    """Compare a retrieved document against expectations. Returns problems."""
    problems = []
    for field, wanted in expect.items():
        if field == "lines":
            continue
        got = saved.get(field)
        if str(got).strip() != str(wanted).strip():
            problems.append("%s expected %r, got %r" % (field, wanted, got))
    wanted_lines = expect.get("lines")
    if wanted_lines is not None:
        got_lines = rows(saved.get("DTL"))
        if len(got_lines) != len(wanted_lines):
            problems.append("line count expected %d, got %d" % (len(wanted_lines), len(got_lines)))
        else:
            for index, (wanted, got) in enumerate(zip(wanted_lines, got_lines), start=1):
                for key, api_field in (("item", "ITNO"), ("qty", "QTY"), ("price", "ITPRICE"),
                                       ("vat_rate", "SALTAX")):
                    if key not in wanted:
                        continue
                    left, right = wanted[key], got.get(api_field)
                    same = (str(left) == str(right))
                    if not same:
                        try:
                            same = abs(float(left) - float(right or 0)) < 0.005
                        except (TypeError, ValueError):
                            same = False
                    if not same:
                        problems.append("line %d %s expected %r, got %r" % (index, key, left, right))
    return problems
