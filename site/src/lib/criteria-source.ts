import index from '../../fixtures/criteria-source.json';
import sourceTable from '../../fixtures/criteria-source-table.json';
import { ServiceError } from './validation';
export async function sha256(bytes: Uint8Array) { return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes as BufferSource)), x => x.toString(16).padStart(2, '0')).join(''); }
export async function criteria_source_codes(pdf:Uint8Array):Promise<Set<string>>{
 // The index is extracted directly from this fixed PDF at build preparation.
 if(await sha256(pdf)!==index.sha256)throw new ServiceError('기준서 PDF가 변경되었습니다. 원문 규칙 코드 색인을 갱신해 주세요.');
 return new Set(index.codes);
}

export async function criteria_source_table(pdf:Uint8Array):Promise<Record<string,Record<string,string>>>{
 // Only repair values against the exact PDF used to generate this table.
 return await sha256(pdf)===sourceTable.sha256 ? sourceTable.table : {};
}
