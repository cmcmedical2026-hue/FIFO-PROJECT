import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
import {FileBlob,SpreadsheetFile} from '@oai/artifact-tool';
const dir=decodeURIComponent(new URL('.',import.meta.url).pathname);
const d=JSON.parse(await fs.readFile(dir+'opening_data.json','utf8'));
const wb=await SpreadsheetFile.importXlsx(await FileBlob.load('/Users/user/.codex/plugins/cache/openai-curated-remote/openai-templates/0.1.1/skills/artifact-template-analytics-dashboard/assets/reference.xlsx'));
const dash=wb.worksheets.getItem('Dashboard'), op=wb.worksheets.getItem('Data & Targets'), h=wb.worksheets.getItem('_Chart Helpers');
const rec=wb.worksheets.add('مطابقة الافتتاحي');
const palette={dark:'#0D1B29',panel:'#15293D',head:'#1C3A53',text:'#F3F7FB',muted:'#A6B8C9',accent:'#34CEF3',input:'#FFF2CC'};
const val=(s,a,v)=>s.getRange(a).values=[[v]];
const formula=(s,a,v)=>s.getRange(a).formulas=[[v]];
const opStart=16, opEnd=opStart+d.opening.length-1, recStart=9, recEnd=recStart+d.reconciliation.length-1;
const O=(col)=>`'Data & Targets'!$${col}$${opStart}:$${col}$${opEnd}`;
const R=(col)=>`'مطابقة الافتتاحي'!$${col}$${recStart}:$${col}$${recEnd}`;

