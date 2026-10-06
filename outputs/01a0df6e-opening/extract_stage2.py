"""Read-only January/February Flow movement extract for store 1."""
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'Integration FLOW' / 'src'))
from flow import FlowClient
from flow.lots import fetch_movements, fetch_return_sources

client = FlowClient(verbose=False, cono='1', strno='1')
client.login()
movements = fetch_movements(client, '2026-01-01', '2026-02-28')
returns = fetch_return_sources(client, '2026-01-01')
control_sql = ("select d.EFFECTITBAL e,sum(d.STRQTY) q,count(*) n from trndtl d "
               "join trnhdr h on h.CONO=d.CONO and h.STRNO=d.STRNO and h.OPCODE=d.OPCODE and h.DOCNO=d.DOCNO "
               "where d.CONO=1 and d.STRNO=1 and d.STS='A' and h.STS='A' and "
               "d.EFFECTITBAL in ('A','S') and d.DOCDT>='2026-01-01' and d.DOCDT<='2026-02-28' "
               "group by d.EFFECTITBAL")
control = client.getrec(control_sql)
snapshots = {}
for label, before in [('jan', '2026-02-01'), ('feb', '2026-03-01')]:
    sql = ("select d.ITNO,d.EFFECTITBAL e,sum(d.STRQTY) q from trndtl d "
           "join trnhdr h on h.CONO=d.CONO and h.STRNO=d.STRNO and h.OPCODE=d.OPCODE and h.DOCNO=d.DOCNO "
           "where d.CONO=1 and d.STRNO=1 and d.STS='A' and h.STS='A' and "
           "d.EFFECTITBAL in ('A','S') and d.DOCDT<'%s' "
           "group by d.ITNO,d.EFFECTITBAL" % before)
    snapshots[label] = {'before': before, 'sql': sql, 'rows': client.getrec(sql)}
by_effect = defaultdict(lambda: [0, 0])
for m in movements:
    by_effect[m['e']][0] += float(m['q'])
    by_effect[m['e']][1] += 1
for r in control:
    e = r['e']
    assert abs(by_effect[e][0] - float(r['q'])) < 1e-7
    assert by_effect[e][1] == int(r['n'])
assert sum(v[1] for v in by_effect.values()) == len(movements)
payload = {
    'scope': {'company': 1, 'store': 1, 'from': '2026-01-01', 'to': '2026-02-28'},
    'fetched_at': datetime.now(ZoneInfo('Africa/Cairo')).isoformat(),
    'control_sql': control_sql,
    'control': control,
    'snapshots': snapshots,
    'movements': movements,
    'return_sources': returns,
}
out = Path(__file__).with_name('stage2_flow_raw.json')
out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
print(json.dumps({'output': str(out), 'lines': len(movements), 'control': control}, ensure_ascii=False))
