# Relatório — Etapa 4A.5 (cliente de object storage)

20 de outubro de 2026 · executor da 4A

## O que foi feito

- `ingestao/storage.py`: protocolo `ObjectStorage` (`gravar`, `ler`, `existe`, `apagar`,
  `listar`), `ArmazenamentoS3` (boto3, endpoint `LUPA_MINIO_ENDPOINT`, assinatura v4, path-style,
  upload em streaming por `upload_fileobj`, listagem paginada), `ArmazenamentoMemoria`,
  `ObjetoAusenteError`, `chave_objeto(gabinete, processo, sha256)` =
  `gabinete/<id>/processo/<id>/<sha256>`, `criar_storage(settings)`.
- `config.py` (acréscimos): `storage_backend` (`s3` ou `memoria`), `storage_regiao`.
- A API cria o storage em `create_app` (`app.state.storage`); o worker em
  `dependencias_da_configuracao`.

## Decisões não previstas

- `boto3` não tem stubs: override `ignore_missing_imports` para `boto3`/`botocore` no
  `pyproject.toml`; o cliente é `Any` só dentro do adaptador.
- Erro do S3 que não é ausência (ex.: 403) propaga; só `404`/`NoSuchKey`/`NotFound` viram
  `ObjetoAusenteError`.

## O que ficou de fora

- Criptografia do lado do servidor por processo (fase 2 dos requisitos).

## Comandos e saída

`pytest tests/ingestao/test_storage.py` → 9 passed (3 testes de contrato × 2 implementações + 3).

## Critério de aceite

- [x] Troca de implementação por configuração: `test_implementacao_escolhida_pela_configuracao`.
- [x] Teste de contrato nas duas: fixture parametrizada `memoria` e `s3` (esta com marcador
  `integracao`, contra o MinIO do compose): `test_gravar_ler_existe_listar_apagar`,
  `test_ler_chave_ausente_lanca_erro_proprio`, `test_gravar_de_novo_substitui`.
- [x] Chaves por gabinete e processo: `test_chave_por_gabinete_processo_e_hash`.

## Verificação

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
