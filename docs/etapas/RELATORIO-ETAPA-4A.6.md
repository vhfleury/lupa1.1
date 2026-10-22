# Relatório — Etapa 4A.6 (recepção e lacre)

20 de outubro de 2026 · executor da 4A

## O que foi feito

- `ingestao/recepcao.py`: `receber` (async) grava o corpo em temporário bloco a bloco, calcula
  SHA-256 e tamanho no caminho, interrompe ao passar de `LUPA_UPLOAD_LIMITE_BYTES`, detecta o
  tipo pelos bytes mágicos (`%PDF-`, `PK 03 04`) e recusa extensão `.pdf`/`.zip` que contradiga o
  conteúdo; `lacrar` grava o objeto (se ainda não existe), insere `arquivo` e cria o job em
  `recebido`, ou devolve o arquivo e o job existentes quando o hash já está no processo
  (inclusive em corrida, por savepoint + `IntegrityError`).
- `api/rotas/ingestao.py`: `POST /processos/{processo_id}/arquivos?nome=...` com
  `exige_processo`, conferência de `SUBIR_PROCESSO`, auditoria `arquivo_enviado` (ok ou negado)
  na transação da requisição e enfileiramento depois do commit (`BackgroundTasks`). Registrada em
  `api/app.py`.
- Respostas: 201 novo; 200 com `duplicado: true`; 415 tipo; 422 vazio; 413 tamanho; 404 processo
  de outro gabinete; 403 processo sigiloso.

## Decisões não previstas

- **Corpo binário em vez de multipart**: `python-multipart` não está nas dependências e o
  `UploadFile` faz spool próprio; com `request.stream()` o streaming é real. Nome em `?nome=`.
- **Processo sigiloso bloqueado (403)**, como pede `requisitos-v1.md` §6, com evento `negado`.
- Falha ao enfileirar (Redis fora) só gera log `fila_indisponivel`; o varredor recupera o job.
- `arquivo_enviado` entra na cadeia do gabinete do processo, também quando quem envia é o
  administrador.

## O que ficou de fora

- `processo.status` não muda para `em_ingestao` (fica para quando a extração existir).
- Antivírus e cifragem antes do parser (fase 2).

## Comandos e saída

`pytest tests/ingestao/test_recepcao.py tests/ingestao/test_rotas.py` → 19 passed.

## Critério de aceite

- [x] Mesmo arquivo duas vezes não duplica: `test_mesmo_arquivo_duas_vezes_nao_duplica` (rota e
  lacre), `test_corrida_no_lacre_devolve_o_arquivo_do_concorrente`.
- [x] Extensão falsa rejeitada pelo conteúdo: `test_conteudo_invalido_e_recusado_e_auditado`
  (`extensao_falsa`, `zip_com_nome_de_pdf`), `test_recusas_apagam_o_temporario`.
- [x] SHA-256 em stream: `test_recebe_em_blocos_com_hash_tamanho_e_tipo` (blocos de 7 bytes).
- [x] Limite configurável: `test_arquivo_acima_do_limite_recebe_413`.
- [x] `arquivo` gravado, objeto no storage, evento e job `recebido`:
  `test_envio_de_pdf_cria_arquivo_job_objeto_evento_e_pedido_na_fila`.
- [x] Usa `exige_processo`: `test_processo_de_outro_gabinete_da_404`.

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
