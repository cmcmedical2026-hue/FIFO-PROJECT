"""Record the checked item-75 lot resolution without rewriting older audits."""
from __future__ import annotations

import copy
import csv
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'outputs'))
from approved_sheet_cost_decisions import apply_decisions


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


csv_path = ROOT / 'Source file/جرد_30-06-2026 .csv'
with csv_path.open(encoding='utf-8-sig', newline='') as file:
    count_rows = list(csv.DictReader(file, fieldnames=['page','item','exp','lot','qty','note','review']))
assert [(r['lot'], int(r['qty'])) for r in count_rows if r['item'] == '75'] == [
    ('0505-E2', 6), ('0469-E3', 2)]
count_sha = hashlib.sha256(csv_path.read_bytes()).hexdigest()
assert count_sha == read(ROOT / 'outputs/phase3-2026/stage3_state.json')['count_sha256']
normalized_count = read(ROOT / 'Integration FLOW/data/inventory/count_2026-06-30.json')
assert [(line[1], line[2]) for line in normalized_count['lines'] if line[0] == '75'] == [
    ('0505-E2', 6), ('0469-E3', 2)]

overrides = read(ROOT / 'Integration FLOW/data/inventory/overrides.json')['overrides']
assert overrides['STROUT:921:75']['lots'] == [['0469-E3', 8], ['0505-E2', 122]]
assert overrides['STROUT:949:75']['lots'] == [['0505-E2', 27], ['0469-E3', 6]]

# Independently roll forward the two lots from the approved June checkpoint.
old, new = 2, 6
movement_ledger = []
for key, old_change, new_change in [
    ('STRIN2 126',0,120), ('STROUT 912',0,-110), ('STRMRT 137',8,0),
    ('STRIN2 128',0,130), ('STROUT 921',-8,-122), ('STRMRT 142',19,0),
    ('STROUT 936',-10,0), ('STROUT 938',0,-10), ('STRMRT 146',5,0),
    ('STROUT 948',-10,0), ('STRIN2 133',0,20), ('STROUT 949',-6,-27),
    ('STROUT 950',0,-6), ('STROUT 953',0,-1),
]:
    old += old_change
    new += new_change
    assert old >= 0 and new >= 0, (key, old, new)
    movement_ledger.append({'movement':key, '0469-E3':old, '0505-E2':new})
assert (old, new) == (0, 0)
assert movement_ledger[4]['0469-E3'] == 2 and movement_ledger[4]['0505-E2'] == 24

baseline = read(ROOT / 'outputs/approved-batch-decisions-2026-09-28/candidate_correction.json')
rows, _ = apply_decisions(copy.deepcopy(baseline['rows']), copy.deepcopy(baseline['month_end_layers']))
resolved = {}
for row in rows:
    movement = row['movement']
    if movement['OPCODE'] == 'STROUT' and str(movement['ITNO']) == '75' and movement['DOCNO'] in (921, 949):
        resolved[movement['DOCNO']] = row
assert set(resolved) == {921, 949}
assert (resolved[921]['value'], resolved[949]['value']) == (108180, 26310)
assert all(row['cost'] is not None for row in rows)

p4_path = ROOT / 'outputs/phase4-2026/prepared.json'
p4 = read(p4_path)
for row in p4['rows']:
    movement = row['movement']
    if movement['OPCODE'] == 'STROUT' and str(movement['ITNO']) == '75' and movement['DOCNO'] in resolved:
        source = resolved[movement['DOCNO']]
        for field in ('cost','cost_expr','value','basis','cost_parts','decision_date','lot','expiry','lot_status'):
            row[field] = copy.deepcopy(source[field])
p4['cost_flags'] = [x for x in p4['cost_flags'] if not (x['item'] == '75' and x['doc'] in resolved)]
p4['lot_cost_conflicts'] = [x for x in p4['lot_cost_conflicts'] if not (x['item'] == '75' and x['doc'] in resolved)]
p4['lot_diffs'] = [x for x in p4['lot_diffs'] if x['item'] != '75']
assert not p4['cost_flags']
assert not [x for x in p4['lot_diffs'] if x['item'] == '75']
report_path = 'outputs/item75-lot-resolution-2026-10-04/audit.json'
p4['approved_cost_decisions_report'] = report_path
write(p4_path, p4)

state_path = ROOT / 'outputs/phase4-2026/stage4_state.json'
state = read(state_path)
for field in ('cost_missing_lines','cost_flags'):
    state[field] = [x for x in state[field] if not (x['item'] == '75' and x['doc'] in resolved)]
for month, value in [('2026-07',108180), ('2026-08',26310)]:
    summary = state['cost_correction_summary'][f'{month}:STROUT']
    if summary['missing'] == 1:
        summary['missing'] = 0
        summary['value'] = round(summary['value'] + value, 4)
    else:
        assert summary['missing'] == 0
        assert summary['value'] == round({
            '2026-07':1725231.9963, '2026-08':1578675.456}[month], 4)
assert not state['cost_missing_lines'] and not state['cost_flags']
state['status'] = 'implemented_with_open_lot_items'
state['approved_cost_decisions_report'] = report_path
write(state_path, state)

audit = {
    'date':'2026-10-04',
    'item':'75',
    'approved_june_count_sha256':count_sha,
    'approved_june_count':{'0469-E3':2,'0505-E2':6},
    'older_count_file_disagreement':'The previous normalized count file used zero because the old-lot row looked crossed out. The later approved CSV and live June count tab use 2, matching Flow quantity 8; the normalized count was updated with this source distinction.',
    'august_count':{'0469-E3':0,'0505-E2':0},
    'movement_ledger':movement_ledger,
    'decisions':[
        {key:copy.deepcopy(row[key]) for key in ('month','sheet','sheet_row','lot','expiry','cost','cost_expr','value','basis','cost_parts','decision_date')}
        | {'document':doc,'source_remark':row['movement']['RMK']}
        for doc,row in sorted(resolved.items())
    ],
    'sheet_verified':{
        'spreadsheet_id':'1TQtVUU3Ao-gZJLRsV4n8_HPXhV0XkBDng9VuuwI-k44',
        'july_row':82,'july_value':108180,
        'august_row':71,'august_value':26310,
        'july_summary_cogs':1725231.9963,
        'august_summary_cogs':1578675.456,
        'method':'Google Sheets connected API CellData after write; no browser capture',
    },
    'source_preservation':'Flow documents, source CSVs, purchase prices, quantities and original remarks were not edited.',
    'other_open_items':'Other item/lot discrepancies, including item 144, remain outside this resolution.',
}
write(OUT / 'audit.json', audit)
print(json.dumps({'resolved_docs':sorted(resolved),'cost_values':[resolved[921]['value'],resolved[949]['value']],
                  'remaining_cost_flags':len(state['cost_flags'])},ensure_ascii=False))
