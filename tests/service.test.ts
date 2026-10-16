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
 it.each([['1','safe'],['2','check_needed'],['3','risky'],['4','safe']])('sample %s produces %s',async(sample_id,level)=>{const steps:number[]=[];const r=await run_review_service({sample_id},{config,asset,use_recorded:false,progress:s=>steps.push(s)});expect(r.final_level).toBe(level);expect(r.mode).toBe('demo');expect(r.agent_level).toBeNull();expect(r.source).toBe('rules');expect(r.review_pdf_base64).toBeTruthy();expect(steps).toEqual([1,2,3,4,5]);});
 it.each([['2','risky'],['3','risky']])('FORCE_DEMO replays recorded sample %s without network',async(sample_id,level)=>{const forced=settings({...Object.fromEntries(SECRET_NAMES.map(k=>[k,'test'])),FORCE_DEMO:'1'});expect(is_live_ready(forced)).toBe(false);const r=await run_review_service({sample_id},{config:forced,asset,fetch:async()=>{throw Error('Unexpected network');}});expect(r.mode).toBe('demo');expect(r.source).toBe('recorded');expect(r.agent_level).toBe(level);expect(r.final_level).toBe(level);expect(r.review).toMatchObject({classify_level:null,schema_level:level});});
 it('cache key changes for document, agent and config changes',async()=>{const bytes=new Uint8Array([1]);const key=await criteria_cache_key(bytes,config);expect(await criteria_cache_key(bytes,config)).toBe(key);for(const alt of [{bytes:new Uint8Array([2]),config},{bytes,config:{...config,CRITERIA_AGENT_ID:'changed'}},{bytes,config:{...config,CRITERIA_CONFIG_ID:'changed'}}])expect(await criteria_cache_key(alt.bytes,alt.config)).not.toBe(key);});
});
describe('PDF validation',()=>{
 it('rejects empty, oversize, false signatures and corrupt files',async()=>{for(const bytes of [new Uint8Array(),new Uint8Array(MAX_BYTES+1),new TextEncoder().encode('not a PDF'),new TextEncoder().encode('%PDF-broken')])await expect(validate_pdf(bytes)).rejects.toThrow();});
 it('accepts samples and enforces 1 to 20 pages',async()=>{await expect(validate_pdf(await asset('/data/samples/sample1.pdf'))).resolves.toBeUndefined();for(const count of [0,20,21]){const pdf=await PDFDocument.create();for(let i=0;i<count;i++)pdf.addPage();const bytes=await pdf.save({addDefaultPage:false});if(count===20)await expect(validate_pdf(bytes)).resolves.toBeUndefined();else await expect(validate_pdf(bytes)).rejects.toThrow('1~20');}});
});

describe('live service assembly with mocked Upstage',()=>{
 it.each([true,false])('accepts review_level without Classify; present=%s',async classified=>{
  const contract=JSON.parse(await readFile('fixtures/expected/contract_sample1.json','utf8'));
  const criteria=JSON.parse(await readFile('fixtures/expected/criteria.json','utf8'));
  const fake=settings(Object.fromEntries(SECRET_NAMES.map(k=>[k,k])));
  const created:string[]=[];let current='';let uploads=0;
  const fakeFetch:typeof fetch=async(url,options)=>{
   if(String(url).endsWith('/files')){uploads++;expect((options!.body as FormData).get('purpose')).toBe('user_data');return Response.json({id:'file-test'});}
   if(options?.method==='POST'){
    const body=JSON.parse(String(options.body));expect(body.include).toEqual(['last']);expect(body.input[0].content[0].file_id).toBe('file-test');
    current=body.model;created.push(current);return Response.json({id:'job-test'});
   }
   const output=current==='CONTRACT_AGENT_ID'?contract:current==='CRITERIA_AGENT_ID'?criteria:classified?{review_level:'safe',summary:'원문 요약'}:{summary:'분류를 읽지 못했습니다'};
   return Response.json({status:'completed',output_text:JSON.stringify(output)});
  };
  const r=await run_review_service({sample_id:'1'},{config:fake,asset,fetch:fakeFetch});
  expect(created).toEqual(['CONTRACT_AGENT_ID','CRITERIA_AGENT_ID','REVIEW_AGENT_ID']);expect(uploads).toBe(3);
  expect(r.mode).toBe('live');expect(r.final_level).toBe('safe');
  expect(r.source).toBe(classified?'agent':'agent_unclassified');
  expect(r.cross_check.status).toBe(classified?'match':'unavailable');
  expect(r.review).toMatchObject({classify_level:null,schema_level:classified?'safe':null});
 });
});
