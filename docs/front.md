# Front do Lupa (Etapa 6)

## Arquitetura

```
navegador ──HTTPS──> proxy (Caddy, tls internal, :8443)
                       ├── /api/*  ──> api:8000   (prefixo /api removido)
                       └── /*      ──> front:8080 (SPA estática, Caddy sem TLS)
```

- **Framework:** SvelteKit 2 + Svelte 5 (runes), TypeScript estrito, `adapter-static` com
  `fallback: index.html` (SPA, `ssr = false`). CSS próprio com tokens; nenhuma biblioteca de UI.
  Única dependência de execução: `qrcode` (gera a matriz do QR; o SVG é desenhado pelo componente).
- **Mesmo origin:** front e API respondem em `https://localhost:8443`. Não há CORS e o cookie
  `lupa_sessao` (`HttpOnly`, `Secure`, `SameSite=Strict`, `Path=/`) funciona sem ajuste na API.
  A API não sabe do prefixo `/api`: o Caddy o remove (`handle_path`), então `api/app.py` ficou
  intocado (sem `root_path`).
- **IP real:** o Caddy grava o IP do cliente no `X-Forwarded-For` (ignora o recebido de fora). A
  API roda com `--proxy-headers --forwarded-allow-ips <sub-rede da rede borda>`; a rede `borda`
  tem sub-rede fixa (`REDE_BORDA_SUBREDE`, padrão `172.31.240.0/24`). Auditoria e rate limit por
  IP veem o cliente, não o proxy.
- **Redes:** `borda` (proxy, front, api), `cliente` (proxy e o contêiner de E2E). O E2E não
  alcança a API nem o banco diretamente.
- **Certificado:** autoassinado pela CA interna do Caddy, em tmpfs: um certificado novo a cada
  subida do proxy. O navegador avisa no primeiro acesso; aceite a exceção (piloto local).
- **Porta da API no host:** a interface usa só o proxy. Com `API_PORTA_HOST` definida a API
  continua publicada nela (compatibilidade com scripts); sem a variável, o Docker escolhe uma
  porta efêmera, sempre só em `127.0.0.1`.

## Telas

| Rota | Quem | O que faz |
| --- | --- | --- |
| `/login` | todos | usuário e senha → código TOTP; no primeiro acesso, QR code + chave em texto + URI `otpauth://` para cadastrar o autenticador |
| `/trocar-senha` | logado | troca obrigatória (senha temporária) ou voluntária; enquanto pendente, o guarda de rotas só permite esta tela |
| `/` | logado | início com o estado da sessão |
| `/usuarios` | desembargador, admin | lista, cria (senha temporária exibida uma vez), desativa, reativa, reseta senha e autenticador |
| `/gabinetes` | admin | lista e cria gabinetes; cria desembargadores |

Guarda de rotas (`src/routes/+layout.ts`): a cada navegação consulta `GET /api/auth/sessao`.
Sem sessão → `/login` (com o aviso "Sua sessão expirou" quando havia sessão antes); troca de
senha pendente → `/trocar-senha`. Qualquer chamada que receba `401 não autenticado` também volta
ao login com o aviso.

Mensagens de login: 401 e 422 do primeiro passo viram sempre "Usuário ou senha inválidos."; 429
vira "Muitas tentativas…", sem dizer se o usuário existe.

Matriz de papéis: `GET /api/auth/sessao` devolve as permissões do papel (`papeis.py`), e
`src/lib/permissoes.ts` só decide o que **mostrar**. O servidor reconfere tudo (o E2E prova com
chamadas diretas que recebem 403).

## Rotas novas na API (para o front)

- `GET /auth/sessao`: usuário, papel, gabinete, troca pendente e permissões; funciona com troca
  pendente.
- `GET /gabinetes`: lista de gabinetes, só administrador (`exige_papel(GERIR_GABINETES)`).

## Comandos

Tudo roda em contêiner; não é preciso Node no host.

| Comando | Onde | O que faz |
| --- | --- | --- |
| `npm run lint` | build da imagem `front` | ESLint 9 + typescript-eslint strict + eslint-plugin-svelte, `--max-warnings 0`, proíbe `{@html}` |
| `npm run typecheck` | idem | `svelte-check --fail-on-warnings` (inclui avisos de acessibilidade do compilador) |
| `npm test` | idem | Vitest + Testing Library em jsdom |
| `npm run e2e` | contêiner `e2e` | Playwright (Chromium) contra a stack real via `https://proxy:8443` |

```
docker build --target verificacao front          # lint + typecheck + testes unitários
docker compose up -d --build --wait              # a imagem do front só sai se os três passarem
bash front/scripts/e2e.sh                        # ou: powershell front/scripts/e2e.ps1
```

