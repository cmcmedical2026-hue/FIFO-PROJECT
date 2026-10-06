"""Rebuild sheet costs under the General Manager's 2026-09-28 rule.

Flow STRIN2 pr is actual incoming purchase cost. All other costs trace to
opening/purchase sheet cells by item, lot and expiry. Never use movement COST.
The existing sheet's row identities and approved count/lot decisions are kept.
Run before exporting cost corrections; this produces bounded native requests.
"""
from __future__ import annotations

import copy
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Integration FLOW/src'))
from flow.lots import Catalog, DATE_RE, lots_in_segment, norm_lot, split_remark

OUT = ROOT / 'outputs/cost-rule-2026-09-28'
OLD = ROOT / 'outputs/01a0df6e-opening'
CAT = Catalog(ROOT / 'Integration FLOW/data/inventory/lot_catalog.json')
OV = json.loads((ROOT / 'Integration FLOW/data/inventory/overrides.json').read_text())['overrides']
LIVE = json.loads((OUT / 'live_before.json').read_text())
P3 = json.loads((ROOT / 'outputs/phase3-2026/prepared.json').read_text())
P4 = json.loads((ROOT / 'outputs/phase4-2026/prepared.json').read_text())
S2 = json.loads((OLD / 'stage2_costs.json').read_text())
D2 = json.loads((OLD / 'stage2_data.json').read_text())
RAW2 = json.loads((OLD / 'stage2_flow_raw.json').read_text())
RAW3 = json.loads((ROOT / 'outputs/phase3-2026/flow_raw.json').read_text())
RAW4 = json.loads((ROOT / 'outputs/phase4-2026/flow_raw.json').read_text())
OPEN = json.loads((OLD / 'opening_data.json').read_text())['opening']

def val(c, effective=False):
    x = c.get('effectiveValue' if effective else 'userEnteredValue', {})
    return next(iter(x.values()), None)

def cells(title):
    return LIVE[title]['sheets'][0]['data'][0]['rowData']

def live_cell(title, row, col, effective=False):
    return val(cells(title)[row-1].get('values', [])[col-1], effective)

def canon(item, lot):
    return CAT.canonical(item, lot) or norm_lot(lot) if lot else ''

def expkey(text):
    s = str(text or '').strip().replace('/', '-').replace('.', '-')
    p = s.split('-')
    if len(p) == 2:
        if len(p[0]) == 4:
            y, m = int(p[0]), int(p[1])
        elif len(p[1]) == 4:
            m, y = int(p[0]), int(p[1])
        elif len(p[0]) == 2:
            y, m = 2000 + int(p[0]), int(p[1])
        else:
            return s
        return f'{y:04d}-{m:02d}'
    if len(p) == 3 and all(x.isdigit() for x in p):
        if len(p[0]) == 4:
            y, m, d = map(int, p)
        else:
            d, m, y = map(int, p)
        return f'{y:04d}-{m:02d}-{d:02d}'
    return s

def same_exp(a, b):
    a, b = expkey(a), expkey(b)
    return not a or not b or a == b or (len(a) == 7 and b.startswith(a)) or (len(b) == 7 and a.startswith(b))

def parse_pairs(text):
    return [(x.group(1).strip(), float(x.group(2)))
            for x in re.finditer(r'([^؛()]+)\s*\((\d+(?:\.\d+)?)\)', text or '')]

ALL_MOVES = [*RAW2['movements'], *RAW3['movements'], *RAW4['movements']]
DOC_ITEMS = defaultdict(list)
for m in ALL_MOVES:
    k = (m['OPCODE'], int(m['DOCNO']))
    if str(m['ITNO']) not in DOC_ITEMS[k]:
        DOC_ITEMS[k].append(str(m['ITNO']))

