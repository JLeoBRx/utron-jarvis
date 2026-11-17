import type { TableName } from '../types';

/**
 * Regras de integridade referencial — espelham as chaves estrangeiras da
 * migração SQL. O banco PostgreSQL aplica estas regras nativamente; o
 * adaptador local (IndexedDB) as aplica via código usando esta tabela.
 *
 * `match`: colunas que devem ter o MESMO valor no registro filho e no pai
 * (equivale às chaves estrangeiras compostas, ex.: `(exam_id, subject_id)`
 * garante que um material só seja vinculado a uma prova da mesma disciplina).
 */
export interface Relation {
  table: TableName;
  column: string;
  parent: TableName;
  onDelete: 'cascade' | 'set_null';
  match?: string[];
}

export const RELATIONS: Relation[] = [
  { table: 'subjects', column: 'academic_year_id', parent: 'academic_years', onDelete: 'cascade' },

  { table: 'exams', column: 'subject_id', parent: 'subjects', onDelete: 'cascade' },

  { table: 'exam_topics', column: 'exam_id', parent: 'exams', onDelete: 'cascade' },

  { table: 'materials', column: 'subject_id', parent: 'subjects', onDelete: 'cascade' },
  { table: 'materials', column: 'exam_id', parent: 'exams', onDelete: 'set_null', match: ['subject_id'] },
  { table: 'materials', column: 'scan_id', parent: 'notebook_scans', onDelete: 'cascade', match: ['subject_id'] },

  { table: 'material_versions', column: 'material_id', parent: 'materials', onDelete: 'cascade' },

  { table: 'summaries', column: 'subject_id', parent: 'subjects', onDelete: 'cascade' },
  { table: 'summaries', column: 'exam_id', parent: 'exams', onDelete: 'set_null', match: ['subject_id'] },

  { table: 'summary_versions', column: 'summary_id', parent: 'summaries', onDelete: 'cascade' },

  { table: 'summary_sources', column: 'summary_id', parent: 'summaries', onDelete: 'cascade' },
  { table: 'summary_sources', column: 'material_id', parent: 'materials', onDelete: 'cascade' },

  { table: 'flashcards', column: 'subject_id', parent: 'subjects', onDelete: 'cascade' },
  { table: 'flashcards', column: 'exam_id', parent: 'exams', onDelete: 'cascade', match: ['subject_id'] },
  { table: 'flashcards', column: 'topic_id', parent: 'exam_topics', onDelete: 'set_null', match: ['exam_id'] },
  { table: 'flashcards', column: 'summary_id', parent: 'summaries', onDelete: 'set_null', match: ['subject_id'] },

  { table: 'flashcard_reviews', column: 'flashcard_id', parent: 'flashcards', onDelete: 'cascade' },

  { table: 'questions', column: 'subject_id', parent: 'subjects', onDelete: 'cascade' },
  { table: 'questions', column: 'exam_id', parent: 'exams', onDelete: 'cascade', match: ['subject_id'] },
  { table: 'questions', column: 'topic_id', parent: 'exam_topics', onDelete: 'set_null', match: ['exam_id'] },
  { table: 'questions', column: 'summary_id', parent: 'summaries', onDelete: 'set_null', match: ['subject_id'] },

  { table: 'quizzes', column: 'subject_id', parent: 'subjects', onDelete: 'cascade' },
  { table: 'quizzes', column: 'exam_id', parent: 'exams', onDelete: 'cascade', match: ['subject_id'] },

  { table: 'quiz_attempts', column: 'quiz_id', parent: 'quizzes', onDelete: 'cascade' },

  { table: 'study_sessions', column: 'subject_id', parent: 'subjects', onDelete: 'cascade' },
  { table: 'study_sessions', column: 'exam_id', parent: 'exams', onDelete: 'set_null', match: ['subject_id'] },

  { table: 'calendar_events', column: 'subject_id', parent: 'subjects', onDelete: 'cascade' },
  { table: 'calendar_events', column: 'exam_id', parent: 'exams', onDelete: 'cascade', match: ['subject_id'] },

  { table: 'notebook_scans', column: 'subject_id', parent: 'subjects', onDelete: 'cascade' },
  { table: 'notebook_scans', column: 'exam_id', parent: 'exams', onDelete: 'set_null', match: ['subject_id'] },
  { table: 'notebook_scans', column: 'summary_id', parent: 'summaries', onDelete: 'set_null', match: ['subject_id'] },

  { table: 'notebook_scan_pages', column: 'scan_id', parent: 'notebook_scans', onDelete: 'cascade' },
  { table: 'notebook_scan_pages', column: 'material_id', parent: 'materials', onDelete: 'set_null' },
];

