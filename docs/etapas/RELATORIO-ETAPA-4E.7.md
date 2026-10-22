# Relatório da Etapa 4E.7 — Construção do índice

## O que foi feito

- `src/lupa/ingestao/indice.py`: `montar_indice` (pura) monta a lista ordenada de peças com
  tipo, origem, páginas, data com evidência, confiança (menor entre fronteira e tipo), método,
  flags (`peca` e `paginas`, saneamento agregado) e detalhes da classificação com versões.
- `src/lupa/ingestao/repositorio_pecas.py`: gravação idempotente (não sobrescreve peças
  existentes), leitura do índice do processo, histórico.
- Worker: ao fim da extração (`concluido`/`parcial`) grava índice, sinais e
  `relatorio.indice` + `relatorio.divergencias_fronteira`.
- `GET /processos/{id}/indice` (`src/lupa/api/rotas/pecas.py`), auditada como
  `processo_aberto` com conteúdo.

## Medição

Índice gerado para os dez processos nos três cenários (tabela do 4E.9); tempo do índice
inteiro: 0,7 s (196 págs) a 19,9 s (4.988 págs).

## Checklist

| Critério | Evidência |
|---|---|
| Índice dos dez processos | 30 execuções, 2.825 peças cada cenário |
| Exportável em JSON | `test_rota_do_indice_auditada_com_resumo_de_flags_e_isolada_por_gabinete` |
| RLS: outro gabinete → 404 | mesmo teste |

## Comandos

```
docker compose up -d --build --wait
docker compose exec api alembic -c src/lupa/migrations/alembic.ini upgrade head   # 0006 (head)
docker compose exec api bash scripts/verificar.sh
```
Saída final no relatório 4E.10.
