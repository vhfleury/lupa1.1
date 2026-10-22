# Relatório da Etapa 4E.6 — Data da peça

## O que foi feito

- `src/lupa/ingestao/data_peca.py`: protocolo ("protocolada em"), assinatura ("assinado
  eletronicamente por ..., em"), local e data, juntada/autuação ("recebidos em", "autuado em"),
  nessa ordem; numérico e por extenso; data inválida ou fora de 1900–2100 rejeitada.
  Evidência: literal, offsets no texto da página, hash; gravada em `evidencia` e ligada por
  `peca.data_evidencia_id` (migração 0006), com `peca.data` e `peca.tipo_data`.

## Medição

| Cenário | Acurácia contra `pecas[].data` | Sem data (não inventada) |
|---|---|---|
| três cenários | **98,8%** (2.791/2.825) | 12 peças |

Erros: 22 datas diferentes (dígito lido errado pelo OCR na assinatura de termos e laudos,
p. ex. 04 → 14) e 12 ausentes (assinatura apagada). Toda data gravada tem evidência literal
(2.813 peças). `tipo_data` coincide com o do gabarito em 31,3%: o gabarito chama de
"protocolo"/"juntada" datas que no texto aparecem só na assinatura; o Lupa registra o que a
evidência mostra.

## Checklist

| Critério | Evidência |
|---|---|
| Datas com evidência | 2.813/2.813 com trecho, offsets e hash; `test_indice_do_processo_sintetico...` confere `texto[inicio:fim] == trecho` |
| Data ausente não inventada | `test_data_da_peca_com_evidencia_e_sem_invencao` |
| Acurácia registrada | 98,8% |

## Comandos

```
docker compose run --rm api python scripts/medir_extracao.py extrair semente_NN --lotes 8 --destino /medicao
docker compose run --rm api python scripts/medir_extracao.py pecas --destino /medicao
```
(volume Docker `lupa_medicao4e` montado em `/medicao`; nada copiado para o host)
