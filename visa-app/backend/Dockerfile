# Stage 1: フロントエンドビルド
FROM node:22-slim AS frontend-build

WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: バックエンド
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends zstd && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/main.py .
COPY backend/application_data.py .
COPY backend/data/ data/
COPY backend/extractors/ extractors/
COPY --from=frontend-build /build/dist/ static/

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
