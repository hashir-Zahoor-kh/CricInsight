# CricInsight backend — FastAPI + async SQLAlchemy
# Multi-stage avoided for now: a single thin image keeps local dev fast and
# the production image is rebuilt on every ECS deploy anyway.

FROM python:3.11-slim

# Prevent .pyc files and force unbuffered stdout so logs surface immediately
# in `docker compose logs` and CloudWatch.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System deps:
#  - libpq-dev / gcc are needed at install-time for psycopg2-binary's optional
#    builds and any source wheels (asyncpg ships wheels but kept for safety).
#  - curl is used by the ECS health check.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first so docker layer cache survives source changes.
COPY requirements.txt ./
RUN pip install -r requirements.txt

# Copy the rest of the backend (app/, ingestion/, alembic/, tests/).
COPY . .

EXPOSE 8000

# uvicorn with --reload is convenient locally but disabled in prod images.
# docker-compose overrides this command for hot-reload during development.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
