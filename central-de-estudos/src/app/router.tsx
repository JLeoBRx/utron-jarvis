import { createBrowserRouter } from 'react-router';
import { AppShell } from '@/components/layout/AppShell';
import { DashboardPage } from '@/features/dashboard/DashboardPage';
import { ExamDetailPage } from '@/features/exams/ExamDetailPage';
import { ExamsPage } from '@/features/exams/ExamsPage';
import { LibraryPage } from '@/features/library/LibraryPage';
import { MaterialPage } from '@/features/library/MaterialPage';
import { ModulePage } from '@/features/modules/ModulePage';
import { ScannerPage } from '@/features/scanner/ScannerPage';
import { NotFoundPage, RouteErrorPage } from '@/features/modules/NotFoundPage';
import { SettingsPage } from '@/features/settings/SettingsPage';
import { SubjectDetailPage } from '@/features/subjects/SubjectDetailPage';
import { SubjectsPage } from '@/features/subjects/SubjectsPage';

export const router = createBrowserRouter([
  // Scanner em tela cheia (sem o menu lateral): melhor para fotografar no celular.
  { path: 'scanner', element: <ScannerPage />, errorElement: <RouteErrorPage /> },
  {
    element: <AppShell />,
    errorElement: <RouteErrorPage />,
    children: [
      { index: true, element: <DashboardPage /> },
      { path: 'disciplinas', element: <SubjectsPage /> },
      { path: 'disciplinas/:subjectId', element: <SubjectDetailPage /> },
      { path: 'provas', element: <ExamsPage /> },
      { path: 'provas/:examId/:tab?', element: <ExamDetailPage /> },
      { path: 'biblioteca', element: <LibraryPage /> },
      { path: 'biblioteca/:materialId', element: <MaterialPage /> },
      { path: 'resumos', element: <ModulePage module="resumos" /> },
      { path: 'flashcards', element: <ModulePage module="flashcards" /> },
      { path: 'exercicios', element: <ModulePage module="exercicios" /> },
      { path: 'simulados', element: <ModulePage module="simulados" /> },
      { path: 'calendario', element: <ModulePage module="calendario" /> },
      { path: 'desempenho', element: <ModulePage module="desempenho" /> },
      { path: 'configuracoes', element: <SettingsPage /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
]);