`front/scripts/e2e.sh` sobe a stack, roda `scripts/e2e_preparar.py` no contêiner da API (garante
o administrador pelo caso de uso do `criar_admin.py`, dá a ele uma senha temporária aleatória com
troca obrigatória, apaga o autenticador e limpa falhas/bloqueios de login; só em
desenvolvimento/teste), passa nome e senha ao contêiner `e2e` por variável de ambiente (nada em
arquivo) e roda `npm run e2e`. O teste resolve o MFA calculando o TOTP a partir da URI
`otpauth://` mostrada na tela. **Atenção:** o script reseta o administrador do banco de
desenvolvimento a cada execução.

`scripts/verificar.sh` ganhou o passo `== front ==` no fim: com Docker disponível (host) refaz o
estágio `verificacao`; com Node, roda `npm run verificar`; dentro do contêiner da API (sem Node
nem Docker) confere o carimbo `http://front:8080/verificacao.json`, gerado no build só depois de
lint, typecheck e testes passarem (o carimbo traz o SHA-256 das fontes verificadas).

## Acessibilidade

Rótulos em todos os campos, `role="alert"` para erros e `role="status"` para avisos, link "Pular
para o conteúdo", menu em `<nav aria-label>` com `aria-current`, foco visível (3 px) e foco
movido para o primeiro campo a cada passo do login, botões das linhas com nome acessível que
inclui o usuário ("Desativar fulano"), tabela com `caption` e cabeçalhos `scope`. Tema claro ou
escuro segundo o sistema (`prefers-color-scheme`), com contraste AA nos tokens.

## Chat (6.8) e auditoria (6.9)

| Rota | Quem | O que faz |
| --- | --- | --- |
| `/processos/[id]/chat` | quem vê o processo | pergunta; resposta com aviso "conteúdo gerado por IA", citações clicáveis, desfecho marcado (sem citação válida, recusa com sugestão, descartada, teto), contador de citações descartadas por resposta e por conversa; histórico das conversas; processo em revisão com botão "Liberar revisão" para desembargador/admin |
| `/auditoria` | desembargador (próprio gabinete), admin (escolhe gabinete ou todos) | filtros (gabinete só para admin, usuário, processo, ação, intervalo, IP), paginação por cursor, exportação CSV/JSON (download direto de `/api/auditoria/exportar`), verificação da cadeia, relatório de uso por processo ou usuário com custo estimado |

**Combinado com o visualizador (6.6):** a citação do chat aponta para
`/processos/{id}/visualizador?arquivo={arquivo_id}&pagina={numero}` (corrigido na 6.10: a rota
`/paginas/{numero}` da 6.8 não existia e caía no 404 da SPA, e levava o trecho dos autos na URL).
`numero` é o número da página no arquivo; `arquivo` desambigua processos com mais de um arquivo.
A API do chat devolve `pagina_numero` e `arquivo_id` em cada citação.

**Modelo falso no E2E:** `front/scripts/e2e.sh` exporta `LUPA_AGENTE_CLIENTE=falso` antes de subir
a stack; a API usa então o roteiro `src/lupa/agente/dados/roteiro_falso.json` (recusado em
produção). Ao terminar (mesmo em falha ou Ctrl+C, por `trap`; no `.ps1`, por `finally`), o
script recria o serviço `api` sem a variável (6.10). `scripts/e2e_semear_chat.py --carga` cria desembargador e processo sintéticos e, só na
primeira vez, 1 milhão de eventos de auditoria em 40 gabinetes "carga" (gerador do
`tests/auditoria/test_carga.py`).

## Segurança, acessibilidade e E2E consolidado (6.10)

**Cabeçalhos do proxy** (`proxy/Caddyfile`), em todas as respostas (SPA, estáticos e `/api`):

