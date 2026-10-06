"""Read-only July/August Flow extract for inventory reconciliation."""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "Integration FLOW" / "src"))
from flow import FlowClient
from flow.lots import fetch_movements, fetch_return_sources

client = FlowClient(verbose=False, cono="1", strno="1")
client.login()
movements = fetch_movements(client, "2026-07-01", "2026-08-31")
assert all("2026-07-01" <= r["dt"][:10] <= "2026-08-31" for r in movements)
return_sources = fetch_return_sources(client, "2026-07-01")
sample_sql = (
    "select m.DOCNO return_doc, q.SRCDOCNO issue_doc from trnhdr m "
    "join trnhdr q on q.CONO=m.CONO and q.STRNO=m.STRNO and q.OPCODE='STRMRS' "
    "and q.DOCNO=m.SRCDOCNO where m.CONO=1 and m.STRNO=1 "
    "and m.OPCODE='STRMR' and m.STS='A' and q.STS='A' "
    "and m.DOCDT>='2026-07-01' and m.DOCDT<='2026-08-31'"
)
sample_links = {str(r["return_doc"]): int(r["issue_doc"]) for r in client.getrec(sample_sql)}
(HERE / "flow_raw.json").write_text(json.dumps({"movements": movements,
    "return_sources": return_sources, "sample_return_links": sample_links}, ensure_ascii=False, indent=2))
summary = defaultdict(lambda: {"lines": 0, "qty": 0.0, "remarks": 0})
for r in movements:
    key = (r["dt"][:7], r["OPCODE"], r["e"])
    summary[key]["lines"] += 1
    summary[key]["qty"] += float(r["q"])
    summary[key]["remarks"] += bool((r.get("RMK") or "").strip())
print(json.dumps({"lines": len(movements), "months": dict(Counter(r["dt"][:7] for r in movements)),
                  "return_sources": len(return_sources), "sample_links": len(sample_links),
                  "summary": [{"month": k[0], "op": k[1], "direction": k[2], **v}
                              for k, v in sorted(summary.items())]}, ensure_ascii=False))