def item_segment(m):
    text = m.get('RMK') or ''
    items = DOC_ITEMS[(m['OPCODE'], int(m['DOCNO']))]
    if len(items) == 1:
        return text
    # These two source spellings identify the corresponding item, not a new item.
    aliases = {'ESA60-2.6': ['es60-2.6'], 'BATTERY': ['BATTRY']}
    marks = []
    for item in items:
        for spelling in [item, *aliases.get(item, [])]:
            pattern = r'\(\s*' + re.escape(spelling) + r'\s*\)|(?m:^\s*' + re.escape(spelling) + r'\s*[-:])'
            for match in re.finditer(pattern, text, re.I):
                marks.append((match.start(), match.end(), item))
    marks.sort()
    chunks = []
    for i, (start, end, item) in enumerate(marks):
        if item == str(m['ITNO']):
            chunks.append(text[end:marks[i+1][0] if i+1 < len(marks) else len(text)])
    return '\n'.join(chunks) if chunks else ''

def receipt_batches(m):
    """Retain explicit source lot/expiry; split only when quantities are stated."""
    item, qty = str(m['ITNO']), float(m['q'])
    seg = item_segment(m)
    dates = list(DATE_RE.finditer(seg))
    found = []
    for i, match in enumerate(dates):
        before = seg[dates[i-1].end() if i else 0:match.start()]
        after = seg[match.end():dates[i+1].start() if i+1 < len(dates) else len(seg)]
        token = re.search(r'(?<![A-Za-z0-9])([A-Za-z0-9][A-Za-z0-9.\-]{4,})(?![A-Za-z0-9])', after)
        lot = token.group(1) if token else ''
        if not lot and len(dates) == 1:
            tokens = re.findall(r'(?<![A-Za-z0-9])([A-Za-z0-9][A-Za-z0-9.\-]{4,})(?![A-Za-z0-9])', before)
            lot = next((t for t in reversed(tokens) if re.search(r'\d', t) and t.lower() not in ('expire',)), '')
        if lot and not re.search(r'\d', lot):
            lot = ''
        lot = canon(item, lot)
        exp = expkey(match.group(0))
        # Documented aliases also carry the already approved canonical expiry.
        if lot and CAT.expiry(item, lot) and any(norm_lot(a) in norm_lot(seg) for a in CAT.aliases.get(item, {})):
            exp = expkey(CAT.expiry(item, lot))
        qs = re.findall(r'\((\d+(?:\.\d+)?)\)\s*$', before.strip())
        prefix = re.search(r'(?:^|\n)\s*(\d+(?:\.\d+)?)\s*-\s*$', before)
        q = float(qs[-1]) if qs else float(prefix.group(1)) if prefix else None
        found.append({'lot': lot, 'exp': exp, 'qty': q})
    if len(found) == 1:
        found[0]['qty'] = qty
    elif found and (any(x['qty'] is None for x in found) or abs(sum(x['qty'] for x in found) - qty) > 1e-8):
        return [{'lot': '', 'exp': '', 'qty': qty, 'unallocated_metadata': found}]
    if found:
        return found
    ov = OV.get(f"STRIN2:{int(m['DOCNO'])}:{item}", {}).get('lots')
    if ov and abs(sum(float(q) for _, q in ov) - qty) < 1e-8:
        return [{'lot': canon(item, l), 'exp': expkey(CAT.expiry(item, canon(item, l))), 'qty': float(q)} for l, q in ov]
    return [{'lot': '', 'exp': '', 'qty': qty}]

ROWS = []
for m, pc in zip(RAW2['movements'], S2['rows']):
    ROWS.append({'month': pc['month'], 'sheet': pc['sheet'], 'sheet_row': pc['row'], 'movement': m,
                 'lot': '', 'expiry': '', 'lot_status': 'غير محدد', 'prior': pc})
