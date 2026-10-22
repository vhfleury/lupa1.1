# Relatório da Etapa 6.1 — Esqueleto do front

## Decisões de arquitetura

| Decisão | Escolha | Por quê |
| --- | --- | --- |
| Framework | **SvelteKit 2 + Svelte 5**, `adapter-static`, SPA (`ssr = false`) | Bundle pequeno e sem runtime pesado; TypeScript estrito de ponta a ponta (`svelte-check`); avisos de acessibilidade do compilador viram erro no typecheck. Next.js traria React + servidor Node para SSR que não usamos: toda a autorização está na API, e uma SPA estática não precisa repassar cookie em servidor intermediário. |
| UI | CSS próprio com tokens (`src/app.css`), claro/escuro por `prefers-color-scheme` | Sem biblioteca de UI; única dependência de execução é `qrcode` (matriz do QR). |
| Servir o front | Serviço `front`: imagem multi-estágio; o estágio `verificacao` roda lint, typecheck e testes e o build só continua se passarem; runtime Caddy estático, usuário `10001`, `read_only`, `no-new-privileges` | Build de produção, não root. |
| Mesmo origin | Serviço `proxy` (Caddy 2.8.4): `/api/*` → `api:8000` com o prefixo removido (`handle_path`), `/*` → `front:8080`; `tls internal` em `https://localhost:8443` (`PROXY_PORTA_HOST`) | Sem CORS; cookie `Secure`/`SameSite=Strict` funciona. `api/app.py` não precisou de `root_path`. |
| IP real na API | `command` da `api` no compose com `--proxy-headers --forwarded-allow-ips <sub-rede borda>`; rede `borda` com sub-rede fixa (`REDE_BORDA_SUBREDE`) | Auditoria e rate limit por IP veem o cliente (conferido: eventos do E2E gravados com o IP do contêiner `e2e`, não o do proxy). |
| Porta direta da API | `127.0.0.1:${API_PORTA_HOST:-}:8000` | Com a variável definida, continua publicando nela (o `.env` atual usa 18000); sem ela, porta efêmera só em loopback. O compose não tem publicação condicional; esta é a forma mais próxima de "não publicar". |
| Testes | Vitest + Testing Library (jsdom) para componentes; Playwright 1.49.1 em contêiner (`e2e`, perfil `e2e`, rede `cliente`) | Ver 6.2 e 6.3. |
| Lockfiles | `package-lock.json` gerados num contêiner `node:22.12.0-alpine3.20` e lidos pela saída padrão; `npm ci` no build | Node não existe no host; nenhuma cópia de diretório do contêiner para o host. `picomatch` 4.0.2 fixado como devDependency para contornar um erro de consistência do `npm ci` 10.9 (lock com `picomatch@2` hoisted). |

## O que foi feito

- `front/`: projeto SvelteKit (`package.json`, `svelte.config.js`, `vite.config.ts`,
  `tsconfig.json` com `strict`, `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`),
  `eslint.config.js` (typescript-eslint strict, eslint-plugin-svelte, `no-at-html-tags` como erro,
  `--max-warnings 0`), `Dockerfile`, `Caddyfile`, `scripts/carimbo.mjs`.
- Layout base (`src/routes/+layout.svelte`): cabeçalho com nome do usuário, papel e "Sair"; menu
  lateral (Início, Usuários e Gabinetes conforme as permissões); link "Pular para o conteúdo".
- Guarda de rotas (`src/routes/+layout.ts`) consultando `GET /api/auth/sessao` a cada navegação.
- Página inicial autenticada com o estado da sessão.
- `docker-compose.yml`: serviços `front`, `proxy`, `e2e` (perfil), redes `borda` e `cliente`,
  `command` da API com proxy headers. `proxy/Caddyfile`. `.env.example`, `.gitignore`, README e
  `docs/front.md` com acréscimos.
- `scripts/verificar.sh` e `.ps1`: passo `== front ==` no fim (ver `docs/front.md`).

## Correção 1 herdada da Revisão da Etapa 3 — auditoria antes da resposta

`auditoria_middleware` (`src/lupa/api/middleware.py`) já rodava depois de `call_next`, mas a
resposta devolvida por `call_next` é um streaming cujo corpo ainda não saiu para o cliente. A
gravação agora acontece ali, antes de devolver a resposta, dentro de `try`: se falhar, o corpo
interno é descartado (`aclose`) e o cliente recebe `500 {"detail": "falha ao registrar a
auditoria; conteúdo não entregue"}`; o erro vai para o log. A gravação usa sessão própria (a
sessão da requisição já foi confirmada pela dependência), o que mantém o middleware genérico
para as rotas de conteúdo da Etapa 6.

Teste: `tests/api/test_auditoria_antes_da_resposta.py::test_falha_ao_gravar_auditoria_vira_500_e_o_conteudo_nao_sai`
— simula falha de gravação, confere 500, ausência do número/classe do processo no corpo e
nenhum evento gravado; desfeita a falha, 200 com o evento `processo_aberto`.

## Critério de aceite

| Critério | Evidência |
| --- | --- |
| `docker compose up` sobe `front` e `proxy` | `docker compose up -d --build --wait`: todos os serviços `healthy` |
| `https://localhost:8443/` redireciona para login | E2E `6.1 rota protegida redireciona para o login…`; `curl -k https://localhost:8443/api/saude` → `{"api":"ok","db":"ok","minio":"ok"}` |
| Página inicial autenticada carrega após login | E2E `6.2 admin…` termina na página inicial com "Sessão ativa" e papel "Administrador" |
| Lint, typecheck, teste de componente | `npm run lint` 0 avisos; `svelte-check` 0 erros e 0 avisos; Vitest 18 testes em 3 arquivos |

## Fora do escopo desta subetapa

CSP, HSTS e demais cabeçalhos de segurança completos (6.10; já há `nosniff`, `Referrer-Policy`,
`X-Frame-Options`). Alternância manual de tema (só segue o sistema).
