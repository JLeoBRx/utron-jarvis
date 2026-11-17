import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo } from 'react';
import { toast } from 'sonner';
import { errorMessage } from '@/lib/errors';
import { groupTopicsByExam } from '@/lib/progress';
import { useBackend } from './DataContext';
import type { DataBackend } from './backend/types';
import { listRecentActivity } from './services/activity';
import { listExams } from './services/exams';
import { listMaterials, listMaterialVersions } from './services/materials';
import { listScanPages } from './services/scans';
import { getContentCounts, getMaterialCountsBySubject } from './services/stats';
import { listSubjects } from './services/subjects';
import { listTopics } from './services/topics';
import { getProfile, listAcademicYears, pickActiveYear } from './services/workspace';
import type { UUID } from './types';

/** Prefixo das chaves de cache: isola dados por modo e por usuário. */
export function scopeKey(db: DataBackend) {
  return [db.mode, db.userId] as const;
}

export function useAcademicYears() {
  const db = useBackend();
  return useQuery({ queryKey: [...scopeKey(db), 'academic_years'], queryFn: () => listAcademicYears(db) });
}

/** Anos letivos + ano ativo. */
export function useWorkspace() {
  const years = useAcademicYears();
  const activeYear = useMemo(() => pickActiveYear(years.data ?? []), [years.data]);
  return { years: years.data ?? [], activeYear, isLoading: years.isLoading, error: years.error, refetch: years.refetch };
}

export function useProfile() {
  const db = useBackend();
  return useQuery({ queryKey: [...scopeKey(db), 'profiles'], queryFn: () => getProfile(db) });
}

export function useSubjects(academicYearId: UUID | null | undefined) {
  const db = useBackend();
  return useQuery({
    queryKey: [...scopeKey(db), 'subjects', academicYearId],
    queryFn: () => listSubjects(db, academicYearId!),
    enabled: Boolean(academicYearId),
  });
}

/** Todas as provas do usuário (filtradas por ano letivo nos componentes). */
export function useAllExams() {
  const db = useBackend();
  return useQuery({ queryKey: [...scopeKey(db), 'exams'], queryFn: () => listExams(db) });
}

export function useAllTopics() {
  const db = useBackend();
  return useQuery({ queryKey: [...scopeKey(db), 'exam_topics'], queryFn: () => listTopics(db) });
}

/**
 * Visão consolidada do ano letivo ativo: disciplinas, provas e conteúdos,
 * já relacionados entre si.
 */
export function useYearData() {
  const { activeYear, isLoading: yearsLoading, error: yearsError } = useWorkspace();
  const subjects = useSubjects(activeYear?.id);
  const exams = useAllExams();
  const topics = useAllTopics();

  return useMemo(() => {
    const subjectList = subjects.data ?? [];
    const subjectIds = new Set(subjectList.map((s) => s.id));
    const subjectById = new Map(subjectList.map((s) => [s.id, s]));
    const examList = (exams.data ?? []).filter((e) => subjectIds.has(e.subject_id));
    const examIds = new Set(examList.map((e) => e.id));
    const topicsByExam = groupTopicsByExam((topics.data ?? []).filter((t) => examIds.has(t.exam_id)));
    return {
      activeYear,
      subjects: subjectList,
      subjectById,
      exams: examList,
      topicsByExam,
      isLoading: yearsLoading || subjects.isLoading || exams.isLoading || topics.isLoading,
      error: yearsError ?? subjects.error ?? exams.error ?? topics.error ?? null,
      refetch: () => {
        void subjects.refetch();
        void exams.refetch();
        void topics.refetch();
      },
    };
  }, [activeYear, subjects, exams, topics, yearsLoading, yearsError]);
}

export function useContentCounts(subjectIds: UUID[]) {
  const db = useBackend();
  return useQuery({
    queryKey: [...scopeKey(db), 'content_counts', subjectIds],
    queryFn: () => getContentCounts(db, subjectIds),
    enabled: subjectIds.length > 0,
  });
}

