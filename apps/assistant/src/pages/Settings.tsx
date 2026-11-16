import { Card, ErrorState, Select, Skeleton, Switch, useToast } from "@safra/ui";

import { messageOf } from "../api";
import { PageHeader, useCanAct } from "../components";
import { useResource, useTitle } from "../hooks";
import { usePreferences } from "../preferences";
import type { Preferences, ProcessSettings } from "../types";

const LABELS: Record<string, string> = { confortavel: "Confortável", compacta: "Compacta", normal: "Normal", grande: "Grande" };

export function SettingsPage() {
  useTitle("Configurações");
  const toast = useToast();
  const canAct = useCanAct();
  const { prefs, save } = usePreferences();
  const process = useResource<ProcessSettings>("/system/settings");
  const update = async (key: keyof Preferences, value: string | boolean) => {
    try {
      await save(key, value);
      toast.notify("Preferência salva.");
    } catch (err) {
      toast.notify(messageOf(err), "erro");
    }
  };
  return (
    <div className="pagina">
      <PageHeader title="Configurações" description="Aparência da interface (guardada no seu banco) e a configuração do processo do Assistant." />
      <div className="grade grade--2">
        <Card title="Aparência" icon="configuracoes">
          {!prefs ? <Skeleton lines={3} /> : (
            <div className="formulario">
              <Switch label="Movimento reduzido" checked={prefs.movimento_reduzido.value === true} disabled={!canAct}
                help="Para o símbolo e reduz as transições. A preferência do sistema operacional também é respeitada."
                onChange={(value) => void update("movimento_reduzido", value)} />
              <Select label="Densidade" value={String(prefs.densidade.value)} disabled={!canAct}
                options={(prefs.densidade.choices ?? []).map((c) => ({ value: c, label: LABELS[c] ?? c }))}
                onChange={(e) => void update("densidade", e.target.value)} />
              <Select label="Tamanho do texto" value={String(prefs.tamanho_texto.value)} disabled={!canAct}
                options={(prefs.tamanho_texto.choices ?? []).map((c) => ({ value: c, label: LABELS[c] ?? c }))}
                onChange={(e) => void update("tamanho_texto", e.target.value)} />
            </div>
          )}
        </Card>
        <Card title="Processo do Assistant" icon="processador">
          {process.error ? <ErrorState message={process.error} onRetry={process.reload} /> : !process.data ? <Skeleton lines={5} /> : (
            <>
              <dl className="dados">
                <dt>Ambiente</dt><dd>{process.data.environment}</dd>
                <dt>Endereço</dt><dd>{process.data.api_host}:{process.data.api_port}</dd>
                <dt>Pasta de dados</dt><dd className="dados__valor-longo">{process.data.data_dir}</dd>
                <dt>Nível de registro</dt><dd>{process.data.log_level}</dd>
                <dt>Registro em arquivo</dt><dd>{process.data.log_to_file ? "sim" : "não"}</dd>
                <dt>Migrar ao iniciar</dt><dd>{process.data.migrate_on_start ? "sim" : "não"}</dd>
              </dl>
              <p className="apoio">{process.data.note}</p>
            </>
          )}
        </Card>
      </div>
    </div>
  );
}
