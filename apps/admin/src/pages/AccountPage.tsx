import { useState, type FormEvent } from "react";

import { del, get, post } from "../api";
import { ErrorBox, Field, Loading, Notice, useAction, useLoad } from "../components/ui";
import { when } from "../format";
import { useSession } from "../session";
import type { SessionInfo } from "../types";

export function AccountPage() {
  const { identity } = useSession();
  const sessions = useLoad(() => get<SessionInfo[]>("/sessions"));
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [repeat, setRepeat] = useState("");
  const [done, setDone] = useState(false);
  const action = useAction();
  const change = async (event: FormEvent) => {
    event.preventDefault();
    setDone(false);
    if (next !== repeat) {
      action.setError(new Error("As senhas novas não coincidem."));
      return;
    }
    if (await action.run(() => post("/auth/password", { current, new: next }))) {
      setDone(true);
      setCurrent(""); setNext(""); setRepeat("");
      sessions.reload();
    }
  };
  const revoke = async (session: SessionInfo) => { if (await action.run(() => del(`/sessions/${session.id}`))) sessions.reload(); };
  return (
    <>
      <header className="pagina__cabecalho"><h1>Minha conta</h1><p>{identity.user.name} · {identity.user.email} · {identity.user.role_name}</p></header>
      <div className="grade-2">
        <form className="cartao" onSubmit={change} aria-labelledby="trocar-senha">
          <h2 id="trocar-senha">Trocar a senha</h2>
          <Field label="Senha atual" id="atual"><input id="atual" type="password" autoComplete="current-password" required value={current} onChange={(e) => setCurrent(e.target.value)} /></Field>
          <Field label="Nova senha" id="nova-senha" hint="Pelo menos 12 caracteres."><input id="nova-senha" type="password" autoComplete="new-password" required minLength={12} maxLength={256} value={next} onChange={(e) => setNext(e.target.value)} /></Field>
          <Field label="Repita a nova senha" id="repetir-senha"><input id="repetir-senha" type="password" autoComplete="new-password" required minLength={12} maxLength={256} value={repeat} onChange={(e) => setRepeat(e.target.value)} /></Field>
          {done && <Notice tone="sucesso">Senha trocada. As suas outras sessões foram encerradas.</Notice>}
          <ErrorBox error={action.error} />
          <button className="botao botao--principal" type="submit" disabled={action.busy}>Trocar senha</button>
        </form>
        <section className="cartao" aria-labelledby="sessoes">
          <h2 id="sessoes">Sessões abertas</h2>
          {sessions.loading && <Loading />}
          <ErrorBox error={sessions.error} onRetry={sessions.reload} />
          <ul className="lista-simples">
            {(sessions.data ?? []).map((s) => (
              <li key={s.id}>
                <span>{s.current ? "Esta sessão" : s.user_agent.slice(0, 60) || "Navegador"}<br /><small>{s.ip} · última atividade {when(s.last_seen_at)}</small></span>
                {!s.current && <button type="button" className="botao botao--discreto" onClick={() => void revoke(s)}>Encerrar</button>}
              </li>
            ))}
          </ul>
        </section>
      </div>
    </>
  );
}