ROWS += [copy.deepcopy(r) for r in P3['rows']] + [copy.deepcopy(r) for r in P4['rows']]
for r in ROWS:
    m, title, n = r['movement'], r['sheet'], r['sheet_row']
    assert live_cell(title, n, 4) == m['DOCNO'], ('document mismatch', title, n)
    assert str(live_cell(title, n, 5)) == str(m['ITNO']), ('item mismatch', title, n)
    assert float(live_cell(title, n, 7)) == float(m['q']), ('quantity mismatch', title, n)
    assert m['OPCODE'] in str(live_cell(title, n, 3)), ('operation mismatch', title, n)
    if len(cells(title)[n-1].get('values', [])) >= 20:
        r['lot'] = live_cell(title, n, 18) or ''
        r['expiry'] = live_cell(title, n, 19) or ''
        r['lot_status'] = live_cell(title, n, 20) or ''
    if m['OPCODE'] == 'STRIN2':
        r['batches'] = receipt_batches(m)
        for b in r['batches']:
            if b['lot'] and b['exp']:
                CAT.items.setdefault(str(m['ITNO']), {}).setdefault(b['lot'], b['exp'])

FEB_COUNT = [{'item': x['item'], 'lot': canon(x['item'], x['lot']),
              'exp': CAT.expiry(x['item'], canon(x['item'], x['lot'])) if canon(x['item'], x['lot']) != norm_lot(x['lot']) else x['expiry'],
              'qty': float(x['qty'])} for x in D2['count']]
CHECKPOINTS = {'2026-02': FEB_COUNT, '2026-06': P3['count'], '2026-08': P4['count']}

def identities(r):
    m, item = r['movement'], str(r['movement']['ITNO'])
    if m['OPCODE'] == 'STRIN2':
        return r['batches']
    pairs, exps = parse_pairs(r['lot']), parse_pairs(r['expiry'])
    batches = [{'lot': canon(item, l), 'exp': expkey(exps[i][0]) if i < len(exps) else expkey(CAT.expiry(item, canon(item, l))), 'qty': q}
               for i, (l, q) in enumerate(pairs)]
    # Explicit receipt lots extend the catalogue, allowing actual movement remarks
    # to supersede earlier count-only guesses (not approved overrides).
    key = f"{m['OPCODE']}:{int(m['DOCNO'])}:{item}"
    seg = item_segment(m)
    if not OV.get(key, {}).get('lots') and seg:
        found = [l for l in lots_in_segment(CAT, item, seg) if norm_lot(l) in norm_lot(seg)]
        if len(set(found)) == 1:
            l = found[0]
            batches = [{'lot': canon(item, l), 'exp': expkey(CAT.expiry(item, canon(item, l))), 'qty': float(m['q'])}]
            r['lot_status'] = 'لوط وصلاحية من ملاحظة المستند'
    if batches and abs(sum(b['qty'] for b in batches) - float(m['q'])) < 1e-8:
        return batches
    return [{'lot': '', 'exp': '', 'qty': float(m['q'])}]

def cost_expression(parts, row):
    if not parts or any(p.get('cost') is None or not p.get('expr') for p in parts):
        return None, None
    cost = sum(p['qty'] * p['cost'] for p in parts) / sum(p['qty'] for p in parts)
    if len({p['expr'] for p in parts}) == 1:
        return cost, parts[0]['expr']
    return cost, '(' + '+'.join(f"{p['qty']:g}*{p['expr']}" for p in parts) + f')/G{row}'

def matches(layer, batch):
    return (not batch['lot'] or layer.get('lot') in ('', None, batch['lot'])) and same_exp(layer.get('exp'), batch['exp'])