// Keep the retained dashboard layout, chart objects and dark visual system.
dash.getRange('B2:Q52').clear({applyTo:'contents'});
dash.getRange('B2:Q52').format.font.name='Arial';
dash.getRange('B2:Q52').conditionalFormats.clear();
op.getRange('B2:P35').clear({applyTo:'contents'});
op.unmergeCells('B29:E29'); op.unmergeCells('G29:J29');
op.getRange('C9').dataValidation={rule:{type:'list',values:['2025-12-31']}};
h.getUsedRange().clear({applyTo:'contents'});
op.getRange('B2:P61').format.font={name:'Arial',size:11};
op.getRange('B2:P13').format.fill=palette.dark;
op.getRange('B2:P13').format.font.color=palette.text;
op.getRange('B14:P61').format.fill='#FFFFFF';
op.getRange('B14:P61').format.font.color='#172B40';
op.getRange('B14:P61').format.borders={preset:'none'};
op.getRange('B14:P61').conditionalFormats.clear();
op.showGridLines=false; rec.showGridLines=false;
val(op,'B2','CMC | مخزون المقطم ١'); val(op,'B3','الافتتاحي — ٣١ ديسمبر ٢٠٢٥');
val(op,'B5','مصدر الكمية والتكلفة: ملف الافتتاحي المعتمد');
val(op,'B6','الصلاحية محفوظة كما وردت؛ 26-07 تعني يوليو 2026، دون افتراض يوم.');
val(op,'B7','الكود ٧٠: دفعة ٨٨٠ أولًا ثم ٨٩٥، حسب اعتمادك. اللوطات غير موجودة في ملف الافتتاحي.');
val(op,'B9','تاريخ الرصيد'); val(op,'C9','2025-12-31');
val(op,'B10','المخزن'); val(op,'C10','المقطم ١');
val(op,'B11','المصدر'); val(op,'C11','Opening balance 2026.csv | التكلفة من الملف فقط');
val(op,'B13','تفاصيل الافتتاحي — ٤٣ طبقة تكلفة');
for(const r of ['B5:P5','B13:P13'])op.getRange(r).format={fill:palette.head,font:{name:'Arial',size:11,bold:true,color:palette.text},rowHeight:28};
for(const r of ['B6:P6','B7:P7','C11:P11'])op.getRange(r).format={fill:palette.panel,font:{name:'Arial',size:11,color:palette.text},rowHeight:28};
op.getRange('B11').format={fill:palette.panel,font:{color:palette.text},rowHeight:28};
op.getRange('B15:K15').values=[['سطر المصدر','كود الصنف','اسم الصنف','الكمية','الصلاحية بالمصدر','تكلفة الوحدة','القيمة','اللوط','ترتيب الكود ٧٠','ملاحظة']];
op.getRange(`B${opStart}:K${opEnd}`).values=d.opening.map(r=>[r.row,r.item,r.name,r.qty,r.expiry_source||null,r.unit_cost,null,null,r.item==='70'?(r.unit_cost===880?1:2):null,r.unit_cost===0?'تكلفة صفر كما في المصدر':r.item==='70'?'الصلاحية مؤكدة؛ اختلاف جرد فبراير للمراجعة':null]);
op.getRange(`B${opStart}:K${opEnd}`).setNumberFormat('General');
op.getRange(`B${opStart}:K${opEnd}`).format.horizontalAlignment='left';
op.getRange(`B${opStart}:B${opEnd}`).setNumberFormat('0');
op.getRange(`B${opStart}:C${opEnd}`).format.horizontalAlignment='center';
op.getRange(`F${opStart}:F${opEnd}`).format.horizontalAlignment='center';
op.getRange(`J${opStart}:J${opEnd}`).format.horizontalAlignment='center';
op.getRange(`E${opStart}:E${opEnd}`).format.horizontalAlignment='right';
op.getRange(`G${opStart}:H${opEnd}`).format.horizontalAlignment='right';
op.getRange(`C${opStart}:C${opEnd}`).setNumberFormat('@');
op.getRange(`F${opStart}:F${opEnd}`).setNumberFormat('@');
op.getRange(`H${opStart}:H${opEnd}`).formulas=d.opening.map((_,i)=>[`=E${opStart+i}*G${opStart+i}`]);
op.getRange(`E${opStart}:G${opEnd}`).format.fill=palette.input;
op.getRange(`E${opStart}:G${opEnd}`).format.font.color='#1D4ED8';
op.getRange(`H${opStart}:H${opEnd}`).format.font.color='#111827';
op.getRange(`I${opStart}:I${opEnd}`).format.fill='#F4F6F8';
op.getRange(`G${opStart}:H${opEnd+2}`).setNumberFormat('#,##0.00;(#,##0.00);0.00');
op.getRange(`E${opStart}:E${opEnd+2}`).setNumberFormat('#,##0');
const ot=opEnd+2; val(op,`D${ot}`,'الإجمالي'); formula(op,`E${ot}`,`=SUM(E${opStart}:E${opEnd})`); formula(op,`H${ot}`,`=SUM(H${opStart}:H${opEnd})`);
op.getRange(`B${ot}:K${ot}`).format.fill=palette.head;op.getRange(`B${ot}:K${ot}`).format.font={bold:true,color:palette.text};
op.getRange('B15:K15').format={fill:palette.head,font:{bold:true,color:palette.text},rowHeight:34,wrapText:true,horizontalAlignment:'center',verticalAlignment:'center'};
op.getRange(`B${opStart}:K${opEnd}`).format.rowHeight=34;
op.getRange(`D${opStart}:D${opEnd}`).format.wrapText=true;
op.getRange(`K${opStart}:K${opEnd}`).format.wrapText=true;
for(const [col,width] of Object.entries({A:3,B:12,C:16,D:57,E:13,F:20,G:16,H:20,I:16,J:19,K:44,L:3,M:3,N:3,O:3,P:3})) op.getRange(`${col}1:${col}61`).format.columnWidth=width;
op.getRange('B2').format.font.size=16;op.getRange('B2').format.font.bold=true;
op.freezePanes.freezeRows(15);op.freezePanes.freezeColumns(3);

