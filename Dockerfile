# Stage 1: Build mobile frontend
FROM node:20-alpine AS build-mobile
WORKDIR /app/static/mobile-app
COPY static/mobile-app/package*.json ./
RUN npm ci
COPY static/mobile-app/ ./
RUN npm run build

# Stage 2: Build Python backend
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Copy built mobile app assets
COPY --from=build-mobile /app/static/mobile-app/dist /app/static/m

# 数据持久化目录
RUN mkdir -p /app/data
VOLUME /app/data

ENV NOVEL_DATA_DIR=/app/data

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
