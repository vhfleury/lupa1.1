# Relatório da Etapa 3 — Autenticação, papéis e auditoria

20 de outubro de 2026 · agente executor

## 1. O que foi feito

| Onde | Conteúdo |
| --- | --- |
| `src/lupa/acesso/senhas.py` | argon2id com parâmetros fixos (t=3, m=64 MiB, p=4, hash 32, sal 16; perfil RFC 9106 baixa memória), `precisa_rehash`, política (12+, fora das 10 mil mais comuns, sem o nome de usuário, sem repetição trivial; sem exigir especiais), senha temporária |
| `src/lupa/acesso/dados/senhas_comuns.txt` | 10 mil senhas mais comuns (ver decisão 12) |
| `src/lupa/acesso/mfa.py` | segredo TOTP de 160 bits, URI `otpauth://` para o QR, verificação com janela de ±1 passo e recusa de passo já usado (replay) |
| `src/lupa/acesso/sessoes.py` | sessão em tabela (token de 256 bits; o banco guarda o SHA-256), 8 h absolutas, 30 min de inatividade, cookie `HttpOnly`/`Secure`/`SameSite=Strict`, desafio do 2º passo |
| `src/lupa/acesso/papeis.py` | enum `Permissao`, `Escopo` e a matriz como dados (`MATRIZ`), `pode`/`tem_permissao` |
| `src/lupa/acesso/autorizacao.py` | dependências `usuario_autenticado`, `usuario_autenticado_permitindo_troca`, `exige_papel`, `exige_gabinete`, `exige_processo` (404 + evento de tentativa); define `lupa.papel` e `lupa.gabinete_id` |
| `src/lupa/acesso/servico.py` | casos de uso: login em dois passos, rate limit, logout, troca e reset de senha/MFA, criar/desativar/reativar usuário, criar gabinete, criar administrador |
| `src/lupa/acesso/rotas.py` | os 12 endpoints da tarefa 8 |
| `src/lupa/acesso/erros.py`, `instalacao.py` | recusas previstas com status HTTP; criação do usuário de conexão e do admin |
| `src/lupa/auditoria/eventos.py` | `AcaoAuditoria` (as 26 ações), `ResultadoEvento`, `NovoEvento` (só campos fixos), serialização canônica e hash |
| `src/lupa/auditoria/registrador.py` | `registrar` (trava da cadeia + hash encadeado) e `verificar_cadeia` |
| `src/lupa/auditoria/geoip.py` | `ResolvedorLocalizacao`, `ResolvedorMaxMind` (`.mmdb`), `ResolvedorNulo`, IP interno → "rede interna" |
| `src/lupa/auditoria/consulta.py`, `rotas.py` | filtros, cursor, exportação CSV/JSON, relatório de uso; `GET /auditoria`, `/exportar`, `/verificar`, `/relatorio-uso` |
| `src/lupa/api/banco.py`, `middleware.py`, `rotas/processos.py`, `app.py` | sessão de banco por requisição sob `lupa_app`, middleware de auditoria automática (`auditar_rota`), rota `GET /processos/{id}` |
| `src/lupa/migrations/esquema_v0002.py` + `versions/v0002_acesso_auditoria.py` | revisão 0002 escrita à mão (`down_revision = "0001"`) |
| `src/lupa/dominio/` (acréscimos) | `SessaoTabela`, `DesafioMfaTabela`, `FalhaLoginTabela`, `BloqueioLoginTabela`; `usuario.mfa_ultimo_passo`; `evento_auditoria.sequencia` e índices; `EventoAuditoria.sequencia`; `definir_papel` |
| `src/lupa/config.py` (acréscimos) | `db_usuario_app`, `db_senha_app`, `geoip_caminho`, `url_banco_aplicacao()` |
| `scripts/criar_admin.py`, `scripts/criar_usuario_banco.py` | scripts finos que chamam `lupa.acesso.instalacao` |
| `docs/auditoria.md`, seção no `README.md`, `.env.example` | documentação |
| `tests/acesso/`, `tests/auditoria/`, `tests/api/test_processos.py`, `tests/api/test_banco.py`, `tests/conftest.py` (acréscimos) | 77 testes novos + 1 de carga |