// Historical Flow stock quantities only, with the union of item codes.
rec.getRange(`B2:J${recEnd+6}`).format={font:{name:'Arial',size:11,color:'#172B40'},verticalAlignment:'center',rowHeight:26};
rec.mergeCells('B2:J2');val(rec,'B2','مطابقة رصيد المقطم ١ — ٣١ ديسمبر ٢٠٢٥');
rec.getRange('B2:J2').format={fill:palette.dark,font:{bold:true,color:palette.text,size:16},rowHeight:34};
for(const rr of [3,4,5,6]) rec.mergeCells(`B${rr}:J${rr}`);
val(rec,'B3','Flow | الشركة ١ / المخزن ١ | كميات فقط، دون تكلفة أو تقييم مالي');
val(rec,'B4','رصيد Flow التاريخي = مجموع الوارد − مجموع المنصرف حتى نهاية ٣١‑١٢‑٢٠٢٥.');
val(rec,'B5','تم التحقق من أن كمية الافتتاح المنفصلة في itbal تساوي صفرًا؛ الحركات وترويساتها نشطة.');
val(rec,'B6',`استخراج: ${d.fetched_at.slice(0,19).replace('T',' ')} بتوقيت القاهرة | trndtl + trnhdr + itbal`);
rec.getRange('B3:J6').format={fill:'#EFF4F8',font:{color:'#334155',size:10},rowHeight:27};
rec.getRange('B8:J8').values=[['كود الصنف','اسم الصنف','كمية الملف','وارد Flow حتى التاريخ','منصرف Flow حتى التاريخ','رصيد Flow','الفرق','الحالة','عدد سطور Flow']];
rec.getRange('B8:J8').format={fill:palette.head,font:{bold:true,color:palette.text},rowHeight:42,wrapText:true,horizontalAlignment:'center'};
rec.getRange(`B${recStart}:J${recEnd}`).values=d.reconciliation.map(r=>[r.item,r.name||'رصيده الافتتاحي صفر',null,r.flow_in,r.flow_out,null,null,null,r.history_lines]);
for(let i=0;i<d.reconciliation.length;i++) {
 const row=recStart+i;
 formula(rec,`D${row}`,`=SUMIFS(${O('E')},${O('C')},B${row})`);
 formula(rec,`G${row}`,`=E${row}-F${row}`);
 formula(rec,`H${row}`,`=D${row}-G${row}`);
 formula(rec,`I${row}`,`=IF(H${row}=0,"مطابق","فرق يحتاج مراجعة")`);
}
rec.getRange(`B${recStart}:B${recEnd}`).setNumberFormat('@');
rec.getRange(`D${recStart}:J${recEnd}`).setNumberFormat('#,##0;(#,##0);0');
rec.getRange(`D${recStart}:D${recEnd}`).format.font.color='#00804A';
rec.getRange(`H${recStart}:H${recEnd}`).conditionalFormats.add('cellIs',{operator:'notEqual',formula:0,format:{fill:'#FEE2E2',font:{color:'#B91C1C',bold:true}}});
rec.getRange(`C${recStart}:C${recEnd}`).format.wrapText=true;
rec.getRange(`B${recStart}:J${recEnd}`).format.rowHeight=34;
const rt=recEnd+2;val(rec,`C${rt}`,'الإجمالي');for(const c of ['D','E','F','G','H','J'])formula(rec,`${c}${rt}`,`=SUM(${c}${recStart}:${c}${recEnd})`);
rec.getRange(`B${rt}:J${rt}`).format={fill:palette.head,font:{bold:true,color:palette.text}};
val(rec,`C${rt+2}`,'أصناف بها فرق');formula(rec,`D${rt+2}`,`=COUNTIFS(H${recStart}:H${recEnd},"<>0")`);
for(const [c,w] of Object.entries({A:3,B:18,C:60,D:16,E:21,F:21,G:18,H:13,I:24,J:18}))rec.getRange(`${c}1:${c}${rt+3}`).format.columnWidth=w;
rec.freezePanes.freezeRows(8);rec.freezePanes.freezeColumns(2);

// Formula-backed dashboard sources, replacing all marketing demo data.
h.getRange('A1:B9').values=[['المؤشر','القيمة'],['الأصناف',null],['الوحدات',null],['القيمة',null],['طبقات الافتتاحي',null],['بصلاحية',null],['بدون صلاحية',null],['تكلفة صفر',null],['أصناف بها فرق',null]];
formula(h,'B2',`=COUNTIFS(${R('D')},">0")`);
formula(h,'B3',`=SUM(${O('E')})`);formula(h,'B4',`=SUM(${O('H')})`);formula(h,'B5',`=COUNTA(${O('C')})`);
formula(h,'B6',`=COUNTA(${O('F')})`);formula(h,'B7',`=COUNTBLANK(${O('F')})`);formula(h,'B8',`=COUNTIFS(${O('G')},0)`);formula(h,'B9',`=COUNTIFS(${R('H')},"<>0")`);
// Numeric item IDs are explicitly prefixed for category labels, while row keys stay text.
const top=[...d.reconciliation].sort((a,b)=>b.opening_qty-a.opening_qty).slice(0,8);
h.getRange('H1:J1').values=[['الصنف','ملف الافتتاحي','Flow']];
h.getRange('L1:M1').values=[['الصنف','قيمة الافتتاحي']];
for(let i=0;i<top.length;i++) {
 const row=i+2, item=top[i].item, rr=recStart+d.reconciliation.findIndex(x=>x.item===item);
 val(h,`H${row}`,'كود '+item);formula(h,`I${row}`,`='مطابقة الافتتاحي'!D${rr}`);formula(h,`J${row}`,`='مطابقة الافتتاحي'!G${rr}`);
 val(h,`L${row}`,'كود '+item);formula(h,`M${row}`,`=SUMIFS(${O('H')},${O('C')},"${item}")`);
}
h.getRange('P1:Q3').values=[['بيانات الصلاحية','عدد السطور'],['بصلاحية',null],['بدون صلاحية',null]];formula(h,'Q2','=B6');formula(h,'Q3','=B7');
h.getRange('S1:T3').values=[['بيانات الصلاحية','الكمية'],['بصلاحية',null],['بدون صلاحية',null]];
formula(h,'T2',`=SUMIFS(${O('E')},${O('F')},"<>")`);formula(h,'T3','=B3-T2');

