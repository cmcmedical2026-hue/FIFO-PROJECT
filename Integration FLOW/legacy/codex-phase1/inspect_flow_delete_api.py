"""Read the captured POS client code around DELPOS without exposing credentials."""

import base64
import json
import re
from pathlib import Path


paths = [
    Path(r"C:\Users\hp\Downloads\Sales request.har"),
    Path(r"C:\Users\hp\Downloads\Sales Order.har"),
]
for path in paths:
    entries = json.loads(path.read_text(encoding="utf-8-sig"))["log"]["entries"]
    print(f"FILE={path.name}")
    for index, entry in enumerate(entries):
        content = entry["response"].get("content", {})
        text = content.get("text") or ""
        if content.get("encoding") == "base64":
            text = base64.b64decode(text).decode("utf-8", errors="replace")
        if path.name == "Sales request.har" and index == 32:
            for term in ("function EXECMD(", "function EXECMD", "DELPOS"):
                where = text.upper().find(term.upper())
                if where >= 0:
                    print(f"FLOW_JS_TERM={term} OFFSET={where}\n{text[where:where + 1700]}\n")
        if path.name == "Sales request.har" and index == 80:
            where = text.find('var T = "DELPOS,"')
            if where >= 0:
                print(f"POS_DELETE_CODE={text[max(0, where - 550):where + 850]}")
        matches = list(re.finditer(r"(?i)del.{0,25}pos|pos.{0,25}del|Delete", text))
        if matches and (index == 80 or entry["request"]["url"].endswith("Flow.js")):
            print(f"MATCH_ENTRY={index} MIME={content.get('mimeType')} COUNT={len(matches)}")
            for match in matches[:12]:
                snippet = text[max(0, match.start() - 200):match.end() + 350]
                if "PASS" not in snippet.upper() and "APIKEY" not in snippet.upper():
                    print(f"OFFSET={match.start()}\n{snippet}\n")