def take(layers, item, batches):
    parts = []
    for b in batches:
        remaining = b['qty']
        arr = sorted(layers[item], key=lambda l: (not matches(l, b), not (b['lot'] and l.get('lot') == b['lot'])))
        all_candidates = [l for l in layers[item] if l['qty'] > 1e-8]
        all_rates = {l['cost'] for l in all_candidates}
        uniform = len(all_rates) == 1 and None not in all_rates and all(l.get('expr') for l in all_candidates)
        possible = [l for l in arr if l['qty'] > 1e-8 and matches(l, b)]
        lots = {l.get('lot') for l in possible if l.get('lot')}
        rates = {l['cost'] for l in possible}
        ambiguous = not b['lot'] and len(lots) > 1 and len(rates) > 1
        for l in arr:
            if remaining < 1e-8:
                break
            q = min(remaining, max(0, l['qty']))
            if q <= 1e-8:
                continue
            l['qty'] -= q
            remaining -= q
            p = dict(l, qty=q)
            if (not matches(l, b) or ambiguous) and uniform:
                p['basis'] += '؛ تكلفة موحدة للدفعات الموثقة؛ توزيع اللوط يحتاج مراجعة'
            elif not matches(l, b) or ambiguous or l.get('allocation_unresolved'):
                p.update(cost=None, expr=None, basis='دفعة الحركة غير محسومة باللوط والصلاحية')
            parts.append(p)
        assert remaining < 1e-8, ('negative item quantity', item, b, remaining)
    return parts

def reanchor(layers, count):
    """Match the approved count, retaining every source price and quantity."""
    by = defaultdict(list)
    for c in count:
        if float(c['qty']) > 0:
            by[str(c['item'])].append({'lot': canon(str(c['item']), c['lot']), 'exp': expkey(c.get('exp', c.get('expiry', ''))), 'qty': float(c['qty'])})
    for item in set(by) | set(layers):
        arr = [dict(l) for l in layers[item] if l['qty'] > 1e-8]
        total = sum(x['qty'] for x in arr)
        assert abs(total - sum(c['qty'] for c in by[item])) < 1e-8, ('count mismatch', item, total, by[item])
        result = []
        for c in by[item]:
            remaining = c['qty']
            ordered = sorted(arr, key=lambda l: (l.get('lot') != c['lot'], not same_exp(l.get('exp'), c['exp'])))
            for l in ordered:
                q = min(remaining, l['qty'])
                if q <= 1e-8:
                    continue
                result.append(dict(l, qty=q, lot=c['lot'], exp=c['exp']))
                l['qty'] -= q
                remaining -= q
                if remaining < 1e-8:
                    break
        layers[item] = result

def source_key(m):
    doc, item, op = str(int(m['DOCNO'])), str(m['ITNO']), m['OPCODE']
    for raw in (RAW2, RAW3, RAW4):
        if op == 'STRMRT':
            link = raw.get('return_sources', {}).get(doc)
            if link and link.get('out') is not None:
                return ('STROUT', int(link['out']), item)
        if op == 'STRMR':
            link = raw.get('sample_return_links', {}).get(doc)
            if link is not None:
                return ('STRMAK', int(link), item)
    return None

def known_batch(history, item, b):
    xs = [l for l in history[item] if matches(l, b) and l['cost'] is not None and l.get('expr')]
    if b['lot']:
        exact = [l for l in xs if l.get('lot') == b['lot']]
        xs = exact or xs
    rates = {round(x['cost'], 8) for x in xs}
    return xs[0] if len(rates) == 1 else None

