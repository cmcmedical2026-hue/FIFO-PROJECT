"""Assign source-batch costs to Jan/Feb movement lines; no Flow average costs."""
import json
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
raw = json.loads((HERE / 'stage2_flow_raw.json').read_text(encoding='utf-8'))
opening = json.loads((HERE / 'opening_data.json').read_text(encoding='utf-8'))
sample_return_links = json.loads((HERE / 'sample_return_links.json').read_text(encoding='utf-8'))['links']
stocks = defaultdict(list)
for source in opening['opening']:
    stocks[source['item']].append({
        'qty': float(source['qty']), 'cost': float(source['unit_cost']),
        'formula': f"='الافتتاحي'!G{source['row'] + 14}",
        'basis': f"افتتاحي، سطر {source['row']}",
    })

issue_by_doc = {}
rows = []
unresolved = []
by_op = defaultdict(lambda: {'lines': 0, 'qty': 0.0, 'value': 0.0, 'docs': set()})
jan_lines = sum(m['dt'][:7] == '2026-01' for m in raw['movements'])

def known_cost(item):
    candidates = [layer for layer in stocks[item] if layer['cost'] is not None]
    distinct = {layer['cost'] for layer in candidates}
    return candidates[0] if len(distinct) == 1 and candidates else None

for index, m in enumerate(raw['movements']):
    month = m['dt'][:7]
    sheet = 'حركات يناير' if month == '2026-01' else 'حركات فبراير'
    sheet_row = index + 2 if month == '2026-01' else index - jan_lines + 2
    item, op, qty = str(m['ITNO']), m['OPCODE'], float(m['q'])
    cost = None
    formula = None
    basis = None
    source_issue_doc = None
    if m['e'] == 'A':
        if op == 'STRIN2':
            cost = float(m['pr'])
            formula = f'=K{sheet_row}'
            basis = f'سعر إذن شراء {m["DOCNO"]}'
        else:
            source = None
            if op == 'STRMRT':
                link = raw['return_sources'].get(str(m['DOCNO']))
                if link:
                    source = issue_by_doc.get(('STROUT', int(link['out']), item))
            elif op == 'STRMR':
                source_issue_doc = sample_return_links.get(str(m['DOCNO']))
                assert source_issue_doc is not None, m['DOCNO']
                source = issue_by_doc.get(('STRMAK', source_issue_doc, item))
            if source is None:
                source = known_cost(item)
            if source is None and item == '70' and op == 'STRMRT':
                source = next((l for l in stocks[item] if l['cost'] == 880.0), None)
            if source is not None:
                cost, formula = source['cost'], source['formula']
                if op == 'STRMR':
                    basis = f'مرتجع إذن عينات {source_issue_doc}؛ تكلفة الدفعة من الشيت'
                elif op == 'STRMRT':
                    basis = 'تكلفة صرف البيع الأصلي من الدفعة'
                else:
                    basis = 'تكلفة الصنف من طبقة المصدر'
            else:
                basis = 'تكلفة التحويل الوارد غير موثقة باللوط'
                unresolved.append({'month': month, 'op': op, 'doc': m['DOCNO'],
                                   'item': item, 'qty': qty})
        stocks[item].append({'qty': qty, 'cost': cost, 'formula': formula, 'basis': basis})
    else:
        left, used = qty, []
        for layer in stocks[item]:
            if left <= 1e-9:
                break
            take = min(left, layer['qty'])
            if take > 0:
                layer['qty'] -= take
                left -= take
                used.append((take, layer))
        assert left < 1e-9, (op, m['DOCNO'], item, left)
        assert len({u[1]['cost'] for u in used}) == 1, (op, m['DOCNO'], item, used)
        assert used[0][1]['cost'] is not None, (op, m['DOCNO'], item)
        cost = used[0][1]['cost']
        formula = used[0][1]['formula']
        basis = used[0][1]['basis']
        issue_by_doc[op, int(m['DOCNO']), item] = {
            'cost': cost, 'formula': formula, 'basis': basis,
        }
    value = None if cost is None else round(qty * cost, 4)
    if op in ('STROUT', 'STRMRT', 'STRMAK', 'STRMR', 'STRIN2'):
        assert value is not None, (op, m['DOCNO'], item)
    a = by_op[month, op]
    a['lines'] += 1
    a['qty'] += qty
    a['value'] += value or 0
    a['docs'].add(int(m['DOCNO']))
    rows.append({'month': month, 'sheet': sheet, 'row': sheet_row,
                 'op': op, 'doc': m['DOCNO'], 'item': item, 'qty': qty,
                 'cost': cost, 'value': value, 'formula': formula,
                 'basis': basis, 'source_issue_doc': source_issue_doc})

assert len(rows) == 194 and jan_lines == 114
assert not [r for r in unresolved if r['op'] != 'STRIN9']
for r in rows:
    if r['op'] == 'STRMR':
        original = issue_by_doc.get(('STRMAK', r['source_issue_doc'], r['item']))
        if original is not None:
            assert (r['cost'], r['formula']) == (original['cost'], original['formula']), r
            r['basis'] = f'مرتجع إذن عينات {r["source_issue_doc"]}؛ تكلفة نفس الدفعة'
        else:
            assert r['formula'].startswith("='الافتتاحي'!"), r
            r['basis'] = f'مرتجع إذن عينات {r["source_issue_doc"]} قبل الافتتاح؛ تكلفة الافتتاحي'
out = {'rows': rows, 'unresolved': unresolved,
       'summary': {f'{month}:{op}': {'lines': x['lines'], 'docs': len(x['docs']),
                                    'qty': x['qty'], 'value': round(x['value'], 2)}
                   for (month, op), x in by_op.items()}}
(HERE / 'stage2_costs.json').write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'unresolved': unresolved,
                  'selected': {k: v for k, v in out['summary'].items()
                               if any(k.endswith(':' + op) for op in
                                      ('STROUT', 'STRMRT', 'STRMAK', 'STRMR', 'STRIN2'))}},
                 ensure_ascii=False))
