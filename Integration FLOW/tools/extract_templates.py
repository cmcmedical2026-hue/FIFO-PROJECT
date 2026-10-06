"""Turn the HAR archive into ``templates/<OP>.json`` -- one payload per operation.

Run this once after adding new captures. Afterwards the scripts no longer need
the HAR files at all, which keeps a 34 MB archive of clear-text credentials out
of everyday use.

    python tools/extract_templates.py            # every operation found
    python tools/extract_templates.py SALINV     # just one

Identity and free-text fields are blanked before writing: they are always
replaced with live values anyway, and there is no reason to keep a copy of a
real customer's address in a checked-in file.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from flow import config  # noqa: E402
from flow.documents import IDENTITY_FIELDS  # noqa: E402
from flow.har import HarLibrary  # noqa: E402

SCRUB_HEADER = IDENTITY_FIELDS + ("RMK", "REFDOCNO", "DOCDT", "SRCDOCNO", "EMPNO")
SCRUB_LINE = ("ITDES", "ITFOR", "RMK", "ITCODE", "SN", "BINDTL")


def scrub(payload: dict) -> dict:
    cleaned = copy.deepcopy(payload)
    cleaned["DOCNO"] = 0
    for field in SCRUB_HEADER:
        if field in cleaned:
            cleaned[field] = 0 if field in ("SDISTNO", "EMPNO") else ""
    for line in cleaned.get("DTL") or []:
        for field in SCRUB_LINE:
            if field in line and isinstance(line[field], str):
                line[field] = ""
    return cleaned


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("operations", nargs="*", help="operation codes; default: all found")
    parser.add_argument("--out", default=None, help="output directory (default: templates/)")
    args = parser.parse_args()

    out_dir = Path(args.out) if args.out else config.TEMPLATES_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    library = HarLibrary()
    if not library.files:
        print("No HAR files found. Looked in: " +
              ", ".join(str(s) for s in config.har_sources()), file=sys.stderr)
        return 1
    print("HAR_FILES %d" % len(library.files))

    index = library.index()
    wanted = [op.upper() for op in args.operations] if args.operations else sorted(index)
    if not wanted:
        print("No ADDPOS payloads found in any capture.", file=sys.stderr)
        return 1

    written = []
    for op in wanted:
        try:
            har, payload = library.find_operation(op)
        except LookupError as exc:
            print("SKIP %s: %s" % (op, exc), file=sys.stderr)
            continue
        document = {
            "operation": op,
            "captured_in": har.label,
            "header_fields": sorted(k for k in payload if k != "DTL"),
            "line_fields": sorted((payload.get("DTL") or [{}])[0]),
            "payload": scrub(payload),
        }
        path = out_dir / (op + ".json")
        path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
        written.append(op)
        print("WROTE %s  <- %s  (%d header fields, %d line fields)" % (
            path.name, har.label, len(document["header_fields"]), len(document["line_fields"])))

    catalogue = out_dir / "index.json"
    catalogue.write_text(json.dumps({
        "operations": {op: index.get(op, []) for op in sorted(index)},
        "extracted": sorted(written),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print("WROTE index.json  (%d operations)" % len(index))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
