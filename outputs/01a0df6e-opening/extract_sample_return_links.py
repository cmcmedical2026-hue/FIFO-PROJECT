"""Read-only STRMR -> STRMRS -> STRMAK source links for stage 2."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'Integration FLOW' / 'src'))
from flow import FlowClient

client = FlowClient(verbose=False, cono='1', strno='1')
client.login()
sql = (
    "select m.DOCNO return_doc, q.DOCNO return_request, q.SRCDOCNO issue_doc "
    "from trnhdr m join trnhdr q on q.CONO=m.CONO and q.STRNO=m.STRNO "
    "and q.OPCODE='STRMRS' and q.DOCNO=m.SRCDOCNO "
    "where m.CONO=1 and m.STRNO=1 and m.OPCODE='STRMR' and m.STS='A' "
    "and q.STS='A' and m.DOCDT>='2026-01-01' and m.DOCDT<='2026-02-28'"
)
rows = client.getrec(sql)
links = {str(r['return_doc']): int(r['issue_doc']) for r in rows}
out = {'sql': sql, 'rows': rows, 'links': links}
Path(__file__).with_name('sample_return_links.json').write_text(
    json.dumps(out, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
print(json.dumps({'links': links}, ensure_ascii=False))
