import { PDFDocument } from 'pdf-lib';
export class ServiceError extends Error {}
export const MAX_BYTES = 10 * 1024 * 1024;
export async function validate_pdf(data: Uint8Array): Promise<void> {
  if (!data.length) throw new ServiceError('빈 파일입니다. 근로계약서 PDF를 다시 올려 주세요.');
  if (data.length > MAX_BYTES) throw new ServiceError('10MB 이하 PDF만 올릴 수 있습니다.');
  if (!new TextDecoder().decode(data.subarray(0, 1024)).trimStart().startsWith('%PDF-')) throw new ServiceError('PDF 파일이 아닙니다.');
  let pdf: PDFDocument;
  try { pdf = await PDFDocument.load(data); }
  catch (error) {
    if (error instanceof Error && /encrypt/i.test(error.message)) throw new ServiceError('암호가 걸린 PDF는 읽을 수 없습니다. 암호를 풀고 다시 올려 주세요.');
    throw new ServiceError('PDF가 손상되어 열 수 없습니다. 다시 저장해 주세요.');
  }
  if (pdf.isEncrypted) throw new ServiceError('암호가 걸린 PDF는 읽을 수 없습니다.');
  const pages = pdf.getPageCount();
  if (!pages || pages > 20) throw new ServiceError('근로계약서는 1~20쪽 PDF만 올릴 수 있습니다.');
}
