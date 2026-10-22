# Relatório da Etapa 6.2 — Login e MFA

## O que foi feito

- `/login` (`front/src/routes/login/+page.svelte`): usuário e senha → segundo passo.
  - `etapa: mfa`: campo do código de 6 dígitos (`inputmode=numeric`, `autocomplete=one-time-code`).
  - `etapa: configurar_mfa` (primeiro acesso ou MFA resetado): QR code desenhado no cliente a
    partir da URI `otpauth://` (`QrCode.svelte`, SVG gerado da matriz, sem `{@html}`), chave em
    texto para digitação e a URI completa num `<details>`; confirma em `/auth/mfa/confirmar`.
  - Erros: 401/422 do primeiro passo → sempre "Usuário ou senha inválidos."; 429 → "Muitas
    tentativas. Aguarde alguns minutos e tente novamente." (sem revelar se o usuário existe);
    código errado → "Código inválido ou expirado…".
- `/trocar-senha`: senha atual, nova e confirmação; enquanto `troca_senha_obrigatoria`, o guarda
  de rotas manda toda navegação para cá e a API responde 403 nas demais rotas.
- Logout no cabeçalho (`POST /api/auth/logout`) e na tela de troca.
- Expiração: o guarda de rotas e o cliente da API (`src/lib/api.ts`) tratam `401 não
  autenticado` levando a `/login?motivo=expirada` com o aviso "Sua sessão expirou. Entre
  novamente.".
- API: `GET /auth/sessao` (usuário, papel, gabinete, troca pendente, permissões), aceito mesmo
  com troca pendente.
- E2E: `front/e2e` (Playwright 1.49.1, Chromium) com `testes/totp.ts` (RFC 6238 com
  `node:crypto`; nunca repete passo, como o servidor exige) e `scripts/e2e_preparar.py` (admin
  com senha temporária aleatória gerada na hora, passada por variável de ambiente).

## Correção 2 herdada da Revisão da Etapa 3 — bloqueio que permitia negação de serviço

`src/lupa/acesso/servico.py`:

- **Bloqueio progressivo por nome:** a 5ª falha seguida bloqueia por 1 minuto, a 10ª por 5, a
  15ª (e cada 5 a mais) por 15 (`duracao_bloqueio`). As falhas contam numa janela de 24 h e zeram
  no login certo. Cada bloqueio grava `login_bloqueado`; cada tentativa durante o bloqueio grava
  `login_falha/bloqueado`. Antes: 15 minutos fixos já na 5ª falha.
- **Rate limit por IP:** 20 falhas (senha ou TOTP) do mesmo IP em 15 minutos recusam qualquer
  login desse IP com a mesma mensagem 429. Ao atingir o limite grava `login_bloqueado` com
  `objeto_tipo="ip"`; cada recusa grava `login_falha/bloqueado` com `objeto_tipo="ip"`. A chave é
  o SHA-256 de `ip:<endereço>` na mesma tabela `falha_login` (sem migração). Sem IP utilizável
  (ex.: o `TestClient`, que informa `testclient`) não há chave por IP; o limite por nome continua.

Testes (`tests/acesso/test_login.py`):

| Teste | Prova |
| --- | --- |
| `test_cinco_falhas_bloqueiam_e_geram_evento_login_bloqueado` | 5ª falha bloqueia; evento gravado (inalterado) |
| `test_primeiro_bloqueio_expira_depois_de_um_minuto` | 429 aos 50 s, 200 aos 2 min |
| `test_bloqueio_por_nome_e_progressivo_1_5_15_minutos` | 1, 5 e 15 min com relógio controlado; 3 eventos `login_bloqueado` |
| `test_duracao_do_bloqueio_progressivo` | tabela da progressão e o teto |
| `test_rate_limit_por_ip_recusa_depois_de_20_falhas_e_registra` | 20 falhas com nomes distintos → até a senha certa recebe 429; eventos por IP; outro IP entra; passados 15 min o IP volta |
| `test_ip_invalido_nao_entra_no_rate_limit_por_ip` | IP ausente ou inválido não gera chave |

## Testes do front

Unitários (Vitest): `api.test.ts` (prefixo `/api`, 204, 401 de sessão aciona o retorno ao login,
401 de login não aciona, 403 de troca obrigatória, mensagens idênticas para inexistente e senha
errada, 429 sem citar usuário), `componentes.test.ts` (QR code em SVG acessível).

E2E (`front/e2e/testes/fluxos.spec.ts`), contra a API real pelo proxy:

| Teste | Cobre |
| --- | --- |
| `6.1 rota protegida redireciona…` | `/` → `/login`; `/api/saude` 200; `/api/auth/sessao` 401 |
| `6.2 admin: primeiro acesso…` | QR + chave + URI; TOTP calculado da URI; código errado recusado; com troca pendente `/usuarios` volta para `/trocar-senha` e a API dá 403; troca; página inicial |
| `6.2/6.3 desembargador: primeiro acesso…` | primeiro acesso com senha temporária criada pela interface |
| `6.3 matriz reconfirmada…` | login normal em dois passos (etapa `mfa`) |
| `6.2/6.3 assessor: primeiro acesso após reset…` | reset de senha e de MFA levam ao recadastro |
| `6.2 sessão expirada volta ao login com aviso` | sessão some no navegador; a próxima navegação leva a `/login?motivo=expirada` com o aviso |
| `6.2 mensagens idênticas e bloqueio após 5 falhas…` | mesma mensagem para usuário existente e inexistente; após 5 falhas, a mesma mensagem de bloqueio para os dois, mesmo com a senha certa |
| logout | `sair()` em vários testes; depois dele `/api/auth/sessao` → 401 |

## Critério de aceite

Fluxo completo testado ponta a ponta com Playwright contra a API real: **8 de 8 testes passando**
(`bash front/scripts/e2e.sh`, ~20 s).

## Limitações

- A expiração real (30 min de inatividade ou 8 h) não é esperada no E2E: o teste remove o cookie
  do navegador, que é o efeito visto pelo front quando o servidor recusa a sessão. A expiração no
  servidor segue coberta por `test_sessao_expira_por_inatividade_e_por_prazo_absoluto`.
- Numa recarga completa da página sem sessão válida o front não distingue "expirou" de "nunca
  entrou" (o cookie é `HttpOnly`); o aviso aparece nas navegações e chamadas dentro da SPA.
- A porta direta da API (`API_PORTA_HOST`), quando publicada, entra pela rede do Docker; se a
  origem cair na sub-rede `borda`, um cliente local poderia forjar `X-Forwarded-For`. Só em
  127.0.0.1; em produção, não publique `API_PORTA_HOST`.