prior_issues = {}
results = []
snapshots = {}
for pass_no in range(2):
    layers, history = defaultdict(list), defaultdict(list)
    issue = {}
    for o in OPEN:
        row = o['row'] + 14
        cost = float(live_cell('الافتتاحي', row, 7, True))
        assert str(live_cell('الافتتاحي', row, 3)) == o['item']
        item, exp = o['item'], expkey(o['expiry_source'])
        lots = {canon(item, l) for l, e in CAT.items.get(item, {}).items() if exp and same_exp(exp, e)}
        l = {'qty': float(o['qty']), 'cost': cost, 'expr': f"'الافتتاحي'!G{row}", 'basis': f'افتتاحي، سطر {o["row"]}', 'lot': next(iter(lots)) if len(lots) == 1 else '', 'exp': exp}
        layers[item].append(dict(l)); history[item].append(dict(l))
    results = []
    for idx, template in enumerate(ROWS):
        r = copy.deepcopy(template)
        m, item, n = r['movement'], str(r['movement']['ITNO']), r['sheet_row']
        op, doc, qty = m['OPCODE'], int(m['DOCNO']), float(m['q'])
        batches = identities(r)
        key = (op, doc, item)
        if op == 'STRIN2':
            cost = float(m['pr']) if m.get('pr') is not None else None
            parts = [dict(b, cost=cost, expr=f"'{r['sheet']}'!K{n}" if cost is not None else None,
                          basis=f'تكلفة شراء فعلية من Flow؛ إذن إضافة موردين {doc}') for b in batches]
            r['lot_status'] = 'لوط وصلاحية من حركة المشتريات' if any(b['lot'] for b in batches) else 'صلاحية من حركة المشتريات؛ اللوط غير متاح' if any(b['exp'] for b in batches) else 'اللوط والصلاحية غير متاحين بحركة المشتريات'
        elif m['e'] == 'S':
            parts = take(layers, item, batches)
            if r['month'] <= '2026-02':
                # These earlier batch costs were already approved in the sheet.
                old_cost = live_cell(r['sheet'], n, 15, True)
                old_formula = live_cell(r['sheet'], n, 15)
                if isinstance(old_cost, (int, float)) and old_formula:
                    for p in parts:
                        p['cost'] = float(old_cost)
                        p['expr'] = f"'{r['sheet']}'!O{n}"
            issue[key] = copy.deepcopy(parts)
        else:
            original_key = source_key(m)
            original = issue.get(original_key) or prior_issues.get(original_key) or []
            parts = []
            for b in batches:
                candidates = [p for p in original if matches(p, b)]
                candidate_rates = {p['cost'] for p in candidates}
                if candidates and None not in candidate_rates and len(candidate_rates) == 1:
                    source = candidates[0]
                    parts.append(dict(source, qty=b['qty'], lot=b['lot'] or source.get('lot', ''), exp=b['exp'] or source.get('exp', ''), basis=f'دفعة صرف {original_key[0]} {original_key[1]} من الشيت'))
                elif candidates and abs(sum(p['qty'] for p in candidates) - b['qty']) < 1e-8:
                    parts.extend(copy.deepcopy(candidates))
                else:
                    source = known_batch(history, item, b)
                    if r['month'] <= '2026-02':
                        pc = r['prior']
                        if pc['cost'] is not None and pc['formula']:
                            f = pc['formula'][1:]
                            if not f.startswith("'"):
                                f = f"'{r['sheet']}'!{f}"
                            source = dict(b, cost=pc['cost'], expr=f, basis=pc['basis'])
                    ov = OV.get(f'{op}:{doc}:{item}', {})
                    if source is None and 'cost' in ov:
                        approved = [l for l in history[item] if matches(l, b) and l['cost'] is not None and abs(l['cost']-float(ov['cost'])) < 1e-8]
                        source = approved[0] if approved else None
                    if source:
                        parts.append(dict(source, qty=b['qty'], lot=b['lot'] or source.get('lot', ''), exp=b['exp'] or source.get('exp', ''), basis='دفعة موثقة في الشيت باللوط والصلاحية'))
                    else:
                        parts.append(dict(b, cost=None, expr=None, basis='تكلفة دفعة الحركة غير محسومة من الشيت باللوط والصلاحية'))
        cost, expr = cost_expression(parts, n)
        if r['month'] <= '2026-02' and op != 'STRIN2':
            # Preserve the previously delivered Jan/Feb formulas while adding identity.
            cost = live_cell(r['sheet'], n, 15, True)
            cost = float(cost) if isinstance(cost, (int, float)) else None
            f = live_cell(r['sheet'], n, 15)
            expr = f[1:] if isinstance(f, str) and f.startswith('=') else None
        if op == 'STRIN2':
            expr = f'K{n}' if cost is not None else None
        if m['e'] == 'A':
            for p in parts:
                layers[item].append(dict(p)); history[item].append(dict(p))
        identity = batches if op == 'STRIN2' else [dict(b) for b in batches]
        if not any(b['lot'] for b in identity) and op != 'STRIN2':
            known = {p.get('lot') for p in parts if p.get('lot')}
            if len(known) == 1 and not any('أكثر من لوط' in str(r.get('lot_status')) for _ in [0]):
                l = next(iter(known)); identity = [{'lot': l, 'exp': next((p.get('exp', '') for p in parts if p.get('lot') == l), ''), 'qty': qty}]
                r['lot_status'] = 'لوط دفعة المصدر في الشيت'
        r.update(cost=cost, cost_expr=expr, value=cost*qty if cost is not None else None,
                 basis='؛ '.join(dict.fromkeys(p['basis'] for p in parts)), cost_parts=parts,
                 lot='؛ '.join(f"{b['lot']} ({b['qty']:g})" for b in identity if b['lot']),
                 expiry='؛ '.join(f"{b['exp']} ({b['qty']:g})" for b in identity if b['exp']),
                 purchase_batches=identity if op == 'STRIN2' else None)
        results.append(r)
        next_month = ROWS[idx+1]['month'] if idx+1 < len(ROWS) else None
        if next_month != r['month']:
            if r['month'] in CHECKPOINTS:
                reanchor(layers, CHECKPOINTS[r['month']])
            snapshots[r['month']] = {item: [dict(l) for l in arr if l['qty'] > 1e-8] for item, arr in layers.items()}
    prior_issues = issue

