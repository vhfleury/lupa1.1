# Relatório — Etapa 4A.2 (esquemas da ingestão)

20 de outubro de 2026 · executor da 4A

## O que foi feito

- `dominio/enums.py` (acréscimos): `EstadoJob` (recebido, validado, em_extracao, parcial,
  em_revisao, concluido, falho, quarentena), `MotivoQuarentena`, `MotivoFalha`, `CenarioArquivo`
  (zip_por_peca, pdf_com_bookmarks, pdf_com_indice, pdf_liso), `EstadoLote`.
- `dominio/esquemas.py` (acréscimos): `JobIngestao` (valida `motivo_quarentena` se e somente se
  `quarentena`), `LoteIngestao`, `DiagnosticoArquivo` (`cenario`, `total_paginas`, `tem_indice`,
  `sinais` JSON) e `EntradaManifesto` (ordem, nome, tamanho, sha256).
- `dominio/tabelas.py` (acréscimos): `JobIngestaoTabela` (estado, motivos, lease, heartbeat,
  fencing token, tentativas, total de páginas, manifesto JSONB, instantes), `LoteIngestaoTabela`
  (único por `(job_id, numero)`), `DiagnosticoArquivoTabela` (um por arquivo). FKs compostas
  `(x_id, gabinete_id)`, CHECK de enums, CHECK `quarentena_com_motivo`, um job por arquivo.
- `migrations/esquema_v0003.py` + `versions/v0003_ingestao.py` (`down_revision = "0002"`), à mão:
  tabelas, índice por gabinete, RLS forçada com política por gabinete e do administrador,
  `GRANT SELECT, INSERT, UPDATE, DELETE` explícito para `lupa_app`.
- `ingestao/estados.py`: `TRANSICOES` como dados, `transicao(atual, novo) -> bool` pura,
  `exigir_transicao`, `ESTADOS_FINAIS` (concluido, quarentena).
- `ingestao/repositorio.py`: `criar_job`, `mudar_estado` (máquina de estados + fencing),
  `salvar_diagnostico`/`obter_diagnostico`, além do que a 4A.3 usa.

## Decisões não previstas

- **`TABELAS_COM_GABINETE` passou a incluir as tabelas novas**, porque o teste da Etapa 1
  `test_rls_ativa_em_todas_as_tabelas_com_gabinete` compara esse conjunto com as tabelas com RLS.
  Como as migrações 0001 e 0002 iteravam sobre essa tupla, criei `TABELAS_COM_GABINETE_V1` (os 13
  nomes originais, congelados) e troquei o import em `esquema_v0001.py` e `esquema_v0002.py`. O
  SQL das revisões antigas é idêntico; os testes de ida e volta e de migração × tabelas passam.
  Alteração em arquivos de etapas anteriores, registrada aqui.
- Transições: `falho -> recebido` (nova tentativa), `em_revisao -> em_extracao` e
  `parcial -> em_extracao` permitidas; `concluido` e `quarentena` sem saída.
- O banco reforça `motivo_quarentena` por CHECK; a máquina de estados fica em código (sem trigger).

## O que ficou de fora

- Preencher `DiagnosticoArquivo` com o cenário real é da 4C.1; aqui só entidade, tabela e
  repositório.
- Estados de `em_extracao` em diante existem e entram na matriz, mas nenhum código da 4A os usa.

## Comandos e saída

`pytest tests/ingestao/test_estados.py` → 71 passed (64 pares da matriz + esquemas e quarentena).
`pytest tests/ingestao/test_repositorio.py` → 9 passed. `tests/dominio` passa (RLS, migração ×
tabelas, downgrade/upgrade).

## Critério de aceite

- [x] Transições válidas impostas por código: `transicao` + `exigir_transicao`, usadas por
  `repositorio.mudar_estado` (`test_mudar_estado_respeita_maquina_e_finaliza`).
- [x] Matriz inteira testada: `test_matriz_completa_de_transicoes` (64 casos).
- [x] `concluido` nunca volta para `em_extracao`: `test_concluido_nunca_volta_para_em_extracao`.
- [x] Migração 0003 com grants e RLS: `test_rls_ativa_em_todas_as_tabelas_com_gabinete`,
  `test_migracao_coincide_com_tabelas`, `test_rls_isola_jobs_e_lotes_por_gabinete`,
  `test_tabelas_novas_tem_grant_para_lupa_app` da Etapa 3.

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
