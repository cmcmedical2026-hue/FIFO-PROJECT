"""Apply the GM's 28 September decisions and documented batch inferences.

This overlay uses stable operation/document/item identities. It never changes
source quantities or Flow prices. Read fresh sheet cells before publishing.
"""
from copy import deepcopy


def apply_decisions(rows, snapshots):
    by_key = {(r['movement']['OPCODE'], int(r['movement']['DOCNO']),
               str(r['movement']['ITNO'])): r for r in rows}

    def assign(key, qty, parts, reason, lot_status=None, decision_date='2026-09-28'):
        r = by_key[key]
        assert float(r['movement']['q']) == qty, ('approved quantity changed', key)
        assert abs(sum(p['qty'] for p in parts) - qty) < 1e-8
        rate = sum(p['qty'] * p['cost'] for p in parts) / qty
        expressions = {p['expr'] for p in parts}
        expr = parts[0]['expr'] if len(expressions) == 1 else (
            '(' + '+'.join(f"{p['qty']:g}*{p['expr']}" for p in parts)
            + f")/G{r['sheet_row']}")
        r.update(cost=rate, cost_expr=expr, value=rate*qty,
                 basis=reason, cost_parts=deepcopy(parts), decision_date=decision_date)
        if lot_status:
            lots, exps = {}, {}
            for p in parts:
                if p.get('lot'): lots[p['lot']] = lots.get(p['lot'], 0) + p['qty']
                if p.get('exp'): exps[p['exp']] = exps.get(p['exp'], 0) + p['qty']
            r.update(lot='؛ '.join(f'{l} ({q:g})' for l,q in lots.items()),
                     expiry='؛ '.join(f'{e} ({q:g})' for e,q in exps.items()),
                     lot_status=lot_status)
        return r

    def part(qty, cost, expr, lot='', exp='', basis=''):
        return dict(qty=qty, cost=cost, expr=expr, lot=lot, exp=exp, basis=basis)

    # The 880 layer remains available throughout Jan-Aug: 685 units at Aug end.
    for op,doc,qty in [('STRIN9',72,10),('STRIN9',76,1),('STRIN9',81,1),
                       ('STRIN9',84,7),('STRIN9',90,3),('STRMRT',123,10)]:
        reason = 'قرار المدير 28-09: استهلاك دفعة الافتتاحي 880 أولًا ثم 895 بعد نفادها؛ دفعة 880 لم تنفد خلال يناير–أغسطس'
        assign((op,doc,'70'),qty,[part(qty,880,"'الافتتاحي'!G50",'U24092318','2027-09-28',reason)],
               reason,'تكلفة بقرار المدير؛ اللوط والصلاحية من الجرد المعتمد')
    for month,items in snapshots.items():
        for layer in items.get('70',[]):
            if layer.get('cost') is None:
                layer.update(cost=880,expr="'الافتتاحي'!G50",
                             basis='قرار المدير: تكلفة الدفعة النشطة 880 من الافتتاحي')

    # The GM explicitly chose the supplier-addition unit price for this issue.
    reason = 'قرار المدير 28-09: تكلفة الوحدة من إضافة الموردين STRIN2 109؛ 420 من خلية شراء الشيت؛ توزيع كمية دفعة المصدر واللوط يحتاج مراجعة'
    assign(('STROUT',810,'142'),50,[part(50,420,"'حركات أبريل'!K2",basis=reason)],
           reason,'تكلفة إضافة الموردين بقرار المدير؛ اللوط والصلاحية غير محسومين')

    # 104 opening - 40 earlier issues + 6 transfers = 70 at 760, then 15 at 790.
    reason = 'قرار المدير 28-09: تتبع الافتتاحي والحركات؛ 70 بسعر 760 (64 افتتاحي و6 تحويلات) ثم 5 من إضافة 111 و5 من إضافة 112 بسعر 790؛ صلاحية الافتتاحي 2027-09؛ ملاحظة السند تختلف عن تخصيص التكلفة المعتمد'
    assign(('STROUT',822,'72'),80,[part(70,760,"'الافتتاحي'!G42",exp='2027-09',basis=reason),
           part(5,790,"'حركات أبريل'!K61",'U26010601','2029-01-13',reason),
           part(5,790,"'حركات أبريل'!K62",'U26010601','2029-01-13',reason)],
           reason,'تتبع الافتتاحي بقرار المدير؛ لوط 70 من 80 غير محدد')
    reason = 'متبقي إضافة الموردين STRIN2 112 بعد استهلاك 70 من دفعة الافتتاحي و10 من دفعة الشراء في صرف 822'
    assign(('STROUT',826,'72'),5,[part(5,790,"'حركات أبريل'!K62",'U26010601','2029-01-13',reason)],
           reason,'دفعة الشراء المتبقية بعد تطبيق قرار المدير')

    # Prior count-only expiry guesses must not supersede explicit movement dates.
    for op,doc,qty in [('STRIN9',84,3),('STRMAK',208,1),('STROU9',169,1),
                       ('STRMR',48,1),('STRIN9',85,2),('STROUT',843,4)]:
        reason = ('تتبع الافتتاحي ESA60-2.6 بتكلفة 700؛ الصلاحية 6-2-2028 من ملاحظات الحركة وجرد فبراير؛ '
                  'لا مشتريات للصنف قبل هذه الحركات؛ تكلفة التحويلات من دفعة الافتتاحي')
        expr = "'حركات أبريل'!O49" if op == 'STRMR' else "'الافتتاحي'!G52"
        if op == 'STRMR': reason += '؛ المرتجع STRMR 48 مرتبط بعينة STRMAK 208'
        assign((op,doc,'ESA60-2.6'),qty,[part(qty,700,expr,exp='2028-02-06',basis=reason)],
               reason,'الصلاحية من ملاحظة المستند وجرد فبراير؛ اللوط غير متاح')

    # Only the old batch can reconcile the June residual: 7 - 1 - 1 - 2 = 3.
    for op,doc in [('STROUT',872),('STRMAK',220)]:
        reason = ('استنتاج من الافتتاحي والحركات وجرد يونيو المعتمد: 7 من اللوط القديم قبل يونيو '
                  'ناقص 1 صرف 872 و1 عينة 220 و2 صرف 879 = 3 بالجرد؛ تكلفة الافتتاحي 335؛ '
                  'اللوط/الصلاحية في ملاحظة المستند مختلفان ويحتاجان مراجعة')
        assign((op,doc,'144'),1,[part(1,335,"'الافتتاحي'!G36",'20241213031','2027-12-12',reason)],
               reason,'لوط وصلاحية مستنتجان من مطابقة جرد يونيو؛ ملاحظة المستند مختلفة')

    # Returns trace to the 2025 issue, and the same-expiry opening batch in sheet.
    for doc,qty,source,date in [(137,8,538,'2025-08-03'),(146,5,644,'2025-11-02')]:
        reason = (f'مرتجع STRMRT {doc} مرتبط بصرف STROUT {source} بتاريخ {date} قبل الافتتاحي؛ '
                  '0469-E3 وصلاحية 25-11-2026 من ملاحظة المرتجع يطابقان دفعة الافتتاحي؛ '
                  'التكلفة 560 من خلية الافتتاحي، مستنتجة من تتبع الدفعة؛ لم يستخدم COST من Flow')
        assign(('STRMRT',doc,'75'),qty,[part(qty,560,"'الافتتاحي'!G43",'0469-E3','2026-11-25',reason)],
               reason,'لوط المرتجع ومطابقة دفعة الافتتاحي؛ المصدر الأصلي متحقق عبر API')

    # In every feasible July split, >=14 old units remain available before 948.
    # The old batch's 850 purchases were entirely exhausted by May's zero stock.
    reason = ('لوط 0469-E3 حسب ملاحظة الصرف؛ مشتريات هذا اللوط بسعر 850 نفدت بنهاية مايو '
              'ورصيده صفر؛ الدفعات المتاحة بعد ذلك مرتجعات بتكلفة أصلية 560؛ '
              'التكلفة موحدة للدفعات الموثقة؛ توزيع دفعة المصدر يحتاج مراجعة بسبب تعارض صرف 921')
    assign(('STROUT',948,'75'),10,[part(10,560,"'الافتتاحي'!G43",'0469-E3','2026-11-25',reason)],
           reason,'لوط وصلاحية من ملاحظة المستند؛ تكلفة موحدة للدفعات المتاحة')

    # The approved June CSV records 2 old + 6 new. Return 137 adds 8 old;
    # receipt 128 adds 130 new before issue 921. The August issue remarks and
    # zero ending count then reconcile only with 8 old + 122 new in issue 921.
    # Keep the conflicting 18/112 source remark in the untouched source column.
    reason = ('تخصيص مستنتج من جرد يونيو المعتمد وتسلسل الدفعات وجرد أغسطس: 8 من 0469-E3 '
              'بسعر 560 (2 من رصيد يونيو و6 من مرتجع 137)، و122 من 0505-E2 بسعر 850 '
              '(16 من إضافة 126 و106 من إضافة 128). ملاحظة المستند الأصلية 18 قديم/112 جديد '
              'تختلف عن التخصيص؛ لم تُستخدم تكلفة Flow المحسوبة')
    assign(('STROUT',921,'75'),130,[
        part(2,560,"'حركات يناير'!O110",'0469-E3','2026-11-25','رصيد يونيو من مرتجع 128 المرتبط بصرف 748'),
        part(6,560,"'حركات يوليو'!O57",'0469-E3','2026-11-25','مرتجع 137 المرتبط بصرف 538'),
        part(16,850,"'حركات يوليو'!K50",'0505-E2','2027-09-04','متبقي إضافة الموردين 126'),
        part(106,850,"'حركات يوليو'!K70",'0505-E2','2027-09-04','إضافة الموردين 128')],
        reason,'تخصيص مستنتج من الجرد وتسلسل الدفعات؛ ملاحظة المستند مختلفة',
        decision_date='2026-10-04')

    reason = ('تخصيص 949 مطابق لملاحظة المستند ومتسق مع جرد أغسطس بعد تصحيح تخصيص 921: '
              '6 من 0469-E3 بسعر 560 (1 من مرتجع 142 و5 من مرتجع 146)، '
              'و27 من 0505-E2 بسعر 850 (14 من إضافة 128 و13 من إضافة 133). '
              'التكلفة من دفعات الشيت، لا من COST أو سعر الصرف في Flow')
    assign(('STROUT',949,'75'),33,[
        part(14,850,"'حركات يوليو'!K70",'0505-E2','2027-09-04','متبقي إضافة الموردين 128'),
        part(13,850,"'حركات أغسطس'!K70",'0505-E2','2027-09-04','إضافة الموردين 133'),
        part(1,560,"'حركات أغسطس'!O12",'0469-E3','2026-11-25','مرتجع 142 المرتبط بصرف 801'),
        part(5,560,"'حركات أغسطس'!O31",'0469-E3','2026-11-25','مرتجع 146 المرتبط بصرف 644')],
        reason,'ملاحظة المستند والجرد وتسلسل الدفعات',decision_date='2026-10-04')

    # Preserve a documented old lot instead of silently relabelling its cost.
    for layer in snapshots.get('2026-08',{}).get('144',[]):
        if layer.get('cost') == 335 and layer.get('lot') == '20251014031':
            layer.update(lot='20241213031',exp='2027-12-12',
                         allocation_unresolved=True,
                         checkpoint_note='الحركات تبقي 3 من اللوط القديم، وجرد أغسطس يسجل 72 جديد؛ فرق لوط يحتاج مراجعة')
    return rows, snapshots
