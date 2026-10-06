"""Prepare phase-3 rows from documented sheet cost layers and Flow quantities."""
import csv
import hashlib
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OLD = ROOT / 'outputs' / '01a0df6e-opening'
sys.path.insert(0, str(ROOT / 'Integration FLOW' / 'src'))
from flow.lots import Catalog, DATE_RE, lots_in_segment, norm_lot, split_remark

raw = json.loads((HERE / 'flow_raw.json').read_text())
prior = json.loads((OLD / 'stage2_data.json').read_text())
prior_costs = json.loads((OLD / 'stage2_costs.json').read_text())
opening = json.loads((OLD / 'opening_data.json').read_text())
cat = Catalog(ROOT / 'Integration FLOW' / 'data' / 'inventory' / 'lot_catalog.json')
overrides = json.loads((ROOT / 'Integration FLOW' / 'data' / 'inventory' / 'overrides.json').read_text())['overrides']

MONTHS = {'2026-03': ('حركات مارس', 'مارس'), '2026-04': ('حركات أبريل', 'أبريل'),
          '2026-05': ('حركات مايو', 'مايو'), '2026-06': ('حركات يونيو', 'يونيو')}
SUMMARY_OPS = ('STROUT', 'STRMRT', 'STRMAK', 'STRMR', 'STRIN2')

def actual_purchase_cost(m):
    """Actual incoming Flow purchase price, per user instruction 2026-09-28."""
    return float(m["pr"]) if m.get("pr") is not None else None

def ref_expr(sheet, formula):
    if not formula:
        return None
    if formula.startswith("='"):
        return formula[1:]
    if re.fullmatch(r'=K\d+', formula):
        return f"'{sheet}'!{formula[1:]}"
    raise ValueError((sheet, formula))

layers = defaultdict(list)
for o in opening['opening']:
    layers[o['item']].append({'qty': float(o['qty']), 'cost': float(o['unit_cost']),
                              'expr': f"'الافتتاحي'!G{o['row'] + 14}",
                              'basis': f"افتتاحي، سطر {o['row']}", 'lot': None})

issue_by_doc = {}
lot_cost_conflicts = []
def consume(item, qty, label, target_lot=None):
    left = qty
    parts = []
    available = layers[item]
    if target_lot and item in ('144', '75'):
        available = ([l for l in available if l['lot'] == target_lot] +
                     [l for l in available if l['lot'] is None] +
                     [l for l in available if l['lot'] not in (target_lot, None)])
    for l in available:
        if left <= 1e-8:
            break
        take = min(left, l['qty'])
        if take > 1e-8:
            l['qty'] -= take
            left -= take
            parts.append({'qty': take, 'cost': l['cost'], 'expr': l['expr'],
                          'basis': l['basis'], 'lot': l['lot']})
            if target_lot and item in ('144', '75') and l['lot'] not in (target_lot, None):
                lot_cost_conflicts.append({'key': label, 'wanted': target_lot,
                                           'used': l['lot'], 'qty': take})
    if left > 1e-8:
        raise ValueError(('negative item stock', label, item, qty, left))
    return parts

def append_layer(item, qty, cost, expr, basis, lot=None):
    layers[item].append({'qty': qty, 'cost': cost, 'expr': expr, 'basis': basis, 'lot': lot})

def value_of(parts):
    return None if any(p['cost'] is None for p in parts) else sum(p['qty'] * p['cost'] for p in parts)

assert len(prior['movements']) == len(prior_costs['rows'])
for m, pc in zip(prior['movements'], prior_costs['rows']):
    item, qty, op = str(m['ITNO']), float(m['q']), m['OPCODE']
    assert (pc['item'], pc['op'], pc['doc']) == (item, op, m['DOCNO'])
    if m['e'] == 'A':
        append_layer(item, qty, pc['cost'], ref_expr(pc['sheet'], pc['formula']), pc['basis'])
    else:
        parts = consume(item, qty, (op, m['DOCNO']))
        calc = value_of(parts)
        assert calc is not None and abs(calc / qty - pc['cost']) < 1e-6, (op, m['DOCNO'], item, calc, pc['cost'])
        issue_by_doc[(op, int(m['DOCNO']), item)] = parts

count_path = ROOT / 'Source file' / 'جرد_30-06-2026 .csv'
with count_path.open(encoding='utf-8-sig', newline='') as f:
    count_csv = list(csv.reader(f))
