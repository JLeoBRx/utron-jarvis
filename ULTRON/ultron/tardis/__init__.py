"""TARDIS — o segundo cérebro do SAFRA: análise, planejamento, organização, consulta contextual,
rotinas, telemetria do sistema, diagnóstico, coordenação e memória de projeto.

É um MÓDULO LÓGICO separado (fila, protocolo, analisadores e memória de projeto próprios). Não é um
segundo modelo de IA: quando precisa de linguagem natural, usa o MESMO modelo do SAFRA com instruções
próprias — e cada resultado diz qual modelo usou (ou "sem modelo: análise determinística").

A TARDIS nunca executa ações nem chama o SAFRA de volta: devolve AÇÕES PROPOSTAS, que o SAFRA só
executa com a confirmação do usuário, pelo mesmo executor (permissões, risco, verificação).
"""
