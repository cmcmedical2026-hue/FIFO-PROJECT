import fs from "node:fs/promises";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const root = "/Users/user/FIFIo project";
const outputDir = `${root}/outputs/physical-count-2026-09-30-20261004`;
const catalog = JSON.parse(await fs.readFile(`${root}/Integration FLOW/data/inventory/lot_catalog.json`, "utf8"));
const lastCount = JSON.parse(await fs.readFile(`${root}/Integration FLOW/data/inventory/count_2026-08-31.json`, "utf8"));
const openingCsv = await fs.readFile(`${root}/Source file/Opening balance 2026.csv`, "utf8");
const names = new Map();
for (const line of openingCsv.replaceAll("\r", "").split("\n").slice(1)) {
  const cells = line.split(",");
  if (cells.length >= 2 && cells[0] && cells[1]) names.set(cells[0].trim(), cells[1].trim());
}

const current = new Set(lastCount.lines.map(([item, lot]) => `${item}\u0000${lot}`));
const entries = [];
for (const [item, lots] of Object.entries(catalog.items)) {
  for (const [lot, expiry] of Object.entries(lots)) {
    entries.push({ item, lot, expiry, source: current.has(`${item}\u0000${lot}`) ? "جرد ٣١ أغسطس" : "لوط معروف سابقًا" });
  }
}
const cmp = (a, b) => {
  const an = /^\d+$/.test(a.item), bn = /^\d+$/.test(b.item);
  if (an && bn && Number(a.item) !== Number(b.item)) return Number(a.item) - Number(b.item);
  if (an !== bn) return an ? -1 : 1;
  const c = a.item.localeCompare(b.item, "en", { numeric: true });
  if (c) return c;
  if (a.source !== b.source) return a.source === "جرد ٣١ أغسطس" ? -1 : 1;
  return a.lot.localeCompare(b.lot, "en", { numeric: true });
};
entries.sort(cmp);

const workbook = Workbook.create();
const sheet = workbook.worksheets.add("جرد 30-09-2026");
sheet.showGridLines = false;
sheet.tabColor = "#1E4C72";
sheet.getRange("A1:J104").format.font = { name: "Arial", size: 10, color: "#243342" };
sheet.getRange("A1:J104").format.verticalAlignment = "center";
sheet.getRange("A:A").format.columnWidth = 5;
sheet.getRange("B:B").format.columnWidth = 16;
sheet.getRange("C:C").format.columnWidth = 51;
sheet.getRange("D:D").format.columnWidth = 22;
sheet.getRange("E:E").format.columnWidth = 25;
sheet.getRange("F:F").format.columnWidth = 17;
sheet.getRange("G:H").format.columnWidth = 18;
sheet.getRange("I:I").format.columnWidth = 35;
sheet.getRange("J:J").format.columnWidth = 21;

sheet.getRange("B2").values = [["تقرير الجرد الفعلي — ٣٠ سبتمبر ٢٠٢٦"]];
sheet.getRange("B2").format.font = { name: "Arial", size: 15, bold: true, color: "#163A59" };
sheet.getRange("B2:J2").format.rowHeight = 31;
sheet.getRange("B3").values = [["مخزن المقطم ١ | الشركة ١ | العد على مستوى الصنف واللوط"]];
sheet.getRange("B3").format.font = { name: "Arial", size: 10, italic: true, color: "#536576" };
sheet.getRange("B4:J4").format.borders = { bottom: { style: "thin", color: "#9EB4C5" } };

sheet.getRange("B5").values = [["بداية الجرد:"]];
sheet.getRange("D5").values = [["نهاية الجرد:"]];
sheet.getRange("F5").values = [["المسؤول:"]];
sheet.getRange("H5").values = [["مكان الجرد:"]];
for (const cell of ["C5", "E5", "G5", "I5"]) {
  const r = sheet.getRange(cell);
  r.format.fill = "#FFF2C6";
  r.format.borders = { bottom: { style: "thin", color: "#C8A94D" } };
}
sheet.getRange("B6").values = [["اكتب صفرًا إذا عُدّ اللوط وتأكدت من عدم وجوده؛ اترك الكمية فارغة إذا لم يُجرد."]];
sheet.getRange("B7").values = [["راجع الاسم واللوط والصلاحية على العبوة، وسجل أي صنف أو لوط جديد في الصفوف الفارغة أسفل القائمة."]];
sheet.getRange("B8").values = [["المرجع: جرد ٣١-٠٨-٢٠٢٦ المصحح وكتالوج اللوطات بالمشروع؛ لا تُعرض كميات سابقة في هذا الملف."]];
sheet.getRange("B6:B8").format.font = { name: "Arial", size: 9, color: "#526171" };
sheet.getRange("B6:J8").format.rowHeight = 19;