assert count_csv[5][:5] == ['الصفحة', 'CODE', 'EXP', 'LOT/IOT', 'Q']
count = []
for source_row, x in enumerate(count_csv[6:], 7):
    if not x[1]:
        continue
    item, exp, lot, qty = x[1], x[2], x[3], float(x[4])
    notes = []
    if item == '144' and lot == '20241213031':
        assert qty == 83
        notes.append('تصحيح معتمد: ٣ بدل ٨٣؛ ٨٠ من اللوط الجديد')
        qty = 3.0
    if item == '144' and lot == '20251014031':
        assert qty == 0
        notes.append('تصحيح معتمد: ٨٠ بدل صفر؛ إذنا إضافة ١١٠ و١١١')
        qty = 80.0
    if item == 'QELC 6035B' and lot == '1.55202E+12':
        lot = '01552022024951'
        notes.append('الرقم الكامل من جرد فبراير؛ CSV يعرضه بصيغة علمية')
    if item == '101' and lot == '3605202 5003':
        lot = '36052025003'
        notes.append('إزالة مسافة داخل رقم اللوط')
    count.append({'source_row': source_row, 'page': x[0], 'item': item, 'qty': qty,
                  'source_qty': float(x[4]), 'exp': exp, 'lot': lot,
                  'source_lot': x[3], 'note': '؛ '.join(filter(None, [x[5], x[6], *notes]))})

count_by_item = defaultdict(float)
count_lots = defaultdict(dict)
for x in count:
    count_by_item[x['item']] += x['qty']
    if x['qty'] > 0 and x['lot'] not in ('', 'بدون'):
        count_lots[x['item']][x['lot']] = x['exp']
feb_lots = defaultdict(dict)
for x in prior['count']:
    if x['qty'] > 0 and x['lot'] not in ('', 'بدون'):
        feb_lots[x['item']][x['lot']] = x['expiry']

def canonical_lot(item, lot):
    return cat.canonical(item, lot) or lot

def expiry(item, lot):
    if lot in count_lots[item]:
        return count_lots[item][lot]
    if lot in feb_lots[item]:
        return feb_lots[item][lot]
    return cat.expiry(item, lot)

doc_items = defaultdict(list)
for m in raw['movements']:
    k = (m['OPCODE'], int(m['DOCNO']))
    if str(m['ITNO']) not in doc_items[k]:
        doc_items[k].append(str(m['ITNO']))
segments = {}
for k, items in doc_items.items():
    remark = next(m.get('RMK') or '' for m in raw['movements'] if (m['OPCODE'], int(m['DOCNO'])) == k)
    segments[k] = split_remark(remark, items)

def lot_info(m):
    item, op, doc, qty = str(m['ITNO']), m['OPCODE'], int(m['DOCNO']), float(m['q'])
    key = f'{op}:{doc}:{item}'
    if item == '144' and (op, doc) == ('STRIN9', 81):
        return [('20241213031', qty)], 'مستنتج من جرد فبراير وتسلسل الرصيد'
    if item == '144' and (op, doc) in [('STROUT', 872), ('STRMAK', 220)]:
        return [], 'ملاحظة المستند تذكر لوطًا غير موجود في الجرد؛ غير محدد'
    if item == '144' and (op, doc) == ('STROUT', 903):
        return [('20251014031', qty)], 'مستنتج من مرتجع ١٣١ وجرد يونيو'
    seg = segments[(op, doc)].get(item) or segments[(op, doc)].get('*', '')
    ov = overrides.get(key, {})
    if ov.get('lots'):
        pairs = [(canonical_lot(item, lot), float(q)) for lot, q in ov['lots']]
        if abs(sum(q for _, q in pairs) - qty) < 1e-8:
            return pairs, 'ملاحظات المستند وجرد يونيو' if seg.strip() else 'مستنتج من جرد يونيو'
    found = lots_in_segment(cat, item, seg) if seg.strip() else []
    found = list(dict.fromkeys(canonical_lot(item, x) for x in found))
    if len(found) == 1:
        tokens = [found[0]] + [alias for alias, canonical in cat.aliases.get(item, {}).items()
                               if canonical == found[0]]
        has_lot = any(norm_lot(token) in norm_lot(seg) for token in tokens)
        has_expiry = bool(DATE_RE.search(seg))
        status = ('ملاحظات المستند' if has_lot else
                  ('ملاحظات المستند والجرد' if has_expiry else 'مستنتج من الجرد'))
        return [(found[0], qty)], status
    if len(found) > 1:
        return [], 'أكثر من لوط؛ الكمية غير محددة'
    known = set(count_lots[item]) | set(feb_lots[item])
    known = {canonical_lot(item, x) for x in known}
    if len(known) == 1:
        return [(next(iter(known)), qty)], 'مستنتج من الجرد'
    return [], 'غير محدد'

