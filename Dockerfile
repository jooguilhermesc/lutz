# ── Stage 1: build the React frontend ────────────────────────────────────────
FROM node:20-slim AS frontend
WORKDIR /app/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# ── Stage 2: Python image ─────────────────────────────────────────────────────
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY lutz/ ./lutz/
COPY --from=frontend /app/web/dist ./web/dist/
RUN pip install --no-cache-dir . && rm -rf /app/web

# The project folder is mounted at runtime. The API has no authentication: publish the port
# on the loopback interface only, e.g.  docker run -p 127.0.0.1:8765:8765 -v "$PWD":/project lutz
# Models run through OpenRouter (ADR-004): pass OPENROUTER_API_KEY at runtime, never bake it in.
VOLUME ["/project"]
WORKDIR /project
EXPOSE 8765
ENTRYPOINT ["lutz", "web", "--host", "0.0.0.0", "--permitir-rede", "--porta", "8765", "--sem-navegador", "--projeto", "/project"]
