# Relatório — Etapa 4A.10 (ponta a ponta da fundação)

20 de outubro de 2026 · executor da 4A

## O que foi feito

- `tests/ingestao/test_ponta_a_ponta.py` (marcador `integracao`): login real, `POST` de um PDF
  (2 páginas) e de um ZIP (3 PDFs) gerados com PyMuPDF no próprio teste, storage S3 real (MinIO
  do compose), fila RQ real (Redis do compose, fila exclusiva do teste) e `SimpleWorker` em
  rajada executando `lupa.ingestao.worker.executar_job`; confere job `validado`, total de
  páginas, manifesto, objeto original e cada entrada no MinIO. Limpa objetos e fila no fim.
- `scripts/verificar.sh`: passo final que roda esse teste com `LUPA_EXIGIR_INTEGRACAO=1`, em que
  a ausência de MinIO ou Redis **falha** em vez de pular.
- `docs/ingestao.md` (novo), seção nova no `README.md` (e a linha de `src/lupa/ingestao/` na
  tabela "Onde cada etapa fica"), variáveis novas comentadas no `.env.example`.

## Decisões não previstas

- PDFs e ZIPs sintéticos de teste em `tests/ingestao/arquivos.py` (sem depender da 4B), com
  metadados vazios, `no_new_id` e data fixa no ZIP, para o mesmo conteúdo ter o mesmo hash.
- `tests/conftest.py` (acréscimo): fixture autouse que remove `LUPA_DB_USUARIO_APP` e
  `LUPA_DB_SENHA_APP` do ambiente dos testes. Com o `.env` atual, que define as duas,
  `tests/acesso/test_banco_acesso.py::test_url_da_aplicacao_troca_usuario_quando_configurado` e
  `::test_scripts_de_instalacao` já falhavam antes das minhas mudanças, porque `Settings()`
  herdava o usuário da API. Os testes que precisam dele passam o valor explicitamente.
- A imagem foi reconstruída (`up -d --build --wait`), o que recriou os contêineres usados também
  pela 4B, e o banco principal foi migrado para `0003`.

## O que ficou de fora

- `scripts/verificar.ps1` não recebeu o passo extra (o fluxo oficial é no contêiner).

## Comandos e saída

Verificação final (todas as subetapas, imagem reconstruída):

```
docker compose up -d --build --wait          # db, minio, redis, api, worker healthy; minio-init exited 0
docker compose exec api alembic -c src/lupa/migrations/alembic.ini upgrade head   # 0003 (head)
docker compose exec api bash scripts/verificar.sh
== ruff check ==            All checks passed!
== ruff format --check ==   137 files already formatted
== mypy --strict ==         Success: no issues found in 137 source files
== pytest ==                476 passed, 1 skipped, 1 deselected; TOTAL 99% (lupa.ingestao: 99-100% por módulo)
== ponta a ponta da ingestao (integracao, sem skip) ==   1 passed
```

## Critério de aceite

- [x] Upload de PDF e ZIP sintéticos até `validado`, com arquivo no storage e manifesto gravado:
  `test_upload_de_pdf_e_zip_ate_validado_com_objeto_e_manifesto`.
- [x] Roda em `scripts/verificar.sh` com marcador `integracao` (passo próprio, sem skip).

## Estado dos arquivos de dependência (convivência com a 4B)

Relidos imediatamente antes de editar. Encontrados assim: `pyproject.toml` e `requirements.in`
(20:20) já com `pymupdf`, `pillow` e `numpy` da 4B; `requirements.txt` (20:24, fim de linha CRLF)
já regenerado pela 4B, com `pymupdf` e sem `tzdata`/`colorama`; `requirements-dev.in`/`.txt` sem
mudança. Acrescentei só `redis==5.2.1`, `rq==2.1.0`, `boto3==1.35.36` e
`prometheus-client==0.21.1` (no `pyproject.toml` e no `requirements.in`) e o override do mypy
para `boto3`/`botocore`. Regenerei dentro do contêiner:

```
docker compose run --rm --no-deps -u root -v <projeto>:/w -w /w --entrypoint sh api -c \
  "pip install pip-tools==7.4.1 && pip-compile --allow-unsafe --generate-hashes --strip-extras \
   --output-file=requirements.txt requirements.in && pip-compile ... requirements-dev.in"
```

`requirements.txt` só ganhou linhas (boto3, botocore 1.35.99, jmespath, prometheus-client,
python-dateutil, redis, rq, s3transfer, six); `requirements-dev.txt` sem diferença de pacotes.
`pymupdf` não foi duplicado.
