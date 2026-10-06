import fs from 'node:fs/promises';
import { Workbook, SpreadsheetFile } from '@oai/artifact-tool';

const root = '/Users/user/FIFIo project';
const outputDir = `${root}/outputs/sap-count-sheet-20261005`;
const catalog = JSON.parse(await fs.readFile(`${root}/Integration FLOW/data/inventory/lot_catalog.json`, 'utf8'));
const openingCsv = await fs.readFile(`${root}/Source file/Opening balance 2026.csv`, 'utf8');
const names = new Map();
for (const line of openingCsv.replaceAll('\r', '').split('\n').slice(1)) {
  const cells = line.split(',');
  if (cells.length >= 2 && cells[0]?.trim() && cells[1]?.trim()) {
    names.set(cells[0].trim(), cells[1].trim());
  }
}

const entries = [];
for (const [item, lots] of Object.entries(catalog.items)) {
  for (const [lot, expiry] of Object.entries(lots)) entries.push({ item, lot, expiry });
}
entries.sort((a, b) =>
  a.item.localeCompare(b.item, 'en', { numeric: true }) ||
  a.lot.localeCompare(b.lot, 'en', { numeric: true }));

function expiryValue(raw) {
  const m = /^(\d{1,2})-(\d{1,2})-(\d{4})$/.exec(raw ?? '');
  if (!m) return raw || '';
  const day = Number(m[1]), month = Number(m[2]), year = Number(m[3]);
  const date = new Date(Date.UTC(year, month - 1, day));
  return date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day ? date : raw;
}

const workbook = Workbook.create();
const sheet = workbook.worksheets.add('ورقة الجرد');
sheet.showGridLines = false;
sheet.tabColor = '#5A626A';
const lastRow = 108;
const body = sheet.getRange(`A1:I${lastRow}`);
body.format.font = { name: 'Arial', size: 10, color: '#222B35' };
body.format.verticalAlignment = 'center';

const widths = { A: 15, B: 22, C: 19, D: 16, E: 12, F: 18, G: 48, H: 23, I: 20 };
for (const [col, width] of Object.entries(widths)) sheet.getRange(`${col}:${col}`).format.columnWidth = width;

sheet.getRange('A2').values = [['ورقة الجرد الفعلي  |  Physical Inventory Count Sheet']];
sheet.getRange('A2').format.font = { name: 'Arial', size: 15, bold: true, color: '#2D3742' };
sheet.getRange('A2:I2').format.rowHeight = 33;
sheet.getRange('A3:I3').format.borders = { bottom: { style: 'thin', color: '#B7BEC5' } };

sheet.getRange('A4').values = [['كود المخزن']];
sheet.getRange('D4').values = [['اسم المخزن']];
sheet.getRange('G4').values = [['تاريخ الجرد']];
sheet.getRange('A5').values = [['الشركة']];
sheet.getRange('D5').values = [['القائم بالعد']];
sheet.getRange('G5').values = [['وقت العد']];
for (const cell of ['B4', 'E4', 'H4', 'B5', 'E5', 'H5']) {
  const r = sheet.getRange(cell);
  r.format.fill = '#FFF2CF';
  r.format.borders = { bottom: { style: 'thin', color: '#C89A3C' } };
}
sheet.getRange('H4').setNumberFormat('dd-mm-yyyy');
sheet.getRange('A4:I5').format.rowHeight = 27;

sheet.getRange('A6').values = [['اكتب الكمية المعدودة بعد العد فقط؛ اترك الخانة فارغة إذا لم يُجرد السطر.']];
sheet.getRange('A7').values = [['الأصناف واللوطات المبدئية من كتالوج المشروع؛ راجع رقم اللوط والصلاحية على العبوة، وأضف أي لوط جديد في الصفوف الفارغة.']];
sheet.getRange('A6:A7').format.font = { name: 'Arial', size: 9, color: '#57636E' };
sheet.getRange('A6:I7').format.rowHeight = 22;

