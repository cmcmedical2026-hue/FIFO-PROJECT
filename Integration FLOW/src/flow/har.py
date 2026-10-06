"""Read-only access to the HAR captures.

A HAR is used for exactly two things:

* the **request schema** of an operation — the captured `ADDPOS` payload is the
  only trustworthy description of the ~90 fields a document line carries;
* a **credential fallback**, when no environment variable is configured.

Nothing here talks to the network, and nothing here is needed at run time once
`tools/extract_templates.py` has written `templates/<OP>.json`.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Iterator
from urllib.parse import urlparse

from . import config


def _decode(raw: bytes):
    return json.loads(raw.decode("utf-8-sig"))


class HarFile:
    """One capture, identified by the archive it came from plus its inner name."""

    def __init__(self, label: str, loader):
        self.label = label
        self._loader = loader
        self._entries: list | None = None

    @property
    def entries(self) -> list:
        if self._entries is None:
            self._entries = _decode(self._loader())["log"]["entries"]
        return self._entries

    def posts(self, path_suffix: str) -> Iterator[dict]:
        """Yield parsed POST bodies whose URL path ends with `path_suffix`."""
        wanted = path_suffix.lower()
        for entry in self.entries:
            request = entry["request"]
            if request["method"] != "POST":
                continue
            if not urlparse(request["url"]).path.lower().endswith(wanted):
                continue
            text = (request.get("postData") or {}).get("text") or ""
            try:
                body = json.loads(text)
            except ValueError:
                continue
            if isinstance(body, dict):
                yield body

    def addpos_payloads(self, op: str | None = None) -> list[dict]:
        found = [body for body in self.posts("/addpos")]
        if op:
            found = [body for body in found if str(body.get("OP", "")).upper() == op.upper()]
        return found

    def operations(self) -> set[str]:
        return {str(body.get("OP", "")).upper() for body in self.addpos_payloads() if body.get("OP")}

    def __repr__(self) -> str:
        return f"<HarFile {self.label}>"


class HarLibrary:
    """Every HAR reachable through `flow.config.har_sources()`."""

    def __init__(self, sources: list[Path] | None = None):
        self._sources = sources if sources is not None else config.har_sources()
        self._files: list[HarFile] | None = None

    @property
    def files(self) -> list[HarFile]:
        if self._files is not None:
            return self._files
        collected: list[HarFile] = []
        seen: set[str] = set()
        for source in self._sources:
            if source.is_dir():
                for path in sorted(source.glob("*.har")):
                    label = path.name
                    if label in seen:
                        continue
                    seen.add(label)
                    collected.append(HarFile(label, lambda p=path: p.read_bytes()))
            elif source.suffix.lower() == ".zip":
                archive = zipfile.ZipFile(source)
                for name in sorted(archive.namelist()):
                    if not name.lower().endswith(".har"):
                        continue
                    label = f"{source.name}!{name}"
                    if label in seen:
                        continue
                    seen.add(label)
                    collected.append(HarFile(label, lambda a=archive, n=name: a.read(n)))
            elif source.suffix.lower() == ".har":
                label = source.name
                if label not in seen:
                    seen.add(label)
                    collected.append(HarFile(label, lambda p=source: p.read_bytes()))
        self._files = collected
        return collected

    def iter_login_bodies(self) -> Iterator[tuple[dict, str]]:
        """Yield `(body, har_label)` for every captured login request."""
        for har in self.files:
            try:
                for body in har.posts("/chkusr/login"):
                    if body.get("PASS") or body.get("pass"):
                        yield body, har.label
            except (ValueError, KeyError, zipfile.BadZipFile):
                continue

    def find_operation(self, op: str) -> tuple[HarFile, dict]:
        """Return the HAR and the captured `ADDPOS` payload for `op`."""
        op = op.upper()
        # Cheap pass first: a capture is usually named after its operation.
        ordered = sorted(self.files, key=lambda h: 0 if op[:3].lower() in h.label.lower() else 1)
        for har in ordered:
            try:
                payloads = har.addpos_payloads(op)
            except (ValueError, KeyError, zipfile.BadZipFile):
                continue
            if payloads:
                return har, payloads[-1]
        raise LookupError(
            f"No captured ADDPOS payload for operation {op}. "
            f"Searched {len(self.files)} HAR file(s) from {[str(s) for s in self._sources]}."
        )

    def index(self) -> dict[str, list[str]]:
        """Map every operation code to the HAR labels that captured a save for it."""
        mapping: dict[str, list[str]] = {}
        for har in self.files:
            try:
                ops = har.operations()
            except (ValueError, KeyError, zipfile.BadZipFile):
                continue
            for op in ops:
                mapping.setdefault(op, []).append(har.label)
        return dict(sorted(mapping.items()))
