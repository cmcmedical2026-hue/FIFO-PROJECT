"""Repository paths, hosts and tenant defaults for the Flow ERP toolkit.

Nothing in this module reads or stores credentials; see `flow.credentials`.
Every value can be overridden with an environment variable so the same code
runs against a different tenant without edits.
"""

from __future__ import annotations

import os
from pathlib import Path

# --- Hosts -------------------------------------------------------------------
LOGIN_HOST = os.environ.get("FLOW_LOGIN_HOST", "login.mcbs-global.com")
API_HOST = os.environ.get("FLOW_API_HOST", "api.mcbs-global.com")
ERP_HOST = os.environ.get("FLOW_ERP_HOST", "erp.mcbs-global.com")
ORIGIN = f"https://{ERP_HOST}"

#: Only these hosts may ever be contacted. Guards against a typo or a
#: tampered template sending tenant data somewhere else.
ALLOWED_HOSTS = (LOGIN_HOST, API_HOST, ERP_HOST)

HTTP_TIMEOUT = int(os.environ.get("FLOW_HTTP_TIMEOUT", "30"))

# --- Tenant defaults ---------------------------------------------------------
DEFAULT_CONO = os.environ.get("FLOW_CONO", "1")
DEFAULT_STRNO = os.environ.get("FLOW_STRNO", "1")
DEFAULT_LNG = os.environ.get("FLOW_LNG", "ENG")
#: Tenant clock. Document dates must come from this zone, not the local machine.
TENANT_TZ = os.environ.get("FLOW_TZ", "Africa/Cairo")

# --- Repository layout -------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = REPO_ROOT / "skills"
SCRIPTS_DIR = REPO_ROOT / "scripts"
TEMPLATES_DIR = Path(os.environ.get("FLOW_TEMPLATES_DIR", REPO_ROOT / "templates"))
HAR_DIR = Path(os.environ.get("FLOW_HAR_DIR", REPO_ROOT / "har"))
RUNS_DIR = Path(os.environ.get("FLOW_RUNS_DIR", REPO_ROOT / "runs"))


def har_sources() -> list[Path]:
    """Every place a HAR capture may live, most specific first.

    `FLOW_HAR_ARCHIVE` pins one archive (a .zip or a directory). Otherwise the
    repo's `har/` directory is used, then the user's Downloads folder, which is
    where the original phase-1 captures were taken.
    """
    pinned = os.environ.get("FLOW_HAR_ARCHIVE")
    found: list[Path] = []
    if pinned:
        found.append(Path(pinned))
    if HAR_DIR.is_dir():
        found.extend(sorted(HAR_DIR.glob("*.zip")))
        found.append(HAR_DIR)
    downloads = Path.home() / "Downloads"
    if downloads.is_dir():
        found.append(downloads)
    return [path for path in found if path.exists()]
