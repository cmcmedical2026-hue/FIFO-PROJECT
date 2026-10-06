"""Put ``src/`` on the import path so scripts can ``import flow`` when run directly.

Also forces UTF-8 output: this tenant's data is Arabic, and the default Windows
console codepage turns it into mojibake.
"""

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
