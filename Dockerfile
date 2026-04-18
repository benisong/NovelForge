# Stage 1: Build mobile frontend
FROM node:20-alpine AS build-mobile
WORKDIR /app/static/mobile-app
COPY static/mobile-app/package*.json ./
RUN npm ci
COPY static/mobile-app/ ./
RUN npm run build

# Stage 2: Python backend
FROM python:3.11-slim

# 创建非 root 运行用户
RUN groupadd --system --gid 1000 app \
 && useradd --system --uid 1000 --gid app --home /app --shell /usr/sbin/nologin app

WORKDIR /app

COPY --chown=app:app requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=app:app . .
# Copy built mobile app assets
COPY --from=build-mobile --chown=app:app /app/static/mobile-app/dist /app/static/m

# 数据持久化目录
RUN mkdir -p /app/data && chown -R app:app /app/data
VOLUME /app/data

ENV NOVEL_DATA_DIR=/app/data \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

USER app

EXPOSE 17000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "17000"]
