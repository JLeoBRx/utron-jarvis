import { useEffect, useState, type FormEvent } from "react";

import { Button, Card, Skeleton, TextField, useToast } from "@safra/ui";

import { messageOf } from "../api";
import { PageHeader, useCanAct } from "../components";
import { useTitle } from "../hooks";
import { usePreferences } from "../preferences";

export function ProfilePage() {
  useTitle("Perfil e preferências");
  const toast = useToast();
  const canAct = useCanAct();
  const { prefs, save } = usePreferences();
  const [nome, setNome] = useState("");
  const [tratamento, setTratamento] = useState("");
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    if (!prefs) return;
    setNome(String(prefs.nome.value));
    setTratamento(String(prefs.tratamento.value));
  }, [prefs]);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    try {
      await save("nome", nome);
      await save("tratamento", tratamento);
      toast.notify("Perfil salvo.");
    } catch (err) {
      toast.notify(messageOf(err), "erro");
    } finally {
      setSaving(false);
    }
  };
  return (
    <div className="pagina">
      <PageHeader title="Perfil e preferências" description="Como o SAFRA te chama. Fica só neste computador." />
      <Card title="Você" icon="perfil">
        {!prefs ? <Skeleton lines={3} /> : (
          <form className="formulario formulario--estreito" onSubmit={submit}>
            <TextField label="Seu nome" maxLength={60} value={nome} onChange={(e) => setNome(e.target.value)} help="Aparece na saudação do início." />
            <TextField label="Como o SAFRA se dirige a você" maxLength={40} value={tratamento} onChange={(e) => setTratamento(e.target.value)}
              help="Opcional. Ex.: pelo nome, por você. Será usado nas respostas quando o gateway de IA existir." />
            <div className="formulario__acoes">
              <Button type="submit" variant="principal" loading={saving} disabled={!canAct}>Salvar</Button>
            </div>
          </form>
        )}
      </Card>
    </div>
  );
}
