FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# CPU-версія torch для sentence-transformers (образ менший, ніж із CUDA)
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch

# Шрифт із кирилицею для експорту тестів у PDF
RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

# --- dev: код монтується томом, автоперезавантаження ---
FROM base AS dev
COPY . .
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# --- prod ---
FROM base AS prod
ENV HF_HOME=/models
RUN useradd --create-home appuser && mkdir -p /data/uploads /models && chown appuser /data/uploads /models
COPY --chown=appuser . .
USER appuser
EXPOSE 8000
# Один воркер: бюджет токенів і фонова генерація живуть у пам'яті процесу
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers"]
