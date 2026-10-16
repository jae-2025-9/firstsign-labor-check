import {describe,it,expect,vi,afterEach} from 'vitest';
import {readFile} from 'node:fs/promises';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {AgentError} from '../src/lib/agent-client';
import {review_stream,STREAM_CHUNK_BYTES} from '../src/lib/review-stream';
import {cached_criteria} from '../src/lib/criteria-cache';
import {criteria_source_codes,criteria_source_table} from '../src/lib/criteria-source';
import {CrossCheckNotice,IncompleteNotice,DisputedNotice,CriteriaRepairNotice,RequestsMissingNotice} from '../src/components/ReviewStatus';
import {evaluate,engine_review,cross_check,final_view,type CrossCheck} from '../src/lib/rules';
import contract from '../fixtures/expected/contract_sample1.json';
import criteria from '../fixtures/expected/criteria.json';

afterEach(()=>vi.useRealTimers());
describe('stream lifetime',()=>{
 it('sends heartbeats throughout a 421-second review and then returns the result',async()=>{
  vi.useFakeTimers();let finish!:(value:{level:string})=>void;
  const result=new Promise<{level:string}>(resolve=>{finish=resolve;});
  const stream=review_stream(async progress=>{progress(4,'평가 대기');return result;});
  const consumed=new Response(stream).text();
  await vi.advanceTimersByTimeAsync(421000);finish({level:'safe'});
  const events=(await consumed).trim().split('\n').map(s=>JSON.parse(s));
  expect(events.filter(e=>e.type==='heartbeat')).toHaveLength(29);
  expect(events.at(-1)).toEqual({type:'result',result:{level:'safe'}});
  expect(vi.getTimerCount()).toBe(0);
 });
 it('transmits large Korean result events in bounded chunks without data loss',async()=>{
  const result={text:'한글 결과'.repeat(150000)};
  const reader=review_stream(async()=>result).getReader();const decoder=new TextDecoder();let body='';let chunks=0;
  while(true){const {done,value}=await reader.read();if(done)break;expect(value.byteLength).toBeLessThanOrEqual(STREAM_CHUNK_BYTES);body+=decoder.decode(value,{stream:true});chunks++;}
  body+=decoder.decode();expect(chunks).toBeGreaterThan(10);
  expect(JSON.parse(body.trim().split('\n').at(-1)!)).toEqual({type:'result',result});
 });
 it('does not expose unexpected exception details',async()=>{
  const body=await new Response(review_stream(async()=>{throw Error('private-document-body');})).text();
  expect(body).not.toContain('private-document-body');expect(body).toContain('점검 중 오류');
 });
});
function memoryBucket(){
 const values=new Map<string,{body:string;etag:string}>();let revision=0;
 return {values,bucket:{
  async get(key:string){const item=values.get(key);return item?{etag:item.etag,json:async()=>JSON.parse(item.body)}:null;},
  async put(key:string,body:string,options?:{onlyIf?:{etagMatches?:string;etagDoesNotMatch?:string}}){
   const current=values.get(key),condition=options?.onlyIf;
   if(condition?.etagDoesNotMatch==='*'&&current)return null;
   if(condition?.etagMatches&&current?.etag!==condition.etagMatches)return null;
   const item={body,etag:String(++revision)};values.set(key,item);return {etag:item.etag};
  }
 } as unknown as R2Bucket};
}
describe('persistent criteria and source validation',()=>{
 it('checks the PDF hash and reads its seven original rule codes',async()=>{
  const bytes=new Uint8Array(await readFile('public/data/criteria_v2_2026-10.pdf'));
  expect((await criteria_source_codes(bytes)).size).toBe(7);
  await expect(criteria_source_codes(bytes.slice(1))).rejects.toThrow('기준서');
 });
 it('coalesces concurrent extraction and reuses the validated R2 result',async()=>{
  const {bucket,values}=memoryBucket();const extract=vi.fn(async()=>({valid:'yes'}));
  const [a,b]=await Promise.all([cached_criteria('one',bucket,d=>d.valid==='yes',extract),cached_criteria('one',bucket,d=>d.valid==='yes',extract)]);
  expect(a).toEqual(b);expect(extract).toHaveBeenCalledTimes(1);
  await cached_criteria('one',bucket,d=>d.valid==='yes',extract);expect(extract).toHaveBeenCalledTimes(1);
  expect(JSON.parse(values.get('one.lease')!.body).expires).toBe(0);
  await cached_criteria('one',bucket,()=>false,extract);expect(extract).toHaveBeenCalledTimes(2);
 });
 it('releases the lease after extraction fails',async()=>{
  const {bucket,values}=memoryBucket();await expect(cached_criteria('failed',bucket,()=>true,async()=>{throw Error('failure');})).rejects.toThrow('failure');
  expect(JSON.parse(values.get('failed.lease')!.body).expires).toBe(0);
  expect(values.has('failed')).toBe(false);
 });
});
describe('result status rendering',()=>{
 const engine=evaluate(contract,criteria),review=engine_review(engine);
 const check=cross_check('safe',[],engine);
 it.each([['match','교차 검증 일치'],['mismatch','교차 검증 결과가 다릅니다'],['partial','교차 검증 일부만 완료'],['unavailable','교차 검증은 하지 못했습니다']])('renders %s distinctly', (status,label)=>{
  const html=renderToStaticMarkup(createElement(CrossCheckNotice,{source:'recorded',check:{...check,status:status as CrossCheck['status'],undetermined:['BREAK_TIME']},review}));
  expect(html).toContain(label);if(status!=='match')expect(html).not.toContain('교차 검증 일치');
 });
 it('escapes document-derived rule text',()=>{
  const html=renderToStaticMarkup(createElement(CrossCheckNotice,{source:'agent',check:{...check,status:'partial',undetermined:['<img src=x onerror=alert(1)>']},review}));
  expect(html).toContain('&lt;img');expect(html).not.toContain('<img');
 });
 it('shows the level as a floor when incomplete',()=>{
  const final={...final_view(review,engine,'safe',check),level:'risky' as const,incomplete:true};
  expect(renderToStaticMarkup(createElement(IncompleteNotice,{final,engine}))).toContain('최소');
 });
});


