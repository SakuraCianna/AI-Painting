FROM python:3.12.10-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY backend/requirements.txt /app/backend/requirements.txt
COPY backend/requirements-local-asr.txt /app/backend/requirements-local-asr.txt
RUN python -m pip install --no-cache-dir -r /app/backend/requirements.txt
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/backend/data \
    && chown -R appuser:appuser /app

COPY backend/app /app/backend/app
COPY backend/local_asr_qwen3.py /app/backend/local_asr_qwen3.py
USER appuser

EXPOSE 8080

CMD ["python", "-m", "uvicorn", "app.main:app", "--app-dir", "/app/backend", "--host", "0.0.0.0", "--port", "8080"]
