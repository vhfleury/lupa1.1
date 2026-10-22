# syntax=docker/dockerfile:1
# Front do Lupa (SvelteKit, SPA estatica). O build so termina se lint, typecheck e testes passarem.
FROM node:22.12.0-alpine3.20 AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

FROM deps AS verificacao
COPY . .
RUN npm run lint && npm run typecheck && npm test \
 && node scripts/carimbo.mjs > /app/verificacao.json

FROM verificacao AS build
RUN npm run build && cp /app/verificacao.json /app/build/verificacao.json

FROM caddy:2.8.4-alpine AS runtime
ENV XDG_CONFIG_HOME=/tmp/config XDG_DATA_HOME=/tmp/data
COPY Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/build /srv
USER 10001:10001
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=5 \
  CMD wget -qO- http://127.0.0.1:8080/verificacao.json >/dev/null || exit 1
CMD ["caddy", "run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]
