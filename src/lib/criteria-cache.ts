import type { ExtractedData } from './rules';
import { ServiceError } from './validation';
const pending=new Map<string,Promise<ExtractedData>>();
const LEASE_MS=1_500_000;
export async function cached_criteria(key:string,bucket:R2Bucket|undefined,valid:(data:ExtractedData)=>boolean,extract:()=>Promise<ExtractedData>):Promise<ExtractedData>{
 const current=pending.get(key);if(current)return current;
 const task=load();pending.set(key,task);
 try{return await task;}finally{pending.delete(key);}
 async function load(){
  if(!bucket)return extract();
  const lockKey=`${key}.lease`;const deadline=Date.now()+LEASE_MS;
  let lease:R2Object|null=null;
  while(!lease){
   const cached=await bucket.get(key);
   if(cached){try{const data=await cached.json<ExtractedData>();if(data && typeof data==='object' && !Array.isArray(data) && valid(data))return data;}catch{/* Invalid JSON is extracted again. */}}
   const lock=await bucket.get(lockKey);
   const expires=lock?Number((await lock.json<{expires:number}>()).expires):0;
   if(!lock || expires<=Date.now()){
    lease=await bucket.put(lockKey,JSON.stringify({expires:Date.now()+LEASE_MS}),{onlyIf:lock?{etagMatches:lock.etag}:{etagDoesNotMatch:'*'}});
   }
   if(!lease){if(Date.now()>=deadline)throw new ServiceError('기준서 추출 대기 시간이 초과되었습니다. 잠시 뒤 다시 시도해 주세요.');await new Promise(resolve=>setTimeout(resolve,2000));}
  }
  try{
   const data=await extract();
   await bucket.put(key,JSON.stringify(data),{httpMetadata:{contentType:'application/json'}});
   return data;
  }finally{
   // Release only our lease. Conditional writes protect concurrent isolates.
   await bucket.put(lockKey,JSON.stringify({expires:0}),{onlyIf:{etagMatches:lease.etag}}).catch(()=>null);
  }
 }
}