# Keep the GM's later cost decisions when rebuilding prepared movement data.
from approved_sheet_cost_decisions import apply_decisions
results, snapshots = apply_decisions(results, snapshots)

def cell(v=None, formula=None):
    if formula is not None:
        return {'userEnteredValue': {'formulaValue': formula}}
    if v is None:
        return {}
    return {'userEnteredValue': {'numberValue' if isinstance(v, (int,float)) else 'stringValue': v}}

requests = []
months = defaultdict(list)
for r in results:
    months[r['month']].append(r)
for month, rows in months.items():
    title = rows[0]['sheet']
    prop = LIVE[title]['sheets'][0]['properties']
    sid, height = prop['sheetId'], len(rows)
    if prop['gridProperties']['columnCount'] < 20:
        requests.append({'updateSheetProperties': {'properties': {'sheetId': sid, 'gridProperties': {'columnCount': 20}}, 'fields': 'gridProperties.columnCount'}})
        peer = LIVE['حركات يوليو']['sheets'][0]['properties']['sheetId']
        requests.append({'copyPaste': {'source': {'sheetId': peer, 'startRowIndex': 0, 'endRowIndex': height+1, 'startColumnIndex': 17, 'endColumnIndex': 20},
                       'destination': {'sheetId': sid, 'startRowIndex': 0, 'endRowIndex': height+1, 'startColumnIndex': 17, 'endColumnIndex': 20},
                       'pasteType': 'PASTE_FORMAT', 'pasteOrientation': 'NORMAL'}})
        requests.append({'updateDimensionProperties': {'range': {'sheetId': sid, 'dimension': 'COLUMNS', 'startIndex': 17, 'endIndex': 20}, 'properties': {'pixelSize': 220}, 'fields': 'pixelSize'}})
        requests.append({'updateCells': {'range': {'sheetId': sid, 'startRowIndex': 0, 'endRowIndex': 1, 'startColumnIndex': 17, 'endColumnIndex': 20}, 'rows': [{'values': [cell('اللوط والكمية'),cell('الصلاحية والكمية'),cell('مصدر تحديد اللوط')]}], 'fields': 'userEnteredValue'}})
    purchases = []
    assessed = []
    for r in rows:
        n = r['sheet_row']; purchase = r['movement']['OPCODE'] == 'STRIN2'
        purchases.append({'values': [cell(r['cost']) if purchase else cell(), cell(formula=f'=G{n}*K{n}') if purchase and r['cost'] is not None else cell()]})
        assessed.append({'values': [cell(formula='='+r['cost_expr']) if r['cost_expr'] else cell(),
                        cell(formula=f'=IF(O{n}="","",G{n}*O{n})'),cell(r['basis']),cell(r['lot']),cell(r['expiry']),cell(r['lot_status'])]})
    requests.append({'updateCells': {'range': {'sheetId':sid,'startRowIndex':1,'endRowIndex':height+1,'startColumnIndex':10,'endColumnIndex':12},'rows':purchases,'fields':'userEnteredValue'}})
    requests.append({'updateCells': {'range': {'sheetId':sid,'startRowIndex':1,'endRowIndex':height+1,'startColumnIndex':14,'endColumnIndex':20},'rows':assessed,'fields':'userEnteredValue'}})

