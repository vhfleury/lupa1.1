# syntax=docker/dockerfile:1
# Testes ponta a ponta do front com Playwright (Chromium), contra a stack real pelo proxy.
FROM mcr.microsoft.com/playwright:v1.49.1-noble
WORKDIR /e2e
RUN chown pwuser:pwuser /e2e
USER pwuser
COPY --chown=pwuser:pwuser package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY --chown=pwuser:pwuser . .
RUN npm run typecheck
CMD ["npm", "run", "e2e"]
