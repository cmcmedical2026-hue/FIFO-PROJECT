import json
from pathlib import Path
from urllib.parse import urlparse


FILES = [
    Path(r"C:\Users\hp\Downloads\Sales request.har"),
    Path(r"C:\Users\hp\Downloads\Sales Order.har"),
]


def main() -> None:
    for path in FILES:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        entries = data["log"]["entries"]
        print(f"FILE={path.name} ENTRIES={len(entries)}")
        for i, entry in enumerate(entries):
            request = entry["request"]
            url = urlparse(request["url"])
            if url.path == "/api/chkusr/login" and request["method"] == "POST":
                body = json.loads(request["postData"]["text"])
                response = entry["response"]["content"].get("text", "")
                try:
                    parsed = json.loads(response)
                    response_keys = list(parsed) if isinstance(parsed, dict) else ["array"]
                except ValueError:
                    response_keys = ["non-json"]
                print(f"LOGIN {i} HOST={url.netloc} BODY_KEYS={list(body)} RESPONSE_KEYS={response_keys} REQUEST_HEADERS={[h['name'] for h in request.get('headers', [])]}")
            if i < 80 or request["method"] not in ("GET", "POST"):
                continue
            if request["method"] == "GET":
                if url.path.startswith("/api/"):
                    print(f"{i:03} GET {url.netloc}{url.path}")
                    if url.path in ("/api/SRVCMD/GETOPC/SALREQ", "/api/CONCMD/GETCON/C", "/api/POSCMD/GETITM/0"):
                        print(f"    HEADERS={[h['name'] for h in request.get('headers', [])]}")
                continue
            body_text = request.get("postData", {}).get("text", "")
            try:
                body = json.loads(body_text)
            except ValueError:
                continue
            command = body.get("CMDTXT") or body.get("cmdtxt")
            parameter = body.get("CMDPAR") or body.get("cmdpar") or ""
            if command in ("GETREC", "LDSRCHDRNO"):
                print(f"{i:03} POST {url.netloc}{url.path} CMD={command} PAR={parameter}")
            elif url.path == "/api/POSCMD/ADDPOS":
                print(f"{i:03} POST {url.netloc}{url.path} OP={body.get('OP')} RESPONSE={entry['response']['content'].get('text', '')} HEADERS={[h['name'] for h in request.get('headers', [])]}")
                if body.get("OP") == "SALREQ":
                    print("    SAVE_FIELDS=" + json.dumps({k: v for k, v in body.items() if k in ("DOCNO", "DOCDT", "CONO", "STRNO", "FRMORD", "EXPDOC", "RGNO", "SALRET", "TOTDISC", "PY", "EMPNO", "TOTSHPVAL", "EXPDT")}, ensure_ascii=False))
                    print("    CUSTOMER_FIELD_PRESENCE=" + json.dumps({k: {"blank": not bool(body.get(k)), "length": len(str(body.get(k, "")))} for k in ("DISTNO", "SDISTNO", "DISTNA", "SDISTNA", "FORDES", "DISTADD", "TEL1", "TEL2", "EMAIL", "RMK", "DLVLOC")}, ensure_ascii=False))
                    print("    LINE_FIELDS=" + json.dumps(body["DTL"][0], ensure_ascii=False))


if __name__ == "__main__":
    main()