summary = defaultdict(lambda: {'lines':0,'qty':0.0,'value':0.0,'missing':0,'docs':set()})
for r in results:
    m = r['movement']; a = summary[(r['month'],m['OPCODE'])]
    a['lines'] += 1; a['qty'] += float(m['q']); a['docs'].add(int(m['DOCNO']))
    if r['value'] is None: a['missing'] += 1
    else: a['value'] += r['value']
serial_summary = {f'{mo}:{op}': dict(lines=x['lines'],qty=x['qty'],value=round(x['value'],4),missing=x['missing'],docs=len(x['docs'])) for (mo,op),x in summary.items()}
report = {'cost_rule_date':'2026-09-28','cost_methodology':'Actual incoming Flow STRIN2 ITPRICE/pr; all calculated costs use opening/purchase sheet cells by item, lot and expiry. Flow COST is never used.',
          'rows':results,'summary':serial_summary,'purchase_lines':sum(r['movement']['OPCODE']=='STRIN2' for r in results),
          'cost_flags':[{'month':r['month'],'sheet':r['sheet'],'row':r['sheet_row'],'op':r['movement']['OPCODE'],'doc':r['movement']['DOCNO'],'item':r['movement']['ITNO'],'qty':r['movement']['q'],'basis':r['basis']} for r in results if r['cost'] is None],
          'lot_flags':[{'month':r['month'],'sheet':r['sheet'],'row':r['sheet_row'],'op':r['movement']['OPCODE'],'doc':r['movement']['DOCNO'],'item':r['movement']['ITNO'],'qty':r['movement']['q'],'reason':r['lot_status']} for r in results if not r['lot']],
          'allocation_flags':[{'sheet':r['sheet'],'row':r['sheet_row'],'basis':r['basis']} for r in results if 'توزيع اللوط يحتاج مراجعة' in r['basis']],
          'receipt_price_flags':[{'sheet':r['sheet'],'row':r['sheet_row'],'doc':r['movement']['DOCNO'],'item':r['movement']['ITNO'],'price':r['cost']} for r in results if r['movement']['OPCODE']=='STRIN2' and r['cost'] is not None and r['cost']<=1],
          'month_end_layers':snapshots,'requests':requests}