Migração 0002: tabelas `sessao`, `desafio_mfa`, `falha_login`, `bloqueio_login`; coluna
`usuario.mfa_ultimo_passo`; `evento_auditoria.sequencia` (numerada para linhas existentes),
`UNIQUE (gabinete_id, sequencia) NULLS NOT DISTINCT`, seis índices compostos
(`ocorrido_em`; `usuario_id|gabinete_id|processo_id|acao|ip` + `ocorrido_em`); triggers
`evento_auditoria_append_only` (UPDATE/DELETE) e `evento_auditoria_sem_truncate`; funções
`lupa_localizar_usuario` e `lupa_travar_cadeia` (SECURITY DEFINER); políticas
`<tabela>_administrador` e `evento_auditoria_global_insercao`; grants. O downgrade volta à 0001
(testado por `test_downgrade_base_remove_e_upgrade_head_recria`), e
`test_migracao_coincide_com_tabelas` continua com diferença vazia. A migração foi aplicada ao
banco do compose (`alembic current` → `0002 (head)`).

## 2. Os cinco pontos herdados da Etapa 1

1. **Login sob RLS.** Função `lupa_localizar_usuario(nome)` (SECURITY DEFINER, `search_path`
   fixo, EXECUTE só para `lupa_app`) devolve apenas `id`, `gabinete_id` e `papel`. O login chama
   a função, define `lupa.papel`/`lupa.gabinete_id` com o resultado e só então lê a linha
   completa do usuário sob a RLS normal. Sem contexto, `SELECT * FROM usuario` continua vazio.
   Sessões e desafios guardam `gabinete_id` e `papel`, então as requisições seguintes definem o
   contexto antes de ler o usuário. Teste:
   `test_login_sob_rls_localiza_usuario_pela_funcao_e_nao_lista_os_demais`.
2. **Administrador.** Nova variável `lupa.papel` (`definir_papel` em `dominio/sessao.py`) e
   política permissiva `<tabela>_administrador` em todas as tabelas com RLS, liberando leitura
   e escrita quando `lupa.papel = 'administrador'`. Acesso do admin a rota de conteúdo gera
   `admin_acesso_conteudo` na cadeia do gabinete do processo. Testes:
   `test_politica_do_administrador_libera_todos_os_gabinetes`,
   `test_acesso_de_admin_a_rota_de_conteudo_gera_admin_acesso_conteudo`.
3. **Eventos globais.** Leitura: pela política do administrador. Escrita: política
   `evento_auditoria_global_insercao` (`FOR INSERT WITH CHECK (gabinete_id IS NULL)`), para que
   a falha de login de usuário inexistente seja gravada sem contexto. A trava da cadeia é a
   função `lupa_travar_cadeia` (SECURITY DEFINER), então o registrador não precisa enxergar os
   eventos para encadear. Teste: `test_eventos_sem_gabinete_formam_a_cadeia_global`.
4. **Membership do papel.** `garantir_usuario_conexao` cria (ou atualiza a senha de) um papel
   `LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE INHERIT` e faz `GRANT lupa_app`.
   `scripts/criar_usuario_banco.py` lê `LUPA_DB_USUARIO_APP`/`LUPA_DB_SENHA_APP`;
   `Settings.url_banco_aplicacao()` troca as credenciais de `LUPA_DATABASE_URL` por essas, e a
   API usa essa URL. O dono das tabelas fica para migrações e scripts. O compose não mudou:
   as variáveis chegam pelo `env_file: .env` (documentadas em `.env.example` e no README). Em
   produção, o dono das tabelas precisa ser superusuário ou ter BYPASSRLS, porque as tabelas
   têm `FORCE ROW LEVEL SECURITY` e as funções SECURITY DEFINER rodam como ele. Testes:
   `test_usuario_de_conexao_nao_e_superusuario_e_assume_lupa_app`,
   `test_lupa_app_nao_altera_auditoria_mesmo_com_contexto_de_admin`,
   `test_scripts_de_instalacao`.
5. **Grants para tabelas novas.** A 0002 faz grant explícito nas quatro tabelas novas e
   `ALTER DEFAULT PRIVILEGES IN SCHEMA public` para tabelas e sequências futuras criadas pelo
   dono das migrações. Também revoga `UPDATE, DELETE, TRUNCATE` de `evento_auditoria` para
   `lupa_app`. Teste: `test_tabelas_novas_tem_grant_para_lupa_app`.