val(dash,'B2','CMC | مخزون المقطم ١');val(dash,'B3','الافتتاحي — المرحلة الأولى');
val(dash,'J2','تاريخ الرصيد');val(dash,'J3','٣١ ديسمبر ٢٠٢٥');val(dash,'N2','حالة العمل');val(dash,'N3','الافتتاحي فقط');
val(dash,'B4','المقطم ١ فقط | التكلفة من ملف الافتتاحي؛ Flow للمطابقة الكمية');
const cards=[['B5','B6','عدد الأصناف','B2'],['F5','F6','إجمالي الوحدات','B3'],['J5','J6','قيمة الافتتاحي','B4'],['N5','N6','طبقات التكلفة','B5'],['B10','B11','سطور بصلاحية','B6'],['F10','F11','سطور بدون صلاحية','B7'],['J10','J11','سطور بتكلفة صفر','B8'],['N10','N11','أصناف بها فرق مع Flow','B9']];
for(const [label,cell,text,source] of cards){val(dash,label,text);formula(dash,cell,`='_Chart Helpers'!${source}`);dash.getRange(cell).setNumberFormat(cell==='J6'?'#,##0.00':'#,##0');}
for(const [a,t] of [['B8','٤١ صنفًا في المصدر'],['F8','رصيد ٣١‑١٢‑٢٠٢٥'],['J8','كمية × تكلفة الوحدة'],['N8','السطر يمثل طبقة مستقلة'],['B13','الدقة كما وردت بالمصدر'],['F13','تظل الصلاحية فارغة'],['J13','الكود ١٣٦ كما بالمصدر'],['N13','فحص ١٠٦ أكواد']]){dash.mergeCells(`${a}:${String.fromCharCode(a.charCodeAt(0)+3)}${a.slice(1)}`);val(dash,a,t);dash.getRange(a).setNumberFormat('@');dash.getRange(a).format.font={size:10,color:palette.muted};}
val(dash,'B15','رصيد أكبر ٨ أصناف بالكمية');val(dash,'J15','قيم الأصناف المعروضة');val(dash,'B29','اكتمال الصلاحية — عدد السطور');val(dash,'J29','توزيع الوحدات حسب توافر الصلاحية');
const charts=dash.charts.items;assert.equal(charts.length,4);
charts[0].setData(h.getRange('H1:J9'));charts[0].title='الملف وFlow — وحدة';
charts[1].setData(h.getRange('L1:M9'));charts[1].title='قيمة الافتتاحي من ملفك';
charts[2].setData(h.getRange('P1:Q3'));charts[2].title='سطور الافتتاحي';
charts[3].setData(h.getRange('S1:T3'));charts[3].title='الوحدات';
for(const ch of charts){ch.titleTextStyle.typeface='Arial';ch.titleTextStyle.fontSize=14;}
for(const ch of charts.slice(0,3)){ch.xAxis={textStyle:{typeface:'Arial',fontSize:11},numberFormatCode:'#,##0',numberFormatSourceLinked:false};ch.yAxis={textStyle:{typeface:'Arial',fontSize:11},numberFormatCode:'#,##0',numberFormatSourceLinked:false};}
charts[0].series.items[0].line={fill:palette.accent,width:2};charts[0].series.items[1].line={fill:'#FFD166',width:2,style:'dashed'};
charts[1].series.items[0].fill=palette.accent;
val(dash,'B43','مراجعة أكبر ٨ أصناف بالكمية');
dash.getRange('B44:H44').values=[['الكود','الملف','Flow','الفرق','الصلاحية','طبقات','المطابقة']];
for(let i=0;i<top.length;i++) {
 const r=45+i, item=top[i].item, rr=recStart+d.reconciliation.findIndex(x=>x.item===item);
 val(dash,`B${r}`,item);formula(dash,`C${r}`,`='مطابقة الافتتاحي'!D${rr}`);formula(dash,`D${r}`,`='مطابقة الافتتاحي'!G${rr}`);formula(dash,`E${r}`,`=C${r}-D${r}`);
 formula(dash,`F${r}`,`=IF(COUNTIFS(${O('C')},B${r},${O('F')},"<>")=COUNTIFS(${O('C')},B${r}),"موجودة","غير مكتملة")`);
 formula(dash,`G${r}`,`=COUNTIFS(${O('C')},B${r})`);formula(dash,`H${r}`,`=IF(E${r}=0,"مطابق","فرق")`);
}
dash.getRange('B45:H52').setNumberFormat('#,##0');dash.getRange('B45:B52').setNumberFormat('@');dash.getRange('B45:H52').format.font.color=palette.text;
dash.getRange('B45:H52').format.fill=palette.panel;
dash.getRange('E45:E52').conditionalFormats.add('cellIs',{operator:'notEqual',formula:0,format:{fill:'#7F1D1D',font:{color:'#FFFFFF',bold:true}}});
val(dash,'J45','المطابقة تشمل كل صنف، بما فيه الأصناف ذات الرصيد صفر. تكلفة الصنف ١٣٦ محفوظة بصفر كما وردت. جرد فبراير واختلاف صلاحية الكود ٧٠ سيُراجعان في المرحلة الثالثة.');
val(dash,'J50','حركات يناير وفبراير وتكلفتها لم تدخل بعد. الانتقال للمرحلة الثانية بعد اعتماد الافتتاحي.');
dash.getRange('J45:Q52').format.wrapText=true;
dash.getRange('J45:Q52').format.font={name:'Arial',size:11,color:palette.muted};
dash.getRange('B44:H52').format.rowHeight=25;

