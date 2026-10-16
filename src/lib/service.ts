import sample1 from '../../fixtures/expected/contract_sample1.json';
import sample2 from '../../fixtures/expected/contract_sample2.json';
import sample3 from '../../fixtures/expected/contract_sample3.json';
import sample4 from '../../fixtures/expected/contract_sample4.json';
import expectedCriteria from '../../fixtures/expected/criteria.json';
import { compute_facts, evaluate, engine_review, cross_check, final_view, criteria_problems, looks_like_contract } from './rules';
import { build_review_input, contract_rows } from './review-builder';
import { AgentClient, normalize_review } from './agent-client';
import { is_live_ready, type Settings } from './settings';
import { ServiceError, validate_pdf } from './validation';

const samples: Record<string, Record<string, unknown>> = { '1': sample1, '2': sample2, '3': sample3, '4': sample4 };
export type ServiceContext = { config: Settings; asset: (path: string) => Promise<Uint8Array>; bucket?: R2Bucket; progress?: (step:number,message:string)=>void };
async function sha256(bytes: Uint8Array) { return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes as BufferSource)), x => x.toString(16).padStart(2, '0')).join(''); }
export async function criteria_cache_key(pdf: Uint8Array, config: Settings) {
  const hash = await sha256(pdf);
  return 'criteria/' + await sha256(new TextEncoder().encode(JSON.stringify([hash, config.CRITERIA_AGENT_ID, config.CRITERIA_CONFIG_ID]))) + '.json';
}
async function extract(bytes: Uint8Array, role: 'CONTRACT'|'CRITERIA'|'REVIEW', ctx: ServiceContext) {
  const client = new AgentClient({api_key:ctx.config.UPSTAGE_API_KEY,agent_id:ctx.config[`${role}_AGENT_ID`],config_id:ctx.config[`${role}_CONFIG_ID`],name:role});
  const file = await client.upload_file(new Blob([bytes as BlobPart],{type:'application/pdf'}), `${role.toLowerCase()}.pdf`);
  return client.run(file);
}
async function loadCriteria(ctx: ServiceContext) {
  const pdf = await ctx.asset('/data/criteria_v2_2026-10.pdf');
  const key = await criteria_cache_key(pdf, ctx.config);
  if (ctx.bucket) {
    try { const cached = await ctx.bucket.get(key); if (cached) { const data = await cached.json<Record<string,unknown>>(); if (!criteria_problems(data).length) return data; } } catch { /* A failed cache read triggers extraction. */ }
  }
  const {result} = await extract(pdf, 'CRITERIA', ctx);
  if (criteria_problems(result).length) throw new ServiceError('점검 기준서를 읽지 못했습니다. Criteria Agent 설정을 확인해 주세요.');
  if (ctx.bucket) { try { await ctx.bucket.put(key, JSON.stringify(result), {httpMetadata:{contentType:'application/json'}}); } catch { /* The validated result remains usable. */ } }
  return result;
}
export async function run_review_service(input:{sample_id?:string;pdf_bytes?:Uint8Array}, ctx: ServiceContext) {
  const live = is_live_ready(ctx.config);
  if ((input.sample_id !== undefined) === (input.pdf_bytes !== undefined)) throw new ServiceError('샘플이나 계약서 파일 중 하나만 선택해 주세요.');
  if (input.sample_id !== undefined && !Object.hasOwn(samples,input.sample_id)) throw new ServiceError('없는 샘플입니다.');
  if (input.pdf_bytes && !live) throw new ServiceError('데모 모드에서는 업로드를 받지 않습니다. 샘플 계약서로 체험해 주세요.');
  if (input.pdf_bytes) await validate_pdf(input.pdf_bytes);
  const progress=ctx.progress ?? (()=>{});
  progress(1,live?'계약서 항목 추출 (Contract Agent)':'샘플 예상 추출값 불러오기');
  const contract = live ? (await extract(input.pdf_bytes ?? await ctx.asset(`/data/samples/sample${input.sample_id}.pdf`), 'CONTRACT', ctx)).result : samples[input.sample_id!];
  progress(2,live?'점검 기준서 불러오기 (Criteria Agent)':'기준서 예상 추출값 불러오기');
  const criteria = live ? await loadCriteria(ctx) : expectedCriteria;
  const facts = compute_facts(contract, criteria);
  progress(3,'계약 정보·기준서·계산 보조값으로 평가 입력 PDF 조립');
  const pdf = looks_like_contract(contract) ? await build_review_input(contract,criteria,facts,await ctx.asset('/fonts/NanumGothic-Regular.ttf')) : null;
  let normalized = null;
  if (live && pdf) { progress(4,'평가 에이전트 분류 (Review Agent)'); const {result,raw} = await extract(pdf,'REVIEW',ctx); normalized = normalize_review(result,raw); }
  else progress(4,'평가 에이전트 미연결 · 규칙 계산으로 진행');
  progress(5,'규칙 계산 교차 검증');
  const engine = evaluate(contract,criteria,facts);
  const review = !engine.is_contract ? null : normalized ?? engine_review(engine);
  const agent_level = live && review ? review.review_level : null;
  const check = cross_check(agent_level,review?.matched_rules ?? [],engine);
  const final = review ? final_view(review,engine,agent_level,check) : null;
  return {mode:live?'live':'demo',source:live?'agent':'rules',sample_id:input.sample_id ?? null,contract,contract_rows:contract_rows(contract),criteria,facts,engine,review,agent_level,engine_level:engine.level,final_level:final?.level ?? null,final,cross_check:check,review_pdf_base64:pdf ? Buffer.from(pdf).toString('base64') : null};
}
export type ReviewResult = Awaited<ReturnType<typeof run_review_service>>;
