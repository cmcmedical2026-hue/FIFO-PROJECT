"""Prepare January/February quantities and the 28 February physical count."""
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
flow = json.loads((HERE / 'stage2_flow_raw.json').read_text(encoding='utf-8'))
opening = json.loads((HERE / 'opening_data.json').read_text(encoding='utf-8'))
count_path = ROOT / 'Source file' / 'جرد 28-02-2026.csv'
decisions = json.loads((HERE / 'stage2_decisions.json').read_text(encoding='utf-8'))

with count_path.open(encoding='utf-8-sig', newline='') as f:
    raw = list(csv.reader(f))
assert raw[0][:5] == ['تاريخ الجرد', 'الكود', 'الكمية', 'تاريخ الصلاحية', 'اللوط / الرقم التسلسلي']
count = []
for n, row in enumerate(raw[1:], 2):
    assert row[0] == '2026-02-28' and row[1] and float(row[2]) > 0
    item = decisions['count_item_code_corrections'].get(row[1], row[1])
    expiry = decisions['count_expiry_corrections'].get(item, row[3])
    count.append({'source_row': n, 'date': row[0], 'item': item, 'qty': float(row[2]),
                  'expiry': expiry, 'lot': row[4],
                  'source_item': row[1], 'source_expiry': row[3]})

names = {r['item']: r['name'] for r in opening['opening']}
opening_qty = defaultdict(float)
for r in opening['opening']:
    opening_qty[r['item']] += r['qty']
count_qty = defaultdict(float)
for r in count:
    count_qty[r['item']] += r['qty']
movement_qty = defaultdict(float)
monthly = defaultdict(lambda: defaultdict(float))
for r in flow['movements']:
    month = r['dt'][:7]
    direction = 'in' if r['e'] == 'A' else 'out'
    movement_qty[(month, r['ITNO'], direction)] += float(r['q'])
    monthly[month][direction] += float(r['q'])
    monthly[month]['lines'] += 1
snapshot_qty = {}
for month, data in flow['snapshots'].items():
    q = defaultdict(float)
    for r in data['rows']:
        q[str(r['ITNO'])] += float(r['q']) * (1 if r['e'] == 'A' else -1)
    snapshot_qty[month] = dict(q)

items = sorted(set(opening_qty) | set(count_qty) | {r['ITNO'] for r in flow['movements']},
               key=lambda x: (not x.isdigit(), int(x) if x.isdigit() else x))
recon = []
for item in items:
    oi = opening_qty[item]
    ji, jo = movement_qty[('2026-01', item, 'in')], movement_qty[('2026-01', item, 'out')]
    fi, fo = movement_qty[('2026-02', item, 'in')], movement_qty[('2026-02', item, 'out')]
    jan_end, feb_end = oi + ji - jo, oi + ji - jo + fi - fo
    fj, ff = snapshot_qty['jan'].get(item, 0), snapshot_qty['feb'].get(item, 0)
    assert abs(jan_end - fj) < 1e-7, (item, 'jan', jan_end, fj)
    assert abs(feb_end - ff) < 1e-7, (item, 'feb', feb_end, ff)
    recon.append({'item': item, 'name': names.get(item, ''), 'opening': oi,
                  'jan_in': ji, 'jan_out': jo, 'jan_end': jan_end, 'flow_jan': fj,
                  'feb_in': fi, 'feb_out': fo, 'feb_end': feb_end, 'flow_feb': ff,
                  'count_feb': count_qty[item], 'count_diff': count_qty[item] - feb_end})
assert len(flow['movements']) == 194
assert sum(opening_qty.values()) == 11347
assert sum(count_qty.values()) == 10423
assert sum(r['feb_end'] for r in recon) == 10423
assert sum(r['count_diff'] for r in recon) == 0
assert not [r for r in recon if r['count_diff']]

payload = {'scope': flow['scope'], 'fetched_at': flow['fetched_at'],
           'source_file': count_path.name, 'approved_decisions': decisions,
           'source_sha256': hashlib.sha256(count_path.read_bytes()).hexdigest(),
           'movements': flow['movements'], 'count': count, 'reconciliation': recon,
           'summary': {'movement_lines': len(flow['movements']),
                       'jan': dict(monthly['2026-01']), 'feb': dict(monthly['2026-02']),
                       'opening_qty': sum(opening_qty.values()),
                       'jan_end_qty': sum(r['jan_end'] for r in recon),
                       'feb_end_qty': sum(r['feb_end'] for r in recon),
                       'count_rows': len(count), 'count_items': len(count_qty),
                       'count_qty': sum(count_qty.values()),
                       'item_differences': [r for r in recon if r['count_diff']]}}
(HERE / 'stage2_data.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(payload['summary'], ensure_ascii=False))