## 3. Decisões que o plano não previa

1. **O banco guarda o SHA-256 do token de sessão,** não o token. Uma cópia do banco não permite
   sequestrar sessões.
2. **Segundo passo do login:** tabela `desafio_mfa` (token de 256 bits, 5 minutos, uso único).
   A sessão só é criada depois do TOTP.
3. **QR code:** a API devolve o segredo em texto e a URI `otpauth://`; quem desenha o QR é a
   interface. Nenhuma biblioteca de QR estava autorizada.
4. **Rate limit:**
   - As tabelas `falha_login` e `bloqueio_login` guardam o SHA-256 do nome digitado, não o
     nome, porque às vezes a pessoa digita a senha no campo de usuário. Pelo mesmo motivo, o
     evento de falha de usuário inexistente não registra o nome digitado.
   - Falhas de TOTP também contam.
   - A 5ª falha ainda responde 401 (resposta idêntica) e grava `login_bloqueado`. A partir da
     6ª tentativa a resposta é 429 por 15 minutos.
   - Usuário inexistente, inativo ou com senha errada recebem resposta idêntica, contam
     igualmente para o bloqueio e passam por um argon2 fictício para igualar o tempo.
5. **Cadeia de auditoria:**
   - A coluna `sequencia` foi acrescentada com unicidade `(gabinete_id, sequencia) NULLS NOT
     DISTINCT`.
   - `lupa_travar_cadeia` toma um `pg_advisory_xact_lock` da cadeia, porque com a cadeia vazia
     não há linha para travar, e faz o `SELECT ... FOR UPDATE` do último evento, como pedido.
   - O hash cobre `id`, `sequencia`, `ocorrido_em`, os identificadores, `acao`, objeto, `ip`,
     `localizacao`, `resultado` e as versões, em JSON ordenado.
   - A verificação aponta o primeiro evento com problema de `hash`, `encadeamento` ou
     `sequencia`.
6. **Tabelas de apoio sem RLS:** `sessao`, `desafio_mfa`, `falha_login` e `bloqueio_login` não
   têm `gabinete_id` próprio de tenant e só guardam hashes e ids, por isso ficaram sem RLS.
   `test_rls_ativa_em_todas_as_tabelas_com_gabinete` continua valendo.
7. **Recusas previstas confirmam a transação.** `RecusaAcessoError` e `HTTPException` confirmam
   a transação da requisição, para não perder o evento da recusa (falha de login, 404 de outro
   gabinete, criação negada). Qualquer outra exceção desfaz tudo.
8. **Troca de senha:** mantém a sessão que trocou e revoga as demais, conforme o critério de
   aceite. Reset, desativação e reset de MFA revogam todas as sessões do alvo.
9. **Troca de senha pendente:** só `/auth/trocar-senha` responde; até o logout devolve 403.
10. **Administrador único:**
    - A API não cria administrador. Só o script cria, e só se não houver outro.
    - A unicidade é garantida pela aplicação, não por constraint no banco, porque os testes
      semeiam vários administradores.
    - O admin também nasce com troca de senha obrigatória.
11. **Rota mínima `GET /processos/{id}`,** necessária para os critérios do 404 e do
    `admin_acesso_conteudo`. É a primeira rota marcada com `@auditar_rota(..., conteudo=True)`.
    O middleware lê a marca do endpoint e grava `processo_aberto`/`pagina_vista`/`busca` (e
    `admin_acesso_conteudo`) em transação própria depois da resposta.
12. **Lista de senhas comuns:** as 10.000 primeiras linhas do `common-passwords.txt.gz` do
    Django 6.0.5, já presente na máquina (licença BSD, lista de Royce Williams ordenada por
    frequência). Nada foi baixado.
13. **Consulta da auditoria:** ordenação decrescente (`ocorrido_em DESC, id DESC`), com cursor
    opaco. A exportação vai em ordem cronológica, com teto de 100 mil eventos.
14. **`geoip2` 5.3.0 traz `aiohttp` e `requests`** como dependências transitivas (cliente do web
    service da MaxMind). Só o leitor offline é usado.
15. **Teste de carga fora da suíte padrão:** `addopts` ganhou `-m 'not carga'`; rode com
    `pytest -m carga --no-cov`.