// Exercise dependent recalculation, then restore the exact source values.
val(op,'G16',426);wb.recalculate();
assert.equal(h.getRange('B4').values[0][0],d.totals.value+203);
val(op,'G16',425);val(op,'E16',202);wb.recalculate();
assert.equal(h.getRange('B3').values[0][0],11346);
assert.equal(h.getRange('B9').values[0][0],1);
val(op,'E16',203);
wb.recalculate();
// Verify computed outputs and every item reconciliation independently.
const metrics=h.getRange('B2:B9').values.map(r=>r[0]);
assert.deepEqual(metrics,[41,11347,6592366.54,43,31,12,1,0]);
assert(rec.getRange(`H${recStart}:H${recEnd}`).values.every(r=>r[0]===0));
assert.equal(op.getRange(`H${ot}`).values[0][0],d.totals.value);
assert.equal(op.getRange(`E${ot}`).values[0][0],d.totals.quantity);
const errors=await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:20},summary:'Final formula error scan'});
console.log('ERROR_SCAN',errors.ndjson);
console.log('METRICS',JSON.stringify(metrics));
await fs.writeFile(dir+'workbook_checks.json',JSON.stringify({metrics,reconciliation_rows:d.reconciliation.length,all_differences_zero:true,formula_errors:errors.ndjson},null,2));
for(const [sheetName,range,file] of [['Dashboard','A1:R53','dashboard'],['Data & Targets','B2:P26','opening_top'],['Data & Targets','B45:K60','opening_bottom'],['مطابقة الافتتاحي','B2:J22','reconciliation_top'],['مطابقة الافتتاحي',`B${recEnd-10}:J${recEnd+4}`,'reconciliation_bottom']]) {
 const p=await wb.render({sheetName,range,scale:1,format:'png'}); await fs.writeFile(dir+file+'.png',new Uint8Array(await p.arrayBuffer()));
}
const xlsx=await SpreadsheetFile.exportXlsx(wb);await xlsx.save(dir+'CMC_Mokattam1.xlsx');
console.log('EXPORTED',dir+'CMC_Mokattam1.xlsx');
