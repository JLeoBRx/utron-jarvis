import { useState, type FormEvent } from "react";

import { del, get, post, put } from "../api";
import { Empty, ErrorBox, Field, Loading, useAction, useLoad } from "../components/ui";
import type { Category } from "../types";
import { slugify } from "./ContentEditor";

export function CategoriesPage() {
  const { data, error, loading, reload } = useLoad(() => get<Category[]>("/categories"));
  const [name, setName] = useState("");
  const [editing, setEditing] = useState<Category | null>(null);
  const action = useAction();
  const create = async (event: FormEvent) => {
    event.preventDefault();
    if (await action.run(() => post("/categories", { name: name.trim(), slug: slugify(name) }))) {
      setName("");
      reload();
    }
  };
  const save = async () => {
    if (editing && await action.run(() => put(`/categories/${editing.id}`, { name: editing.name.trim(), slug: editing.slug }))) {
      setEditing(null);
      reload();
    }
  };
  const remove = async (category: Category) => {
    if (window.confirm(`Remover a categoria "${category.name}"? As notícias dela ficam sem categoria.`) && await action.run(() => del(`/categories/${category.id}`))) reload();
  };
  return (
    <>
      <header className="pagina__cabecalho"><h1>Categorias de notícias</h1></header>
      <form className="filtros" onSubmit={create}>
        <Field label="Nova categoria" id="nova-categoria"><input id="nova-categoria" required maxLength={80} value={name} onChange={(e) => setName(e.target.value)} /></Field>
        <button className="botao botao--principal" type="submit" disabled={action.busy || !slugify(name)}>Criar</button>
      </form>
      <ErrorBox error={action.error} />
      {loading && <Loading />}
      <ErrorBox error={error} onRetry={reload} />
      {data && data.length === 0 && <Empty>Nenhuma categoria.</Empty>}
      {data && data.length > 0 && (
        <ul className="lista-simples cartao">
          {data.map((category) => (
            <li key={category.id}>
              {editing?.id === category.id ? (
                <span className="linha">
                  <input aria-label="Nome" value={editing.name} maxLength={80} onChange={(e) => setEditing({ ...editing, name: e.target.value })} />
                  <input aria-label="Endereço" value={editing.slug} maxLength={80} onChange={(e) => setEditing({ ...editing, slug: e.target.value })} />
                  <button type="button" className="botao botao--principal" onClick={() => void save()}>Salvar</button>
                  <button type="button" className="botao botao--discreto" onClick={() => setEditing(null)}>Cancelar</button>
                </span>
              ) : (
                <>
                  <span>{category.name} <code>{category.slug}</code></span>
                  <span>
                    <button type="button" className="botao botao--discreto" onClick={() => setEditing(category)}>Editar</button>
                    <button type="button" className="botao botao--discreto" onClick={() => void remove(category)}>Remover</button>
                  </span>
                </>
              )}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
