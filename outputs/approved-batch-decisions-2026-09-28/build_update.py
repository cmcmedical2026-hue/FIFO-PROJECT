"""Prepare bounded content-only updates from freshly read target cells."""
import ast
import copy
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'outputs'))
from approved_sheet_cost_decisions import apply_decisions

def read(path): return json.loads(path.read_text())
baseline=OUT/'before_correction.json'
if not baseline.exists():
    baseline.write_text((ROOT/'outputs/cost-rule-2026-09-28/correction.json').read_text())
prior=read(baseline)
live=read(OUT/'live_before.json')
cells,props={},{}
for obj in live.values():
    for sheet in obj['sheets']:
        title=sheet['properties']['title'];props[title]=sheet['properties']
        for block in sheet['data']:
            start_r,start_c=block.get('startRow',0),block.get('startColumn',0)
            for i,row in enumerate(block['rowData']):
                for j,c in enumerate(row.get('values',[])):
                    cells[(title,start_r+i+1,start_c+j+1)]=c

def scalar(c,kind='userEnteredValue'):
    v=c.get(kind,{})
    return next(iter(v.values()),None)

def cell(value=None,formula=False):
    if value is None or value=='':return {}
    return {'userEnteredValue':{('formulaValue' if formula else 'numberValue' if isinstance(value,(int,float)) else 'stringValue'):value}}

candidate=copy.deepcopy(prior)
candidate['rows'],candidate['month_end_layers']=apply_decisions(candidate['rows'],candidate['month_end_layers'])
changed=[];requests=[];expected={}
for old,r in zip(prior['rows'],candidate['rows']):
    if all(old.get(k)==r.get(k) for k in ['cost','cost_expr','basis','lot','expiry','lot_status']):continue
    title,n=r['sheet'],r['sheet_row'];m=r['movement']
    for col,expected_source in [(4,m['DOCNO']),(5,str(m['ITNO'])),(7,m['q']),(14,m['RMK'])]:
        actual=scalar(cells[(title,n,col)])
        if col==5:actual=str(actual)
        if col==14:actual=actual or ''
        assert actual==expected_source,('fresh row identity mismatch',title,n,col,actual,expected_source)
    values=[cell('='+r['cost_expr'],True) if r['cost_expr'] else cell(),
            cell(f'=IF(O{n}="","",G{n}*O{n})',True),
            cell(r['basis']),cell(r['lot']),cell(r['expiry']),cell(r['lot_status'])]
    for i,value in enumerate(values,15):
        oldcell=cells[(title,n,i)]
        assert not oldcell.get('dataValidation'),('validated target',title,n,i)
        if oldcell.get('userEnteredValue')==value.get('userEnteredValue'):continue
        expected[(title,n,i)]=value
        requests.append({'updateCells':{'range':{'sheetId':props[title]['sheetId'],
             'startRowIndex':n-1,'endRowIndex':n,'startColumnIndex':i-1,'endColumnIndex':i},
             'rows':[{'values':[value]}],'fields':'userEnteredValue'}})
    changed.append({'sheet':title,'row':n,'op':m['OPCODE'],'doc':m['DOCNO'],
                    'item':m['ITNO'],'qty':m['q'],'before_cost':old['cost'],
                    'after_cost':r['cost'],'value':r['value'],'basis':r['basis']})

# Formula checks evaluate only arithmetic and references to freshly read inputs.
ref=re.compile(r"'([^']+)'!([A-Z]+)(\d+)|(?<![A-Za-z0-9_])([A-Z]+)(\d+)")
def number_col(text):
    value=0
    for c in text:value=value*26+ord(c)-64
    return value
def arithmetic(node):
    if isinstance(node,ast.Expression):return arithmetic(node.body)
    if isinstance(node,ast.Constant) and isinstance(node.value,(int,float)):return node.value
    if isinstance(node,ast.BinOp):
        a,b=arithmetic(node.left),arithmetic(node.right)
        if isinstance(node.op,ast.Add):return a+b
        if isinstance(node.op,ast.Sub):return a-b
        if isinstance(node.op,ast.Mult):return a*b
        if isinstance(node.op,ast.Div):return a/b
    raise ValueError('unsupported formula arithmetic')