const headers = ["م", "كود الصنف", "اسم الصنف", "رقم اللوط", "الصلاحية كما على العبوة", "المكان / الرف", "الكمية الفعلية", "منها تالف / منتهي", "ملاحظات الجرد", "مرجع السطر"];
sheet.getRange("A9:J9").values = [headers];
sheet.getRange("A9:J9").format = {
  fill: "#173F5F",
  font: { name: "Arial", size: 10, bold: true, color: "#FFFFFF" },
  rowHeight: 29,
  horizontalAlignment: "center",
  verticalAlignment: "center",
};

const blankExtra = 30;
const data = entries.map((entry, i) => {
  let note = "";
  if (entry.item === "75") note = "أكد توزيع الموجود بين اللوطين.";
  if (entry.item === "144" && entry.lot === "20241213031") note = "راجع وجود اللوط القديم؛ عليه فرق سابق.";
  if (entry.item === "108") note = "راجع رقم اللوط المطبوع على العبوة.";
  return [i + 1, entry.item, names.get(entry.item) ?? "", entry.lot, entry.expiry || "", "", null, null, note, entry.source];
});
for (let i = 0; i < blankExtra; i++) data.push([entries.length + i + 1, "", "", "", "", "", null, null, "", "صنف / لوط إضافي"]);
const lastRow = 9 + data.length;
sheet.getRange(`A10:J${lastRow}`).values = data;
sheet.getRange(`A10:J${lastRow}`).format.rowHeight = 23;
sheet.getRange(`A10:J${lastRow}`).format.borders = { insideHorizontal: { style: "thin", color: "#E6ECF0" } };
sheet.getRange(`A10:A${lastRow}`).format.horizontalAlignment = "center";
sheet.getRange(`G10:H${lastRow}`).setNumberFormat("#,##0.##");
sheet.getRange(`G10:H${lastRow}`).format.fill = "#FFF2C6";
sheet.getRange(`F10:F${lastRow}`).format.fill = "#FFF9E8";
sheet.getRange(`I10:I${lastRow}`).format.fill = "#FFF9E8";
sheet.getRange(`D10:E${lastRow}`).format.fill = "#F5F8FA";
sheet.getRange(`J10:J${lastRow}`).format.font = { name: "Arial", size: 9, color: "#647587" };
const firstExtra = 10 + entries.length;
for (let i = 0; i < entries.length; i++) {
  if (!names.has(entries[i].item)) sheet.getRange(`C${10 + i}`).format.fill = "#FFF2C6";
}
sheet.getRange(`A${firstExtra}:J${lastRow}`).format.fill = "#FFF9E8";
sheet.getRange(`G${firstExtra}:H${lastRow}`).format.fill = "#FFF2C6";
sheet.getRange(`A${firstExtra}:J${firstExtra}`).format.borders = { top: { style: "medium", color: "#9EB4C5" } };
sheet.freezePanes.freezeRows(9);

workbook.recalculate();
const preview = await workbook.render({ sheetName: sheet.name, range: "A1:J17", scale: 1.4, format: "png" });
await fs.writeFile(`${outputDir}/preview.png`, new Uint8Array(await preview.arrayBuffer()));
const check = await workbook.inspect({ kind: "table", range: `A9:J14`, include: "values", tableMaxRows: 6, tableMaxCols: 10 });
console.log(check.ndjson);
const errors = await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!", options: { useRegex: true, maxResults: 20 } });
console.log(errors.ndjson);
const xlsx = await SpreadsheetFile.exportXlsx(workbook);
const finalPath = `${outputDir}/تقرير_الجرد_الفعلي_30-09-2026.xlsx`;
await xlsx.save(finalPath);
console.log(JSON.stringify({ finalPath, knownLots: entries.length, extraRows: blankExtra, lastRow }));
