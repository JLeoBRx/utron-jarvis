/**
 * Tipos das entidades — espelham exatamente as tabelas definidas em
 * `supabase/migrations/*_esquema_inicial.sql`. Qualquer alteração no esquema
 * deve ser refletida aqui (e no adaptador local, em `relations.ts`).
 */

export type UUID = string;
/** Data no formato `YYYY-MM-DD`. */
export type ISODate = string;
/** Data/hora ISO 8601. */
export type ISODateTime = string;

export interface BaseRow {
  id: UUID;
  user_id: UUID;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

// ---------------------------------------------------------------------------
// Enumerações
// ---------------------------------------------------------------------------
export type SubjectCategory = 'formacao_geral' | 'formacao_tecnica';
export type ExamPriority = 'baixa' | 'media' | 'alta';
export type ExamStatus =
  | 'nao_iniciada'
  | 'em_preparacao'
  | 'em_revisao'
  | 'preparacao_concluida'
  | 'realizada';
export type TopicStatus = 'nao_estudado' | 'estudando' | 'revisado' | 'dominado';
export type MaterialKind = 'arquivo' | 'link' | 'digitalizacao';
export type MaterialCategory =
  | 'slides'
  | 'caderno'
  | 'exercicios'
  | 'atividades'
  | 'provas_anteriores'
  | 'apostilas'
  | 'complementares';
export type SummaryStatus = 'rascunho' | 'em_revisao' | 'concluido';
export type Difficulty = 'facil' | 'medio' | 'dificil';
export type ContentOrigin = 'manual' | 'importado' | 'ia';
export type FlashcardResult = 'nao_sei' | 'duvidas' | 'parcial' | 'sei_bem';
export type QuestionType =
  | 'multipla_escolha'
  | 'verdadeiro_falso'
  | 'discursiva'
  | 'calculo'
  | 'associacao'
  | 'lacunas'
  | 'interpretacao'
  | 'problema';
export type StudyActivity =
  | 'leitura'
  | 'resumo'
  | 'flashcards'
  | 'exercicios'
  | 'simulado'
  | 'revisao'
  | 'outro';
export type CalendarEventType = 'sessao_estudo' | 'meta' | 'lembrete' | 'revisao' | 'outro';
export type ScanStatus =
  | 'capturado'
  | 'processando'
  | 'aguardando_revisao'
  | 'revisado'
  | 'concluido'
  | 'erro';

// ---------------------------------------------------------------------------
// Linhas das tabelas
// ---------------------------------------------------------------------------
export interface Profile extends BaseRow {
  display_name: string | null;
  preferences: Record<string, unknown>;
}

export interface AcademicYear extends BaseRow {
  name: string;
  start_date: ISODate | null;
  end_date: ISODate | null;
  is_active: boolean;
}

export interface Subject extends BaseRow {
  academic_year_id: UUID;
  name: string;
  /** `null` = código institucional ainda não confirmado. */
  code: string | null;
  category: SubjectCategory;
  description: string | null;
  teacher: string | null;
  color: string;
  position: number;
  archived_at: ISODateTime | null;
}

export interface Exam extends BaseRow {
  subject_id: UUID;
  title: string;
  /** `null` = data ainda não definida. */
  exam_date: ISODate | null;
  /** `HH:MM:SS` ou `null`. */
  exam_time: string | null;
  teacher: string | null;
  description: string | null;
  priority: ExamPriority;
  status: ExamStatus;
  score: number | null;
  max_score: number | null;
}

export interface ExamTopic extends BaseRow {
  exam_id: UUID;
  title: string;
  notes: string | null;
  status: TopicStatus;
  position: number;
}

export interface Material extends BaseRow {
  subject_id: UUID;
  exam_id: UUID | null;
  kind: MaterialKind;
  category: MaterialCategory;
  title: string;
  description: string | null;
  origin: string | null;
  file_name: string | null;
  mime_type: string | null;
  size_bytes: number | null;
  storage_path: string | null;
  url: string | null;
  version: number;
  replaced_at: ISODateTime | null;
  /** Preenchido quando o material é um caderno digitalizado. */
  scan_id: UUID | null;
}

/** Arquivo anterior de um material (preservado ao substituir). */
export interface MaterialVersion extends BaseRow {
  material_id: UUID;
  version_number: number;
  storage_path: string;
  file_name: string;
  mime_type: string | null;
  size_bytes: number | null;
  replaced_at: ISODateTime;
}

export interface Summary extends BaseRow {
  subject_id: UUID;
  exam_id: UUID | null;
  title: string;
  status: SummaryStatus;
  content: string;
  current_version: number;
}

export interface SummaryVersion extends BaseRow {
  summary_id: UUID;
  version_number: number;
  content: string;
  change_note: string | null;
  source_material_ids: UUID[];
  created_by: 'usuario' | 'importacao' | 'ia';
}

export interface SummarySource extends BaseRow {
  summary_id: UUID;
  material_id: UUID;
}

export interface Flashcard extends BaseRow {
  subject_id: UUID;
  exam_id: UUID | null;
  topic_id: UUID | null;
  summary_id: UUID | null;
  question: string;
  answer: string;
  category: string | null;
  difficulty: Difficulty;
  origin: ContentOrigin;
  ease_factor: number;
  interval_days: number;
  repetitions: number;
  due_at: ISODateTime | null;
  last_result: FlashcardResult | null;
  last_reviewed_at: ISODateTime | null;
}

export interface FlashcardReview extends BaseRow {
  flashcard_id: UUID;
  result: FlashcardResult;
  reviewed_at: ISODateTime;
}

export interface Question extends BaseRow {
  subject_id: UUID;
  exam_id: UUID | null;
  topic_id: UUID | null;
  summary_id: UUID | null;
  type: QuestionType;
  statement: string;
  options: unknown[];
  correct_answer: unknown;
  explanation: string | null;
  difficulty: Difficulty;
  topic_label: string | null;
  origin: ContentOrigin;
}

export interface Quiz extends BaseRow {
  subject_id: UUID;
  exam_id: UUID | null;
  title: string;
  question_ids: UUID[];
  topic_ids: UUID[];
  difficulty: Difficulty | 'misto' | null;
  time_limit_minutes: number | null;
}

export interface QuizAttempt extends BaseRow {
  quiz_id: UUID;
  status: 'em_andamento' | 'finalizada';
  started_at: ISODateTime;
  finished_at: ISODateTime | null;
  elapsed_seconds: number;
  answers: Record<string, unknown>;
  results: unknown;
  score: number | null;
  correct_count: number | null;
  wrong_count: number | null;
  total_count: number | null;
}

export interface StudySession extends BaseRow {
  subject_id: UUID | null;
  exam_id: UUID | null;
  started_at: ISODateTime;
  duration_minutes: number;
  activity: StudyActivity;
  notes: string | null;
}

export interface CalendarEvent extends BaseRow {
  subject_id: UUID | null;
  exam_id: UUID | null;
  type: CalendarEventType;
  title: string;
  description: string | null;
  starts_at: ISODateTime;
  ends_at: ISODateTime | null;
  all_day: boolean;
  priority: ExamPriority;
  remind_at: ISODateTime | null;
  completed_at: ISODateTime | null;
}

export interface NotebookScan extends BaseRow {
  subject_id: UUID;
  exam_id: UUID | null;
  summary_id: UUID | null;
  topic_label: string | null;
  status: ScanStatus;
  page_count: number;
  recognized: unknown;
  error: string | null;
}

export interface NotebookScanPage extends BaseRow {
  scan_id: UUID;
  position: number;
  /** Fotografia original, exatamente como capturada/enviada. */
  original_path: string;
  /** Versão tratada (recorte, perspectiva, iluminação) usada para leitura. */
  processed_path: string | null;
  material_id: UUID | null;
  recognized_text: string | null;
  confidence: number | null;
  needs_review: boolean;
  review_notes: unknown;
  source: 'camera' | 'galeria';
  original_file_name: string | null;
  original_mime_type: string | null;
  original_size_bytes: number | null;
  processed_mime_type: string | null;
  processed_size_bytes: number | null;
  width: number | null;
  height: number | null;
  edits: Record<string, unknown>;
}

export interface AiOperation extends BaseRow {
  operation: string;
  model: string | null;
  status: 'pendente' | 'executando' | 'sucesso' | 'erro';
  input_tokens: number | null;
  output_tokens: number | null;
  estimated_cost_usd: number | null;
  related_table: string | null;
  related_id: UUID | null;
  error: string | null;
  finished_at: ISODateTime | null;
}

// ---------------------------------------------------------------------------
// Mapa de tabelas
// ---------------------------------------------------------------------------
export interface TableMap {
  profiles: Profile;
  academic_years: AcademicYear;
  subjects: Subject;
  exams: Exam;
  exam_topics: ExamTopic;
  materials: Material;
  material_versions: MaterialVersion;
  summaries: Summary;
  summary_versions: SummaryVersion;
  summary_sources: SummarySource;
  flashcards: Flashcard;
  flashcard_reviews: FlashcardReview;
  questions: Question;
  quizzes: Quiz;
  quiz_attempts: QuizAttempt;
  study_sessions: StudySession;
  calendar_events: CalendarEvent;
  notebook_scans: NotebookScan;
  notebook_scan_pages: NotebookScanPage;
  ai_operations: AiOperation;
}

export type TableName = keyof TableMap;
export type Row<T extends TableName> = TableMap[T];

type ManagedColumns = 'id' | 'user_id' | 'created_at' | 'updated_at';
/** Valores para inserção: todas as colunas de negócio; `id` opcional. */
export type Insert<T extends TableName> = Omit<Row<T>, ManagedColumns> & { id?: UUID };
/** Alteração parcial. */
export type Patch<T extends TableName> = Partial<Omit<Row<T>, ManagedColumns>>;

/** Ordem de dependência (pais antes dos filhos) — usada em backup/importação. */
export const TABLES_IN_DEPENDENCY_ORDER: TableName[] = [
  'profiles',
  'academic_years',
  'subjects',
  'exams',
  'exam_topics',
  'summaries',
  'summary_versions',
  'notebook_scans',
  'materials',
  'material_versions',
  'notebook_scan_pages',
  'summary_sources',
  'flashcards',
  'flashcard_reviews',
  'questions',
  'quizzes',
  'quiz_attempts',
  'study_sessions',
  'calendar_events',
];
