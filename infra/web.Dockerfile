# Fallback: serve the built frontend from Cloud Run (no Firebase Hosting / ToS dependency).
# Build from repo root:  docker build -f infra/web.Dockerfile \
#   --build-arg VITE_WS_URL=wss://<agents-run-url>/ws \
#   --build-arg VITE_API_BASE=https://<agents-run-url> \
#   --build-arg VITE_VOICE_WS_URL=wss://<voice-run-url> \
#   --build-arg VITE_MAPS_API_KEY=<key> \
#   --build-arg VITE_DEMO_MODE=live  .
FROM node:20-slim AS build
# web/ builds at /app/web with contracts/ as its sibling at /app/contracts, so that
# src/lib/replay.ts's `../../../contracts/fixtures/ws_replay.jsonl?raw` import resolves
# (mirrors the repo layout the host Firebase build relied on).
WORKDIR /app/web
COPY web/package.json web/package-lock.json* ./
RUN npm install --no-audit --no-fund
COPY web/ ./
COPY contracts/fixtures/ /app/contracts/fixtures/
ARG VITE_WS_URL
ARG VITE_API_BASE
ARG VITE_VOICE_WS_URL
ARG VITE_MAPS_API_KEY
ARG VITE_DEMO_MODE=live
ENV VITE_WS_URL=$VITE_WS_URL \
    VITE_API_BASE=$VITE_API_BASE \
    VITE_VOICE_WS_URL=$VITE_VOICE_WS_URL \
    VITE_MAPS_API_KEY=$VITE_MAPS_API_KEY \
    VITE_DEMO_MODE=$VITE_DEMO_MODE
RUN npm run build

FROM nginx:alpine
COPY infra/web.nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/web/dist /usr/share/nginx/html
EXPOSE 8080
