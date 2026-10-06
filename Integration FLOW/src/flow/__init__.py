"""Flow ERP toolkit -- a Python-only interface to the tenant at erp.mcbs-global.com.

Typical use from a script::

    from flow import FlowClient, documents, lookup

    client = FlowClient()
    client.login()
    order = client.getdoc("SALORD", 989)

Nothing in this package writes without an explicit ``confirm=True``.
"""

from .client import FlowClient, FlowError, UncertainWrite, rows
from .credentials import CredentialError, Credentials, redact, resolve

__all__ = ["FlowClient", "FlowError", "UncertainWrite", "rows",
           "Credentials", "CredentialError", "resolve", "redact"]