/**
 * Restrições de unicidade relevantes para o usuário (espelham os índices
 * únicos do SQL). `caseInsensitive` compara textos sem diferenciar
 * maiúsculas/minúsculas e ignorando espaços nas pontas.
 */
export interface UniqueRule {
  table: TableName;
  columns: string[];
  caseInsensitive?: string[];
  /** Só se aplica quando esta coluna é verdadeira (índice parcial). */
  whereTrue?: string;
  message: string;
  /** Nome do índice/constraint no PostgreSQL (para traduzir erros). */
  constraint: string;
}

export const UNIQUE_RULES: UniqueRule[] = [
  {
    table: 'academic_years',
    columns: ['name'],
    caseInsensitive: ['name'],
    message: 'Já existe um ano letivo com este nome.',
    constraint: 'academic_years_unique_name',
  },
  {
    table: 'academic_years',
    columns: [],
    whereTrue: 'is_active',
    message: 'Já existe um ano letivo ativo.',
    constraint: 'academic_years_one_active_per_user',
  },
  {
    table: 'subjects',
    columns: ['academic_year_id', 'name'],
    caseInsensitive: ['name'],
    message: 'Já existe uma disciplina com este nome neste ano letivo.',
    constraint: 'subjects_unique_name_per_year',
  },
  {
    table: 'material_versions',
    columns: ['material_id', 'version_number'],
    message: 'Esta versão do material já existe.',
    constraint: 'material_versions_material_id_version_number_key',
  },
  {
    table: 'materials',
    columns: ['scan_id'],
    message: 'Esta digitalização já está na biblioteca.',
    constraint: 'materials_scan_id_key',
  },
  {
    table: 'summary_versions',
    columns: ['summary_id', 'version_number'],
    message: 'Esta versão do resumo já existe.',
    constraint: 'summary_versions_summary_id_version_number_key',
  },
  {
    table: 'summary_sources',
    columns: ['summary_id', 'material_id'],
    message: 'Este material já está vinculado ao resumo.',
    constraint: 'summary_sources_summary_id_material_id_key',
  },
];

/** Colunas que apontam para arquivos no Storage (limpeza ao excluir). */
export const STORAGE_PATH_COLUMNS: Partial<Record<TableName, string[]>> = {
  materials: ['storage_path'],
  material_versions: ['storage_path'],
  notebook_scan_pages: ['original_path', 'processed_path'],
};

export const FRIENDLY_TABLE_NAMES: Record<TableName, string> = {
  profiles: 'perfil',
  academic_years: 'ano letivo',
  subjects: 'disciplina',
  exams: 'prova',
  exam_topics: 'conteúdo',
  materials: 'material',
  material_versions: 'versão de material',
  summaries: 'resumo',
  summary_versions: 'versão do resumo',
  summary_sources: 'fonte do resumo',
  flashcards: 'flashcard',
  flashcard_reviews: 'revisão de flashcard',
  questions: 'questão',
  quizzes: 'simulado',
  quiz_attempts: 'tentativa de simulado',
  study_sessions: 'sessão de estudo',
  calendar_events: 'evento do calendário',
  notebook_scans: 'digitalização de caderno',
  notebook_scan_pages: 'página digitalizada',
  ai_operations: 'operação de IA',
};