16. **Arquivos de outras etapas alterados (só acréscimos):**
    - Etapa 0: `config.py`, `api/app.py`, `api/middleware.py`.
    - Etapa 1: `dominio/tabelas.py`, `dominio/sessao.py`, `dominio/esquemas.py`
      (`EventoAuditoria.sequencia`, padrão 1).
    - `tests/conftest.py`.
    - Compartilhados: `pyproject.toml`, `requirements*.in`, `requirements*.txt`, `README.md`,
      `.env.example`.

## 4. Convivência com a Etapa 2 (registro obrigatório)

**Estado dos arquivos compartilhados quando cheguei:**
- `pyproject.toml` já tinha `pyyaml==6.0.2` e `types-PyYAML`, e `requirements.in` já tinha
  `pyyaml`.
- `requirements*.txt` tinham sido gerados no Windows: incluíam `tzdata` (via psycopg) e
  `colorama` (via pytest).

**O que fiz nesses arquivos:**
- `pyproject.toml` e `requirements.in`: reli cada um logo antes de editar e só acrescentei as
  três dependências, o marcador `carga` e o `-m 'not carga'`.
- Regenerei `requirements.txt` e `requirements-dev.txt` com o comando do cabeçalho
  (`pip-compile --allow-unsafe --generate-hashes --strip-extras`), num contêiner
  `python:3.12-slim` descartável.
- O pip-compile no Linux removeu `tzdata` e `colorama`. Reinseri os blocos originais, com os
  mesmos hashes, para manter a regra de só acrescentar. Fora isso, as únicas mudanças são as
  dependências novas e as transitivas delas.

**Incidente, precisa de conferência da Etapa 2.**
- O que aconteceu: para rodar `ruff format` e `ruff --fix`, copiei `src/lupa` e `tests` do
  contêiner de volta para o diretório do projeto, por volta das 19:59:07 e de novo às 19:59:44.
  O contêiner tinha a cópia de `src` da imagem construída por volta das 19:57.
- Efeito 1: arquivos da Etapa 2 alterados no host entre o build e essas cópias podem ter
  voltado à versão do build. Vi `src/lupa/validacoes/modelo.py` ser reescrito depois pela
  própria Etapa 2, às 20:00:16.
- Efeito 2: `ruff format` reformatou arquivos em `src/lupa/validacoes/` (`adaptador.py`,
  `apoio.py`, `__main__.py`, `criminal/*`) e possivelmente em `tests/validacoes/`. São mudanças
  só de formatação.
- Depois disso não copiei mais nada do contêiner para o host.
- Na execução final de `verificar.sh` os testes de validação passam (ver seção 7). Mesmo assim,
  peço que a Etapa 2 confira se alguma alteração dela entre 19:57 e 19:59 se perdeu.

Não toquei em `docs/validacoes.md` nem em `docs/exemplos/**`.

## 5. O que ficou de fora e por quê

- **Base GeoLite2:** exige conta na MaxMind. O caminho de instalação está no README; os testes
  usam um leitor falso.
- **Desenho do QR:** fica para a interface (ver decisão 3).
- **Rotas que ainda não existem:** upload, páginas, busca, chat, anotação, validação e chamada
  ao modelo pertencem a etapas futuras. As ações estão no enum, e o middleware e `auditar`
  estão prontos para elas.
- **Rate limit por IP** e confiança em `X-Forwarded-For`: não estavam pedidos. O README
  documenta o uso de `--proxy-headers` atrás de proxy.
- **Constraint de banco para o administrador único:** ver decisão 10.
- **Vault:** os segredos continuam no `.env`.
- **`docker-compose.yml`:** não mudou; as variáveis novas entram pelo `.env`. Para ativar o
  usuário sem superusuário no ambiente local, acrescente `LUPA_DB_USUARIO_APP` e
  `LUPA_DB_SENHA_APP` ao seu `.env`, rode `scripts/criar_usuario_banco.py` e depois
  `docker compose up -d api`.

## 6. Teste de carga

`docker compose exec api python -m pytest -m carga --no-cov -s`:

```
teste_carga  eventos=1000000 segundos_carga=67.2 mediana_ms=3.0 maximo_ms=13.3
1 passed, 211 deselected in 63.41s
```

- Carga: 1 milhão de eventos por `COPY`, distribuídos em 40 gabinetes e 1.000 usuários ao longo
  de um ano, num banco próprio.
