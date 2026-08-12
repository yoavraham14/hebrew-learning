# Multi-stage build: React frontend, then the FastAPI backend serving both
# the API and the built frontend from one container (Cloud Run — see
# DEPLOY.md). Not used for local dev (see README.md — backend and frontend
# run natively there for hot reload); this is the production image only.

# ---- Stage 1: build the frontend ----
FROM node:20-alpine AS frontend-build
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# Empty, not unset: same-container serving means the frontend calls /api/...
# as a relative path, not an absolute origin. See src/api/client.ts and
# src/components/AudioButton.tsx — both prefix requests with this value.
ENV VITE_API_URL=""
RUN npm run build

# ---- Stage 2: the backend, serving both API and the built frontend ----
FROM python:3.12-slim AS backend
WORKDIR /app

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./

# See app/main.py's STATIC_DIR — must land at /app/static, sibling to ./app,
# not inside it.
COPY --from=frontend-build /frontend/dist ./static

# Cloud Run injects PORT (default 8080) and expects the container to listen
# on it — never hardcode a port here. Shell form (not exec-form JSON array)
# specifically so ${PORT} actually expands.
ENV PORT=8080
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
