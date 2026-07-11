# Runs as a non-root user; reads config from environment variables at
# runtime (see .env.example in amorim-crm-deploy/) — nothing secret is
# baked into the image.

FROM python:3.12-slim
WORKDIR /app

RUN adduser --disabled-password --gecos "" appuser

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

USER appuser
EXPOSE 8000

# --workers 2: um processo lento (ex.: upload bloqueante que escapou do
# run_in_threadpool) não trava os outros workers — cada um tem seu próprio
# event loop. Ajustar conforme CPU disponível na VPS se ela crescer.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
