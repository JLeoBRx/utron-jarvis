import { z } from 'zod';
import { isValidISODate, normalizeTime } from '@/lib/dates';
import { AppError } from '@/lib/errors';

/**
 * Esquemas de validação das entradas do usuário. Os limites espelham as
 * restrições CHECK do banco, então o mesmo dado é aceito nos dois modos.
 * Usados pelos formulários (react-hook-form) e pelos serviços.
 */

const optionalText = (max: number) =>
  z
    .string()
    .trim()
    .max(max, `Use no máximo ${max} caracteres.`)
    .nullable()
    .optional()
    .transform((value) => (value ? value : null));

const requiredText = (max: number, message: string) =>
  z.string().trim().min(1, message).max(max, `Use no máximo ${max} caracteres.`);

const optionalDate = z
  .string()
  .nullable()
  .optional()
  .refine((value) => !value || isValidISODate(value), 'Data inválida.')
  .transform((value) => (value ? value : null));

const optionalTime = z
  .string()
  .nullable()
  .optional()
  .refine((value) => !value || /^\d{2}:\d{2}(:\d{2})?$/.test(value), 'Horário inválido.')
  .transform((value) => normalizeTime(value));

const optionalScore = z.preprocess(
  (value) => {
    if (value === '' || value === null || value === undefined) return null;
    if (typeof value === 'number') return value;
    const parsed = Number(String(value).replace(',', '.'));
    return Number.isNaN(parsed) ? value : parsed;
  },
  z.number({ error: 'Informe um número.' }).min(0, 'Não pode ser negativo.').max(9999, 'Valor muito alto.').nullable(),
);

export const academicYearSchema = z
  .object({
    name: requiredText(60, 'Informe o nome do ano letivo.'),
    start_date: optionalDate,
    end_date: optionalDate,
  })
  .refine((v) => !v.start_date || !v.end_date || v.end_date >= v.start_date, {
    message: 'O término deve ser depois do início.',
    path: ['end_date'],
  });

export const subjectSchema = z.object({
  name: requiredText(120, 'Informe o nome da disciplina.'),
  code: optionalText(40),
  category: z.enum(['formacao_geral', 'formacao_tecnica'], { error: 'Selecione a categoria.' }),
  description: optionalText(2000),
  teacher: optionalText(120),
  color: z.string().regex(/^[a-z]{3,16}$/, 'Cor inválida.'),
});

export const examSchema = z
  .object({
    subject_id: z.string().min(1, 'Selecione a disciplina.'),
    title: requiredText(160, 'Informe o nome da avaliação.'),
    exam_date: optionalDate,
    exam_time: optionalTime,
    teacher: optionalText(120),
    description: optionalText(4000),
    priority: z.enum(['baixa', 'media', 'alta']),
    status: z.enum(['nao_iniciada', 'em_preparacao', 'em_revisao', 'preparacao_concluida', 'realizada']),
    score: optionalScore,
    max_score: optionalScore,
  })
  .refine((v) => v.max_score === null || v.max_score > 0, {
    message: 'A nota máxima deve ser maior que zero.',
    path: ['max_score'],
  })
  .refine((v) => v.score === null || v.max_score === null || v.score <= v.max_score, {
    message: 'A nota não pode ser maior que a nota máxima.',
    path: ['score'],
  });

export const topicSchema = z.object({
  title: requiredText(200, 'Informe o conteúdo.'),
  notes: optionalText(4000),
  status: z.enum(['nao_estudado', 'estudando', 'revisado', 'dominado']),
});

const MATERIAL_CATEGORIES = [
  'slides',
  'caderno',
  'exercicios',
  'atividades',
  'provas_anteriores',
  'apostilas',
  'complementares',
] as const;

/** Dados descritivos de um material (arquivo, link ou caderno digitalizado). */
export const materialMetaSchema = z.object({
  subject_id: z.string().min(1, 'Selecione a disciplina.'),
  exam_id: z
    .string()
    .nullable()
    .optional()
    .transform((value) => (value ? value : null)),
  category: z.enum(MATERIAL_CATEGORIES, { error: 'Selecione a categoria.' }),
  title: requiredText(200, 'Informe o nome do material.'),
  description: optionalText(4000),
  origin: optionalText(200),
});

export const linkSchema = materialMetaSchema.extend({
  url: z
    .string()
    .trim()
    .min(1, 'Informe o endereço.')
    .max(2000, 'Endereço muito longo.')
    .refine((value) => {
      try {
        const u = new URL(value);
        return u.protocol === 'http:' || u.protocol === 'https:';
      } catch {
        return false;
      }
    }, 'Informe um endereço completo, começando com https://'),
});

export type MaterialMetaInput = z.input<typeof materialMetaSchema>;
export type MaterialMetaValues = z.output<typeof materialMetaSchema>;
export type LinkInput = z.input<typeof linkSchema>;
export type LinkValues = z.output<typeof linkSchema>;

export const profileSchema = z.object({
  display_name: optionalText(80),
});

export type AcademicYearInput = z.input<typeof academicYearSchema>;
export type AcademicYearValues = z.output<typeof academicYearSchema>;
export type SubjectInput = z.input<typeof subjectSchema>;
export type SubjectValues = z.output<typeof subjectSchema>;
export type ExamInput = z.input<typeof examSchema>;
export type ExamValues = z.output<typeof examSchema>;
export type TopicInput = z.input<typeof topicSchema>;
export type TopicValues = z.output<typeof topicSchema>;

/** Valida e converte; lança `AppError('validation')` com a primeira mensagem. */
export function parseOrThrow<S extends z.ZodType>(schema: S, input: unknown): z.output<S> {
  const result = schema.safeParse(input);
  if (!result.success) {
    const first = result.error.issues[0];
    throw new AppError('validation', first?.message ?? 'Dados inválidos.', result.error);
  }
  return result.data;
}
