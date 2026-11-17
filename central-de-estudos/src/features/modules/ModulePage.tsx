import { ArrowRight, Check, Clock } from 'lucide-react';
import { Link } from 'react-router';
import { NAV_SECTIONS } from '@/app/navigation';
import { PageHeader } from '@/components/layout/PageHeader';
import { Badge } from '@/components/ui/Badge';
import { Card } from '@/components/ui/Card';

export type ModuleKey = 'resumos' | 'flashcards' | 'exercicios' | 'simulados' | 'calendario' | 'desempenho';

interface ModuleInfo {
  title: string;
  phase: number;
  summary: string;
  features: string[];
  meanwhile: { label: string; to: string };
}

/** Descrição honesta dos módulos que ainda serão entregues (sem ações simuladas). */
const MODULES: Record<ModuleKey, ModuleInfo> = {
  resumos: {
    title: 'Resumos',
    phase: 4,
    summary:
      'Editor de resumos completos, com a estrutura obrigatória (introdução, definições, fórmulas, exemplos, exercícios resolvidos, erros comuns e revisão final).',
    features: [
      'Fórmulas formatadas, tabelas comparativas e imagens',
      'Separação visível entre conteúdo do professor, explicações complementares e fontes externas',
      'Histórico de versões com comparação e restauração',
      '“Atualizar resumo com novos materiais” com prévia do que será adicionado, alterado ou removido',
      'Geração e atualização com IA a partir dos materiais (Fase 7)',
    ],
    meanwhile: { label: 'Organizar os conteúdos das provas', to: '/provas' },
  },
  flashcards: {
    title: 'Flashcards',
    phase: 5,
    summary: 'Cartões de revisão por prova, com animação de virar e registro do seu desempenho em cada cartão.',
    features: [
      'Autoavaliação: Não sei · Tenho dúvidas · Sei parcialmente · Sei muito bem',
      'Embaralhar, filtrar por assunto e revisar apenas os cartões errados',
      'Base pronta para repetição espaçada (intervalos e datas de revisão)',
      'Criação a partir dos resumos',
    ],
    meanwhile: { label: 'Ver minhas provas', to: '/provas' },
  },
  exercicios: {
    title: 'Exercícios',
    phase: 5,
    summary: 'Banco de questões vinculadas a cada prova e a cada conteúdo cobrado.',
    features: [
      'Múltipla escolha, verdadeiro ou falso, discursivas, cálculos, associação, lacunas, interpretação e problemas',
      'Enunciado, alternativas, resposta correta, explicação, dificuldade e assunto',
      'Criação manual e importação de questões geradas pelo Claude',
    ],
    meanwhile: { label: 'Ver minhas provas', to: '/provas' },
  },
  simulados: {
    title: 'Simulados',
    phase: 5,
    summary: 'Avaliações montadas a partir do seu banco de questões, com correção apenas ao final.',
    features: [
      'Escolha de disciplina, prova, assuntos, quantidade, dificuldade e tempo',
      'Progresso salvo automaticamente durante a prova',
      'Nota, acertos, erros, aproveitamento, tempo e explicações ao finalizar',
      'Novas tentativas e comparação de resultados',
    ],
    meanwhile: { label: 'Ver minhas provas', to: '/provas' },
  },
  calendario: {
    title: 'Calendário e planejamento',
    phase: 6,
    summary: 'Visão mensal e semanal das provas e das sessões de estudo, com metas e lembretes.',
    features: [
      'Provas cadastradas aparecem automaticamente nas suas datas',
      'Sessões de estudo, metas diárias, prioridades e lembretes',
      'Sugestões de planejamento com base nas datas, conteúdos, progresso e desempenho',
    ],
    meanwhile: { label: 'Ver próximas provas', to: '/provas' },
  },
  desempenho: {
    title: 'Desempenho',
    phase: 5,
    summary:
      'Estatísticas baseadas no que você realmente fez: conteúdos estudados, flashcards dominados, simulados e tempo de estudo.',
    features: [
      'Progresso por disciplina e por prova',
      'Aproveitamento e evolução das notas nos simulados',
      'Flashcards dominados, conteúdos pendentes e tempo de estudo registrado',
    ],
    meanwhile: { label: 'Ver o progresso no Dashboard', to: '/' },
  },
};

export function ModulePage({ module }: { module: ModuleKey }) {
  const info = MODULES[module];
  const nav = NAV_SECTIONS.flatMap((s) => s.items).find((item) => item.to === `/${module}`);
  const Icon = nav?.icon ?? Clock;
  return (
    <>
      <PageHeader
        title={info.title}
        description={info.summary}
        eyebrow={
          <Badge tone="accent">
            <Clock aria-hidden /> Chega na Fase {info.phase}
          </Badge>
        }
      />
      <Card className="animate-rise overflow-hidden">
        <div className="grid gap-0 md:grid-cols-[240px_1fr]">
          <div className="flex flex-col items-start gap-3 border-b border-border bg-surface-2/40 p-5 md:border-r md:border-b-0">
            <div className="flex size-11 items-center justify-center rounded-xl border border-border bg-surface text-accent-text">
              <Icon className="size-5" aria-hidden />
            </div>
            <p className="text-sm font-medium text-fg">Módulo em desenvolvimento</p>
            <p className="text-xs leading-relaxed text-fg-muted">
              A estrutura de dados deste módulo já está pronta no banco. A interface será entregue na Fase {info.phase} do
              roteiro — nenhuma função aqui é simulada.
            </p>
          </div>
          <div className="p-5">
            <p className="mb-3 text-xs font-medium tracking-wide text-fg-subtle uppercase">O que estará disponível</p>
            <ul className="space-y-2.5">
              {info.features.map((feature) => (
                <li key={feature} className="flex gap-2.5 text-sm text-fg-muted">
                  <Check className="mt-0.5 size-4 shrink-0 text-accent-text" aria-hidden />
                  <span>{feature}</span>
                </li>
              ))}
            </ul>
            <Link
              to={info.meanwhile.to}
              className="mt-5 inline-flex items-center gap-1.5 text-sm font-medium text-accent-text hover:underline"
            >
              Enquanto isso: {info.meanwhile.label} <ArrowRight className="size-4" aria-hidden />
            </Link>
          </div>
        </div>
      </Card>
    </>
  );
}
