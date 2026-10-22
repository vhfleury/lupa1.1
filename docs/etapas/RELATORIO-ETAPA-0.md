# Relatório — Etapa 0 (esqueleto do projeto)

20 de outubro de 2026 · agente executor

## O que foi feito

- Tarefas 1–11 do plano: `pyproject.toml` (versões fixadas, ruff/mypy/pytest configurados),
  `Dockerfile` multi-stage com usuário `lupa` (uid 10001), `docker-compose.yml` (`api`, `db`,
  `minio`, `minio-init`, healthchecks, rede `interna`), `.env.example`, `src/lupa/config.py`
  (`Settings` com pydantic-settings, prefixo `LUPA_`), `src/lupa/logging.py` (structlog JSON com
  `timestamp`, `level`, `event`, `request_id` e filtro `CAMPOS_PROIBIDOS`), `src/lupa/api/app.py`
  (fábrica `create_app`, middleware `request_id`, `GET /saude`), `Makefile`, `README.md`,
  `scripts/verificar.sh` e `scripts/verificar.ps1`.
- Pacotes vazios com docstring: `dominio`, `validacoes`, `acesso`, `auditoria`, `ingestao`, `agente`.
- Testes em `tests/unit/` e `tests/api/` (18 testes, incluindo um de integração real com o compose).

## Decisões que o plano não previa

1. **pip + `requirements.txt` com hashes** (não há `uv` na máquina). Gerados por `pip-compile
   --generate-hashes` a partir de `requirements.in` e `requirements-dev.in`; o `Dockerfile` instala
   com `--require-hashes`. Versões espelhadas no `pyproject.toml`.
2. **Imagem do MinIO**: `minio/minio` e `quay.io/minio/*` não estão mais disponíveis publicamente
   (pull negado). Usei o fork comunitário `pgsty/minio` fixado por digest
   (`sha256:b6bfe723…2372`, MinIO RELEASE.2026-08-04), que inclui `mc` e serve também ao
   `minio-init`. Recomendo o revisor/arquiteto validar a fonte ou trocar por imagem interna.
3. `GET /saude` responde **503** com `"falha"` no componente quando banco ou MinIO não respondem
   (o plano só especificava o caso 200). O healthcheck da `api` usa a própria `/saude`.
4. Verificação do MinIO via `GET /minio/health/live` com `urllib` (sem SDK S3, para não adicionar
   dependência que o plano não lista). Banco via SQLAlchemy `SELECT 1`.
5. Filtro de log: modo estrito (lança `CampoProibidoError`) quando `LUPA_AMBIENTE=teste`; nos demais
   remove a chave. Comparação insensível a maiúsculas.
6. Portas publicadas só em `127.0.0.1`. A API S3 do MinIO (9000) e o PostgreSQL não são expostos.
7. A imagem contém `tests/` e `scripts/` e, no compose, as dependências de desenvolvimento
   (`INSTALAR_DEV=true`) para que o revisor rode `verificar.sh` dentro do contêiner. Para produção,
   construir com `INSTALAR_DEV=false` (padrão do `Dockerfile`).
8. `.dockerignore` criado (exclui `.env`, PDFs, DOCX, caches).
10. **Correções da revisão (REVISAO-ETAPA-0.md, seção 4):** `db` roda com `user: "70:70"` (uid
   do `postgres` na imagem alpine; o volume nomeado herda a posse do diretório de dados da imagem e
   continua gravável). `minio` e `minio-init` rodam com `user: "10002:10002"` e `HOME=/tmp`. Como o
   `/data` da imagem pertence a root, o volume `minio-dados` é montado em `/var/tmp` (diretório 1777
   da imagem, cuja permissão o volume novo herda) e o servidor usa `/var/tmp/dados`. Sem contêiner
   auxiliar rodando como root. O healthcheck fictício do `minio-init` foi removido. O README registra
   que a imagem do MinIO é fork comunitário e que o object storage está em aberto.
9. `pytest` ignora um `DeprecationWarning` interno do `starlette.testclient` (de terceiros).

## O que ficou de fora e por quê