describe('source repair and disputed rendering',()=>{
 it('does not apply a table to another PDF',async()=>{
  const bytes=new Uint8Array(await readFile('public/data/criteria_v2_2026-10.pdf'));
  expect(Object.keys(await criteria_source_table(bytes))).toHaveLength(7);
  expect(await criteria_source_table(bytes.slice(1))).toEqual({});
 });
 it('keeps disputed agent flags separate from the grade and escapes their text',()=>{
  const engine=evaluate(contract,criteria),review={...engine_review(engine),matched_rules:['LABOR_SIGN_COPY'],recommendations:['사본을 주세요.']};
  const check=cross_check('safe',review.matched_rules,engine),final=final_view(review,engine,'safe',check);
  expect(final.level).toBe('safe');expect(final.requests).toEqual([]);expect(final.cards).toEqual([]);
  expect(final.disputed).toHaveLength(1);
  const html=renderToStaticMarkup(createElement(DisputedNotice,{disputed:final.disputed.map(x=>({...x,reason:'<script>alert(1)</script>'}))}));
  expect(html).toContain('의견 차이 (1건) · 등급에 넣지 않음');expect(html).toContain('&lt;script&gt;');expect(html).not.toContain('<script>');
  const notice=renderToStaticMarkup(createElement(CrossCheckNotice,{source:'recorded',check,review,disputed:final.disputed}));
  expect(notice).toContain('최종 등급은 지적한 규칙의 기준서 분류로 정했고');expect(notice).toContain('의견 차이');expect(notice).not.toContain('더 엄격한 등급과');
 });
 it('explains repaired criteria in details and hides empty notices',()=>{
  expect(renderToStaticMarkup(createElement(CriteriaRepairNotice,{codes:['LABOR_MIN_WAGE_NEXT']}))).toContain('PDF 원문 표로 바로잡았습니다.');
  expect(renderToStaticMarkup(createElement(CriteriaRepairNotice,{codes:[]}))).toBe('');
  expect(renderToStaticMarkup(createElement(DisputedNotice,{disputed:[]}))).toBe('');
 });
});


it('shows uncovered request titles safely and hides the empty notice',()=>{
 const html=renderToStaticMarkup(createElement(RequestsMissingNotice,{titles:['다음 해 최저임금 미달 예정','<script>test</script>']}));
 expect(html).toContain('메시지에 빠진 지적:');expect(html).toContain('다음 해 최저임금 미달 예정');expect(html).toContain('&lt;script&gt;');expect(html).not.toContain('<script>');
 expect(renderToStaticMarkup(createElement(RequestsMissingNotice,{titles:[]}))).toBe('');
});

it('delivers safe Studio diagnostics through the error stream',async()=>{
 const message='에이전트 실행에 실패했습니다. [Studio: model_request_error] Model failed (Job 시도 3/3, 재시도 2회)';
 const body=await new Response(review_stream(async()=>{throw new AgentError(message);})).text();
 const events=body.trim().split('\n').map(line=>JSON.parse(line));
 expect(events.at(-1)).toEqual({type:'error',error:message});expect(events.some(event=>event.type==='result')).toBe(false);
});
