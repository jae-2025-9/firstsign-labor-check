import {describe,it,expect} from 'vitest';
import {readFile} from 'node:fs/promises';
import {PDFDocument} from 'pdf-lib';
import {run_review_service,criteria_cache_key} from '../src/lib/service';
import {settings,is_live_ready,SECRET_NAMES} from '../src/lib/settings';
import {validate_pdf,MAX_BYTES} from '../src/lib/validation';
const config=settings({});
const asset=async(path:string)=>new Uint8Array(await readFile(`public${path}`));
describe('service boundary',()=>{
 it('requires all seven runtime secrets',()=>{expect(is_live_ready(config)).toBe(false);const full=Object.fromEntries(SECRET_NAMES.map(k=>[k,'test']));expect(is_live_ready(settings(full))).toBe(true);for(const key of SECRET_NAMES){expect(is_live_ready(settings({...full,[key]:''}))).toBe(false);}});
 it('rejects upload in demo before asset or agent calls',async()=>{await expect(run_review_service({pdf_bytes:new Uint8Array([1])},{config,asset})).rejects.toThrow('데모');});
 it('rejects missing, ambiguous and unknown input',async()=>{for(const input of [{},{sample_id:'5'},{sample_id:'1',pdf_bytes:new Uint8Array()}]) await expect(run_review_service(input,{config,asset})).rejects.toThrow();});
 it.each([['1','safe'],['2','check_needed'],['3','risky'],['4','safe']])('sample %s produces %s',async(sample_id,level)=>{const steps:number[]=[];const r=await run_review_service({sample_id},{config,asset,progress:s=>steps.push(s)});expect(r.final_level).toBe(level);expect(r.mode).toBe('demo');expect(r.agent_level).toBeNull();expect(r.source).toBe('rules');expect(r.review_pdf_base64).toBeTruthy();expect(steps).toEqual([1,2,3,4,5]);});
 it('cache key changes for document, agent and config changes',async()=>{const bytes=new Uint8Array([1]);const key=await criteria_cache_key(bytes,config);expect(await criteria_cache_key(bytes,config)).toBe(key);for(const alt of [{bytes:new Uint8Array([2]),config},{bytes,config:{...config,CRITERIA_AGENT_ID:'changed'}},{bytes,config:{...config,CRITERIA_CONFIG_ID:'changed'}}])expect(await criteria_cache_key(alt.bytes,alt.config)).not.toBe(key);});
});
describe('PDF validation',()=>{
 it('rejects empty, oversize, false signatures and corrupt files',async()=>{for(const bytes of [new Uint8Array(),new Uint8Array(MAX_BYTES+1),new TextEncoder().encode('not a PDF'),new TextEncoder().encode('%PDF-broken')])await expect(validate_pdf(bytes)).rejects.toThrow();});
 it('accepts samples and enforces 1 to 20 pages',async()=>{await expect(validate_pdf(await asset('/data/samples/sample1.pdf'))).resolves.toBeUndefined();for(const count of [0,20,21]){const pdf=await PDFDocument.create();for(let i=0;i<count;i++)pdf.addPage();const bytes=await pdf.save({addDefaultPage:false});if(count===20)await expect(validate_pdf(bytes)).resolves.toBeUndefined();else await expect(validate_pdf(bytes)).rejects.toThrow('1~20');}});
});
