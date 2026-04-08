# Stage 1: Flutter 웹 빌드
FROM ghcr.io/cirruslabs/flutter:3.41.5 AS builder

WORKDIR /app
COPY pubspec.yaml pubspec.lock ./
RUN flutter pub get

COPY . .

ARG API_URL=http://localhost:8000
ARG DEPLOY_ENV=local
ARG BASE_HREF=/

RUN flutter build web --release \
    --base-href "${BASE_HREF}" \
    --dart-define=DEPLOY_ENV=${DEPLOY_ENV}

# Stage 2: Nginx 서빙
FROM nginx:alpine

COPY nginx/default.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/build/web /usr/share/nginx/html

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
