import type { CrossCheck, EngineResult, FinalView, Review } from '../lib/rules';
const labels:Record<string,string>={safe:'안심',check_needed:'확인 필요',risky:'위험'};
export const SOURCE_NOTES:Record<string,string>={agent:'Upstage Studio 평가 에이전트 + 규칙 계산 교차 검증',recorded:'저장된 실행 결과 재생 · 평가 에이전트 + 규칙 계산 교차 검증',rules:'데모: 규칙 계산 결과 (평가 에이전트 미연결)',agent_unclassified:'평가 에이전트의 분류를 확인하지 못해 규칙 계산 결과로 표시'};
export function IncompleteNotice({final,engine}:{final:FinalView;engine:EngineResult}){
 return <>{engine.criteria_problems.length>0&&<p className="notice amber">점검 기준서 추출 결과에 문제가 있어 규칙 계산 등급을 내지 않았습니다: {engine.criteria_problems.join(', ')}</p>}{final.level===null?<p>일부 규칙을 판단하지 못해 등급을 정하지 않았습니다. 아래 판단 보류 항목을 원문으로 확인하세요.</p>:final.incomplete&&<p>판단하지 못한 규칙이 있어 최소 '{labels[final.level]}' 등급입니다. 아래 판단 보류 항목을 원문으로 확인하세요.</p>}</>;
}
export function CrossCheckNotice({source,check,review,disputed=[]}:{source:string;check:CrossCheck;review:Review|null;disputed?:FinalView['disputed']}){
 if(source==='rules')return null;
 const normalized=review as (Review&{level_conflict?:boolean;schema_level?:string|null;classify_level?:string|null})|null;
 const conflict=normalized?.level_conflict&&<p>Classify 분류는 {labels[normalized.classify_level??'']}, review_level은 {labels[normalized.schema_level??'']}입니다. 더 엄격한 등급을 썼습니다.</p>;
 const agent=labels[check.agent_level??'']??'찾지 못함',engine=labels[check.engine_level??'']??'판정 보류';
 if(check.status==='unavailable')return <section className="notice amber"><strong>평가 에이전트의 분류를 찾지 못했습니다</strong>{conflict}<p>규칙 계산 결과로 표시합니다. 교차 검증은 하지 못했습니다.</p></section>;
 if(check.status==='match')return <section className="notice green"><strong>교차 검증 일치</strong>{conflict}<p>평가 에이전트({agent})와 규칙 계산({engine})의 등급과 해당 규칙이 같습니다.</p></section>;
 if(check.status==='partial')return <section className="notice slate"><strong>교차 검증 일부만 완료</strong>{conflict}<p>규칙 계산이 {check.undetermined.length}개 규칙({check.undetermined.join(', ')})을 판단하지 못했습니다. 그 규칙은 평가 에이전트({agent})의 판단만 반영했고, 나머지 규칙에서는 두 결과가 같습니다.</p></section>;
 return <section className="notice amber"><strong>교차 검증 결과가 다릅니다</strong>{conflict}<p>평가 에이전트: {agent} · 규칙 계산: {engine}</p>{check.agent_only.length>0&&<p>에이전트만 지적: {check.agent_only.join(', ')}</p>}{check.engine_only.length>0&&<p>규칙 계산만 지적: {check.engine_only.join(', ')}</p>}<p>최종 등급은 지적한 규칙의 기준서 분류로 정했고, 두 쪽의 지적을 아래에 모두 표시합니다.</p>{disputed.length>0&&<p>계약서 값으로 계산해 해당하지 않음을 확인한 에이전트 지적은 아래 '의견 차이'에 따로 적었습니다.</p>}</section>;
}

export function DisputedNotice({disputed}:{disputed:FinalView['disputed']}){
 if(!disputed.length)return null;
 return <div className="notice slate"><strong>의견 차이 ({disputed.length}건) · 등급에 넣지 않음</strong><ul>{disputed.map((item,i)=><li key={i}>{item.title}: {item.reason}</li>)}</ul></div>;
}
export function CriteriaRepairNotice({codes}:{codes:string[]}){
 return codes.length>0?<p className="subtle">기준서 원문 대조: Criteria Agent가 읽은 {codes.join(', ')} 규칙의 내용이 잘려 있어 PDF 원문 표로 바로잡았습니다.</p>:null;
}