| Cabeçalho | Valor |
| --- | --- |
| `Content-Security-Policy` | `default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-hashes' 'sha256-S8qMpvofolR8Mpjy4kQvEm7m1q8clzU4dfDH0AmvZjo='; img-src 'self'; font-src 'self'; connect-src 'self'; manifest-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'; object-src 'none'` |
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` (só vale em produção com certificado real; com o certificado autoassinado o navegador ignora) |
| `Permissions-Policy` | câmera, microfone, geolocalização, pagamento, USB etc. desligados |
| `Cross-Origin-Opener-Policy` / `Cross-Origin-Resource-Policy` | `same-origin` |
| já existentes | `X-Content-Type-Options nosniff`, `Referrer-Policy no-referrer`, `X-Frame-Options DENY`, sem `Server` |

Nada inline, sem `unsafe-inline`: o `<script>` de partida que o SvelteKit grava no
`index.html` vira `/inicio.js` no build (`front/scripts/externalizar-inicio.mjs`, que também aplica
o tema salvo antes do primeiro desenho e falha o build se sobrar script, `<style>`, atributo
`style` ou `on*=` no HTML); os estilos dinâmicos (zoom e destaque do visualizador) usam a diretiva
`style:` do Svelte, que escreve pela API CSSOM (permitida pela CSP), e não atributo `style`.
Única exceção: o anunciador de rota do SvelteKit (`div` `aria-live` gerada pelo framework, com
atributo `style` fixo) — permitido só pelo hash SHA-256 desse texto exato com `'unsafe-hashes'`
(a varredura confere o hash; qualquer outro estilo inline continua bloqueado).
Varredura: `scripts/verificar_cabecalhos.py` (passo `== cabecalhos de seguranca ==` do
`verificar.sh`/`.ps1`; falha se faltar cabeçalho ou a CSP afrouxar; proxy fora do ar só avisa, a
menos que `LUPA_EXIGIR_CABECALHOS=1`) e `front/e2e/testes/seguranca.spec.ts`.

**Conteúdo dos autos só como texto** (`prompt-injection.md`, seção 6): nenhum `{@html}` (regra do
ESLint), `innerHTML`, renderizador de Markdown nem "linkificação"; os únicos links montados pelo
front usam ids (citação → visualizador), nunca o texto. `src/lib/seguranca.test.ts` renderiza a
mensagem do chat com `<script>`, `[link](http://x)` e `http://exemplo` e varre as fontes;
`seguranca.spec.ts` pergunta no chat de um processo sintético cuja certidão traz esses padrões
(`scripts/e2e_semear_chat.py`) e confere que saem literais, que nada executou e que não há link
externo na página.

**Acessibilidade:** varredura `@axe-core/playwright` (WCAG 2.1 A/AA) em login, início, processos,
processo, dossiê, visualizador, validações, chat, auditoria, usuários e gabinetes, nos temas claro
e escuro, sem violação séria ou crítica; navegação por teclado com foco visível (login, menu,
pular para o conteúdo, visualizador); `aria-live` no progresso do envio (degraus de 10%) e
`role="status"` nos "Carregando…". Tema manual (claro, escuro, do sistema) no cabeçalho e no
rodapé das telas sem moldura, guardado só em `localStorage` (`lupa.tema`).

**Confirmações e sessão:** desativar usuário e liberar revisão abrem um `<dialog>` modal com
foco em "Cancelar" (Esc cancela). Uma recarga completa sem sessão válida, quando o separador
tinha sessão (marcador `lupa.sessao-anterior` em `sessionStorage`, sem nenhum dado da sessão),
leva a `/login?motivo=expirada` com "Sessão encerrada ou expirada"; sair de propósito apaga o
marcador.

**Suíte E2E:** dois projetos no `playwright.config.ts`. `fluxos` (6.1 a 6.9) faz o primeiro acesso
de cada conta e a guarda pela fixture global (`testes/global-setup.ts` limpa
`/tmp/lupa-e2e-estado` no contêiner efêmero; `testes/credenciais.ts` guarda senha, segredo TOTP,
último passo usado e o estado de sessão do navegador). `finais` depende de `fluxos`:
`acessibilidade.spec.ts`, `seguranca.spec.ts` e `auditoria-admin.spec.ts` (admin vê todos os
gabinetes, custo no relatório por usuário, aviso de sessão expirada). Rodar tudo:
`bash front/scripts/e2e.sh` (ou `front/scripts/e2e.ps1`). No host, `scripts/verificar.ps1` roda a
suíte no passo opcional `== e2e ==` com `LUPA_VERIFICAR_E2E=1`; dentro do contêiner da API o
passo não existe (sem Docker).

**Limpeza do banco de desenvolvimento:** `python scripts/limpar_dev.py` (no contêiner da API)
mostra quantos gabinetes sintéticos ("Gabinete ponta a ponta", "Gabinete de calibração",
"Gabinete E2E", "Gabinete Processos E2E", "carga", "e2e") e eventos seriam removidos;
`--sim` remove tudo numa transação (eventos desses gabinetes, com a trava append-only desligada só
dentro da transação, e todas as linhas com `gabinete_id` deles). Recusa fora de
`desenvolvimento`/`teste` e se algum evento da cadeia global apontar para esses usuários. Não
apaga objetos no MinIO. Depois dela, o próximo E2E recria a carga de 1 milhão de eventos.

