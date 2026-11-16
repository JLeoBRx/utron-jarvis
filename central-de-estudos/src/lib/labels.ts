import type {
  ExamPriority,
  ExamStatus,
  MaterialCategory,
  SubjectCategory,
  SummaryStatus,
  TopicStatus,
} from '@/data/types';

export const CATEGORY_LABELS: Record<SubjectCategory, string> = {
  formacao_geral: 'Formação Geral',
  formacao_tecnica: 'Formação Técnica',
};

export const EXAM_STATUS_LABELS: Record<ExamStatus, string> = {
  nao_iniciada: 'Não iniciada',
  em_preparacao: 'Em preparação',
  em_revisao: 'Em revisão',
  preparacao_concluida: 'Preparação concluída',
  realizada: 'Realizada',
};

export const EXAM_STATUS_ORDER: ExamStatus[] = [
  'nao_iniciada',
  'em_preparacao',
  'em_revisao',
  'preparacao_concluida',
  'realizada',
];

export const PRIORITY_LABELS: Record<ExamPriority, string> = {
  baixa: 'Baixa',
  media: 'Média',
  alta: 'Alta',
};

export const PRIORITY_ORDER: ExamPriority[] = ['alta', 'media', 'baixa'];

export const TOPIC_STATUS_LABELS: Record<TopicStatus, string> = {
  nao_estudado: 'Não estudado',
  estudando: 'Estudando',
  revisado: 'Revisado',
  dominado: 'Dominado',
};

export const TOPIC_STATUS_ORDER: TopicStatus[] = ['nao_estudado', 'estudando', 'revisado', 'dominado'];

export const MATERIAL_CATEGORY_LABELS: Record<MaterialCategory, string> = {
  slides: 'Slides do professor',
  caderno: 'Caderno',
  exercicios: 'Exercícios',
  atividades: 'Atividades',
  provas_anteriores: 'Provas anteriores',
  apostilas: 'Apostilas',
  complementares: 'Materiais complementares',
};

export const SUMMARY_STATUS_LABELS: Record<SummaryStatus, string> = {
  rascunho: 'Rascunho',
  em_revisao: 'Em revisão',
  concluido: 'Concluído',
};
