import { ServiceError } from './validation';
export const HEARTBEAT_MS=15_000;
export const STREAM_CHUNK_BYTES=64*1024;
export function review_stream<T>(task:(progress:(step:number,message:string)=>void)=>Promise<T>):ReadableStream<Uint8Array>{
 const encoder=new TextEncoder();let closed=false;let heartbeat:ReturnType<typeof setInterval>|undefined;
 return new ReadableStream({
  start(controller){
   const send=(event:unknown)=>{
    if(closed)return;
    const bytes=encoder.encode(JSON.stringify(event)+'\n');
    try{for(let offset=0;offset<bytes.length;offset+=STREAM_CHUNK_BYTES)controller.enqueue(bytes.slice(offset,offset+STREAM_CHUNK_BYTES));}
    catch{closed=true;if(heartbeat)clearInterval(heartbeat);}
   };
   send({type:'heartbeat'});
   heartbeat=setInterval(()=>send({type:'heartbeat'}),HEARTBEAT_MS);
   // Keep stream startup synchronous so readers can drain queued data immediately.
   void (async()=>{
    try{const result=await task((step,message)=>send({type:'progress',step,message}));send({type:'result',result});}
    catch(error){send({type:'error',error:error instanceof Error&&(error.name==='AgentError'||error instanceof ServiceError)?error.message:'점검 중 오류가 발생했습니다. 잠시 뒤 다시 시도해 주세요.'});}
    finally{clearInterval(heartbeat);if(!closed){closed=true;controller.close();}}
   })();
  },
  cancel(){closed=true;clearInterval(heartbeat);}
 });
}
