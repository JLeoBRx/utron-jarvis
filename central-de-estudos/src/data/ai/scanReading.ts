/**
 * CONTRATO DA LEITURA DE CADERNOS POR IA (preparado na Fase 3, executado na Fase 7)
 * ================================================================================
 * Nada aqui chama um modelo. Este módulo define:
 *   1. as instruções de fidelidade que acompanham as imagens;
 *   2. o pedido (`ScanReadingRequest`) montado a partir das páginas salvas — o
 *      backend da Fase 7 baixará as imagens pelo `storage_path` (com a chave de
 *      serviço, no servidor) e as enviará a um modelo multimodal;
 *   3. o formato OBRIGATÓRIO da resposta (`scanReadingResultSchema`), validado
 *      antes de qualquer gravação — respostas fora do formato são rejeitadas.
 *
 * Ciclo de status da digitalização (`notebook_scans.status`):
 *   capturado → processando → aguardando_revisao → revisado → concluido   (ou erro)
 */
import { z } from 'zod';
import type { NotebookScan, NotebookScanPage } from '../types';

export const SCAN_READING_VERSION = 1;

export const SCAN_READING_INSTRUCTIONS = `Você vai ler fotografias de páginas de caderno de um estudante do ensino médio técnico, em português do Brasil.

FIDELIDADE (obrigatório):
- Use as fotografias como fonte principal. Não invente anotações, não altere valores numéricos e não substitua fórmulas.
- Não omita observações do professor, exemplos resolvidos, setas, destaques ou anotações nas margens.
- Respeite a ordem das páginas e a sequência do conteúdo em cada página.
- Quando um trecho estiver ilegível ou duvidoso, NÃO adivinhe: marque "incerto": true, transcreva o que for possível e explique a dúvida.
- Fórmulas em LaTeX. Fórmulas que não puderem ser reconhecidas com segurança devem ser sinalizadas.
- Considere letra cursiva, abreviações, rasuras, marca-texto e cores diferentes.
- Descreva desenhos e diagramas de forma objetiva (o que mostram e seus rótulos).
- Separe o que está ESCRITO no caderno de qualquer explicação complementar (complementos só no campo "observacao").

Responda SOMENTE com JSON no formato especificado.`;

const confidence = z.number().min(0).max(1);

export const scanBlockSchema = z.object({
  tipo: z.enum(['titulo', 'subtitulo', 'paragrafo', 'lista', 'formula', 'calculo', 'tabela', 'diagrama', 'destaque', 'observacao_professor']),
  /** Texto transcrito; LaTeX para fórmulas; Markdown para tabelas e listas. */
  conteudo: z.string(),
  confianca: confidence,
  incerto: z.boolean(),
  motivo_incerteza: z.string().optional(),
  observacao: z.string().optional(),
});

export const scanReadingResultSchema = z.object({
  versao: z.literal(SCAN_READING_VERSION),
  paginas: z.array(
    z.object({
      page_id: z.string(),
      posicao: z.number().int().min(0),
      blocos: z.array(scanBlockSchema),
      trechos_ilegiveis: z.array(z.object({ descricao: z.string(), localizacao: z.string().optional() })),
    }),
  ),
  assuntos: z.array(z.object({ titulo: z.string(), paginas: z.array(z.number().int().min(0)) })),
  formulas: z.array(z.object({ latex: z.string(), pagina: z.number().int().min(0), confianca: confidence, verificar: z.boolean() })),
  pontos_para_revisao: z.array(z.object({ pagina: z.number().int().min(0), trecho: z.string(), motivo: z.string() })),
});

export type ScanReadingResult = z.infer<typeof scanReadingResultSchema>;

/** JSON Schema da resposta (para "structured outputs" do modelo na Fase 7). */
export function scanReadingJsonSchema() {
  return z.toJSONSchema(scanReadingResultSchema);
}

export interface ScanReadingRequest {
  versao: number;
  scan_id: string;
  idioma: 'pt-BR';
  contexto: { disciplina: string; prova: string | null; assunto: string | null };
  instrucoes: string;
  paginas: {
    page_id: string;
    posicao: number;
    /** Imagem tratada (recorte/perspectiva/iluminação) — preferida para leitura. */
    imagem: { storage_path: string; mime_type: string; largura: number | null; altura: number | null };
    /** Original intocado — usado para conferir trechos duvidosos. */
    original: { storage_path: string; mime_type: string | null };
  }[];
}

/** Monta o pedido de leitura a partir do que foi salvo no banco (função pura). */
export function buildScanReadingRequest(
  scan: Pick<NotebookScan, 'id' | 'topic_label'>,
  pages: NotebookScanPage[],
  context: { subjectName: string; examTitle: string | null },
): ScanReadingRequest {
  const ordered = [...pages].sort((a, b) => a.position - b.position);
  return {
    versao: SCAN_READING_VERSION,
    scan_id: scan.id,
    idioma: 'pt-BR',
    contexto: { disciplina: context.subjectName, prova: context.examTitle, assunto: scan.topic_label },
    instrucoes: SCAN_READING_INSTRUCTIONS,
    paginas: ordered.map((page, index) => ({
      page_id: page.id,
      posicao: index,
      imagem: {
        storage_path: page.processed_path ?? page.original_path,
        mime_type: page.processed_path ? (page.processed_mime_type ?? 'image/jpeg') : (page.original_mime_type ?? 'image/jpeg'),
        largura: page.width,
        altura: page.height,
      },
      original: { storage_path: page.original_path, mime_type: page.original_mime_type },
    })),
  };
}

/**
 * Valida a resposta do modelo. Lança erro se o JSON não seguir o contrato ou se
 * citar páginas que não pertencem à digitalização.
 */
export function parseScanReadingResult(raw: unknown, pages: Pick<NotebookScanPage, 'id'>[]): ScanReadingResult {
  const result = scanReadingResultSchema.parse(raw);
  const ids = new Set(pages.map((p) => p.id));
  const unknown = result.paginas.filter((p) => !ids.has(p.page_id));
  if (unknown.length) throw new Error(`Resposta cita páginas desconhecidas: ${unknown.map((p) => p.page_id).join(', ')}`);
  return result;
}

/**
 * Texto para o MODO MANUAL: o estudante baixa as páginas, abre o Claude, anexa as
 * imagens e cola este texto. Nada é enviado automaticamente.
 */
export function manualReadingPrompt(context: { subjectName: string; examTitle: string | null; topic: string | null; pageCount: number }): string {
  return [
    SCAN_READING_INSTRUCTIONS.replace('Responda SOMENTE com JSON no formato especificado.', ''),
    `Contexto: disciplina "${context.subjectName}"${context.examTitle ? `, prova "${context.examTitle}"` : ''}${context.topic ? `, assunto "${context.topic}"` : ''}.`,
    `Estou enviando ${context.pageCount} ${context.pageCount === 1 ? 'página' : 'páginas'}, em ordem (pagina-01, pagina-02…).`,
    'Primeiro, transcreva fielmente cada página (marcando os trechos duvidosos com [?]). Depois, organize um resumo completo com: título, introdução, explicação dos assuntos, definições, conceitos, fórmulas explicadas, exemplos do caderno, cálculos passo a passo, tabelas, descrição dos diagramas, pontos para memorizar e revisão final. Identifique separadamente qualquer explicação complementar que não esteja no caderno.',
  ]
    .join('\n\n')
    .trim();
}
