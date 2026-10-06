"""Credential resolution for the Flow ERP toolkit.

Resolution order, first hit wins:

1. Environment variables `FLOW_ACC`, `FLOW_USRID`, `FLOW_PASS`.
2. A `.env` file in the repository root (same keys, `KEY=value` per line).
3. A HAR capture, only when `FLOW_ALLOW_HAR_CREDENTIALS` is not set to `0`.

Credentials are never written to disk by this toolkit, never logged, and never
included in an exception message. `describe_source()` is the only thing that is
safe to print.
"""

from __future__ import annotations

import json
import os
import re

from . import config

_ENV_KEYS = {"acc": "FLOW_ACC", "usrid": "FLOW_USRID", "password": "FLOW_PASS"}
_REDACTED = "***"


class CredentialError(RuntimeError):
    """Raised when no credential source could be resolved."""


class Credentials:
    """Tenant login values plus a human-readable note about where they came from."""

    def __init__(self, acc: str, usrid: str, password: str, source: str):
        self.acc = str(acc)
        self.usrid = str(usrid)
        self._password = str(password)
        self.source = source

    @property
    def password(self) -> str:
        return self._password

    def describe_source(self) -> str:
        return f"account={self.acc} user={self.usrid} password={_REDACTED} source={self.source}"

    def login_body(self) -> dict:
        """The uppercase wrapper the login endpoint expects."""
        return {
            "ACC": self.acc,
            "USRID": self.usrid,
            "PASS": self._password,
            "LNG": config.DEFAULT_LNG,
            "CMDTXT": "CHKUSR",
            "CMDPAR": "",
            "SRCAPP": "FLOW",
        }

    def command_wrapper(self, apikey: str) -> dict:
        """The lowercase wrapper every `srvcmd`/legacy command is nested in."""
        return {
            "acc": self.acc,
            "usrid": self.usrid,
            "pass": self._password,
            "lng": config.DEFAULT_LNG,
            "thm": "",
            "srcapp": "FLOW",
            "srcver": 0,
            "APIKEY": apikey,
        }

    def __repr__(self) -> str:  # never leak the secret through a traceback
        return f"<Credentials {self.describe_source()}>"

    __str__ = __repr__


def _from_environment() -> Credentials | None:
    values = {name: os.environ.get(key) for name, key in _ENV_KEYS.items()}
    if all(values.values()):
        return Credentials(**values, source="environment")
    return None


def _from_dotenv() -> Credentials | None:
    path = config.REPO_ROOT / ".env"
    if not path.is_file():
        return None
    parsed: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        parsed[key.strip()] = value.strip().strip("'\"")
    values = {name: parsed.get(key) for name, key in _ENV_KEYS.items()}
    if all(values.values()):
        return Credentials(**values, source=".env")
    return None


def _from_har() -> Credentials | None:
    if os.environ.get("FLOW_ALLOW_HAR_CREDENTIALS", "1") == "0":
        return None
    from .har import HarLibrary  # imported lazily: HAR parsing is expensive

    for entry_body, origin in HarLibrary().iter_login_bodies():
        acc = entry_body.get("ACC") or entry_body.get("acc")
        usrid = entry_body.get("USRID") or entry_body.get("usrid")
        password = entry_body.get("PASS") or entry_body.get("pass")
        if acc and usrid and password:
            return Credentials(acc, usrid, password, source=f"har:{origin}")
    return None


def resolve(verbose: bool = True) -> Credentials:
    """Return the first available credential set, or raise `CredentialError`."""
    for loader in (_from_environment, _from_dotenv, _from_har):
        found = loader()
        if found is None:
            continue
        if verbose:
            print(f"CREDENTIALS {found.describe_source()}", flush=True)
            if found.source.startswith("har:"):
                print(
                    "CREDENTIALS_WARNING HAR files store the password in clear text. "
                    "Set FLOW_ACC / FLOW_USRID / FLOW_PASS to stop reading them from a capture.",
                    flush=True,
                )
        return found
    raise CredentialError(
        "No credentials available. Set FLOW_ACC, FLOW_USRID and FLOW_PASS "
        "(see .env.example), or make an authorised HAR capture reachable."
    )


def redact(text: str, credentials: Credentials | None = None) -> str:
    """Strip anything that looks like a secret out of text before printing it."""
    cleaned = re.sub(r"(?i)(['\"]?(?:pass|password|apikey|xapikey)['\"]?\s*[:=]\s*)(['\"])(.*?)\2",
                     lambda m: m.group(1) + m.group(2) + _REDACTED + m.group(2), text)
    if credentials is not None and credentials.password:
        cleaned = cleaned.replace(credentials.password, _REDACTED)
    return cleaned


def redact_json(value, credentials: Credentials | None = None) -> str:
    return redact(json.dumps(value, ensure_ascii=False), credentials)
