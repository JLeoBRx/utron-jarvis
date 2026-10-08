import tkinter as tk
import math
import time
import threading


# ============================================================
# CONFIGURAÇÕES
# ============================================================

LARGURA = 1200
ALTURA = 700


# ============================================================
# JANELA
# ============================================================

janela = tk.Tk()

janela.title("J.A.R.V.I.S.")
janela.geometry(f"{LARGURA}x{ALTURA}")
janela.configure(bg="#02050a")
janela.minsize(900, 600)


# ============================================================
# CANVAS PRINCIPAL
# ============================================================

canvas = tk.Canvas(
    janela,
    bg="#02050a",
    highlightthickness=0
)

canvas.pack(fill="both", expand=True)


# ============================================================
# VARIÁVEIS
# ============================================================

estado = "ONLINE"
angulo = 0
pulso = 0
rodando = True


# ============================================================
# CORES
# ============================================================

CIANO = "#00d9ff"
CIANO_FRACO = "#07556a"
BRANCO = "#dffaff"
CINZA = "#6b818a"
FUNDO = "#02050a"
VERDE = "#00ff9d"


# ============================================================
# TEXTO CENTRAL
# ============================================================

def texto_central():

    largura = janela.winfo_width()
    altura = janela.winfo_height()

    cx = largura // 2
    cy = altura // 2

    # título
    canvas.create_text(
        cx,
        cy - 150,
        text="J.A.R.V.I.S.",
        fill=BRANCO,
        font=("Segoe UI", 30, "bold"),
        tags="hud"
    )

    canvas.create_text(
        cx,
        cy - 115,
        text="JUST A RATHER VERY INTELLIGENT SYSTEM",
        fill=CINZA,
        font=("Segoe UI", 9),
        tags="hud"
    )


# ============================================================
# CÍRCULOS CENTRAIS
# ============================================================

def desenhar_nucleo():

    global pulso

    largura = janela.winfo_width()
    altura = janela.winfo_height()

    cx = largura // 2
    cy = altura // 2

    canvas.delete("nucleo")

    # pulsação

    pulsacao = math.sin(pulso) * 8

    raio_externo = 120 + pulsacao
    raio_interno = 78 + pulsacao * 0.5

    # anel externo

    canvas.create_oval(
        cx - raio_externo,
        cy - raio_externo,
        cx + raio_externo,
        cy + raio_externo,
        outline=CIANO_FRACO,
        width=2,
        tags="nucleo"
    )

    # segundo anel

    canvas.create_oval(
        cx - raio_interno,
        cy - raio_interno,
        cx + raio_interno,
        cy + raio_interno,
        outline=CIANO,
        width=2,
        tags="nucleo"
    )

    # núcleo

    canvas.create_oval(
        cx - 45,
        cy - 45,
        cx + 45,
        cy + 45,
        fill="#03141c",
        outline=CIANO,
        width=3,
        tags="nucleo"
    )

    canvas.create_oval(
        cx - 20,
        cy - 20,
        cx + 20,
        cy + 20,
        fill=CIANO,
        outline="",
        tags="nucleo"
    )

    # pequenos pontos orbitais

    for i in range(8):

        a = angulo + (i * 45)

        x = cx + math.cos(math.radians(a)) * 155
        y = cy + math.sin(math.radians(a)) * 155

        canvas.create_oval(
            x - 3,
            y - 3,
            x + 3,
            y + 3,
            fill=CIANO,
            outline="",
            tags="nucleo"
        )


# ============================================================
# STATUS
# ============================================================

def desenhar_status():

    largura = janela.winfo_width()
    altura = janela.winfo_height()

    cx = largura // 2
    cy = altura // 2

    canvas.create_text(
        cx,
        cy + 155,
        text=estado,
        fill=VERDE,
        font=("Segoe UI", 14, "bold"),
        tags="status"
    )


# ============================================================
# PAINEL ESQUERDO
# ============================================================

def painel_esquerdo():

    canvas.delete("esquerda")

    canvas.create_text(
        40,
        40,
        anchor="w",
        text="SYSTEM STATUS",
        fill=CIANO,
        font=("Segoe UI", 11, "bold"),
        tags="esquerda"
    )

    linhas = [
        ("CORE", "QWEN 2.5"),
        ("VOICE", "ONLINE"),
        ("AUDIO", "ONLINE"),
        ("MEMORY", "ACTIVE"),
        ("NETWORK", "LOCAL")
    ]

    y = 75

    for nome, valor in linhas:

        canvas.create_text(
            40,
            y,
            anchor="w",
            text=nome,
            fill=CINZA,
            font=("Segoe UI", 9),
            tags="esquerda"
        )

        canvas.create_text(
            150,
            y,
            anchor="w",
            text=valor,
            fill=BRANCO,
            font=("Segoe UI", 9, "bold"),
            tags="esquerda"
        )

        y += 28


# ============================================================
# PAINEL DIREITO
# ============================================================

def painel_direito():

    canvas.delete("direita")

    largura = janela.winfo_width()

    canvas.create_text(
        largura - 260,
        40,
        anchor="w",
        text="JARVIS LOG",
        fill=CIANO,
        font=("Segoe UI", 11, "bold"),
        tags="direita"
    )

    logs = [
        "SYSTEM INITIALIZED",
        "OLLAMA CONNECTED",
        "VOICE ENGINE READY",
        "MICROPHONE READY",
        "AWAITING COMMAND..."
    ]

    y = 75

    for log in logs:

        canvas.create_text(
            largura - 260,
            y,
            anchor="w",
            text="> " + log,
            fill=CINZA,
            font=("Consolas", 9),
            tags="direita"
        )

        y += 25


# ============================================================
# RELÓGIO
# ============================================================

def relogio():

    largura = janela.winfo_width()

    hora = time.strftime("%H:%M:%S")

    canvas.delete("relogio")

    canvas.create_text(
        largura - 35,
        35,
        text=hora,
        anchor="e",
        fill=BRANCO,
        font=("Consolas", 14),
        tags="relogio"
    )


# ============================================================
# LINHAS HUD
# ============================================================

def linhas_hud():

    largura = janela.winfo_width()
    altura = janela.winfo_height()

    canvas.delete("linhas")

    # linhas horizontais

    canvas.create_line(
        0,
        110,
        largura,
        110,
        fill="#061923",
        width=1,
        tags="linhas"
    )

    canvas.create_line(
        0,
        altura - 80,
        largura,
        altura - 80,
        fill="#061923",
        width=1,
        tags="linhas"
    )


# ============================================================
# ANIMAÇÃO
# ============================================================

def animar():

    global angulo
    global pulso

    if not rodando:
        return

    angulo += 1
    pulso += 0.08

    canvas.delete("hud")
    canvas.delete("status")

    texto_central()
    desenhar_nucleo()
    desenhar_status()

    janela.after(30, animar)


# ============================================================
# ATUALIZAÇÃO DOS PAINÉIS
# ============================================================

def atualizar_interface():

    painel_esquerdo()
    painel_direito()
    linhas_hud()
    relogio()

    janela.after(1000, atualizar_interface)


# ============================================================
# ENCERRAMENTO
# ============================================================

def fechar():

    global rodando

    rodando = False
    janela.destroy()


janela.protocol(
    "WM_DELETE_WINDOW",
    fechar
)


# ============================================================
# INICIAR
# ============================================================

painel_esquerdo()
painel_direito()
linhas_hud()
relogio()

animar()
atualizar_interface()

janela.mainloop()