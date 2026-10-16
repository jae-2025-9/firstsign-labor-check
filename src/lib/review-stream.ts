import { ServiceError } from './validation';
export const HEARTBEAT_MS=15_000;
export function review_stream<T>(task:(progress:(step:number,message:string)=>void)=>Promise<T>):ReadableStream<Uint8Array>{
 const encoder=new TextEncoder();let closed=false;
 return new ReadableStream({
  async start(controller){
   const send=(event:unknown)=>{if(!closed)try{controller.enqueue(encoder.encode(JSON.stringify(event)+'\n'));}catch{closed=true;}};
   const heartbeat=setInterval(()=>send({type:'heartbeat'}),HEARTBEAT_MS);
   try{send({type:'heartbeat'});const result=await task((step,message)=>send({type:'progress',step,message}));send({type:'result',result});}
   catch(error){send({type:'error',error:error instanceof Error&&(error.name==='AgentError'||error instanceof ServiceError)?error.message:'점검 중 오류가 발생했습니다. 잠시 뒤 다시 시도해 주세요.'});}
   finally{clearInterval(heartbeat);if(!closed)controller.close();}
  },
  cancel(){closed=true;}
 });
}
