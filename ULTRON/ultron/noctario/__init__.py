"""Noctário — o robô seguidor de linha (ESP32 + TB6612FNG + 8 QTR analógicos) visto do PC.

* ``protocol`` — NOCT/1 (linhas de texto sobre Bluetooth SPP), parâmetros e limites;
* ``transport`` — porta COM, RFCOMM e o SIMULADOR (rotulado);
* ``service`` — conexão, comandos com confirmação, estado solicitado × confirmado, PARADA, voltas;
* ``store`` — voltas e operações no banco do JARVIS (migração v6);
* ``simulator`` — robô simulado que fala NOCT/1 (não é o robô; tudo que vem dele é marcado).

O controle (PD, rampas, cruzamentos, perda de linha, política sem link) roda no firmware
(``firmware/noctario/``). A interface só lê, pede e registra.
"""