assert abs(sum(l['qty'] for l in layers['144']) - 1425) < 1e-8
for l in layers['144']:
    l['lot'] = '20241213031'
assert abs(sum(l['qty'] for l in layers['75']) - 14) < 1e-8
old_remaining = 4.0
reassigned_75 = []
for l in layers['75']:
    if l['qty'] <= 1e-8:
        continue
    old = min(old_remaining, l['qty'])
    if old > 0:
        reassigned_75.append(dict(l, qty=old, lot='0469-E3'))
        old_remaining -= old
    if l['qty'] > old:
        reassigned_75.append(dict(l, qty=l['qty'] - old, lot='0505-E2'))
assert old_remaining == 0
layers['75'] = reassigned_75

base_layers = {item: [dict(layer) for layer in arr] for item, arr in layers.items()}
base_issues = dict(issue_by_doc)
seed_issues = {}
for pass_no in range(2):
    layers = defaultdict(list, {item: [dict(layer) for layer in arr] for item, arr in base_layers.items()})
    issue_by_doc = dict(base_issues)
    rows = []
    cost_flags = []
    lot_flags = []
    summary = defaultdict(lambda: {'lines': 0, 'docs': set(), 'qty': 0.0, 'value': 0.0, 'missing': 0})
    month_row = Counter()
    for m in raw['movements']:
        month = m['dt'][:7]
        sheet, month_ar = MONTHS[month]
        month_row[month] += 1
        sheet_row = month_row[month] + 1
        item, op, doc, qty = str(m['ITNO']), m['OPCODE'], int(m['DOCNO']), float(m['q'])
        key = (op, doc, item)
        pairs, lot_status = lot_info(m)
        cost = None
        expr = None
        parts = []
        basis = ''
        if m['e'] == 'S':
            parts = ([p for lot, amount in pairs for p in consume(item, amount, key, lot)]
                     if item in ('144', '75') and pairs else consume(item, qty, key))
            v = value_of(parts)
            if v is not None:
                cost = v / qty
                terms = [f'{p["qty"]:g}*{p["expr"]}' for p in parts]
                if any(p['expr'] is None for p in parts):
                    v = None
                    cost = None
                elif len(parts) == 1:
                    expr = parts[0]['expr']
                else:
                    expr = '(' + '+'.join(terms) + f')/G{sheet_row}'
            basis = '؛ '.join(dict.fromkeys(p['basis'] for p in parts))
            if len(parts) > 1:
                basis = f'{len(parts)} دفعات: ' + basis
            issue_by_doc[key] = parts
        else:
            if op == 'STRIN2':
                cost = actual_purchase_cost(m)
                if cost is not None:
                    expr = f'K{sheet_row}'
                    basis = f'تكلفة شراء فعلية واردة من Flow؛ إذن إضافة موردين {doc}'
                else:
                    basis = 'سعر الشراء الفعلي غير موجود في حركة المشتريات'
            elif op in ('STRMRT', 'STRMR'):
                if op == 'STRMRT':
                    src = raw['return_sources'].get(str(doc), {})
                    src_op = 'STROUT'
                    src_doc = src.get('out')
                else:
                    src_op = 'STRMAK'
                    src_doc = raw['sample_return_links'].get(str(doc))
                original = (issue_by_doc.get((src_op, int(src_doc), item)) or seed_issues.get((src_op, int(src_doc), item))) if src_doc is not None else None
                if original and value_of(original) is not None:
                    rates = {p['cost'] for p in original}
                    if len(rates) == 1:
                        cost = next(iter(rates))
                        expr = original[0]['expr']
                        basis = f'تكلفة صرف {src_op} {src_doc}'
                    else:
                        basis = f'صرف {src_op} {src_doc} متعدد الدفعات؛ تحديد دفعة المرتجع مطلوب'
                else:
                    known = {l['cost'] for l in layers[item] if l['qty'] > 1e-8 and l['cost'] is not None}
                    if len(known) == 1:
                        cost = next(iter(known))
                        expr = next(l['expr'] for l in layers[item] if l['qty'] > 1e-8 and l['cost'] == cost)
                        basis = f'طبقة موثقة بالصنف؛ الصرف الأصلي {src_doc or "قديم"} خارج الفترة'
                    else:
                        basis = f'تكلفة صرف {src_op} {src_doc or "قديم"} غير محددة من الشيت'
            else:
                known = {(l['cost'], l['expr']) for l in layers[item] if l['qty'] > 1e-8 and l['cost'] is not None}
                costs = {x[0] for x in known}
                if len(costs) == 1:
                    cost = next(iter(costs))
                    expr = next(x[1] for x in known if x[0] == cost)
                    basis = 'تكلفة طبقة موثقة للصنف'
                else:
                    basis = 'تكلفة التحويل الوارد غير محددة من الشيت'
            if item in ('144', '75') and pairs:
                for lot, amount in pairs:
                    append_layer(item, amount, cost,
                                 f"'{sheet}'!O{sheet_row}" if cost is not None else None,
                                 basis, lot)
            else:
                append_layer(item, qty, cost, f"'{sheet}'!O{sheet_row}" if cost is not None else None, basis)
            v = None if cost is None else qty * cost
        if cost is None:
            cost_flags.append({'month': month, 'op': op, 'doc': doc, 'item': item, 'qty': qty, 'basis': basis})
        lot_text = '؛ '.join(f'{l} ({q:g})' for l, q in pairs)
        exp_text = '؛ '.join(f'{expiry(item, l)} ({q:g})' for l, q in pairs)
        if not pairs:
            lot_flags.append({'month': month, 'op': op, 'doc': doc, 'item': item, 'qty': qty, 'why': lot_status})
        rec = {'month': month, 'sheet': sheet, 'sheet_row': sheet_row, 'movement': m,
               'cost': cost, 'cost_expr': expr, 'value': v, 'basis': basis,
               'cost_parts': parts, 'lot': lot_text, 'expiry': exp_text,
               'lot_status': lot_status}
        rows.append(rec)
        a = summary[(month, op)]
        a['lines'] += 1
        a['docs'].add(doc)
        a['qty'] += qty
        if v is None:
            a['missing'] += 1
        else:
            a['value'] += v
    seed_issues = dict(issue_by_doc)

