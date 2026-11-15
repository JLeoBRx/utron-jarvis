"""Conteúdo inicial do site, criado uma única vez num banco vazio. Depois disso, tudo é editado pelo painel.

O texto descreve o estado REAL do projeto em novembro de 2026: nada aqui apresenta como disponível o que ainda
está em desenvolvimento. As páginas legais são modelos e dizem isso na primeira linha.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session as Db

from ..cms import content, homepage
from ..domain.models import Content, SiteSetting

DRAFT_NOTICE = {"type": "callout", "tone": "attention", "title": "Texto-modelo",
                "text": "Este texto é um modelo inicial e ainda não foi revisado pelo responsável pelo projeto. "
                        "Ele será substituído pela versão definitiva antes da publicação oficial do site."}
BUILDING = {"type": "callout", "tone": "status", "title": "Em reconstrução",
            "text": "O SAFRA 4 está em desenvolvimento e ainda não está disponível para uso. "
                    "Esta página descreve o que está pronto, o que está em andamento e o que está planejado."}


def p(text: str) -> dict:
    return {"type": "paragraph", "text": text}


def h(text: str, level: int = 2) -> dict:
    return {"type": "heading", "level": level, "text": text}


def card(title: str, text: str, tag: str = "") -> dict:
    return {"title": title, "text": text, "tag": tag}


PAGES: list[dict] = [
    {"slug": "sobre", "title": "Sobre o SAFRA",
     "summary": "O que é o SAFRA, de onde vem e em que estágio está.",
     "blocks": [
         BUILDING,
         p("O SAFRA é uma plataforma inteligente integrada: um assistente que roda no computador do usuário, com "
           "voz, memória e ferramentas sob controle de permissões, acompanhado deste portal público."),
         h("Origem"),
         p("O projeto nasceu como trabalho de conclusão de um curso técnico em Desenvolvimento de Sistemas, com "
           "conclusão prevista para 2027. A geração anterior do software (3.0) funciona e é coberta por testes "
           "automatizados; a geração 4 é uma reconstrução da arquitetura, feita para ser mais confiável, segura e "
           "fácil de manter."),
         h("Prioridades"),
         {"type": "list", "ordered": True, "items": ["Confiabilidade", "Segurança", "Estabilidade", "Desempenho",
                                                     "Experiência de uso", "Facilidade de manutenção"]},
         h("Como o projeto é conduzido"),
         p("Cada funcionalidade passa por quatro estados, registrados separadamente: planejada, implementada, "
           "testada e validada em ambiente real. O que aparece neste site segue essa distinção."),
     ]},
    {"slug": "funcionalidades", "title": "Funcionalidades",
     "summary": "O que o SAFRA faz e em que estado está cada parte.",
     "blocks": [
         BUILDING,
         p("As funções abaixo existem na geração 3.0 e estão sendo reconstruídas na geração 4. O selo de cada item "
           "indica o estado **na geração 4**."),
         {"type": "cards", "items": [
             card("Conversa por texto", "Pedidos em português, respondidos por regras diretas ou por um modelo de linguagem.", "em desenvolvimento"),
             card("Conversa por voz", "Reconhecimento e síntese de fala executados no próprio computador.", "em desenvolvimento"),
             card("Memória persistente", "Lembretes, anotações e fatos guardados num banco local e privado.", "em desenvolvimento"),
             card("Projetos e contextos", "Conversas, memórias e tarefas organizadas por projeto.", "planejado"),
             card("Ferramentas com permissão", "Toda ação no computador passa por um executor único, com permissões, confirmação e verificação do resultado.", "em desenvolvimento"),
             card("Inteligência artificial híbrida", "Modelos locais e provedores remotos atrás de um mesmo contrato, com escolha por privacidade, custo e disponibilidade.", "planejado"),
             card("Aplicativo para Windows", "Janela, bandeja do sistema, notificações e início com o Windows.", "planejado"),
             card("Console operacional", "A mesma interface de operação aberta no navegador do próprio computador.", "planejado"),
             card("Portal e painel administrativo", "Este site, com o conteúdo administrado por um painel próprio.", "implementado"),
         ]},
     ]},
    {"slug": "inteligencia-artificial", "title": "Inteligência artificial",
     "summary": "Estratégia híbrida: modelos locais primeiro, provedores remotos quando o usuário permitir.",
     "blocks": [
         BUILDING,
         p("O SAFRA foi desenhado para funcionar com modelos de linguagem executados no próprio computador e, "
           "opcionalmente, com provedores remotos."),
         h("Como a escolha é feita"),
         {"type": "list", "ordered": False, "items": [
             "**Privacidade**: conteúdo marcado como privado não sai do computador sem uma política explícita e o consentimento do usuário.",
             "**Disponibilidade**: se um provedor falhar, o seguinte da lista é tentado; as funções que não dependem dele continuam.",
             "**Custo e latência**: cada chamada tem prazo, pode ser cancelada e é medida.",
             "**Capacidade**: o modelo é escolhido conforme a tarefa e o tamanho do contexto.",
         ]},
         {"type": "callout", "tone": "info", "title": "Estado atual",
          "text": "O gateway de IA da geração 4 está planejado e ainda não foi implementado. Na geração 3.0, o uso de "
                  "um modelo local e o uso opcional de um provedor remoto existem e são testados com serviços simulados."},
     ]},
    {"slug": "seguranca-e-privacidade", "title": "Segurança e privacidade",
     "summary": "Onde ficam os dados, o que este site registra e como o assistente é protegido.",
     "blocks": [
         h("Dois serviços que não se falam"),
         p("O assistente e este portal são serviços separados. O assistente roda no computador do usuário, com um "
           "banco de dados privado. O portal roda em outro servidor, com outro banco, e não tem nenhum caminho para "
           "consultar conversas, memórias ou arquivos de quem usa o assistente."),
         h("Este site"),
         {"type": "list", "ordered": False, "items": [
             "As páginas públicas não usam *cookies* nem *scripts* de rastreamento.",
             "O único *cookie* do portal é o de sessão do painel administrativo, restrito a quem administra o conteúdo.",
             "Só o que foi publicado pelo painel aparece aqui; rascunhos nunca são servidos ao público.",
         ]},
         h("O assistente"),
         {"type": "list", "ordered": False, "items": [
             "A interface de comunicação do assistente só aceita conexões do próprio computador.",
             "Toda ação passa por permissões por categoria; as sensíveis pedem confirmação e expiram se não forem respondidas.",
             "Senhas e chaves de serviços ficam no cofre do sistema operacional, nunca em arquivos de configuração.",
         ]},
         {"type": "callout", "tone": "info", "title": "O que ainda não foi verificado",
          "text": "As proteções do portal são cobertas por testes automatizados, mas o site ainda não passou por "
                  "avaliação externa de segurança."},
     ]},
    {"slug": "atualizacoes", "title": "Atualizações",
     "summary": "Novidades do projeto, em ordem cronológica.",
     "blocks": [p("Acompanhe aqui o andamento do desenvolvimento.")]},
    {"slug": "documentacao", "title": "Documentação",
     "summary": "O que já está documentado e o que será publicado para quem usa o SAFRA.",
     "blocks": [
         p("A documentação técnica do projeto é mantida junto ao código: auditoria da geração anterior, arquitetura "
           "da nova geração, decisões registradas, plano de entregas, modelo de dados, matriz de permissões e modelo "
           "de ameaças do portal."),
         h("Para quem vai usar"),
         p("Os guias de instalação, de uso e de administração serão publicados aqui conforme as funções da geração 4 "
           "ficarem disponíveis."),
     ]},
    {"slug": "downloads", "title": "Downloads",
     "summary": "Versões do SAFRA para instalação.",
     "blocks": [
         p("Quando houver versões publicadas, elas aparecerão nesta página com o número, o canal (estável, beta ou "
           "experimental), as notas e o resumo criptográfico de cada arquivo."),
     ]},
    {"slug": "perguntas-frequentes", "title": "Perguntas frequentes",
     "summary": "Respostas diretas sobre o estado e o funcionamento do SAFRA.",
     "blocks": [{"type": "faq", "items": [
         {"question": "O que é o SAFRA?",
          "answer": "Uma plataforma com um assistente que roda no computador do usuário — voz, memória e ferramentas sob permissões — e um portal público."},
         {"question": "Já posso instalar e usar?",
          "answer": "Ainda não. A geração 4 está em desenvolvimento e não há instaladores publicados."},
         {"question": "Qual é a licença?",
          "answer": "A licença ainda não foi definida. Enquanto a análise das licenças das bibliotecas usadas não terminar, nenhum instalador será publicado."},
         {"question": "Funciona sem internet?",
          "answer": "O assistente é projetado para funcionar localmente. O uso de provedores remotos de inteligência artificial é opcional."},
         {"question": "Meus dados vão para a nuvem?",
          "answer": "Os dados do assistente ficam no computador do usuário. Este portal não tem acesso a eles."},
         {"question": "Em que sistemas funciona?",
          "answer": "O alvo é o Windows 10 e 11 de 64 bits."},
         {"question": "Como acompanho o andamento?",
          "answer": "Pela página [Atualizações](/atualizacoes)."},
     ]}]},
    {"slug": "contato", "title": "Contato",
     "summary": "Como falar com o responsável pelo projeto.",
     "blocks": [p("Os canais de contato do projeto são publicados nesta página.")]},
    {"slug": "politica-de-privacidade", "title": "Política de privacidade",
     "summary": "Como este site trata dados de visitantes.",
     "blocks": [
         DRAFT_NOTICE,
         h("Dados de visitantes"),
         p("As páginas públicas deste site não usam *cookies* nem ferramentas de rastreamento e não pedem cadastro."),
         h("Registros técnicos"),
         p("O servidor pode registrar endereço IP, data, hora e página acessada em registros técnicos, usados para "
           "segurança e diagnóstico e mantidos por tempo limitado."),
         h("Painel administrativo"),
         p("O acesso ao painel usa um *cookie* de sessão estritamente necessário e registra as ações administrativas."),
         h("O assistente"),
         p("O assistente SAFRA é instalado no computador do usuário e não envia dados a este site."),
     ]},
    {"slug": "termos-de-uso", "title": "Termos de uso",
     "summary": "Condições de uso deste site.",
     "blocks": [
         DRAFT_NOTICE,
         h("Sobre o conteúdo"),
         p("O conteúdo deste site descreve um projeto em desenvolvimento e pode mudar sem aviso. As informações de "
           "estado (implementado, em desenvolvimento, planejado) refletem a data de cada publicação."),
         h("Software"),
         p("Nenhum instalador é oferecido por este site até que a licença do SAFRA seja definida."),
     ]},
]

NEWS: list[dict] = [
    {"slug": "safra-4-comeca-a-reconstrucao", "title": "SAFRA 4: começa a reconstrução",
     "summary": "A nova geração separa o assistente do portal e refaz a base do sistema.",
     "blocks": [
         p("Em novembro de 2026 começou a reconstrução do SAFRA. A geração anterior continua preservada e "
           "funcionando, enquanto a nova arquitetura é construída ao lado dela."),
         h("O que já foi feito"),
         {"type": "list", "ordered": False, "items": [
             "Auditoria completa da geração anterior, com inventário de funcionalidades e medição de desempenho.",
             "Separação em dois serviços independentes: o assistente, no computador do usuário, e este portal.",
             "Base comum com configuração validada, registros estruturados, migrações de banco com cópia de segurança e testes.",
             "Primeira versão deste portal, com painel administrativo próprio.",
         ]},
         h("O que vem a seguir"),
         p("O design system, o núcleo do assistente com a sua interface de comunicação e o gateway de inteligência "
           "artificial."),
     ]},
]

HOMEPAGE = {
    "title": "SAFRA",
    "subtitle": "Plataforma inteligente integrada. Um assistente que roda no seu computador, com voz, memória e "
                "ferramentas sob o seu controle.",
    "image_media_id": None,
    "buttons": [{"label": "Conhecer as funcionalidades", "href": "/funcionalidades"},
                {"label": "Ver o andamento", "href": "/atualizacoes"}],
    "featured_news": 3,
    "sections": [
        {"key": "status", "enabled": True, "title": "Estado do projeto",
         "text": "O SAFRA 4 está em reconstrução. Cada parte é marcada pelo estado em que realmente está.",
         "items": [
             {"title": "Base dos serviços", "text": "Configuração, registros, banco com migrações e cópia de segurança.", "tag": "implementado"},
             {"title": "Portal e painel administrativo", "text": "Site público e gestão de conteúdo com permissões.", "tag": "implementado"},
             {"title": "Núcleo do assistente", "text": "Conversa, memória, ferramentas e voz sobre a nova arquitetura.", "tag": "em desenvolvimento"},
             {"title": "Aplicativo para Windows", "text": "Janela, bandeja e instalação.", "tag": "planejado"},
         ], "links": []},
        {"key": "features", "enabled": True, "title": "O que o SAFRA faz",
         "text": "Um assistente local que conversa, lembra e age, sempre dentro das permissões que você define.",
         "items": [
             {"title": "Conversa por texto e voz", "text": "Em português, com reconhecimento e síntese de fala no próprio computador.", "tag": ""},
             {"title": "Memória persistente", "text": "Lembretes, anotações e contexto guardados num banco privado.", "tag": ""},
             {"title": "Ações controladas", "text": "Cada ação passa por permissão, confirmação quando necessário e verificação do resultado.", "tag": ""},
         ], "links": [{"label": "Todas as funcionalidades", "href": "/funcionalidades"}]},
        {"key": "hybrid_ai", "enabled": True, "title": "Inteligência artificial híbrida",
         "text": "Modelos locais em primeiro lugar. Provedores remotos só quando você permitir, e nunca para "
                 "conteúdo marcado como privado.",
         "items": [], "links": [{"label": "Como funciona", "href": "/inteligencia-artificial"}]},
        {"key": "security", "enabled": True, "title": "Segurança e privacidade",
         "text": "O assistente e este portal são serviços separados, com bancos separados. O portal não tem como "
                 "consultar os dados de quem usa o assistente.",
         "items": [], "links": [{"label": "Ler mais", "href": "/seguranca-e-privacidade"}]},
        {"key": "news", "enabled": True, "title": "Novidades", "text": "", "items": [],
         "links": [{"label": "Todas as atualizações", "href": "/atualizacoes"}]},
        {"key": "resources", "enabled": True, "title": "Documentação e downloads",
         "text": "A documentação pública cresce junto com o projeto. Ainda não há instaladores publicados.",
         "items": [], "links": [{"label": "Documentação", "href": "/documentacao"}, {"label": "Downloads", "href": "/downloads"}]},
    ],
}

SITE = {
    "tagline": "Plataforma inteligente integrada",
    "footer_text": "SAFRA é um projeto em desenvolvimento. As informações deste site refletem o estado do projeto na data de cada publicação.",
    "footer_links": [],
    "contact_email": "",
    "contact_links": [],
}


def seed_initial_content(db: Db) -> bool:
    """Cria e publica o conteúdo inicial se o banco não tiver nenhum conteúdo nem configuração. Idempotente."""
    has_content = db.scalar(select(func.count()).select_from(Content)) or 0
    has_settings = db.scalar(select(func.count()).select_from(SiteSetting)) or 0
    if has_content or has_settings:
        return False
    for content_type, items in (("page", PAGES), ("news", NEWS)):
        for item in items:
            created = content.create(db, content_type, item, actor_id=None, kind="seed")
            content.publish(db, content_type, created.id, actor_id=None)
    homepage.save(db, homepage.HOMEPAGE_KEY, HOMEPAGE, actor_id=None)
    homepage.save(db, homepage.SITE_KEY, SITE, actor_id=None)
    return True