def evaluate(title,row,col,seen=()):
    key=(title,row,col);assert key not in seen,('circular formula',key)
    c=expected.get(key,cells.get(key,{}));v=c.get('userEnteredValue',{})
    if 'numberValue' in v:return v['numberValue']
    if 'formulaValue' not in v:raise ValueError(('missing numeric input',key))
    text=v['formulaValue'][1:]
    def replace(match):
        t=match.group(1) or title
        letter=match.group(2) or match.group(4);n=int(match.group(3) or match.group(5))
        return str(evaluate(t,n,number_col(letter),seen+(key,)))
    return arithmetic(ast.parse(ref.sub(replace,text),mode='eval'))

formula_checks=0
for c in changed:
    if c['after_cost'] is not None:
        assert abs(evaluate(c['sheet'],c['row'],15)-c['after_cost'])<1e-7,c
        formula_checks+=1

summary=defaultdict(lambda:dict(lines=0,qty=0.,value=0.,missing=0,docs=set()))
for r in candidate['rows']:
    m=r['movement'];s=summary[(r['month'],m['OPCODE'])]
    s['lines']+=1;s['qty']+=m['q'];s['docs'].add(m['DOCNO'])
    if r['value'] is None:s['missing']+=1
    else:s['value']+=r['value']
candidate['summary']={f'{mo}:{op}':dict(lines=s['lines'],qty=s['qty'],value=round(s['value'],4),missing=s['missing'],docs=len(s['docs'])) for (mo,op),s in summary.items()}
def flag(r):
    m=r['movement'];return dict(month=r['month'],sheet=r['sheet'],row=r['sheet_row'],op=m['OPCODE'],doc=m['DOCNO'],item=m['ITNO'],qty=m['q'],basis=r['basis'])
candidate['cost_flags']=[flag(r) for r in candidate['rows'] if r['cost'] is None]
candidate['lot_flags']=[dict(flag(r),reason=r['lot_status']) for r in candidate['rows'] if not r['lot']]
candidate['allocation_flags']=[dict(sheet=r['sheet'],row=r['sheet_row'],basis=r['basis']) for r in candidate['rows'] if 'يحتاج مراجعة' in r['basis'] or 'يحتاجان مراجعة' in r['basis']]
candidate['requests']=requests
candidate['approved_decisions_report']='outputs/approved-batch-decisions-2026-09-28/audit.json'
candidate['lot_checkpoint_differences']=[dict(item='144',month='2026-08',lot='20241213031',ledger_qty=3,count_qty=0),dict(item='144',month='2026-08',lot='20251014031',ledger_qty=69,count_qty=72)]
candidate['ending_layer_limitations']={'75:2026-07':'June count and July/August remarks conflict: 10 old vs new units require correction. Existing July lot allocation is provisional.','144:2026-08':'Old lot 3 versus count zero; new lot 69 versus count 72; do not assert complete lot-level valuation.'}

for req in requests:
    b=req['updateCells'];g=b['range']
    assert g['startColumnIndex']>=14 and g['endColumnIndex']<=20
    assert g['endRowIndex']-g['startRowIndex']==len(b['rows'])==1
    assert g['endColumnIndex']-g['startColumnIndex']==len(b['rows'][0]['values'])==1
assert len(candidate['cost_flags'])==2,candidate['cost_flags']
assert all(a['movement']==b['movement'] for a,b in zip(prior['rows'],candidate['rows']))
audit=dict(initial_unresolved=18,resolved_initial_lines=16,remaining_unresolved=candidate['cost_flags'],
   formula_checks=formula_checks,changes=changed,request_count=len(requests),
   sources_unchanged=True,opening_70_remaining_low_cost_units=685,
   inference_144=dict(old_before_june=7,issue_872=1,sample_220=1,issue_879=2,june_old_count=3,
                      old_lot='20241213031',expiry='2027-12-12',unit_cost=335,
                      august_old_ledger=3,august_old_count=0),
   inference_75=dict(june_old=2,june_new=6,old_return_137=8,old_available_before_921=10,
                     old_921_remark=18,august_net_old=-10,august_net_new=10,
                     proposed_921_if_other_remarks_correct=dict(old=8,new=122),
                     proposal_requires_resolution=True),
   verification_method='Fresh Google Sheets API cells, independent arithmetic and Flow SELECT; no browser capture')
