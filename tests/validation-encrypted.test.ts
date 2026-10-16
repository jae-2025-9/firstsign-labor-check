import {expect,it} from 'vitest';
import {PDFDocument,PDFName,PDFNumber} from 'pdf-lib';
import {validate_pdf} from '../src/lib/validation';
it('rejects PDFs that declare encryption',async()=>{
 const doc=await PDFDocument.create();doc.addPage();
 doc.context.trailerInfo.Encrypt=doc.context.register(doc.context.obj({Filter:PDFName.of('Standard'),V:PDFNumber.of(1),R:PDFNumber.of(2)}));
 await expect(validate_pdf(await doc.save())).rejects.toThrow('암호');
});
