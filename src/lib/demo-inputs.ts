/// <reference types="vite/client" />
import sample1 from '../../fixtures/expected/contract_sample1.json';
import sample2 from '../../fixtures/expected/contract_sample2.json';
import sample3 from '../../fixtures/expected/contract_sample3.json';
import sample4 from '../../fixtures/expected/contract_sample4.json';
import expectedCriteria from '../../fixtures/expected/criteria.json';
import type { ExtractedData } from './rules';
const expected: Record<string, ExtractedData> = {'1':sample1,'2':sample2,'3':sample3,'4':sample4};
const recordings = import.meta.glob('../../fixtures/live/*.json', {eager:true,import:'default'}) as Record<string,ExtractedData>;
export const sample_ids = Object.keys(expected);
export function demo_inputs(id:string, use_recorded=true){
 const get=(name:string)=>recordings[`../../fixtures/live/${name}.json`];
 const contract=get(`contract_sample${id}`), review=get(`review_sample${id}`), criteria=get('criteria');
 if(use_recorded && contract && review && criteria) return {contract,criteria,review,raw:get(`review_sample${id}_raw`)??{},source:'recorded' as const};
 return {contract:expected[id],criteria:expectedCriteria,review:null,raw:{},source:'rules' as const};
}