export function useMaterialCounts(subjectIds: UUID[]) {
  const db = useBackend();
  return useQuery({
    queryKey: [...scopeKey(db), 'material_counts', subjectIds],
    queryFn: () => getMaterialCountsBySubject(db, subjectIds),
    enabled: subjectIds.length > 0,
  });
}

export function useRecentActivity(subjectIds: UUID[]) {
  const db = useBackend();
  return useQuery({
    queryKey: [...scopeKey(db), 'activity', subjectIds],
    queryFn: () => listRecentActivity(db, subjectIds),
    enabled: subjectIds.length > 0,
  });
}

interface ActionOptions<TResult> {
  success?: string | ((result: TResult) => string);
  onSuccess?: (result: TResult) => void;
}

/**
 * Mutação padrão: executa a ação no backend, mostra o resultado em um aviso
 * e atualiza todas as consultas do usuário.
 */
export function useAction<TArgs, TResult>(
  action: (db: DataBackend, args: TArgs) => Promise<TResult>,
  options: ActionOptions<TResult> = {},
) {
  const db = useBackend();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (args: TArgs) => action(db, args),
    onSuccess: async (result) => {
      const message = typeof options.success === 'function' ? options.success(result) : options.success;
      if (message) toast.success(message);
      // Navegação/fechamento primeiro; depois as consultas são atualizadas.
      options.onSuccess?.(result);
      await queryClient.invalidateQueries({ queryKey: scopeKey(db) });
    },
    onError: (error) => {
      toast.error(errorMessage(error));
    },
  });
}

/** Contagens reais dos itens vinculados a uma prova (abas da página da prova). */
export function useExamCounts(examId: UUID | undefined) {
  const db = useBackend();
  return useQuery({
    queryKey: [...scopeKey(db), 'exam_counts', examId],
    enabled: Boolean(examId),
    queryFn: async () => {
      const where = { exam_id: examId! };
      const [materials, summaries, flashcards, questions, quizzes] = await Promise.all([
        db.count('materials', where),
        db.count('summaries', where),
        db.count('flashcards', where),
        db.count('questions', where),
        db.count('quizzes', where),
      ]);
      return { materials, summaries, flashcards, questions, quizzes };
    },
  });
}

// ---------------------------------------------------------------------------
// Biblioteca
// ---------------------------------------------------------------------------
export function useMaterials(subjectIds: UUID[]) {
  const db = useBackend();
  return useQuery({
    queryKey: [...scopeKey(db), 'materials', subjectIds],
    queryFn: () => listMaterials(db, subjectIds),
    enabled: subjectIds.length > 0,
  });
}

export function useMaterial(id: UUID | undefined) {
  const db = useBackend();
  return useQuery({
    queryKey: [...scopeKey(db), 'material', id],
    queryFn: () => db.get('materials', id!),
    enabled: Boolean(id),
  });
}

export function useMaterialVersions(id: UUID | undefined) {
  const db = useBackend();
  return useQuery({
    queryKey: [...scopeKey(db), 'material_versions', id],
    queryFn: () => listMaterialVersions(db, id!),
    enabled: Boolean(id),
  });
}

export function useScan(scanId: UUID | null | undefined) {
  const db = useBackend();
  return useQuery({
    queryKey: [...scopeKey(db), 'scan', scanId],
    queryFn: async () => {
      const [scan, pages] = await Promise.all([db.get('notebook_scans', scanId!), listScanPages(db, scanId!)]);
      return { scan, pages };
    },
    enabled: Boolean(scanId),
  });
}

/**
 * Conteúdo de um arquivo do Storage, baixado pela sessão do usuário (o
 * arquivo nunca fica público). Retorna também uma URL local para exibição.
 */
export function useStoredFile(path: string | null | undefined) {
  const db = useBackend();
  const query = useQuery({
    queryKey: [...scopeKey(db), 'file', path],
    queryFn: () => db.storage.download(path!),
    enabled: Boolean(path),
    staleTime: 5 * 60_000,
    gcTime: 5 * 60_000,
  });
  const url = useMemo(() => (query.data ? URL.createObjectURL(query.data) : null), [query.data]);
  useEffect(() => () => {
    if (url) URL.revokeObjectURL(url);
  }, [url]);
  return { ...query, url };
}
