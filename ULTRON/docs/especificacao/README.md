# Especificação da transformação em SAFRA — Fase 2

Situação em 14/11/2026: **especificação concluída; nenhuma linha de código do produto foi alterada.** A
implementação começa pela Fase 3 (preservação), descrita no plano de migração.

Origem: auditoria de 13/11/2026 (`../technical/AUDITORIA_TRANSFORMACAO_SAFRA.md`), aprovada pelo autor com sete
direcionamentos, todos incorporados.

## Documentos

| Ordem de leitura | Documento | Conteúdo |
|---|---|---|
| 1 | [`DECISOES.md`](DECISOES.md) | Registro de Decisões Técnicas: 27 decisões, com contexto, consequências e situação. Duas estão abertas |
| 2 | [`ARQUITETURA_DESTINO.md`](ARQUITETURA_DESTINO.md) | processos, domínios, regra de dependência, inicialização, isolamento de falhas, segurança, dados |
| 3 | [`CONTRATO_V1.md`](CONTRATO_V1.md) | contrato único entre o núcleo e qualquer interface: rotas HTTP, eventos, erros, sessões |
| 4 | [`REQUISITOS_SAFRA.md`](REQUISITOS_SAFRA.md) | requisitos funcionais, não funcionais, de segurança e restrições do novo escopo, com origem e forma de verificação |
| 5 | [`ESPECIFICACAO_DA_INTERFACE.md`](ESPECIFICACAO_DA_INTERFACE.md) | dois contextos, paridade com a interface atual, símbolo, design system, autorização, responsividade |
| 6 | [`PLANO_DE_MIGRACAO.md`](PLANO_DE_MIGRACAO.md) | etapas M3 a M8, critérios de saída, mapas de código, banco e configurações, reversão, cronograma |

Diagramas (fontes em `../diagrams/src/`, imagens em `../diagrams/`): 11 processos, 12 domínios, 13
inicialização, 14 autenticação, 15 isolamento de falhas, 16 etapas da migração, 17 dados de Projetos.

## Como as sete decisões do autor entraram

| Direcionamento | Onde |
|---|---|
| 1. TARDIS e ULTRON: sai o nome e o tema, fica a função, com nomes próprios | ADR-010, ADR-011, ADR-012; plano §9.1 |
| 2. NOCTARIO: exportar tudo antes de remover | ADR-013; plano §9.2 |
| 3. Nomes internos: troca gradual, com compatibilidade; pasta de dados intocada até tudo funcionar | ADR-014; plano M5.12 e M8 |
| 4. Ativação só por "Safra", mais tecla de atalho | ADR-015; RF-09, RF-10; plano M5.5 |
| 5. Os 24 documentos históricos numa pasta de legado, sem apagar nenhum | ADR-016; plano §9.7 |
| 6. TCC reescrito; resultados de 3D e sincronização labial fora | ADR-017; plano M7 |
| 7. Painel local primeiro, responsivo e preparado para celular; acesso externo depois | ADR-018; arquitetura §10; interface §8 |

## O que continua aberto

| Assunto | Quem decide | Bloqueia |
|---|---|---|
| Licença do SAFRA, dado que a biblioteca de voz é GPL-3.0 (ADR-024) | autor e instituição | publicar ou distribuir; não o desenvolvimento |
| Tom e tratamento do assistente (ADR-026) | autor | nada: vale a proposta se não houver objeção |
| Desenho final do símbolo | autor, entre três estudos | fechar as telas (etapa M4.3) |

## Limites desta especificação

- Nenhuma tecnologia nova foi instalada ou medida; as metas são metas.
- O comportamento no Windows real só será conhecido com o roteiro de validação.
- O contrato pode ganhar rotas durante a implementação; mudanças entram como decisão registrada.
