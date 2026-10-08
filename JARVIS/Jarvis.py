import json
import urllib.request
import pyttsx3
import pyaudio
from vosk import Model, KaldiRecognizer

# ============================================================
# CONFIGURAÇÕES
# ============================================================

OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "qwen2.5:3b"

MODEL_PATH = "vosk-model-small-pt-0.3"

SAMPLE_RATE = 16000
CHUNK = 4000

# ============================================================
# VOZ DO JARVIS
# ============================================================

voz = pyttsx3.init()

voz.setProperty("rate", 165)
voz.setProperty("volume", 1.0)

# Tenta encontrar uma voz em português
for v in voz.getProperty("voices"):
    nome = (v.name or "").lower()
    idioma = str(getattr(v, "languages", "")).lower()

    if "portugu" in nome or "brazil" in nome or "pt-br" in idioma or "pt_br" in idioma:
        voz.setProperty("voice", v.id)
        break


def falar(texto):
    print(f"\nJARVIS: {texto}")
    voz.say(texto)
    voz.runAndWait()


# ============================================================
# CÉREBRO DO JARVIS
# ============================================================

historico = [
    {
        "role": "system",
        "content": (
            "Você é J.A.R.V.I.S., Just A Rather Very Intelligent System. "
            "Responda em português brasileiro. "
            "Seja sério, composto, preciso e discretamente sarcástico. "
            "Seja descontraído, mas não amigável. Não bajule, não use entusiasmo artificial e não use emojis. "
            "Evite 'Claro', 'Perfeito', 'Ótimo' e frases típicas de atendimento. "
            "Use 'senhor' naturalmente. Humor seco é permitido quando for elegante e breve. "
            "Explique o necessário e não invente ações que não executou."
        )
    }
]


def perguntar_ao_ollama(pergunta):

    historico.append({
        "role": "user",
        "content": pergunta
    })

    dados = {
        "model": OLLAMA_MODEL,
        "messages": historico,
        "stream": False
    }

    requisicao = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(dados).encode("utf-8"),
        headers={
            "Content-Type": "application/json"
        }
    )

    try:

        with urllib.request.urlopen(
            requisicao,
            timeout=120
        ) as resposta:

            resultado = json.loads(
                resposta.read().decode("utf-8")
            )

        mensagem = resultado["message"]["content"].strip()

        historico.append({
            "role": "assistant",
            "content": mensagem
        })

        # Mantém o histórico controlado
        if len(historico) > 13:
            del historico[1:3]

        return mensagem

    except Exception as erro:

        print("\nErro ao conectar com o Ollama:")
        print(erro)

        return (
            "Senhor, não consegui me conectar "
            "ao meu núcleo de inteligência."
        )


# ============================================================
# MICROFONE
# ============================================================

print("=" * 60)
print("              JARVIS - INICIALIZAÇÃO")
print("=" * 60)

print("\nCarregando reconhecimento de voz...")

try:
    modelo = Model(MODEL_PATH)
except Exception as erro:
    print("\nErro ao carregar o Vosk:")
    print(erro)
    input("\nPressione Enter para sair...")
    raise SystemExit


audio = pyaudio.PyAudio()

# ============================================================
# ESCOLHER MICROFONE
# ============================================================

microfones = []

print("\nMicrofones disponíveis:\n")

for i in range(audio.get_device_count()):

    info = audio.get_device_info_by_index(i)

    if int(info["maxInputChannels"]) > 0:

        microfones.append(i)

        print(
            f"[{i}] {info['name']}"
        )

print()

while True:

    entrada = input("Escolha o número do microfone: ").strip()

    try:

        device_index = int(entrada)

        if device_index in microfones:
            break

        print("Microfone inválido.")

    except ValueError:

        print("Digite apenas o número.")


# ============================================================
# ABRIR MICROFONE
# ============================================================

recognizer = KaldiRecognizer(
    modelo,
    SAMPLE_RATE
)

stream = audio.open(
    format=pyaudio.paInt16,
    channels=1,
    rate=SAMPLE_RATE,
    input=True,
    input_device_index=device_index,
    frames_per_buffer=CHUNK
)

stream.start_stream()

# ============================================================
# INÍCIO
# ============================================================

print("\n" + "=" * 60)
print("🤖 JARVIS ONLINE")
print("=" * 60)

falar(
    "JARVIS online. "
    "Sistemas disponíveis. Aguardando instruções."
)

print("\nFale normalmente.")
print("Para encerrar, diga: Jarvis, desligar.")

# ============================================================
# LOOP PRINCIPAL
# ============================================================

try:

    while True:

        dados = stream.read(
            CHUNK,
            exception_on_overflow=False
        )

        if recognizer.AcceptWaveform(dados):

            resultado = json.loads(
                recognizer.Result()
            )

            texto = resultado.get(
                "text",
                ""
            ).strip()

            if not texto:
                continue

            print(f"\nVOCÊ: {texto}")

            # --------------------------------------------
            # ENCERRAR
            # --------------------------------------------

            if (
                "jarvis desligar" in texto
                or "jarvis encerrar" in texto
                or texto == "desligar"
            ):

                falar("Até logo, senhor.")
                break

            # --------------------------------------------
            # COMANDO PARA A IA
            # --------------------------------------------

            resposta = perguntar_ao_ollama(
                texto
            )

            falar(resposta)

except KeyboardInterrupt:

    print("\n\nJARVIS encerrado pelo teclado.")

finally:

    stream.stop_stream()
    stream.close()

    audio.terminate()

    print("\nSistema encerrado.")