import { env } from 'cloudflare:workers';
import { review_stream } from '../../../src/lib/review-stream';
import { run_review_service } from '../../../src/lib/service';
import { settings, is_live_ready } from '../../../src/lib/settings';
import { ServiceError, MAX_BYTES } from '../../../src/lib/validation';

export async function POST(request: Request) {
  const origin = new URL(request.url).origin;
  if (request.headers.get('origin') && request.headers.get('origin') !== origin) return Response.json({error:'같은 사이트에서 요청해 주세요.'},{status:403});
  const config = settings(env as unknown as Record<string, unknown>);
  let input: {sample_id?: string; pdf_bytes?: Uint8Array};
  try {
    if (request.headers.get('content-type')?.includes('application/json')) {
      const data = await request.json() as {sample_id?:unknown};
      if (typeof data.sample_id !== 'string') throw new ServiceError('샘플을 선택해 주세요.');
      input={sample_id:data.sample_id};
    } else {
      if (!is_live_ready(config)) return Response.json({error:'데모 모드에서는 업로드를 받지 않습니다.'},{status:403});
      if (Number(request.headers.get('content-length')) > MAX_BYTES + 65536) throw new ServiceError('10MB 이하 PDF만 올릴 수 있습니다.');
      // Limit streamed multipart bytes before parsing the file.
      const reader=request.body?.getReader(); if(!reader) throw new ServiceError('빈 요청입니다.');
      const chunks:Uint8Array[]=[]; let size=0;
      while(true){const {done,value}=await reader.read();if(done)break;size+=value.length;if(size>MAX_BYTES+65536){await reader.cancel();throw new ServiceError('10MB 이하 PDF만 올릴 수 있습니다.');}chunks.push(value);}
      const body = new Blob(chunks as BlobPart[]);
      const form = await new Response(body,{headers:{'content-type':request.headers.get('content-type') ?? ''}}).formData();
      const file=form.get('file'); if(!(file instanceof File))throw new ServiceError('PDF 파일을 선택해 주세요.');
      input={pdf_bytes:new Uint8Array(await file.arrayBuffer())};
    }
  } catch(error) { return Response.json({error:error instanceof ServiceError ? error.message:'입력 내용을 확인해 주세요.'},{status:400}); }
  const stream=review_stream(async progress=>{
    const runtime=env as unknown as {BUCKET?:R2Bucket;ASSETS?:{fetch:(request:Request)=>Promise<Response>}};
    return run_review_service(input,{config,bucket:runtime.BUCKET,progress,asset:async path=>{
      const req=new Request(new URL(path,origin));
      const response=runtime.ASSETS?await runtime.ASSETS.fetch(req):await fetch(req);
      if(!response.ok)throw new ServiceError('기준서 또는 글꼴 파일을 불러오지 못했습니다.');
      return new Uint8Array(await response.arrayBuffer());
    }});
  });
  return new Response(stream,{headers:{'Content-Type':'application/x-ndjson; charset=utf-8','Cache-Control':'no-store, no-transform','X-Content-Type-Options':'nosniff','X-Accel-Buffering':'no'}});
}
