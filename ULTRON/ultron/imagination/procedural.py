"""Gerador procedural determinístico (sem modelo de linguagem).

Usado como fallback declarado: todo conteúdo gerado aqui sai marcado com
``generator = "procedural"``. Não é apresentado como criação do modelo de linguagem.
"""
from __future__ import annotations

import hashlib
import random

CLIMATES = ("árido de ventos constantes", "úmido e enevoado", "glacial sob auroras", "tropical de chuvas violentas",
            "temperado de estações longas", "tempestuoso e elétrico", "seco com noites gélidas", "oceânico e salino")
ARCHITECTURES = ("torres espirais de vidro fumê", "domos de pedra porosa", "pontes suspensas entre cânions",
                 "estruturas orgânicas cultivadas", "terraços escalonados em encostas", "monólitos de metal escovado",
                 "cidades flutuantes ancoradas por cabos", "galerias subterrâneas iluminadas")
LIGHTING = ("luz âmbar rasante", "neblina dourada ao entardecer", "brilho bioluminescente", "sol pálido e baixo",
            "reflexos metálicos frios", "lanternas de plasma", "penumbra quente", "eclipses frequentes")
TRANSPORT = ("trilhos magnéticos aéreos", "barcaças de vento", "elevadores de cabo entre torres", "criaturas de carga",
             "cápsulas pneumáticas", "planadores solares", "túneis de correnteza", "caminhadas cerimoniais")
CULTURES = ("arquivistas que veneram a memória", "artesãos do som", "conselhos de engenheiros", "nômades das marés",
            "guildas de cartógrafos", "monastérios de calculistas", "festivais de luz", "clãs de navegadores")
TECHNOLOGIES = ("energia de cristais piezoelétricos", "computação em fluxos de água", "tecidos que armazenam luz",
                "ligas que se reparam", "redes de sinais por fungos", "motores de pressão térmica",
                "lentes que registram o passado", "autômatos de bronze")
HISTORIES = ("fundada após uma grande migração", "reconstruída sobre ruínas de uma civilização anterior",
             "nascida de um acordo entre clãs rivais", "isolada por séculos após um colapso",
             "erguida em torno de uma descoberta científica", "moldada por um longo inverno")
GEOGRAPHIES = ("um vale entre falésias", "um arquipélago vulcânico", "um planalto desértico", "o delta de um rio",
               "uma cratera antiga", "uma costa de recifes", "florestas de árvores colossais", "planícies de sal")
MATERIALS = ("basalto", "cobre oxidado", "vidro âmbar", "madeira petrificada", "cerâmica branca", "aço escovado",
             "obsidiana", "calcário dourado")
SYLLABLES = ("ar", "vel", "dor", "an", "ka", "mir", "eth", "os", "tha", "ul", "zen", "ri", "o", "lis", "ver", "nax",
             "sol", "qua", "dra", "mon")


def rng_for(text: str) -> random.Random:
    seed = int(hashlib.sha256(str(text).encode("utf-8")).hexdigest()[:16], 16)
    return random.Random(seed)


def name(rng: random.Random, parts: int = 3) -> str:
    return "".join(rng.choice(SYLLABLES) for _ in range(parts)).capitalize()


def concept(idea: str) -> dict:
    r = rng_for(idea)
    title = name(r)
    facets = {
        "ARCHITECTURE": f"{r.choice(ARCHITECTURES)} em {r.choice(MATERIALS)}",
        "CLIMATE": r.choice(CLIMATES),
        "LIGHTING": r.choice(LIGHTING),
        "TRANSPORT": r.choice(TRANSPORT),
        "CULTURE": r.choice(CULTURES),
        "HISTORY": r.choice(HISTORIES),
        "TECHNOLOGY": r.choice(TECHNOLOGIES),
        "POPULATION": f"cerca de {r.randint(2, 900) * 1000:,} habitantes".replace(",", "."),
        "GEOGRAPHY": r.choice(GEOGRAPHIES),
    }
    relationships = [
        ["CLIMATE", "molda", "ARCHITECTURE"], ["GEOGRAPHY", "determina", "TRANSPORT"],
        ["TECHNOLOGY", "sustenta", "CULTURE"], ["HISTORY", "explica", "CULTURE"],
    ]
    visual = (f"{title}: {facets['ARCHITECTURE']} sobre {facets['GEOGRAPHY']}, {facets['LIGHTING']}, "
              f"clima {facets['CLIMATE']}.")
    return {"name": title, "summary": f"{title}, {facets['HISTORY']}.", "facets": facets,
            "relationships": relationships, "visual_description": visual,
            "image_prompt": f"concept art, {title} city, {facets['ARCHITECTURE']}, {facets['LIGHTING']}, cinematic",
            "generator": "procedural"}


