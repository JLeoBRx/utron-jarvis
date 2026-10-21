"""Sala de controle da TARDIS: console hexagonal com seis painéis, rotor central ligado ao estado REAL
do motor da TARDIS, telas flutuantes com a fila e os resultados, e o ARQUIVO (a memória espacial).

* ``scene`` — estado e animação, sem Qt (testável);
* ``view`` — desenho 3D em QPainter (CPU), no mesmo estilo do rosto do JARVIS;
* ``page`` — a página da plataforma: sala + painéis laterais + o ARQUIVO.
"""
