"""Resolving a human's words -- an Arabic customer name, an item code -- into
the exact tenant record, or refusing when the match is ambiguous.

Guessing here is how the wrong customer gets a document, so every resolver
returns exactly one row or raises.
"""

from __future__ import annotations

import re
import unicodedata

from .client import FlowError

_ARABIC_MARKS = re.compile(r"[ً-ٰٟـ\s]")
_LETTER_FOLD = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه"})
#: Honorifics people type before a name that are not part of the stored record.
_TITLES = ("د.", "د/", "دكتور", "الدكتور", "أ.", "ا.", "م.", "مهندس", "mr.", "dr.", "eng.")


def normalized(value) -> str:
    """Fold Arabic orthography so 'د. أحمد جبر' and 'احمد جبر' compare equal."""
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = _ARABIC_MARKS.sub("", text)
    return text.translate(_LETTER_FOLD).lower()


def strip_title(value: str) -> str:
    text = normalized(value)
    for title in _TITLES:
        folded = normalized(title)
        if folded and text.startswith(folded):
            text = text[len(folded):]
    return text


def _fields(row: dict, fields) -> list:
    return [row.get(field) for field in fields if row.get(field)]


def find_contacts(contacts: list, needle: str, fields=("CNAME", "FORDES")) -> dict:
    """Split contacts into exact / title-insensitive / substring matches."""
    target = normalized(needle)
    bare = strip_title(needle)
    exact, folded, partial = [], [], []
    for row in contacts:
        if not isinstance(row, dict):
            continue
        values = [normalized(v) for v in _fields(row, fields)]
        if any(value == target for value in values):
            exact.append(row)
        elif any(strip_title(value) == bare for value in values):
            folded.append(row)
        elif any(bare and bare in value for value in values):
            partial.append(row)
    return {"exact": exact, "folded": folded, "partial": partial}


def resolve_contact(contacts: list, needle: str) -> dict:
    """Return the single contact matching ``needle``, or raise with the options."""
    if str(needle).isdigit():
        found = [row for row in contacts if str(row.get("CNO")) == str(needle)]
        if len(found) == 1:
            return found[0]
        raise FlowError("Contact code %s matched %d records" % (needle, len(found)))
    buckets = find_contacts(contacts, needle)
    for name in ("exact", "folded", "partial"):
        found = buckets[name]
        if len(found) == 1:
            return found[0]
        if len(found) > 1:
            options = ", ".join("%s=%s" % (row.get("CNO"), row.get("CNAME")) for row in found[:10])
            raise FlowError("'%s' matched %d contacts (%s); use the code instead"
                            % (needle, len(found), options))
    raise FlowError("No contact matched '%s'" % needle)


def resolve_item(items: list, code) -> dict:
    found = [row for row in items if isinstance(row, dict) and str(row.get("ITNO")) == str(code)]
    if len(found) != 1:
        raise FlowError("Item %s matched %d records" % (code, len(found)))
    return found[0]


def resolve_agent(agents: list, needle) -> dict:
    if str(needle).isdigit():
        found = [row for row in agents if str(row.get("empno")) == str(needle)]
    else:
        target = strip_title(needle)
        found = [row for row in agents if target and target in strip_title(row.get("empnm"))]
    if len(found) != 1:
        options = ", ".join("%s=%s" % (row.get("empno"), row.get("empnm")) for row in found[:10])
        raise FlowError("Agent '%s' matched %d records (%s)" % (needle, len(found), options))
    return found[0]


def item_requirements(item: dict) -> list:
    """Flags that mean a plain item line is not enough (serial, pack, size...)."""
    required = []
    for flag, meaning in (("USESN", "serial numbers"), ("USEUNT", "alternate units"),
                          ("USEWEG", "weights"), ("USECZ", "colour/size"),
                          ("HASPCK", "packing"), ("USEEXP", "expiry batches")):
        value = item.get(flag)
        if value and str(value).upper() not in ("N", "0", "FALSE", ""):
            required.append("%s (%s=%s)" % (meaning, flag, value))
    return required


def stock_for(balances: list, item_code) -> list:
    return [row for row in balances if isinstance(row, dict)
            and str(row.get("ITNO", row.get("itno", ""))) == str(item_code)]
