"""Avatar holográfico do SAFRA: rosto robótico 3D renderizado em tempo real (sem imagens prontas).

* ``geometry`` — a cabeça esculpida (NumPy puro);
* ``states`` — os 12 estados resolvidos a partir de sinais reais (função pura);
* ``rig`` / ``animator`` — expressão, olhar, piscadas, boca e transições;
* ``renderer`` — desenho por camadas com QPainter (CPU) ou num QOpenGLWidget (GPU opcional);
* ``view`` — o widget da página SAFRA, com legendas sincronizadas e indicadores.
"""
