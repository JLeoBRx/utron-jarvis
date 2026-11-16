# JARVIS Gateway — imagem do serviço da JARVIS WEB ORB (sem inteligência, sem memória, sem chaves de IA)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    JARVIS_HOST=0.0.0.0 JARVIS_PORT=8080 JARVIS_GATEWAY_DB=/data/gateway.sqlite3 \
    JARVIS_SCENE_DIR=/app/scene JARVIS_TRUST_PROXY=1

WORKDIR /app
COPY gateway/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt && useradd --system --uid 10001 --home /app jarvis \
    && mkdir -p /data && chown jarvis /data
COPY gateway/jarvis_gateway /app/jarvis_gateway
# só os módulos 3D da ORBE (a cena do JARVIS) — nada do resto do programa entra na imagem
COPY ultron/hud/scene3d/web/js /app/scene/js
COPY ultron/hud/scene3d/web/css/tokens.css /app/scene/css/tokens.css
COPY ultron/hud/scene3d/web/vendor/three /app/scene/vendor/three

USER jarvis
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=4).status == 200 else 1)"
CMD ["python", "-m", "jarvis_gateway"]
