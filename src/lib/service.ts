import { apply_source_table, compute_facts, evaluate, engine_review, cross_check, final_view, criteria_problems, looks_like_contract, type ExtractedData } from './rules';
import { build_review_input, contract_rows } from './review-builder';
import { AgentClient, normalize_review } from './agent-client';
import { is_live_ready, type Settings } from './settings';
import { ServiceError, validate_pdf } from './validation';
import { demo_inputs, sample_ids } from './demo-inputs';
import { criteria_source_codes, criteria_source_table, sha256 } from './criteria-source';
import { cached_criteria } from './criteria-cache';

export type ServiceContext = { config: Settings; asset: (path: string) => Promise<Uint8Array>; bucket?: R2Bucket; progress?: (step:number,message:string)=>void; fetch?:typeof fetch; use_recorded?:boolean };
export async function criteria_cache_key(pdf: Uint8Array, config: Settings) {
 return 'criteria/' + await sha256(new TextEncoder().encode(JSON.stringify([await sha256(pdf), config.CRITERIA_AGENT_ID, config.CRITERIA_CONFIG_ID]))) + '.json';
}
async function extract(bytes: Uint8Array, role: 'CONTRACT'|'CRITERIA'|'REVIEW', ctx: ServiceContext) {
 const client = new AgentClient({api_key:ctx.config.UPSTAGE_API_KEY,agent_id:ctx.config[`${role}_AGENT_ID`],config_id:ctx.config[`${role}_CONFIG_ID`],name:role,fetch:ctx.fetch});
 const file = await client.upload_file(new Blob([bytes as BlobPart],{type:'application/pdf'}), `${role.toLowerCase()}.pdf`);
 return client.run(file);
}
export async function load_or_extract_criteria(ctx: ServiceContext,pdf:Uint8Array,codes:Set<string>) {
 const key = await criteria_cache_key(pdf, ctx.config);
 return cached_criteria(key,ctx.bucket,data=>!criteria_problems(data,codes).length,async()=>{
  const {result}=await extract(pdf,'CRITERIA',ctx);
  const problems=criteria_problems(result,codes);
  if(problems.length)throw new ServiceError('점검 기준서를 읽지 못했습니다. Criteria Agent 설정을 확인해 주세요.');
  return result;
 });
}
export async function run_review_service(input:{sample_id?:string;pdf_bytes?:Uint8Array}, ctx: ServiceContext) {
 const live=is_live_ready(ctx.config);
 if((input.sample_id!==undefined)===(input.pdf_bytes!==undefined))throw new ServiceError('샘플이나 계약서 파일 중 하나만 선택해 주세요.');
 if(input.sample_id!==undefined&&!sample_ids.includes(input.sample_id))throw new ServiceError('없는 샘플입니다.');
 if(input.pdf_bytes&&!live)throw new ServiceError('데모 모드에서는 업로드를 받지 않습니다. 샘플 계약서로 체험해 주세요.');
 if(input.pdf_bytes)await validate_pdf(input.pdf_bytes);
 const progress=ctx.progress??(()=>{});
 const demo=live?null:demo_inputs(input.sample_id!,ctx.use_recorded);
 let source:'agent'|'agent_unclassified'|'recorded'|'rules'=live?'agent':demo!.source;
 progress(1,live?'계약서 항목 추출 (Contract Agent)':source==='recorded'?'저장된 실행 결과 재생':'샘플 예상 추출값 불러오기');
 const contract=live?(await extract(input.pdf_bytes??await ctx.asset(`/data/samples/sample${input.sample_id}.pdf`),'CONTRACT',ctx)).result:demo!.contract;
 progress(2,live?'점검 기준서 불러오기 (Criteria Agent)':'기준서 추출값 불러오기');
 const criteriaPdf=await ctx.asset('/data/criteria_v2_2026-10.pdf');
 const codes=await criteria_source_codes(criteriaPdf);
 const extracted=live?await load_or_extract_criteria(ctx,criteriaPdf,codes):demo!.criteria;
 const [criteria,criteria_repaired]=apply_source_table(extracted,await criteria_source_table(criteriaPdf));
 const facts=compute_facts(contract,criteria);
 progress(3,'계약 정보·기준서·계산 보조값으로 평가 입력 PDF 조립');
 const pdf=(!live||looks_like_contract(contract))?await build_review_input(contract,criteria,facts,await ctx.asset('/fonts/NanumGothic-Regular.ttf')):null;
 let reviewJson:ExtractedData|null=demo?.review??null,raw:ExtractedData=demo?.raw??{};
 if(live&&pdf){progress(4,'평가 에이전트 분류 (Review Agent) · 수 분이 걸릴 수 있습니다');const response=await extract(pdf,'REVIEW',ctx);reviewJson=response.result;raw=response.raw;}
 else progress(4,source==='recorded'?'저장된 실행 결과 재생':live?'근로계약서가 아니므로 평가 생략':'평가 에이전트 미연결 · 규칙 계산으로 진행');
 progress(5,'규칙 계산 교차 검증');
 const engine=evaluate(contract,criteria,facts,codes);
 const review=!engine.is_contract?null:reviewJson!==null?normalize_review(reviewJson,raw):engine_review(engine);
 const agent_level=review&&source!=='rules'?review.review_level:null;
 if(source==='agent'&&review&&agent_level===null)source='agent_unclassified';
 const check=cross_check(agent_level,review?.matched_rules??[],engine);
 const final=review?final_view(review,engine,agent_level,check):null;
 return {mode:live?'live':'demo',source,sample_id:input.sample_id??null,contract,contract_rows:contract_rows(contract),criteria,criteria_repaired,facts,engine,review,agent_level,engine_level:engine.level,final_level:final?.level??null,final,disputed_rule_codes:final?.disputed.map(card=>card.rule_code)??[],cross_check:check,review_pdf_base64:pdf?Buffer.from(pdf).toString('base64'):null};
}
export type ReviewResult=Awaited<ReturnType<typeof run_review_service>>;
