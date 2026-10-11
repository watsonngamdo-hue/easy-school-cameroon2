# ---------- Étape 1 : construction des roues Python ----------
FROM python:3.12-slim AS builder
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --upgrade pip && pip wheel --no-cache-dir --wheel-dir /app/wheels -r requirements.txt

# ---------- Étape 2 : image d'exécution ----------
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && addgroup --system django && adduser --system --ingroup django django
WORKDIR /app
COPY --from=builder /app/wheels /wheels
COPY requirements.txt .
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt && rm -rf /wheels
COPY --chown=django:django . .
# collectstatic n'a besoin d'aucun secret réel
RUN SECRET_KEY=build-only DEBUG=False python manage.py collectstatic --noinput \
    && mkdir -p /app/media /app/private_media && chown -R django:django /app/media /app/private_media /app/staticfiles
USER django
EXPOSE 8000
CMD ["gunicorn", "Elearning.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120"]
