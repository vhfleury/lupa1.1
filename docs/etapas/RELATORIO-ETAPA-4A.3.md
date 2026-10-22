# Relatório — Etapa 4A.3 (fila e worker base)

20 de outubro de 2026 · executor da 4A

## O que foi feito

- `docker-compose.yml`: serviço `redis` (`redis:7.4-alpine`, sem persistência, sem porta no host,
  healthcheck `redis-cli ping`) e serviço `worker` (mesmo Dockerfile, `python -m
  lupa.ingestao.worker`, healthcheck que faz `PING` no Redis). `api` passa a depender do `redis`.
- `ingestao/fila.py`: `FilaIngestao` (protocolo), `FilaRQ` (RQ 2.1 sobre Redis) e `FilaMemoria`.
  A mensagem leva só `job_id` e `gabinete_id`.
- `ingestao/repositorio.py`: `adquirir_lease` (UPDATE condicional que incrementa `fencing_token`
  e `tentativas`), `renovar_lease` (heartbeat), `liberar_lease`, `gravar_lote` (INSERT ... ON
  CONFLICT DO NOTHING depois de travar o job e conferir o token), `registrar_resultado`,
  `lotes_do_job`, `jobs_recuperaveis`. Toda escrita trava a linha do job (`FOR UPDATE`) e lança
  `LeasePerdidoError` se o token mudou.
- `ingestao/worker.py`: `processar_job` (adquire, monta unidades, processa lotes reaproveitando
  os já gravados, finaliza), `executar_job` (entrada do RQ), `varrer` (reenfileira jobs
  parados), `main` (loop: varredura + `SimpleWorker.work(burst=True)` + pausa de 2 s).

## Decisões não previstas

- **RQ** escolhido (registrado), com `SimpleWorker` (sem fork por job): o isolamento pesado está
  no sandbox por subprocesso (4A.4).
- **O banco é a fonte da verdade; o Redis é volátil.** O varredor reenfileira jobs `recebido` com
  lease vencido ou nunca tomados há mais de 30 s. Mensagem perdida, Redis reiniciado ou falha no
  enfileiramento do upload não perdem job.
- **Lote = um PDF**: PDF avulso é um lote; ZIP vira um lote por entrada do manifesto. Na 4C o lote
  pode passar a ser faixa de páginas sem mudar o protocolo.
- Instantes vêm do chamador (`agora`), não do `now()` do banco, para a expiração ser testável.
- O worker conecta com `url_banco_aplicacao()` (usuário sem superusuário), assume `lupa_app` e
  define o gabinete do job em cada transação; só o varredor usa `lupa.papel = administrador`
  para ler jobs de todos os gabinetes.
- Depois de `LUPA_MAX_TENTATIVAS` (3) aquisições o job vai para `falho/erro_interno`.
- O loop captura exceção por ciclo e loga só o nome da classe; sem isso o contêiner morreria
  enquanto a 0003 não estivesse aplicada.

## O que ficou de fora

- Retentativa automática de jobs `falho` (falha por limite tende a repetir); a volta é manual
  (`falho -> recebido`).
- Morte por `SIGKILL` real: simulada por uma `BaseException` lançada depois do lote 1 (não é
  capturada como `Exception`, então nada é finalizado, como num kill).

## Comandos e saída

`pytest tests/ingestao/test_worker.py tests/ingestao/test_repositorio.py` → 33 passed.

## Critério de aceite

- [x] Redis e worker no compose, sem porta no host: `docker compose ps` mostra `redis` e
  `worker` healthy, sem portas publicadas.
- [x] Lease com expiração, heartbeat e fencing token na tabela do job:
  `test_lease_exclusivo_expira_e_novo_dono_recebe_token_maior`,
  `test_heartbeat_estende_lease_e_dono_antigo_perde_tudo`.
- [x] Worker morto no meio do lote tem o lease recuperado:
  `test_worker_morto_no_meio_tem_lease_recuperado_sem_duplicar_lotes` (morte depois do lote 1;
  sucessor recusado enquanto o lease vale; depois de expirar, o job aparece em
  `jobs_recuperaveis` e é retomado).
- [x] Lote reprocessado não duplica: o mesmo teste confere `[(1, token 1), (2, token 2),
  (3, token 2)]`; `test_lote_gravado_uma_unica_vez`,
  `test_worker_antigo_que_volta_nao_grava_depois_do_sucessor`,
  `test_lease_perdido_no_meio_interrompe_sem_gravar`, `test_job_ja_validado_nao_e_reprocessado`.

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
