# Roteiro — tarefas concluídas e pendentes

Legenda: ✅ concluído e testado · 🔜 pendente · ⚠️ depende de você

## Fase 1 — Fundação ✅
- ✅ Arquitetura (React + TS + Vite + Tailwind; Supabase; Netlify) — `docs/ARQUITETURA.md`
- ✅ Identidade visual própria: marca, paleta, tipografia (Inter / JetBrains Mono), tema escuro padrão e claro
- ✅ Kit de componentes reutilizáveis (botões, cards, diálogos, menus, progresso, estados vazios)
- ✅ Menu lateral com 11 itens, ícones, página atual destacada, recolhimento persistente; gaveta no celular
- ✅ Esquema completo do banco (19 tabelas), RLS e Storage privado — testados em Supabase real
- ✅ Camada de dados com dois adaptadores (Supabase / local) e tratamento de erros em português
- ✅ Dashboard: 8 indicadores, próximas provas, preparação por disciplina, atividades recentes, acesso rápido
- ✅ Autenticação (cadastro, login, recuperação de senha) no modo nuvem

## Fase 2 — Organização escolar ✅
- ✅ Anos letivos (criar, editar, ativar, excluir) — expansível para novos períodos
- ✅ 20 disciplinas oficiais com nomes e códigos exatos; Formação Geral × Técnica
- ✅ Disciplinas: criar, editar, arquivar, excluir (com prévia do impacto e confirmação digitada), busca e filtros
- ✅ Página da disciplina: dados, provas, indicadores e progresso
- ✅ Provas: cadastro com validação, status (5), prioridade, data/horário opcionais, professor, descrição, nota
- ✅ Lista de provas com filtros (período, disciplina, status, prioridade, busca) salvos na URL
- ✅ Página da prova com 8 abas (Visão geral, Conteúdos, Materiais, Resumo, Flashcards, Exercícios, Simulado, Desempenho)
- ✅ Conteúdos: cadastro em lote (colar lista), status de estudo, anotações, reordenação, remoção
- ✅ Progresso baseado no estudo registrado; "Próximos passos" calculados a partir dos dados
- ✅ Configurações: tema, perfil, anos letivos, backup/restauração JSON (sem sobrescrever), armazenamento
- ✅ Restaurar backup direto na tela de início (migração do modo local para a nuvem)

## Fase 3 — Biblioteca 🔜
- 🔜 Upload (PDF, DOCX, PPTX, TXT, PNG, JPG/JPEG, WEBP) e links (vídeos, sites)
- 🔜 Visualização, download, substituição preservando o original, exclusão
- 🔜 Categorias, busca e filtros; organização por disciplina e por prova
- 🔜 "Fotografar meu caderno": captura pela câmera/galeria, várias páginas, recorte, rotação, perspectiva, contraste, reordenação
- 🔜 Arquivos incluídos no backup

## Fase 4 — Resumos 🔜
- 🔜 Editor com a estrutura obrigatória (13 seções), fórmulas (LaTeX), tabelas e imagens
- 🔜 Marcação de origem: professor × complementar × externo; trechos para revisão
- 🔜 Histórico de versões, comparação e restauração
- 🔜 "Atualizar resumo com novos materiais" com prévia de adições/alterações/remoções
- 🔜 Modo manual de IA: exportar materiais, copiar prompts, importar resumos/questões

## Fase 5 — Aprendizado 🔜
- 🔜 Flashcards com animação, autoavaliação em 4 níveis e repetição espaçada
- 🔜 Exercícios (8 tipos), criação manual e importação
- 🔜 Simulados com tempo, salvamento de progresso, correção ao final e novas tentativas
- 🔜 Página de Desempenho com gráficos

## Fase 6 — Planejamento 🔜
- 🔜 Calendário mensal/semanal, sessões de estudo, metas diárias, lembretes, sugestões de planejamento

## Fase 7 — Exportação e IA 🔜
- 🔜 PDFs com capa, sumário, fórmulas, tabelas, imagens e numeração
- 🔜 Funções no servidor (Netlify) para a API da Anthropic, com registro de consumo
- 🔜 Leitura de documentos e do caderno (visão), geração/atualização de resumos, questões e flashcards

## Fase 8 — Testes e publicação 🔜
- 🔜 Revisão de segurança (incluindo Content-Security-Policy), acessibilidade e desempenho
- 🔜 Deploy na Netlify conectado ao Supabase de produção

## Pendências que dependem de você ⚠️
- ⚠️ Criar o projeto no Supabase e aplicar as migrações — `docs/CONFIGURACAO.md`
- ⚠️ Cadastrar `VITE_SUPABASE_URL` e `VITE_SUPABASE_PUBLISHABLE_KEY` na Netlify
- ⚠️ Confirmar o código institucional de **Máquinas e Comandos Industriais**
  (edite a disciplina quando souber; até lá ela mostra "Código a confirmar")
- ⚠️ (Fase 7) Chave da API da Anthropic