# Update only changed cells, never send a broad blank-filled purchase block.
# Existing input prices, notes and quantities outside the correction are kept.
properties = {v['sheets'][0]['properties']['sheetId']: k for k,v in LIVE.items()}
delta = []
for request in requests:
    if 'updateCells' not in request:
        delta.append(request)
        continue
    body = request['updateCells']; rg = body['range']; title = properties[rg['sheetId']]
    for i,row in enumerate(body['rows']):
        ri = rg['startRowIndex'] + i
        old_rows = cells(title)
        old_row = old_rows[ri].get('values', []) if ri < len(old_rows) else []
        for j,c in enumerate(row['values']):
            ci = rg['startColumnIndex'] + j
            prior = old_row[ci].get('userEnteredValue') if ci < len(old_row) else None
            if prior == c.get('userEnteredValue'):
                continue
            previous = delta[-1].get('updateCells') if delta else None
            if previous and previous['range']['sheetId'] == rg['sheetId'] and previous['range']['startRowIndex'] == ri and previous['range']['endColumnIndex'] == ci:
                previous['range']['endColumnIndex'] += 1
                previous['rows'][0]['values'].append(c)
            else:
                delta.append({'updateCells':{'range':{'sheetId':rg['sheetId'],'startRowIndex':ri,'endRowIndex':ri+1,'startColumnIndex':ci,'endColumnIndex':ci+1},'rows':[{'values':[c]}],'fields':'userEnteredValue'}})
requests = delta
report['requests'] = requests
(OUT / 'correction.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
# Native correction batches stay grouped by month; no quantity/source columns
# are included in the content writes.
sid_month = {LIVE[rr[0]['sheet']]['sheets'][0]['properties']['sheetId']:mo for mo,rr in months.items()}
for group in [('2026-01','2026-02'),('2026-03','2026-04'),('2026-05','2026-06'),('2026-07','2026-08')]:
    selected = []
    for req in requests:
        assert len(req) == 1
        typ, body = next(iter(req.items()))
        if typ == 'updateCells':
            rg = body['range']; sid = rg['sheetId']
            assert rg['endRowIndex']-rg['startRowIndex'] == len(body['rows'])
            assert all(len(row['values']) == rg['endColumnIndex']-rg['startColumnIndex'] for row in body['rows'])
            assert body['fields'] == 'userEnteredValue'
        elif typ == 'updateSheetProperties': sid = body['properties']['sheetId']
        elif typ == 'copyPaste': sid = body['destination']['sheetId']
        else: sid = body['range']['sheetId']
        if sid_month[sid] in group: selected.append(req)
    (OUT / f'requests-{group[0][-2:]}-{group[1][-2:]}.json').write_text(json.dumps(selected,ensure_ascii=False,separators=(',',':')))
for sid in sid_month:
    selected = []
    for req in requests:
        kind,b = next(iter(req.items()))
        actual_sid = b['range']['sheetId'] if 'range' in b else b['properties']['sheetId'] if 'properties' in b else b['destination']['sheetId']
        if actual_sid == sid: selected.append(req)
    (OUT / f'delta-sheet-{sid}.json').write_text(json.dumps(selected,ensure_ascii=False,separators=(',',':')))
for output, month_set in [(ROOT/'outputs/phase3-2026/prepared.json',set(['2026-03','2026-04','2026-05','2026-06'])), (ROOT/'outputs/phase4-2026/prepared.json',set(['2026-07','2026-08']))]:
    d = json.loads(output.read_text()); rr = [r for r in results if r['month'] in month_set]
    d.update(rows=rr,cost_methodology=report['cost_methodology'],cost_flags=[f for f in report['cost_flags'] if f['sheet'] in {r['sheet'] for r in rr}],
             lot_flags=[f for f in report['lot_flags'] if f['sheet'] in {r['sheet'] for r in rr}],ending_layers=snapshots[max(month_set)],cost_rule_date='2026-09-28')
    if 'summary' in d: d['summary'] = {k:v for k,v in serial_summary.items() if k[:7] in month_set}
    output.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'movement_lines':len(results),'purchase_lines':report['purchase_lines'],'purchase_qty':sum(r['movement']['q'] for r in results if r['movement']['OPCODE']=='STRIN2'),
                  'purchase_value':sum(r['value'] or 0 for r in results if r['movement']['OPCODE']=='STRIN2'),'missing_cost':len(report['cost_flags']),
                  'missing_by_month':dict(Counter(r['sheet'] for r in report['cost_flags'])),'requests':len(requests),'unusual_prices':report['receipt_price_flags']},ensure_ascii=False))
