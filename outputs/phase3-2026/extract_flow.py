"""Read-only Flow extract for March through June 2026, store 1."""
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'Integration FLOW' / 'src'))
from flow import FlowClient
from flow.lots import fetch_movements, fetch_return_sources

client = FlowClient(verbose=False, cono='1', strno='1')
client.login()
movements = fetch_movements(client, '2026-03-01', '2026-06-30')
returns = fetch_return_sources(client, '2026-03-01')
sample_sql = (
    "select m.DOCNO return_doc, q.SRCDOCNO issue_doc from trnhdr m "
    "join trnhdr q on q.CONO=m.CONO and q.STRNO=m.STRNO and q.OPCODE='STRMRS' "
    "and q.DOCNO=m.SRCDOCNO where m.CONO=1 and m.STRNO=1 "
    "and m.OPCODE='STRMR' and m.STS='A' and q.STS='A' "
    "and m.DOCDT>='2026-03-01' and m.DOCDT<='2026-06-30'"
)
sample_links = {str(r['return_doc']): int(r['issue_doc']) for r in client.getrec(sample_sql)}
controls = {}
snapshots = {}
for month, start, end, before in [
    ('2026-03', '2026-03-01', '2026-03-31', '2026-04-01'),
    ('2026-04', '2026-04-01', '2026-04-30', '2026-05-01'),
    ('2026-05', '2026-05-01', '2026-05-31', '2026-06-01'),
    ('2026-06', '2026-06-01', '2026-06-30', '2026-07-01'),
]:
    control_sql = (
        "select d.EFFECTITBAL e,sum(d.STRQTY) q,count(*) n from trndtl d "
        "join trnhdr h on h.CONO=d.CONO and h.STRNO=d.STRNO and h.OPCODE=d.OPCODE "
        "and h.DOCNO=d.DOCNO where d.CONO=1 and d.STRNO=1 and d.STS='A' "
        "and h.STS='A' and d.EFFECTITBAL in ('A','S') "
        f"and d.DOCDT>='{start}' and d.DOCDT<='{end}' group by d.EFFECTITBAL"
    )
    controls[month] = client.getrec(control_sql)
    snapshot_sql = (
        "select d.ITNO,d.EFFECTITBAL e,sum(d.STRQTY) q from trndtl d "
        "join trnhdr h on h.CONO=d.CONO and h.STRNO=d.STRNO and h.OPCODE=d.OPCODE "
        "and h.DOCNO=d.DOCNO where d.CONO=1 and d.STRNO=1 and d.STS='A' "
        "and h.STS='A' and d.EFFECTITBAL in ('A','S') "
        f"and d.DOCDT<'{before}' group by d.ITNO,d.EFFECTITBAL"
    )
    snapshots[month] = client.getrec(snapshot_sql)
    check = defaultdict(lambda: [0.0, 0])
    for row in movements:
        if row['dt'][:7] == month:
            check[row['e']][0] += float(row['q'])
            check[row['e']][1] += 1
    for row in controls[month]:
        qty, count = check[row['e']]
        assert abs(qty - float(row['q'])) < 1e-8 and count == int(row['n'])

assert len(movements) == 407, len(movements)
out = {
    'scope': {'company': 1, 'store': 1, 'from': '2026-03-01', 'to': '2026-06-30'},
    'fetched_at': datetime.now(ZoneInfo('Africa/Cairo')).isoformat(),
    'movements': movements, 'return_sources': returns,
    'sample_return_links': sample_links, 'controls': controls, 'snapshots': snapshots,
}
(HERE / 'flow_raw.json').write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str))
print(json.dumps({'lines': len(movements), 'controls': controls,
                  'sample_returns': len(sample_links)}, ensure_ascii=False))
