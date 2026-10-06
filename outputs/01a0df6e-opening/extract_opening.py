"""Read-only Flow opening reconciliation. Never fetch ERP valuation fields."""
import argparse
import csv
import hashlib
import json
import sys
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'Integration FLOW' / 'src'))
from flow import FlowClient

parser = argparse.ArgumentParser()
parser.add_argument('--before', required=True)
args = parser.parse_args()
datetime.strptime(args.before, '%Y-%m-%d')
client = FlowClient(verbose=False, cono='1', strno='1')
queries = {
 'store': "select CONO,STRNO,FORDES from stores where CONO=1 and STRNO=1",
 'history': "select d.CONO,d.STRNO,d.ITNO,d.EFFECTITBAL,sum(d.STRQTY) quantity,count(*) line_count from trndtl d join trnhdr h on h.CONO=d.CONO and h.STRNO=d.STRNO and h.OPCODE=d.OPCODE and h.DOCNO=d.DOCNO where d.CONO=1 and d.STRNO=1 and d.STS='A' and h.STS='A' and d.EFFECTITBAL in ('A','S') and d.DOCDT<'%s' group by d.CONO,d.STRNO,d.ITNO,d.EFFECTITBAL" % args.before,
 'opening_flags': "select CONO,STRNO,ITNO,OPBAL,OPDT from itbal where CONO=1 and STRNO=1",
 'control': "select EFFECTITBAL,sum(STRQTY) quantity,count(*) line_count from trndtl where CONO=1 and STRNO=1 and STS='A' and EFFECTITBAL in ('A','S') and DOCDT<'%s' group by EFFECTITBAL" % args.before,
}
raw = {}
for name, sql in queries.items():
 result = client.srvcmd('getrec', 'GETREC', sql)
 if not isinstance(result, list) or not result:
  raise RuntimeError('Expected nonempty read-only result for ' + name)
 for row in result:
  if name != 'control':
   assert str(row['CONO']) == '1' and str(row['STRNO']) == '1'
 raw[name] = result
assert len(raw['store']) == 1 and raw['store'][0]['FORDES'] == 'مخزون المقطم 1'
assert all(Decimal(str(r['OPBAL'])) == 0 for r in raw['opening_flags']), 'Nonzero separate opening quantity requires review'

src = ROOT / 'Source file' / 'Opening balance 2026.csv'
with src.open(encoding='utf-8-sig', newline='') as f:
 input_rows = list(csv.reader(f))
assert input_rows[0] == ['Item Code', 'Item Name', 'َQTY', 'Expiry Date', 'Unit Cost']
opening=[]
for idx, row in enumerate(input_rows[1:], 2):
 assert len(row) == 5 and row[0] and row[1] and row[2] and row[4]
 qty, cost = Decimal(row[2]), Decimal(row[4])
 assert qty > 0 and cost >= 0
 opening.append({'row':idx,'layer_id':f'OPEN-{idx:03d}','item':row[0],'name':row[1], 'qty':float(qty), 'expiry_source':row[3], 'unit_cost':float(cost), 'value':float(qty*cost)})

flow=defaultdict(lambda:{'in':Decimal(0),'out':Decimal(0),'lines':0})
for r in raw['history']:
 item=str(r['ITNO']); effect=r['EFFECTITBAL']
 flow[item]['in' if effect=='A' else 'out'] += Decimal(str(r['quantity']))
 flow[item]['lines'] += int(r['line_count'])
for effect in ['A','S']:
 expected=next(Decimal(str(r['quantity'])) for r in raw['control'] if r['EFFECTITBAL']==effect)
 actual=sum((v['in' if effect=='A' else 'out'] for v in flow.values()),Decimal(0))
 assert actual == expected, 'Header/detail status mismatch'

names={r['item']:r['name'] for r in opening}
keys=set(flow)|set(names)|{str(r['ITNO']) for r in raw['opening_flags']}
reconciliation=[]
for item in sorted(keys,key=lambda v:(not v.isdigit(),int(v) if v.isdigit() else v)):
 f=flow[item]
 qty=sum((Decimal(str(r['qty'])) for r in opening if r['item']==item),Decimal(0))
 balance=f['in']-f['out']
 reconciliation.append({'item':item,'name':names.get(item,''),'opening_qty':float(qty),'flow_in':float(f['in']),'flow_out':float(f['out']),'flow_qty':float(balance),'difference':float(qty-balance),'history_lines':f['lines']})
issues=[r for r in reconciliation if r['difference'] != 0]
totals={'source_rows':len(opening),'source_items':len(names),'quantity':sum(r['qty'] for r in opening),'value':float(sum((Decimal(str(r['qty']))*Decimal(str(r['unit_cost'])) for r in opening),Decimal(0))),'reconciliation_items':len(keys),'mismatches':len(issues),'missing_expiry_rows':sum(not r['expiry_source'] for r in opening),'zero_cost_rows':sum(r['unit_cost']==0 for r in opening)}
payload={'as_of':'2025-12-31','company':1,'store':1,'store_name':raw['store'][0]['FORDES'],'fetched_at':datetime.now(ZoneInfo('Africa/Cairo')).isoformat(),'source_file':src.name,'source_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'queries':queries,'raw':raw,'opening':opening,'reconciliation':reconciliation,'totals':totals,'issues':issues}
out=Path(__file__).parent/'opening_data.json'
out.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'totals':totals,'issues':issues,'output':str(out)},ensure_ascii=False))
