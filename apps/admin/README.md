# SAFRA Portal — painel administrativo

Interface do CMS em React + TypeScript (decisão AD-06). É compilada para arquivos estáticos que o próprio Portal
serve em `/admin/`, na mesma origem da API: sem CORS, com o cookie de sessão `SameSite=Strict` e a política de
segurança de conteúdo do Portal (nenhum script embutido).

A interface **não protege nada**: ela só esconde o que o papel do usuário não permite. Toda permissão é conferida
pelo servidor (`backend/portal`), e os testes do backend percorrem cada rota com cada papel.

| Tela | O que faz |
|---|---|
| Resumo | contagens reais, últimas alterações, atividades (todas para quem lê a auditoria; só as próprias para os demais) |
| Páginas e Notícias | lista com filtro; editor de blocos; rascunho, publicação, despublicação; versões e restauração; pré-visualização; exclusão com confirmação; SEO; imagem de destaque; categoria |
| Categorias | criar, renomear, remover |
| Mídia | envio (PNG, JPEG, GIF, WebP até 5 MiB), galeria, texto alternativo, categoria, uso, remoção controlada |
| Página inicial | título, subtítulo, imagem, botões, seções (ordem, ativação, destaques, links), notícias em destaque, rodapé e contato |
| Downloads | cadastro de versões; publicação bloqueada até a decisão de licença |
| Usuários | criar conta (nasce sem senha), papel, desativar, código de recuperação de uso único |
| Auditoria | registro de ações administrativas, com paginação |
| Minha conta | trocar a senha, ver e encerrar sessões |

```text
npm ci                  instala pelo arquivo de trava
npm run dev             desenvolvimento em http://localhost:5173/admin/ (repassa a API ao Portal em 127.0.0.1:47900)
npm test                testes de unidade e de componente (Vitest)
npm run build           compila em dist/ — o Portal passa a servir o painel em /admin/
```

Teste de ponta a ponta num navegador real, contra um Portal descartável:
`python scripts/e2e/portal_e2e.py` (na raiz; exige o painel compilado e o pacote `playwright` do Node).

`.npmrc` desliga a instalação automática de dependências pares: o npm 10 falha ao resolver os pares opcionais do
Vitest. Os pares necessários estão declarados no `package.json`.