sheet.getRange('A8:I8').values = [[
  'Store Code\nكود المخزن', 'Store Name\nاسم المخزن', 'S/L Batch\nدفعة النظام',
  'Counted\nالمعدود', 'UOM\nالوحدة', 'Item Code\nكود الصنف',
  'Item Description\nاسم الصنف', 'LOT No\nرقم اللوط', 'Expiry Date\nالصلاحية'
]];
sheet.getRange('A8:I8').format = {
  fill: '#59636D',
  font: { name: 'Arial', size: 10, bold: true, color: '#FFFFFF' },
  rowHeight: 38,
  horizontalAlignment: 'center',
  verticalAlignment: 'center',
  wrapText: true,
};
sheet.getRange('A8:I8').format.borders = { insideVertical: { style: 'thin', color: '#DBE0E4' } };

const rows = entries.map(e => [null, null, '', null, '', e.item, names.get(e.item) ?? '', e.lot, expiryValue(e.expiry)]);
while (rows.length < 100) rows.push([null, null, '', null, '', '', '', '', '']);
sheet.getRange(`A9:I${lastRow}`).values = rows;
sheet.getRange(`A9:I${lastRow}`).format.rowHeight = 24;
sheet.getRange(`A9:I${lastRow}`).format.borders = { insideHorizontal: { style: 'thin', color: '#E2E6E9' } };
sheet.getRange(`A9`).formulas = [['=IF($B$4="","",$B$4)']];
sheet.getRange(`A9:A${lastRow}`).fillDown();
sheet.getRange(`B9`).formulas = [['=IF($E$4="","",$E$4)']];
sheet.getRange(`B9:B${lastRow}`).fillDown();
sheet.getRange(`D9:D${lastRow}`).format.fill = '#FFF2CF';
sheet.getRange(`C9:C${lastRow}`).format.fill = '#FFF9E8';
sheet.getRange(`E9:E${lastRow}`).format.fill = '#FFF9E8';
sheet.getRange(`D9:D${lastRow}`).setNumberFormat('#,##0.##');
sheet.getRange(`I9:I${lastRow}`).setNumberFormat('dd-mm-yyyy');
sheet.getRange(`A9:F${lastRow}`).format.horizontalAlignment = 'center';
sheet.getRange(`H9:I${lastRow}`).format.horizontalAlignment = 'center';
sheet.getRange(`F9:F${lastRow}`).setNumberFormat('@');
sheet.getRange(`H9:H${lastRow}`).setNumberFormat('@');

const firstExtra = 9 + entries.length;
sheet.getRange(`A${firstExtra}:I${firstExtra}`).format.borders = { top: { style: 'medium', color: '#B7BEC5' } };
sheet.getRange(`F${firstExtra}:I${lastRow}`).format.fill = '#FFF9E8';
for (let i = 0; i < entries.length; i++) {
  if (!names.has(entries[i].item)) sheet.getRange(`G${9 + i}`).format.fill = '#FFF2CF';
}
sheet.freezePanes.freezeRows(8);

workbook.recalculate();
const inspected = await workbook.inspect({ kind: 'table', range: 'A8:I13', include: 'values,formulas', tableMaxRows: 6, tableMaxCols: 9 });
console.log(inspected.ndjson);
const errors = await workbook.inspect({ kind: 'match', searchTerm: '#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!', options: { useRegex: true, maxResults: 20 } });
console.log(errors.ndjson);
const preview = await workbook.render({ sheetName: sheet.name, range: 'A1:I14', scale: 1.3, format: 'png' });
await fs.writeFile(`${outputDir}/preview.png`, new Uint8Array(await preview.arrayBuffer()));
const output = await SpreadsheetFile.exportXlsx(workbook);
const finalPath = `${outputDir}/ورقة_جرد_بنمط_SAP.xlsx`;
await output.save(finalPath);
console.log(JSON.stringify({ finalPath, knownLots: entries.length, blankRows: 100 - entries.length }));