assert len(rows) == 407
assert dict(month_row) == {'2026-03': 71, '2026-04': 163, '2026-05': 72, '2026-06': 101}
snapshot = {}
for month, snaprows in raw['snapshots'].items():
    q = defaultdict(float)
    for x in snaprows:
        q[str(x['ITNO'])] += float(x['q']) * (1 if x['e'] == 'A' else -1)
    snapshot[month] = q
rolling = defaultdict(float)
for o in opening['opening']:
    rolling[o['item']] += o['qty']
for m in prior['movements']:
    rolling[str(m['ITNO'])] += float(m['q']) * (1 if m['e'] == 'A' else -1)
for month in MONTHS:
    for m in raw['movements']:
        if m['dt'][:7] == month:
            rolling[str(m['ITNO'])] += float(m['q']) * (1 if m['e'] == 'A' else -1)
    assert all(abs(rolling[i] - snapshot[month][i]) < 1e-8 for i in set(rolling) | set(snapshot[month])), month
assert abs(sum(snapshot['2026-06'].values()) - 8195) < 1e-8
assert all(abs(count_by_item[i] - snapshot['2026-06'][i]) < 1e-8 for i in set(count_by_item) | set(snapshot['2026-06']))

out = {
    'source': {'flow_fetched_at': raw['fetched_at'], 'count_file': count_path.name,
               'count_sha256': hashlib.sha256(count_path.read_bytes()).hexdigest()},
    'cost_methodology': ('Purchase receipts use actual Flow ITPRICE/pr as authorized on 2026-09-28. '
                         'movement.cost is retained as Flow-reported raw data only and is never '
                         'used for calculated movement costs, which follow sheet batches by lot/expiry.'),
    'rows': rows, 'count': count,
    'summary': {f'{m}:{op}': {'lines': a['lines'], 'docs': len(a['docs']), 'qty': a['qty'],
                              'value': round(a['value'], 4), 'missing': a['missing']}
                for (m, op), a in summary.items()},
    'month_rows': dict(month_row), 'snapshot_totals': {m: sum(q.values()) for m, q in snapshot.items()},
    'cost_flags': cost_flags, 'lot_flags': lot_flags,
    'lot_cost_conflicts': lot_cost_conflicts,
    'ending_layers': {item: [l for l in arr if l['qty'] > 1e-8]
                      for item, arr in layers.items()},
}
(HERE / 'prepared.json').write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str))
print(json.dumps({'rows': len(rows), 'month_rows': dict(month_row),
                  'snapshot_totals': out['snapshot_totals'],
                  'missing_cost': len(cost_flags), 'missing_lot': len(lot_flags),
                  'summary': {k: v for k, v in out['summary'].items() if k.split(':')[1] in SUMMARY_OPS}},
                 ensure_ascii=False))
