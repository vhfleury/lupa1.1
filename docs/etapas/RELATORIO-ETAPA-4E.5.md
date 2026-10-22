# Relatório da Etapa 4E.5 — Origem da peça

## O que foi feito

- `classificacao.classificar_origem`: cargo na última assinatura (juiz → `juizo`, promotor →
  `mp`, advogado/OAB/defensor → `defesa`, perito/delegado/testemunha → `terceiro`; confiança
  0,95); cargo aproximado por semelhança quando o OCR estragou o cargo ("Perivo rirúinal" →
  perito criminal; 0,8); vocabulário do início (0,7); senão `desconhecida` (0, flag
  `origem_desconhecida`). Alimenta a origem por trecho (4D.8), que agora lê só peças vigentes.

## Medição

Acurácia **99,6%** (2.813/2.825) em cada cenário; os 12 erros são todos
`terceiro → desconhecida` (laudos/termos cuja linha de assinatura o OCR forte apagou).
`desconhecida` nunca conta como acerto (medido como erro pelo `medir`).

## Checklist

| Critério | Evidência |
|---|---|
| Acurácia medida | 99,6% |
| `desconhecida` quando incerto | 12 casos; `test_origem_por_assinatura_cargo_aproximado_vocabulario_e_desconhecida` |

## Comandos

```
docker compose run --rm api python scripts/medir_extracao.py extrair semente_NN --lotes 8 --destino /medicao
docker compose run --rm api python scripts/medir_extracao.py pecas --destino /medicao
```
(volume Docker `lupa_medicao4e` montado em `/medicao`; nada copiado para o host)
