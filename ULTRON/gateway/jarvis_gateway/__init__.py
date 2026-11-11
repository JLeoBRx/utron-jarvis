"""SAFRA Gateway — o serviço de conexão da SAFRA WEB ORB.

Ponte entre a ORBE no navegador (celular ou computador) e a MATRIZ-MÃE (o computador onde o SAFRA roda). O
gateway não tem inteligência, memória, modelos, chaves de API nem acesso ao computador: ele autentica, pareia
dispositivos, mantém as sessões e retransmite mensagens em tempo real. O agente da matriz-mãe se conecta a ele
por uma conexão de SAÍDA (nenhuma porta aberta no roteador). Banco próprio (dispositivos, pareamentos, auditoria)
— nunca a memória pessoal do SAFRA.
"""
__version__ = "1.0.0"
