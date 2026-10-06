import fs from 'node:fs/promises';
import {FileBlob,SpreadsheetFile} from '@oai/artifact-tool';
const dir=decodeURIComponent(new URL('.',import.meta.url).pathname);
const path='/Users/user/.codex/plugins/cache/openai-curated-remote/openai-templates/0.1.1/skills/artifact-template-analytics-dashboard/assets/reference.xlsx';
const wb=await SpreadsheetFile.importXlsx(await FileBlob.load(path));
console.log((await wb.inspect({kind:'workbook,sheet,table,drawing',maxChars:7000,tableMaxRows:3,tableMaxCols:5})).ndjson);
for(const name of ['Dashboard','Data & Targets','_Chart Helpers']) {
 const s=wb.worksheets.getItem(name);
 const r=s.getUsedRange();
 await fs.writeFile(dir+name.replaceAll(' ','_')+'.json',JSON.stringify({values:r.values,formulas:r.formulas},null,2));
}
const preview=await wb.render({sheetName:'Dashboard',range:'A1:R53',scale:1,format:'png'});
await fs.writeFile(dir+'template.png',new Uint8Array(await preview.arrayBuffer()));
