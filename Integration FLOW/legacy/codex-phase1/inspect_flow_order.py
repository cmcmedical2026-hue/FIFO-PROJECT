import json
from pathlib import Path


path = Path(r"C:\Users\hp\Downloads\Sales Order.har")
entries = json.loads(path.read_text(encoding="utf-8-sig"))["log"]["entries"]
source = json.loads(entries[122]["response"]["content"]["text"])
order = json.loads(entries[124]["request"]["postData"]["text"])

safe_headers = ("OP", "DOCNO", "DOCDT", "CONO", "STRNO", "DISTNO", "SDISTNO", "EMPNO", "SRCDOCNO", "REFDOCNO", "FRMORD", "EXPDOC", "RGNO", "PY", "SALRET", "TOTDISC", "TOTDISC5", "TOTSHPVAL", "EXPDT")
print("ORDER_HEADER=" + json.dumps({k: order.get(k) for k in safe_headers}, ensure_ascii=False))
print("SOURCE_HEADER=" + json.dumps({k: source.get(k) for k in safe_headers}, ensure_ascii=False))

before = source["DTL"][0]
after = order["DTL"][0]
for key in sorted(set(before) | set(after)):
    left = before.get(key)
    right = after.get(key)
    if left != right:
        if key in ("ITDES", "ITFOR", "RMK", "FORDES", "DISTNA", "DISTADD"):
            continue
        if isinstance(left, (str, int, float, bool, type(None))) and isinstance(right, (str, int, float, bool, type(None))):
            print(f"LINE_DIFF {key}: source={left!r}, order={right!r}")
        else:
            print(f"LINE_DIFF {key}: source_type={type(left).__name__}, order_type={type(right).__name__}")
