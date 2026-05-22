# ── Stage 1: build the React frontend ────────────────────────────────────────
FROM node:20-slim AS frontend

WORKDIR /app/web
COPY web/package.json web/package-lock.json ./
RUN npm ci

COPY web/ ./
RUN npm run build

# ── Stage 2: final Python image ───────────────────────────────────────────────
FROM python:3.12-slim

# System deps required by lutz's heavier Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install the package first (deps layer — changes rarely)
COPY pyproject.toml README.md ./
COPY lutz/ ./lutz/

# Copy the pre-built React SPA where hatchling expects it
COPY --from=frontend /app/web/dist ./lutz/web/

RUN pip install --no-cache-dir .

# Project directory mounted at runtime
VOLUME ["/project"]
WORKDIR /project

EXPOSE 8765

ENV LUTZ_PROJECT_ROOT=/project

ENTRYPOINT ["lutz", "web", "--host", "0.0.0.0", "--no-browser"]
