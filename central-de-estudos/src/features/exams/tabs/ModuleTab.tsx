import { Clock, type LucideIcon } from 'lucide-react';
import { Badge } from '@/components/ui/Badge';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/misc';

interface ModuleTabProps {
  icon: LucideIcon;
  title: string;
  description: string;
  phase: number;
  count: number;
  noun: [string, string];
}

/**
 * Aba de módulo ainda não entregue: mostra a contagem REAL de itens
 * vinculados à prova e informa em que fase o módulo chega — sem botões falsos.
 */
export function ModuleTab({ icon: Icon, title, description, phase, count, noun }: ModuleTabProps) {
  return (
    <Card className="animate-rise">
      <EmptyState
        icon={<Icon />}
        title={count ? `${count} ${count === 1 ? noun[0] : noun[1]} vinculados a esta prova` : title}
        description={description}
        actions={
          <Badge tone="accent">
            <Clock aria-hidden /> Módulo disponível na Fase {phase}
          </Badge>
        }
      />
    </Card>
  );
}
