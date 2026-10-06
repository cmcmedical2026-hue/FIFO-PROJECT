"""Compare HAR legacy-command wrappers without printing credential values."""

import json
import re
from pathlib import Path


entries = json.loads(Path(r"C:\Users\hp\Downloads\Sales Order.har").read_text(encoding="utf-8-sig"))["log"]["entries"]
login_body = json.loads(entries[64]["request"]["postData"]["text"])


def valid_json(text):
    try:
        json.loads(text)
        return True
    except ValueError:
        return False


for index in (68, 70, 80, 119, 126, 127):
    text = entries[index]["request"].get("postData", {}).get("text", "")
    if not text:
        continue
    credential = re.search(r"(?i)['\"]?pass['\"]?\s*:\s*(['\"])(.*?)\1", text)
    command = re.search(r"(?i)['\"]?cmdtxt['\"]?\s*:\s*(['\"])(.*?)\1", text)
    secret = credential.group(2) if credential else None
    print(f"INDEX={index} METHOD={entries[index]['request']['method']} POST_MIME={entries[index]['request']['postData'].get('mimeType')} "
          f"JSON_VALID={valid_json(text)} QUOTE={credential.group(1) if credential else None} "
          f"PASS_PRESENT={secret is not None} PASS_LENGTH={len(secret) if secret is not None else None} "
          f"SAME_AS_LOGIN={secret == login_body.get('PASS') if secret is not None else None} "
          f"CMD={command.group(2) if command else None}")
