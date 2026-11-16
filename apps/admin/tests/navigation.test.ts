import { describe, expect, it } from "vitest";

import { visibleNav } from "../src/App";
import type { Permission } from "../src/types";

// Retrato da matriz do servidor (backend/portal/src/safra_portal/domain/permissions.py). A interface só esconde;
// quem recusa é o servidor — e os testes do backend conferem isso rota a rota.
const EDITOR: Permission[] = ["admin.access", "dashboard.read", "content.read", "content.edit", "categories.manage", "media.read", "media.upload", "media.delete"];
const PUBLICADOR: Permission[] = ["admin.access", "dashboard.read", "content.read", "content.publish", "media.read"];

describe("navegação conforme o papel", () => {
  it("o editor não vê usuários, auditoria, página inicial nem downloads", () => {
    const labels = visibleNav(EDITOR).map((item) => item.label);
    expect(labels).toEqual(["Resumo", "Páginas", "Notícias", "Categorias", "Mídia"]);
  });

  it("o publicador vê conteúdo e mídia, sem administrar", () => {
    expect(visibleNav(PUBLICADOR).map((item) => item.label)).toEqual(["Resumo", "Páginas", "Notícias", "Mídia"]);
  });

  it("sem permissão nenhuma, nada aparece", () => {
    expect(visibleNav([])).toEqual([]);
  });
});
