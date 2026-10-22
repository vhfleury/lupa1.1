# Relatório da Etapa 4E.3 — Uso do índice quando existe

## O que foi feito

- `fronteiras.conferir_origem` e `indice._fronteiras`: com `diagnostico.fronteiras_origem`, a
  fonte principal é o manifesto do ZIP, depois bookmarks, depois índice; o classificador roda e
  cada divergência vira item em `job_ingestao.relatorio.divergencias_fronteira`
  (`origem_sem_sinal_forte`, `sinal_forte_sem_origem`, `origens_discordam`) e flag
  `divergencia_fronteira` na peça (na peça que começa na página e na que contém uma fronteira
  forte não declarada).

## Medição

| Cenário | Divergências (dez processos) | Motivo |
|---|---|---|
| zip_por_peca | 22 em 2.825 peças (0,78%) | todas `origem_sem_sinal_forte` |
| pdf_indice | 22 em 2.825 peças (0,78%) | idem; bookmarks e índice concordam |

Por processo: 1, 2, 1, 1, 4, 2, 4, 2, 4, 1. São exatamente as 22 fronteiras fracas do
cenário liso (peça após a capa e assinatura perdida no OCR): a fronteira da origem está
certa, mas o conteúdo só tem o título. Nenhum `sinal_forte_sem_origem`.

Índice errado de propósito: `test_indice_correto_nao_diverge_e_errado_gera_divergencia_marcada`
move uma fronteira duas páginas num processo pequeno e obtém `origem_sem_sinal_forte` na
página movida, `sinal_forte_sem_origem` na verdadeira e a flag nas duas peças afetadas;
`test_origem_errada_gera_divergencias_dos_dois_lados` faz o mesmo com sinais fabricados.

## Decisões não previstas

- "Sem sinal forte" segue literal o roteiro (pontuação < 0,8), por isso a capa gera uma
  divergência por processo; afrouxar para "sem sinal nenhum" zeraria o número, mas esconderia
  as peças cuja assinatura o OCR perdeu.

## Comandos

```
docker compose run --rm api python scripts/medir_extracao.py extrair semente_NN --lotes 8 --destino /medicao
docker compose run --rm api python scripts/medir_extracao.py pecas --destino /medicao
```
(volume Docker `lupa_medicao4e` montado em `/medicao`; nada copiado para o host)

## Checklist

| Critério | Evidência |
|---|---|
| Índice errado gera divergência marcada | teste acima |
| Índice correto ≈ 0 | 22/2.825 (0,78%), explicadas |
