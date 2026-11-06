# Front do Lupa

Interface web do Lupa: SvelteKit 2 + Svelte 5, TypeScript, gerada como SPA estática e servida por
Caddy. O documento principal (arquitetura, telas, segurança, E2E) é
[docs/sistema/front.md](../docs/sistema/front.md).

## Pastas

| Caminho | Conteúdo |
| --- | --- |
| `src/routes/` | Telas, uma pasta por rota (`login`, `processos/[id]/chat`, `usuarios`...) |
| `src/lib/` | Cliente da API, sessão, permissões e tema. Testes Vitest ao lado (`*.test.ts`) |
| `src/lib/<assunto>/` | Lógica e componentes de cada assunto: `auditoria`, `chat`, `processos`, `visualizador` |
| `src/lib/componentes/` | Componentes usados por mais de uma tela |
| `static/` | Favicon e logos |
| `e2e/` | Testes ponta a ponta (Playwright), com imagem própria. Suíte em `e2e/testes/` |
| `scripts/` | `e2e.sh` e `capturas.sh` (com o preparo comum em `preparar-e2e.sh`), `carimbo.mjs` e `externalizar-inicio.mjs` (usados no build) |
| `Dockerfile`, `Caddyfile` | Imagem: verificação, build e servidor estático na porta 8080 |

## Comandos

Tudo roda em contêiner. Não é preciso Node na máquina. Os comandos abaixo partem da raiz do repositório.

```bash
docker build --target verificacao front
```

Roda lint, typecheck e testes unitários. O `docker compose up --build` só gera a imagem do front se
os três passarem.

```bash
bash front/scripts/e2e.sh
```

Roda os testes ponta a ponta contra a stack real. **Reseta o administrador do banco de
desenvolvimento.**

```bash
bash front/scripts/capturas.sh
```

Gera as capturas de tela dos guias em `docs/imagens/`.
