"""PV-03 — Recuperação de memória (taxa de recuperação correta).

Usa o MESMO subsistema de memória do SAFRA (``MemorySystem`` sobre o banco SQLite, ``Retriever``) e a busca da
memória pessoal (``SecondBrainService.search``), numa pasta temporária. O conjunto de teste é SINTÉTICO e está
neste arquivo (fatos e perguntas escritos para o experimento), para que qualquer pessoa repita a medição.

Três tipos de pergunta para cada fato:

* **lexical** — repete palavras-chave do fato ("quando é o aniversário da Ana?");
* **paráfrase** — mesma intenção com outras palavras ("em que dia a Ana faz anos?");
* **ausente** — pergunta sobre algo que NÃO foi guardado (o certo é não recuperar fato nenhum).

Métricas: acerto entre as 1 e as 3 primeiras recuperações (recall@1, recall@3) por tipo, e taxa de
recuperação indevida nas perguntas sobre o que não existe. Meta RNF09: recall@3 ≥ 80 %.

Uso:  python tools/experimentos/pv03_memoria.py [--rotulo NOME]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _comum as C  # noqa: E402

# (assunto, fato, pergunta lexical, pergunta em paráfrase)
FATOS = (
    ("aniversário da Ana", "12 de março", "quando é o aniversário da Ana?", "em que dia a Ana faz anos?"),
    ("roteador do wi-fi", "fica atrás da estante da sala", "onde está o roteador do wi-fi?",
     "onde fica o aparelho da internet sem fio?"),
    ("médico da família", "doutor Paulo, clínica Santa Luzia", "quem é o médico da família?",
     "qual doutor cuida da gente?"),
    ("time do Pedro", "Palmeiras", "qual é o time do Pedro?", "para quem o Pedro torce no futebol?"),
    ("alergia da Júlia", "camarão", "a Júlia tem alergia a quê?", "o que a Júlia não pode comer?"),
    ("horário da academia", "segunda a sexta às 7 horas", "qual o horário da academia?",
     "que horas eu treino durante a semana?"),
    ("placa do carro", "ABC1D23", "qual é a placa do carro?", "como é a identificação do veículo?"),
    ("escola do Lucas", "Colégio Estadual Monteiro Lobato", "em qual escola o Lucas estuda?",
     "onde o Lucas tem aula?"),
    ("tamanho do sapato", "41", "qual o tamanho do meu sapato?", "que número eu calço?"),
    ("cor preferida da Marina", "verde", "qual é a cor preferida da Marina?", "de que tom a Marina mais gosta?"),
    ("vacina do cachorro", "vence em agosto", "quando vence a vacina do cachorro?",
     "quando o Thor precisa voltar ao veterinário para a dose?"),
    ("projeto do TCC", "SAFRA, entrega em 2027", "qual é o projeto do TCC?", "qual trabalho eu apresento para formar?"),
    ("pizzaria preferida", "Forno a Lenha, na rua 7", "qual é a pizzaria preferida?",
     "de onde a gente costuma pedir comida no sábado?"),
    ("dentista", "doutora Carla, consultório no centro", "quem é a dentista?", "quem cuida dos meus dentes?"),
    ("número do apartamento da avó", "302", "qual o número do apartamento da avó?", "onde a vovó mora no prédio?"),
    ("linguagem do projeto", "Python 3.11", "qual a linguagem do projeto?", "em que o sistema foi programado?"),
    ("dia da coleta de lixo reciclável", "quinta-feira", "qual o dia da coleta de lixo reciclável?",
     "quando passa o caminhão da reciclagem?"),
    ("filme favorito do Rafa", "Interestelar", "qual o filme favorito do Rafa?", "a que obra de cinema o Rafa mais assiste?"),
    ("remédio da pressão", "losartana às 8 horas", "qual é o remédio da pressão?", "o que eu tomo de manhã para hipertensão?"),
    ("professor de matemática", "professor Henrique", "quem é o professor de matemática?", "quem dá aula de cálculo?"),
)
AUSENTES = (
    "qual o tipo sanguíneo do Pedro?", "onde fica a farmácia mais próxima?", "qual a altura da Ana?",
    "quanto custou a geladeira?", "qual o nome do vizinho?", "quando é a formatura da Marina?",
    "qual o CEP da casa da avó?", "qual a marca do celular do Lucas?", "quem é o técnico do Palmeiras?",
    "qual a senha do banco?",
)
# memória pessoal: (tipo, título, busca exata, busca sem acento/variação)
REGISTROS = (
    ("task", "Renovar a carteira de motorista", "carteira de motorista", "renovacao carteira"),
    ("idea", "Horta vertical na varanda", "horta vertical", "horta na varanda"),
    ("event", "Reunião com a orientadora do TCC", "orientadora", "reuniao orientadora"),
    ("task", "Comprar ração do Thor", "ração", "racao"),
    ("idea", "Painel solar na garagem", "painel solar", "solar garagem"),
    ("task", "Estudar fundamentação teórica", "fundamentação", "fundamentacao teorica"),
    ("note", "Dentista às 14h", "dentista", "dentista"),
    ("project", "Robô de limpeza da escola", "robô de limpeza", "robo limpeza"),
)


def main() -> int:
    args = C.argumentos(__doc__.splitlines()[0])
    pasta = C.preparar()
    from ultron.memory.store import Database
    from ultron.memory.system import MemorySystem
    from ultron.secondbrain.service import SecondBrainService
    db = Database(str(pasta / "memoria.sqlite3"))
    memoria = MemorySystem(db, import_legacy=False)
    for assunto, fato, _l, _p in FATOS:
        memoria.remember_fact(assunto, fato, source="experimento")
    brutos = []
    for i, (assunto, fato, lexical, parafrase) in enumerate(FATOS):
        for tipo, pergunta in (("lexical", lexical), ("parafrase", parafrase)):
            achados = [r for r in memoria.recall(pergunta, limit=3) if r.kind == "fact"]
            posicao = next((k + 1 for k, r in enumerate(achados) if r.data.get("subject") == assunto), None)
            brutos.append({"tipo": tipo, "assunto": assunto, "pergunta": pergunta, "posicao": posicao,
                           "recuperados": [r.text for r in achados], "scores": [round(r.score, 3) for r in achados]})
    for pergunta in AUSENTES:
        achados = [r for r in memoria.recall(pergunta, limit=3) if r.kind == "fact"]
        brutos.append({"tipo": "ausente", "pergunta": pergunta, "recuperados": [r.text for r in achados],
                       "scores": [round(r.score, 3) for r in achados]})
    metricas = {}
    for tipo in ("lexical", "parafrase"):
        sub = [b for b in brutos if b["tipo"] == tipo]
        metricas[f"{tipo}_recall@1"] = C.proporcao(sum(b["posicao"] == 1 for b in sub), len(sub))
        metricas[f"{tipo}_recall@3"] = C.proporcao(sum(b["posicao"] is not None for b in sub), len(sub))
    aus = [b for b in brutos if b["tipo"] == "ausente"]
    metricas["ausente_recuperacao_indevida"] = C.proporcao(sum(bool(b["recuperados"]) for b in aus), len(aus))
    # memória pessoal (busca com índice de texto completo e sem acentos)
    sb = SecondBrainService(db)
    sb.start() if hasattr(sb, "start") else None
    for tipo, titulo, _e, _v in REGISTROS:
        sb.create(tipo, titulo, origin="experimento")
    busca = []
    for tipo, titulo, exata, variacao in REGISTROS:
        for modo, consulta in (("exata", exata), ("variacao", variacao)):
            achados = [r.get("title") if isinstance(r, dict) else getattr(r, "title", str(r))
                       for r in sb.search(consulta)][:3]
            busca.append({"modo": modo, "consulta": consulta, "esperado": titulo, "achados": achados,
                          "acerto": titulo in achados})
    for modo in ("exata", "variacao"):
        sub = [b for b in busca if b["modo"] == modo]
        metricas[f"memoria_pessoal_{modo}@3"] = C.proporcao(sum(b["acerto"] for b in sub), len(sub))
    resultado = {"protocolo": "PV-03", "conjunto": "sintético (definido neste script)",
                 "real": ["MemorySystem/Retriever e SecondBrainService sobre SQLite em arquivo"], "simulado": [],
                 "ambiente": C.ambiente(), "metricas": metricas, "amostras": brutos, "memoria_pessoal": busca}
    caminho = C.gravar("pv03_memoria", resultado, rotulo=args.rotulo)
    for k, v in metricas.items():
        print(f"{k}: {v['acertos']}/{v['total']} = {v['taxa']}")
    print(f"resultado: {caminho}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
