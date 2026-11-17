import { Camera, FilePlus2, Link2 } from 'lucide-react';
import { useState } from 'react';
import { Button, ButtonLink } from '@/components/ui/Button';
import { LinkDialog, UploadDialog } from './MaterialDialogs';

export function scannerUrl(subjectId?: string, examId?: string): string {
  const params = new URLSearchParams();
  if (subjectId) params.set('disciplina', subjectId);
  if (examId) params.set('prova', examId);
  const query = params.toString();
  return `/scanner${query ? `?${query}` : ''}`;
}

/** Botões para adicionar material (já preenchem disciplina/prova do contexto). */
export function AddMaterialActions({ subjectId, examId, size = 'md' }: { subjectId?: string; examId?: string; size?: 'sm' | 'md' }) {
  const [upload, setUpload] = useState(false);
  const [link, setLink] = useState(false);
  return (
    <>
      <ButtonLink to={scannerUrl(subjectId, examId)} size={size}>
        <Camera /> Fotografar caderno
      </ButtonLink>
      <Button size={size} onClick={() => setLink(true)}>
        <Link2 /> Adicionar link
      </Button>
      <Button size={size} variant="primary" onClick={() => setUpload(true)}>
        <FilePlus2 /> Enviar arquivos
      </Button>
      <UploadDialog open={upload} onOpenChange={setUpload} defaultSubjectId={subjectId} defaultExamId={examId} />
      <LinkDialog open={link} onOpenChange={setLink} defaultSubjectId={subjectId} defaultExamId={examId} />
    </>
  );
}