def scenario(idea: str) -> dict:
    r = rng_for("scenario:" + idea)
    title = name(r)
    return {"name": f"Cenário {title}", "premise": idea.strip()[:300],
            "rules": [f"a sociedade se organiza em torno de {r.choice(TECHNOLOGIES)}",
                      f"o ambiente é {r.choice(CLIMATES)}"],
            "environment": r.choice(GEOGRAPHIES), "entities": [r.choice(CULTURES), r.choice(CULTURES)],
            "relationships": [["entidades", "disputam", "recursos"]], "history": r.choice(HISTORIES),
            "physics": "física convencional", "technology": r.choice(TECHNOLOGIES),
            "visual_description": f"{r.choice(ARCHITECTURES)} sob {r.choice(LIGHTING)}", "generator": "procedural"}


ARCHETYPES = (("Conservadora", 2, 3, 3, 2, 2), ("Equilibrada", 3, 3, 4, 3, 3), ("Radical", 5, 4, 4, 5, 5),
              ("Experimental", 3, 2, 3, 4, 4))


def branches(idea: str) -> dict:
    options = []
    for letter, (label, cost, time_, quality, complexity, risk) in zip("ABCD", ARCHETYPES):
        options.append({"id": letter, "title": f"Abordagem {label.lower()}",
                        "description": f"Abordagem {label.lower()} para: {idea.strip()[:120]}",
                        "cost": cost, "time": time_, "quality": quality, "complexity": complexity, "risk": risk,
                        "expected_result": "estimativa genérica (sem modelo de linguagem)"})
    return {"idea": idea, "options": options, "generator": "procedural"}


def world(idea: str) -> dict:
    r = rng_for("world:" + idea)
    title = name(r, 2)
    layers = {
        "MAP": f"um supercontinente fragmentado e {r.randint(2, 5)} mares interiores",
        "TERRAIN": r.choice(GEOGRAPHIES), "CLIMATE": r.choice(CLIMATES),
        "ARCHITECTURE": r.choice(ARCHITECTURES), "POPULATION": f"{r.randint(1, 40)} milhões de habitantes",
        "CULTURE": r.choice(CULTURES), "ECONOMY": f"baseada em {r.choice(MATERIALS)} e conhecimento",
        "HISTORY": r.choice(HISTORIES), "LANGUAGE": f"idiomas derivados do antigo {name(r, 2)}",
        "TECHNOLOGY": r.choice(TECHNOLOGIES), "BIOLOGY": "fauna adaptada a ciclos longos de luz",
        "EVENTS": f"a era atual começou com a queda de {name(r, 3)}",
        "RELATIONSHIPS": "alianças comerciais frágeis entre continentes",
    }
    return {"name": title, "summary": f"O mundo de {title}.", "layers": layers,
            "children": [name(r, 3) for _ in range(r.randint(3, 4))], "generator": "procedural"}


def child(parent_name: str, level: str, child_name: str | None = None) -> dict:
    r = rng_for(f"{parent_name}:{level}:{child_name}")
    title = child_name or name(r)
    layers = {"ARCHITECTURE": r.choice(ARCHITECTURES), "CLIMATE": r.choice(CLIMATES),
              "CULTURE": r.choice(CULTURES), "HISTORY": r.choice(HISTORIES)}
    next_names = [name(r, 2) for _ in range(r.randint(2, 4))]
    return {"name": title, "summary": f"{level.lower()} {title} em {parent_name}.", "layers": layers,
            "children": next_names, "generator": "procedural"}


def blend(labels: list[str], seed: str) -> dict:
    r = rng_for("dream:" + seed)
    pieces = [label.split()[0][:4] for label in labels if label]
    title = "".join(pieces[:3]).capitalize() or name(r)
    return {"name": title, "description": "Combinação de " + ", ".join(labels[:4]) + f" sob {r.choice(TECHNOLOGIES)}.",
            "generator": "procedural"}
