# API와 워커가 같이 쓰는 이미지. 실행 명령으로 역할을 고른다: api | worker | migrate | seed
FROM node:22-alpine AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    STATIC_DIR=/app/static
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/alembic.ini .
COPY backend/migrations migrations
COPY backend/app app
COPY --from=web /web/dist static
RUN useradd --uid 10001 --create-home app
USER app
EXPOSE 8000
ENTRYPOINT ["python", "-m", "app"]
CMD ["api"]
