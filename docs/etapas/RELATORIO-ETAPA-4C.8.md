# Relatório da Etapa 4C.8 — Paralelismo e desempenho

## O que foi feito

- `src/lupa/ingestao/extracao.py`: `planejar` divide as fontes (PDF ou entradas do ZIP) em lotes de páginas consecutivas; cada lote roda num processo filho do sandbox (`extrator_paginas`), que abre o seu próprio documento. No pai, um `ThreadPoolExecutor` só espera os filhos (nenhum objeto PyMuPDF em thread). Resultados chegam na ordem de término e são gravados na hora.
- Tetos: lotes por job e lotes por gabinete (`LimitadorGabinete`, semáforo por gabinete compartilhado no processo worker). Configuração: `LUPA_EXTRACAO_PAGINAS_POR_LOTE=8`, `LUPA_EXTRACAO_LOTES_POR_JOB=4`, `LUPA_EXTRACAO_LOTES_POR_GABINETE=4`.
- **Justiça entre jobs: round-robin por fatias.** Depois de `LUPA_EXTRACAO_FATIA_PAGINAS=400` páginas o job grava o progresso, solta o lease sem contar tentativa (`repositorio.ceder_vez`) e volta ao fim da fila; o próximo job da fila (de qualquer gabinete) é atendido antes da fatia seguinte.

## Decisões não previstas

- Round-robin em vez de fila com prioridade: não exige mudar o RQ nem saber o tamanho do job ao enfileirar, e o estado do job continua só no banco.
- O semáforo por gabinete vale por processo worker; com várias réplicas o teto passa a ser por réplica (registrado em `docs/ingestao.md`). Um semáforo no Redis fica para quando houver mais de um worker.
- O varredor também recupera jobs `validado`/`em_extracao` com lease vencido, e os que cederam a vez e ficaram 10 min sem heartbeat (mensagem perdida).

## Comandos e saída

```
docker compose run --rm api python scripts/medir_extracao.py tempo
```
PDFs montados das folhas dos processos de referência; paralelismo padrão (4 lotes de 8 páginas), 12 CPUs disponíveis ao Docker.

| Tipo | Páginas | Tempo de parede | Por mil páginas |
|---|---|---|---|
| nativo | 1.000 | 39,5 s | **39,5 s** |
| digitalizado (OCR + OSD a 300 DPI) | 200 | 176,4 s | **881,9 s** |

## Critério

| Critério | Evidência |
|---|---|
| Tempo por mil páginas nativo e digitalizado registrado | tabela acima |
| Um PDF enorme não ocupa toda a capacidade | `test_job_grande_cede_a_vez_e_job_pequeno_de_outro_gabinete_termina_antes` (20 páginas em fatias de 4; o job de 2 páginas de outro gabinete, enfileirado depois, conclui primeiro; `tentativas` fica 1) e `test_paralelismo_respeita_o_teto_do_gabinete` (pico de lotes simultâneos = teto) |