- **Alembic não inicializado** (sem `alembic.ini`/`migrations/`): não há modelos até a Etapa 1. O alvo
  `make migrate` já chama `alembic upgrade head` e passará a funcionar quando a Etapa 1 criar o ambiente.
- **Log de acesso do uvicorn** não está em JSON (sai no formato padrão do uvicorn; não contém corpo
  nem cabeçalhos). Unificar com structlog fica para quando houver rotas com dados.
- Alvos do `Makefile` (`test`, `lint`, `typecheck`) rodam dentro do contêiner `api`; `format` roda
  no host porque altera arquivos do repositório.

## Como rodar

```bash
cp .env.example .env
docker compose up -d --build --wait
docker compose exec api bash scripts/verificar.sh
```

Localmente (venv): `PYTHON=.venv/Scripts/python bash scripts/verificar.sh` ou
`$env:PYTHON=".venv\Scripts\python.exe"; .\scripts\verificar.ps1`.

### Saída resumida (dentro do contêiner `api`)

```
== ruff check ==            All checks passed!
== ruff format --check ==   22 files already formatted
== mypy --strict ==         Success: no issues found in 22 source files
== pytest ==                18 passed in 1.30s — Total coverage: 100.00%
```

Fora do compose (Windows, Python 3.12.1): mesmo lint/mypy limpos; `17 passed, 1 skipped`
(integração pulada), cobertura 97%. `verificar.ps1` termina com código 0.

## Docker Compose

Executado (Docker 29.2.0). Após `docker compose down -v`, `docker compose up -d --build --wait`
levou **12,8 s** (imagens já baixadas; build em cache) com `api`, `db`, `minio` saudáveis e
`minio-init` encerrado com código 0 (`Bucket created successfully lupa/lupa-autos`).

```
$ curl -i http://127.0.0.1:18000/saude
HTTP/1.1 200 OK
x-request-id: eefa075ba5a14683ac6685f1d49d7985
{"api":"ok","db":"ok","minio":"ok"}
```

Observação: nesta máquina as portas 8000 e 8080 estavam ocupadas por outros projetos, então o `.env`
local usou `API_PORTA_HOST=18000`. O padrão do `.env.example` continua 8000.

## Checklist dos critérios de aceite

| Critério | Resultado | Evidência |
|---|---|---|
| `docker compose up` sobe os três serviços saudáveis em < 2 min | ok | `up --wait` em 12,8 s; `docker compose ps`: api/db/minio `(healthy)`. Não medido em máquina totalmente limpa (sem cache de imagens). |
| `GET /saude` → 200 `{"api":"ok","db":"ok","minio":"ok"}` | ok | `curl` acima; `tests/api/test_saude.py::test_saude_integracao_com_servicos_reais` passou no contêiner |
| `scripts/verificar.sh` sem avisos de lint e sem erros de tipagem | ok | saída acima (ruff limpo, mypy strict sem erros, 0 warnings no pytest) |
| Teste prova que o logger rejeita chave proibida | ok | `tests/unit/test_logging.py::test_logger_rejeita_chave_proibida_em_modo_estrito` (7 casos) |
| Teste prova que a aplicação não inicia sem variável obrigatória | ok | `tests/unit/test_config.py::test_aplicacao_nao_inicia_sem_variavel_obrigatoria`; também `docker run --rm lupa-api` sem env encerra com `ValidationError ... database_url Field required` |
| Nenhuma imagem roda como root | ok | Após `down -v` e `up --wait` (14,1 s): `api` → `lupa` uid=10001; `db` → `postgres` uid=70; `minio` → uid=10002 (sem nome em `/etc/passwd`, por isso `whoami` não resolve). `minio-init` também uid 10002 e criou o bucket. `/saude` 200 e `verificar.sh` com 18 testes aprovados depois da mudança. |
| `.env` no `.gitignore` e `.env.example` sem valor real | ok | `.gitignore` contém `.env` e `.env.*` com exceção `!.env.example`; valores do exemplo são fictícios (`troque-esta-senha-ficticia` etc.). Sem git inicializado, `git check-ignore` não foi executado. |