- Consulta: filtrada por usuário e por intervalo de 90 dias, sob RLS de desembargador, página de
  50. Mediana de 3,0 ms e máximo de 13,3 ms em 10 execuções (meta: < 200 ms).
- Tempo total: cerca de 65 s, por isso o teste é marcado `integracao` e `carga` e fica fora da
  suíte padrão.

## 7. Lint, tipagem e testes

A imagem foi reconstruída para incluir as dependências novas (`docker compose up -d --build
--wait`).

```
$ docker compose exec api bash scripts/verificar.sh
== ruff check ==            All checks passed!
== ruff format --check ==   87 files already formatted
== mypy --strict ==         Success: no issues found in 87 source files
== pytest ==                210 passed, 1 skipped, 1 deselected
                            Required test coverage of 90% reached. Total coverage: 98.68%
```

Durante a verificação, `test_cinco_falhas_bloqueiam...` falhou uma vez em quatro execuções.
A causa: o helper dos testes ordenava os eventos por `ocorrido_em`, que vem do relógio da
aplicação, e o relógio da VM do Docker pode recuar. O helper passou a ordenar por `sequencia`,
que é a ordem verdadeira da cadeia. Depois disso, 6 execuções seguidas da suíte passaram.

Cobertura dos pacotes da etapa:
- `acesso`: 97–100% por módulo.
- `auditoria`: 100%.
- `api`: 97–100%.

## 8. Critérios de aceite

| Critério | Status | Evidência |
| --- | --- | --- |
| Senha certa + TOTP errado não cria sessão | ok | `test_login_com_senha_certa_e_totp_errado_nao_cria_sessao` |
| TOTP reutilizado na janela é rejeitado | ok | `test_codigo_totp_reutilizado_dentro_da_janela_e_rejeitado`, `test_totp_recusa_codigo_reutilizado` |
| 5 falhas bloqueiam e geram `login_bloqueado` | ok | `test_cinco_falhas_bloqueiam_e_geram_evento_login_bloqueado`, `test_bloqueio_expira_depois_de_quinze_minutos` |
| Assessor de A recebe 404 (não 403) no processo de B, tentativa registrada | ok | `test_assessor_do_gabinete_a_recebe_404_no_processo_do_gabinete_b_e_tentativa_e_registrada` |
| Desembargador não cria assessor em outro gabinete | ok | `test_desembargador_nao_consegue_criar_assessor_em_outro_gabinete` |
| `troca_senha_obrigatoria` só acessa a rota de troca | ok | `test_usuario_com_troca_senha_obrigatoria_so_acessa_rota_de_troca` |
| Troca de senha revoga as demais sessões | ok | `test_troca_de_senha_revoga_as_demais_sessoes` |
| UPDATE/DELETE em `evento_auditoria` falha no banco | ok | `test_update_ou_delete_em_evento_auditoria_falha_no_banco` (UPDATE, DELETE, TRUNCATE), `test_papel_da_aplicacao_nao_tem_privilegio_de_update` |
| Alterar evento no meio da cadeia → `/auditoria/verificar` aponta aquele evento | ok | `test_alterar_evento_no_meio_da_cadeia_faz_verificar_apontar_aquele_evento` |
| Registros concorrentes no mesmo gabinete → cadeia válida | ok | `test_dois_registros_concorrentes_no_mesmo_gabinete_produzem_cadeia_valida` (4 threads × 10) |
| Nenhum evento contém chave de `CAMPOS_PROIBIDOS` | ok | `test_nenhum_evento_contem_campo_proibido_nem_segredo` (importa `CAMPOS_PROIBIDOS` de `lupa.logging`, varre todos os eventos e também os valores) |
| Carga: 1 milhão de eventos, consulta por usuário e intervalo < 200 ms | ok | `test_um_milhao_de_eventos_consulta_por_usuario_e_intervalo_abaixo_de_200ms`: mediana 3,0 ms |
| Admin em rota de conteúdo gera `admin_acesso_conteudo` além do evento normal | ok | `test_acesso_de_admin_a_rota_de_conteudo_gera_admin_acesso_conteudo` |
| `docs/auditoria.md` em linguagem simples | ok | `docs/auditoria.md` |
| Cobertura ≥ 90% e `verificar.sh` passa | ok | seção 7 |
