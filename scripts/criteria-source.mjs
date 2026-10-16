import { readFile, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
const pdf = new URL('../public/data/criteria_v2_2026-10.pdf',import.meta.url);
const manifest = new URL('../fixtures/criteria-source.json',import.meta.url);
const sha256=createHash('sha256').update(await readFile(pdf)).digest('hex');
if(process.argv.includes('--refresh')){
 const content=execFileSync('pdftotext',[pdf.pathname,'-'],{encoding:'utf8'});
 const codes=[...new Set(content.match(/[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+/g)??[])].sort();
 if(!codes.length)throw new Error('No rule codes found in criteria PDF');
 await writeFile(manifest,JSON.stringify({sha256,codes},null,2)+'\n');
 console.log(`Criteria source index refreshed: ${codes.length} codes`);
}else{
 const index=JSON.parse(await readFile(manifest,'utf8'));
 if(index.sha256!==sha256||!index.codes.length)throw new Error('Criteria PDF changed. Run node scripts/criteria-source.mjs --refresh');
 console.log(`Criteria source hash verified: ${index.codes.length} codes`);
}
