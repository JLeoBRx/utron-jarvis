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

## Fase 3 — Biblioteca e scanner de cadernos ✅
- ✅ Migração aditiva (dados existentes preservados): versões de materiais, caderno digitalizado como material, metadados das páginas, HEIC/HEIF no bucket
- ✅ Upload de PDF, DOCX, PPTX, TXT, PNG, JPG/JPEG e WEBP (vários de uma vez, arrastar e soltar, status por arquivo, limite de 50 MB)
- ✅ Links de vídeos e sites (YouTube incorporado sem cookies)
- ✅ Organização por disciplina e prova (a prova depende da disciplina — sem misturar avaliações); categorias
- ✅ Visualização no app: PDF (pdf.js, inclusive no celular), DOCX, imagens, TXT; PPTX por download
- ✅ Download, "Abrir" com link temporário assinado, armazenamento privado no Supabase
- ✅ Substituição preservando o original (versões anteriores para download)
- ✅ Exclusão com confirmação (remove versões e arquivos)
- ✅ Busca e filtros (disciplina, prova, categoria, tipo) guardados na URL
- ✅ Aba "Materiais" da prova, card na disciplina, "Adicionar material" no Dashboard
- ✅ Backup .zip com todos os arquivos; restauração em outra conta/modo
- ✅ "Fotografar meu caderno": câmera ao vivo (várias páginas em sequência, lanterna, troca de câmera), galeria e câmera do sistema
- ✅ Detecção automática da folha; recorte com 4 cantos e correção de perspectiva; girar; iluminação (Original, Realçar, Documento, P&B), brilho e contraste
- ✅ Reordenar, excluir e adicionar páginas; revisão de todas as imagens antes de salvar
- ✅ Disciplina, prova e assunto (preenchidos automaticamente quando aberto numa disciplina/prova)
- ✅ Foto original sempre preservada + versão tratada; rascunho automático no aparelho
- ✅ Permissão da câmera: concedida, negada, indisponível, em uso, sem HTTPS — com orientação e alternativas
- ✅ Preparação para IA: dados das páginas, contrato do pedido/resposta (`src/data/ai/scanReading.ts`) e modo manual (baixar páginas + copiar instruções)

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
- 🔜 Leitura das digitalizações usando o contrato já pronto (`buildScanReadingRequest` → modelo multimodal → `parseScanReadingResult`)
- 🔜 Tela de conferência do texto reconhecido (trechos duvidosos ao lado da foto original)
- 🔜 Geração/atualização de resumos, questões e flashcards a partir do conteúdo conferido

## Fase 8 — Testes e publicação 🔜
- 🔜 Revisão de segurança (incluindo Content-Security-Policy), acessibilidade e desempenho
- 🔜 Teste em aparelhos reais (Android e iPhone) da câmera e de fotos HEIC
- 🔜 Deploy na Netlify conectado ao Supabase de produção

## Pendências que dependem de você ⚠️
- ⚠️ Criar o projeto no Supabase e aplicar as **3** migrações — `docs/CONFIGURACAO.md`
- ⚠️ Cadastrar `VITE_SUPABASE_URL` e `VITE_SUPABASE_PUBLISHABLE_KEY` na Netlify
- ⚠️ Confirmar o código institucional de **Máquinas e Comandos Industriais**
  (edite a disciplina quando souber; até lá ela mostra "Código a confirmar")
- ⚠️ (Fase 7) Chave da API da Anthropic
