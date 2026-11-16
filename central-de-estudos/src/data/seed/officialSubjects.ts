import type { SubjectCategory } from '../types';

export interface OfficialSubject {
  name: string;
  /** `null` = código ainda não confirmado pela instituição (não inventar). */
  code: string | null;
  category: SubjectCategory;
  color: string;
}

/**
 * As 20 disciplinas oficiais, com nomes e códigos institucionais exatamente
 * como informados. Começam vazias: sem professor, descrição ou conteúdos.
 */
export const OFFICIAL_SUBJECTS: readonly OfficialSubject[] = [
  // Formação Geral
  { name: 'Arte 2', code: 'INT.12841', category: 'formacao_geral', color: 'fuchsia' },
  { name: 'Educação Física 2', code: 'INT.12843', category: 'formacao_geral', color: 'green' },
  { name: 'Linguagens Artísticas e Literárias', code: 'INT.12842', category: 'formacao_geral', color: 'pink' },
  { name: 'Língua Inglesa 2', code: 'INT.12844', category: 'formacao_geral', color: 'sky' },
  { name: 'Língua Portuguesa e Redação 2', code: 'INT.12840', category: 'formacao_geral', color: 'rose' },
  { name: 'Matemática 2', code: 'INT.12845', category: 'formacao_geral', color: 'indigo' },
  { name: 'Biologia 2', code: 'INT.12846', category: 'formacao_geral', color: 'emerald' },
  { name: 'Física 2', code: 'INT.12847', category: 'formacao_geral', color: 'blue' },
  { name: 'Química 2', code: 'INT.12848', category: 'formacao_geral', color: 'teal' },
  { name: 'Filosofia 2', code: 'INT.12851', category: 'formacao_geral', color: 'violet' },
  { name: 'Geografia 2', code: 'INT.12850', category: 'formacao_geral', color: 'lime' },
  { name: 'História 2', code: 'INT.12849', category: 'formacao_geral', color: 'amber' },
  { name: 'Sociologia 2', code: 'INT.12852', category: 'formacao_geral', color: 'orange' },
  // Formação Técnica
  { name: 'Análise de Circuitos em Correntes Alternadas', code: 'INT.12855', category: 'formacao_tecnica', color: 'yellow' },
  { name: 'Manufatura Auxiliada por Computador', code: 'INT.12856', category: 'formacao_tecnica', color: 'cyan' },
  { name: 'Máquinas e Comandos Industriais', code: null, category: 'formacao_tecnica', color: 'red' },
  { name: 'Projeto Integrador', code: 'INT.12858', category: 'formacao_tecnica', color: 'purple' },
  { name: 'Resistência dos Materiais', code: 'INT.12859', category: 'formacao_tecnica', color: 'slate' },
  { name: 'Sistemas Analógicos', code: 'INT.12854', category: 'formacao_tecnica', color: 'copper' },
  { name: 'Sistemas Digitais', code: 'INT.12853', category: 'formacao_tecnica', color: 'stone' },
];