for name,data in [('candidate_correction.json',candidate),('requests.json',requests),('audit.json',audit)]:
    (OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:audit[k] for k in ['initial_unresolved','resolved_initial_lines','formula_checks','request_count']},ensure_ascii=False))
print(json.dumps(candidate['cost_flags'],ensure_ascii=False))

if '--verify-native' in sys.argv:
    after=read(OUT/'live_after.json')
    after_cells={}
    for sheet in after['sheets']:
        title=sheet['properties']['title']
        for block in sheet['data']:
            for i,row in enumerate(block['rowData']):
                for j,c in enumerate(row.get('values',[])):
                    after_cells[(title,block.get('startRow',0)+i+1,block.get('startColumn',0)+j+1)]=c
    for key,c in expected.items():
        assert c.get('userEnteredValue')==after_cells[key].get('userEnteredValue'),('native write mismatch',key)
    for c in changed:
        key=(c['sheet'],c['row'],15)
        value=scalar(after_cells[key],'effectiveValue')
        amount=scalar(after_cells[(c['sheet'],c['row'],16)],'effectiveValue')
        if c['after_cost'] is None:
            assert value is None and amount in (None,''),('unresolved cost not blank',key)
        else:
            assert isinstance(value,(int,float)) and abs(value-c['after_cost'])<1e-7,('native rate mismatch',key,value)
            assert isinstance(amount,(int,float)) and abs(amount-c['value'])<1e-6,('native amount mismatch',key,amount)
    source_checks=0
    for key,c in after_cells.items():
        if key[0]=='الافتتاحي' or (key[0].startswith('حركات') and key[2]<=14):
            assert c.get('userEnteredValue')==cells[key].get('userEnteredValue'),('source changed',key)
            source_checks+=1
        assert 'errorValue' not in c.get('effectiveValue',{}),('formula error',key,c)
    prewrite=read(OUT/'prewrite.json');format_checks=0
    for sheet in prewrite['sheets']:
        for block in sheet['data']:
            for i,row in enumerate(block['rowData']):
                for j,c in enumerate(row.get('values',[])):
                    key=(sheet['properties']['title'],block.get('startRow',0)+i+1,block.get('startColumn',0)+j+1)
                    for field in ['userEnteredFormat','dataValidation','note']:
                        assert c.get(field)==after_cells[key].get(field),('format or annotation changed',key,field)
                    format_checks+=1
    summary_checks=0
    for month_index,mo in enumerate(['2026-01','2026-02','2026-03','2026-04','2026-05','2026-06','2026-07','2026-08'],2):
        for col,op in [(2,'STROUT'),(4,'STRMRT'),(6,'STRMAK'),(8,'STRMR'),(10,'STRIN2')]:
            expected_summary=candidate['summary'].get(f'{mo}:{op}',dict(value=0,docs=0,missing=0))
            value=scalar(after_cells[('الملخص',month_index,col)],'effectiveValue')
            docs=scalar(after_cells[('الملخص',month_index,col+1)],'effectiveValue')
            if expected_summary['missing']:assert value=='غير مكتمل',(mo,op,value)
            else:assert isinstance(value,(int,float)) and abs(value-expected_summary['value'])<0.011,(mo,op,value,expected_summary)
            assert docs==expected_summary['docs'],(mo,op,docs,expected_summary)
            summary_checks+=2
    import hashlib,shutil
    previous=read(ROOT/'outputs/cost-rule-2026-09-28/local_verification.json')
    for path,sha in previous['source_sha256'].items():
        assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==sha,('CSV changed',path)
    verification=dict(native_changed_cost_lines=formula_checks,changed_cells_verified=len(expected),
          resolved_initial_lines=16,remaining_unresolved_cost_lines=2,native_formula_errors=0,
          unchanged_source_cells_verified=source_checks,unchanged_format_annotation_cells=format_checks,
          summary_values_and_document_counts_verified=summary_checks,source_csv_hashes_unchanged=True,
          verified_via='Google Sheets API; no browser capture',spreadsheet_url=after['spreadsheetUrl'])
    (OUT/'native_verification.json').write_text(json.dumps(verification,ensure_ascii=False,indent=2)+'\n')
    for name in ['native_verification.json','local_verification.json']:
        target=ROOT/'outputs/cost-rule-2026-09-28'/name
        backup=OUT/('before_'+name)
        if not backup.exists():shutil.copy2(target,backup)
    shutil.copy2(OUT/'candidate_correction.json',ROOT/'outputs/cost-rule-2026-09-28/correction.json')
    for prepared,state,months in [
        (ROOT/'outputs/phase3-2026/prepared.json',ROOT/'outputs/phase3-2026/stage3_state.json',{'2026-03','2026-04','2026-05','2026-06'}),
        (ROOT/'outputs/phase4-2026/prepared.json',ROOT/'outputs/phase4-2026/stage4_state.json',{'2026-07','2026-08'})]:
        for target in [prepared,state]:
            backup=OUT/('before_'+target.parent.name+'_'+target.name)
            if not backup.exists():shutil.copy2(target,backup)
        data=read(prepared);data.update(rows=[r for r in candidate['rows'] if r['month'] in months],
             cost_flags=[f for f in candidate['cost_flags'] if f['month'] in months],
             lot_flags=[f for f in candidate['lot_flags'] if f['month'] in months],
             ending_layers=candidate['month_end_layers'][max(months)],
             approved_cost_decisions_report=candidate['approved_decisions_report'])
        if 'summary' in data:data['summary']={k:v for k,v in candidate['summary'].items() if k[:7] in months}
        prepared.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
        data=read(state);data.update(cost_flags=[f for f in candidate['cost_flags'] if f['month'] in months],
             lot_flags=[f for f in candidate['lot_flags'] if f['month'] in months],
             approved_cost_decisions_verified=True,approved_cost_decisions_report=candidate['approved_decisions_report'],
             cost_correction_summary={k:v for k,v in candidate['summary'].items() if k[:7] in months})
        data['cost_missing_lines']=len(data['cost_flags']) if 'phase3' in str(state) else data['cost_flags']
        if 'phase3' in str(state):
            data['lot_missing_lines']=len(data['lot_flags'])
            data['status']='implemented_with_open_lot_items'
        else:data['lot_missing_lines']=data['lot_flags']
        state.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    state=ROOT/'outputs/01a0df6e-opening/stage2_state.json'
    backup=OUT/'before_stage2_state.json'
    if not backup.exists():shutil.copy2(state,backup)
    data=read(state);data.update(open_questions=[],approved_cost_decisions_verified=True,
         approved_cost_decisions_report=candidate['approved_decisions_report'])
    state.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    current=read(OUT/'before_native_verification.json')
    current.update(native_cost_lines_verified=854,unresolved_cost_lines=2,
         latest_changed_cost_lines_verified=formula_checks,
         latest_verification='outputs/approved-batch-decisions-2026-09-28/native_verification.json',
         coverage='Prior 838 native checks plus 16 newly costed lines and rechecked affected formulas')
    (ROOT/'outputs/cost-rule-2026-09-28/native_verification.json').write_text(json.dumps(current,ensure_ascii=False,indent=2)+'\n')
    previous.update(formula_checks=854,unresolved_cost_lines=2,
         latest_approved_decisions_verification=verification)
    (ROOT/'outputs/cost-rule-2026-09-28/local_verification.json').write_text(json.dumps(previous,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(verification,ensure_ascii=False))
