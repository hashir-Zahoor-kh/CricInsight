# CricInsight backend — FastAPI + async SQLAlchemy
# Multi-stage avoided for now: a single thin image keeps local dev fast and
# the production image is rebuilt on every ECS deploy anyway.

FROM python:3.12-slim

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

# Shell form so $PORT is expanded at container start — Railway, ECS, and
# Cloud Run all inject PORT at runtime. Falls back to 8000 for plain
# `docker run` without -e PORT. `exec` gives uvicorn PID 1 so SIGTERM
# from the orchestrator is delivered directly and triggers graceful shutdown.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
