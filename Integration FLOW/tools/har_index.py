"""Summarise what each HAR capture contains, without printing any credential.

Useful when a new capture arrives and you need to know which operation it
covers and which endpoints the browser actually called.

    python tools/har_index.py                 # one line per capture
    python tools/har_index.py --detail        # endpoints and commands too
    python tools/har_index.py --op SALINV     # where an operation was captured
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from flow import config  # noqa: E402
from flow.har import HarLibrary  # noqa: E402


def summarise(har) -> dict:
    ops: Counter = Counter()
    commands: Counter = Counter()
    endpoints: Counter = Counter()
    saves = []
    for entry in har.entries:
        request = entry["request"]
        url = urlparse(request["url"])
        if request["method"] == "GET" and url.path.startswith("/api/"):
            endpoints[re.sub(r"/-?\d+(?=/|$)", "/{n}", url.path)] += 1
            continue
        text = (request.get("postData") or {}).get("text") or ""
        if not text:
            continue
        try:
            body = json.loads(text)
        except ValueError:
            found = re.search(r"(?i)cmdtxt\W{1,4}(\w+)", text)
            if found:
                commands["~" + found.group(1)] += 1
            continue
        if not isinstance(body, dict):
            continue
        command = body.get("CMDTXT") or body.get("cmdtxt")
        if command:
            parameter = str(body.get("CMDPAR") or body.get("cmdpar") or "")
            found = re.search(r"OPCODE=([A-Z0-9]+)", parameter)
            commands[command + ("[%s]" % found.group(1) if found else "")] += 1
        if url.path.upper().endswith("/ADDPOS") and body.get("OP"):
            ops[body["OP"]] += 1
            response = (entry["response"].get("content") or {}).get("text", "")
            saves.append("%s -> %s" % (body["OP"], response[:24]))
    return {"entries": len(har.entries), "operations": dict(ops), "saves": saves,
            "commands": dict(commands.most_common(12)),
            "endpoints": dict(endpoints.most_common(15))}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--detail", action="store_true", help="also list commands and endpoints")
    parser.add_argument("--op", help="only captures that saved this operation")
    args = parser.parse_args()

    library = HarLibrary()
    if not library.files:
        print("No HAR files found in: " + ", ".join(str(s) for s in config.har_sources()),
              file=sys.stderr)
        return 1
    print("SOURCES " + json.dumps([str(s) for s in config.har_sources()], ensure_ascii=False))
    print("CAPTURES %d\n" % len(library.files))

    for har in library.files:
        try:
            summary = summarise(har)
        except (ValueError, KeyError) as exc:
            print("## %s  UNREADABLE (%s)" % (har.label, type(exc).__name__))
            continue
        if args.op and args.op.upper() not in {o.upper() for o in summary["operations"]}:
            continue
        print("## %s" % har.label)
        print("   entries=%d  operations=%s  saves=%s"
              % (summary["entries"], summary["operations"] or "-", summary["saves"] or "-"))
        if args.detail:
            print("   commands  = " + json.dumps(summary["commands"], ensure_ascii=False))
            print("   endpoints = " + json.dumps(summary["endpoints"], ensure_ascii=False))
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
