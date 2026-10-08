import json
import pyaudio
from vosk import Model, KaldiRecognizer

# ============================================================
# CONFIGURAÇÕES
# ============================================================

MODEL_PATH = "vosk-model-small-pt-0.3"
TAXA_AMOSTRAGEM = 16000
CHUNK = 4000

# ============================================================
# INICIAR ÁUDIO
# ============================================================

audio = pyaudio.PyAudio()

print("=" * 60)
print("           JARVIS - TESTE DE MICROFONE")
print("=" * 60)

# ============================================================
# LISTAR MICROFONES
# ============================================================

microfones = []

print("\nMicrofones encontrados:\n")

for i in range(audio.get_device_count()):
    info = audio.get_device_info_by_index(i)

    if int(info["maxInputChannels"]) > 0:
        microfones.append(i)

        print(
            f"[{i}] {info['name']}"
            f" | entradas: {int(info['maxInputChannels'])}"
            f" | taxa: {int(info['defaultSampleRate'])}"
        )

if not microfones:
    print("\nERRO: nenhum microfone foi encontrado.")
    audio.terminate()
    input("\nPressione Enter para sair...")
    raise SystemExit

# ============================================================
# ESCOLHER MICROFONE
# ============================================================

print("\nDigite o número do microfone que você deseja usar.")
print("Exemplo: 2")

while True:
    escolha = input("\nMicrofone: ").strip()

    try:
        device_index = int(escolha)

        if device_index in microfones:
            break

        print("Número inválido. Escolha um dos microfones listados.")

    except ValueError:
        print("Digite apenas o número do microfone.")

# ============================================================
# INFORMAÇÕES DO MICROFONE
# ============================================================

info = audio.get_device_info_by_index(device_index)

print("\n" + "=" * 60)
print(f"Microfone escolhido: {info['name']}")
print("=" * 60)

# ============================================================
# CARREGAR MODELO VOSK
# ============================================================

print("\nCarregando modelo de reconhecimento de voz...")

try:
    model = Model(MODEL_PATH)
except Exception as erro:
    print("\nERRO AO CARREGAR O MODELO:")
    print(erro)
    audio.terminate()
    input("\nPressione Enter para sair...")
    raise SystemExit

print("Modelo carregado com sucesso!")

# ============================================================
# RECONHECEDOR
# ============================================================

recognizer = KaldiRecognizer(model, TAXA_AMOSTRAGEM)

# ============================================================
# ABRIR MICROFONE
# ============================================================

print("\nAbrindo microfone...")

try:
    stream = audio.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=TAXA_AMOSTRAGEM,
        input=True,
        input_device_index=device_index,
        frames_per_buffer=CHUNK
    )

except Exception as erro:
    print("\nERRO AO ABRIR O MICROFONE:")
    print(erro)
    audio.terminate()
    input("\nPressione Enter para sair...")
    raise SystemExit

stream.start_stream()

# ============================================================
# INICIAR TESTE
# ============================================================

print("\n" + "=" * 60)
print("🎙️  JARVIS ESTÁ OUVINDO")
print("=" * 60)
print("Fale normalmente.")
print("Quando terminar uma frase, o texto aparecerá.")
print("Pressione CTRL + C para encerrar.\n")

# ============================================================
# RECONHECIMENTO
# ============================================================

try:

    while True:

        dados = stream.read(
            CHUNK,
            exception_on_overflow=False
        )

        # Resultado final
        if recognizer.AcceptWaveform(dados):

            resultado = json.loads(
                recognizer.Result()
            )

            texto = resultado.get("text", "").strip()

            if texto:
                print(f"\n✅ Você disse: {texto}\n")

        # Resultado parcial enquanto fala
        else:

            parcial = json.loads(
                recognizer.PartialResult()
            )

            texto_parcial = parcial.get(
                "partial",
                ""
            ).strip()

            if texto_parcial:
                print(
                    f"\r🎧 Ouvindo: {texto_parcial}",
                    end="",
                    flush=True
                )

except KeyboardInterrupt:

    print("\n\nTeste encerrado pelo usuário.")

# ============================================================
# ENCERRAR
# ============================================================

finally:

    print("\nFechando microfone...")

    stream.stop_stream()
    stream.close()

    audio.terminate()

    print("Microfone encerrado.")
    print("\nJARVIS: Até logo, senhor.")