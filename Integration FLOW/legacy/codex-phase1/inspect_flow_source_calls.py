"""Print only command names/parameters of captured source lookups; no secrets."""

import json
import re
import ast
from pathlib import Path

h = json.loads(Path(r"C:\Users\hp\Downloads\Sales Order.har").read_text(encoding="utf-8-sig"))
for entry in h["log"]["entries"]:
    req = entry["request"]
    if req["url"].split("?")[0] != "https://erp.mcbs-global.com/":
        continue
    body_text = req.get("postData", {}).get("text", "")
    if not ("GETSRC" in body_text.upper() or "LDSRCHDRNO" in body_text.upper()):
        continue
    try:
        body = json.loads(body_text)
    except ValueError:
        try:
            body = ast.literal_eval(body_text)
            print("LEGACY_SOURCE_COMMAND=" + json.dumps(
                {key: body.get(key) for key in ("cmdtxt", "cmdpar", "CMDTXT", "CMDPAR")},
                ensure_ascii=True))
            continue
        except (ValueError, SyntaxError):
            pass
        print("NON_JSON_SOURCE_CALL", "length=" + str(len(body_text)),
              "first_char=" + repr(body_text[:1]),
              "command_tokens=" + json.dumps(re.findall(r"(?:GETSRC|LDSRCHDRNO)[^\\f\\v\\r\\n]{0,100}",
                                                    body_text, flags=re.IGNORECASE)[:3]))
        continue
    print(json.dumps({key: body.get(key) for key in ("cmdtxt", "cmdpar", "CMDTXT", "CMDPAR")},
                     ensure_ascii=True))
