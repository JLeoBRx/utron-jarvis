import { useState, type FormEvent } from "react";

import { post } from "../api";
import { ErrorBox, Field, Notice, Symbol, useAction } from "../components/ui";
import { href } from "../router";
import type { Identity } from "../types";

export function LoginPage({ onSignedIn }: { onSignedIn: (identity: Identity) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const action = useAction();
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const identity = await action.run(() => post<Identity>("/auth/login", { email, password }));
    if (identity) {
      setPassword("");
      onSignedIn(identity);
    }
  };
  return (
    <main className="entrada">
      <form className="entrada__caixa" onSubmit={submit} aria-labelledby="entrada-titulo">
        <div className="entrada__marca"><Symbol size={44} /><span>SAFRA</span></div>
        <h1 id="entrada-titulo">Painel administrativo</h1>
        <Field label="E-mail" id="email">
          <input id="email" type="email" autoComplete="username" required maxLength={254} value={email} onChange={(e) => setEmail(e.target.value)} />
        </Field>
        <Field label="Senha" id="senha">
          <input id="senha" type="password" autoComplete="current-password" required maxLength={256} value={password} onChange={(e) => setPassword(e.target.value)} />
        </Field>
        <ErrorBox error={action.error} />
        <button className="botao botao--principal botao--largo" type="submit" disabled={action.busy}>{action.busy ? "Entrando…" : "Entrar"}</button>
        <p className="entrada__rodape"><a href={href("recuperar")}>Tenho um código de recuperação</a></p>
      </form>
    </main>
  );
}

export function RecoverPage() {
  const [token, setToken] = useState("");
  const [password, setPassword] = useState("");
  const [repeat, setRepeat] = useState("");
  const [done, setDone] = useState(false);
  const action = useAction();
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (password !== repeat) {
      action.setError(new Error("As senhas não coincidem."));
      return;
    }
    const ok = await action.run(() => post("/auth/recover", { token: token.trim(), new_password: password }));
    if (ok) setDone(true);
  };
  return (
    <main className="entrada">
      <form className="entrada__caixa" onSubmit={submit} aria-labelledby="recuperar-titulo">
        <div className="entrada__marca"><Symbol size={44} /><span>SAFRA</span></div>
        <h1 id="recuperar-titulo">Definir senha</h1>
        {done ? (
          <>
            <Notice tone="sucesso">Senha definida. Todas as sessões anteriores desta conta foram encerradas.</Notice>
            <a className="botao botao--principal botao--largo" href={href("")}>Ir para a entrada</a>
          </>
        ) : (
          <>
            <p className="campo__ajuda">Use o código de uso único que o administrador lhe entregou.</p>
            <Field label="Código de recuperação" id="codigo">
              <input id="codigo" autoComplete="one-time-code" required maxLength={200} value={token} onChange={(e) => setToken(e.target.value)} />
            </Field>
            <Field label="Nova senha" id="nova" hint="Pelo menos 12 caracteres. Uma frase longa é mais segura e mais fácil de lembrar.">
              <input id="nova" type="password" autoComplete="new-password" required minLength={12} maxLength={256} value={password} onChange={(e) => setPassword(e.target.value)} />
            </Field>
            <Field label="Repita a nova senha" id="repetir">
              <input id="repetir" type="password" autoComplete="new-password" required minLength={12} maxLength={256} value={repeat} onChange={(e) => setRepeat(e.target.value)} />
            </Field>
            <ErrorBox error={action.error} />
            <button className="botao botao--principal botao--largo" type="submit" disabled={action.busy}>Definir senha</button>
            <p className="entrada__rodape"><a href={href("")}>Voltar à entrada</a></p>
          </>
        )}
      </form>
    </main>
  );
}
