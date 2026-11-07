# 1) собираем React Mini App
FROM node:22-slim AS web
WORKDIR /web
COPY webapp/package.json webapp/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY webapp/ ./
RUN npx tsc -b && npx vite build --outDir /dist

# 2) Python: бот + API + раздача собранного приложения
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATA_DIR=/data
WORKDIR /bot
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY --from=web /dist ./app/web/dist
VOLUME /data
EXPOSE 8080
CMD ["python", "-m", "app"]
