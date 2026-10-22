# Relatório da Etapa 4E.4 — Tipo da peça por regras

## O que foi feito

- `src/lupa/ingestao/classificacao.py` + `dados/classificacao.yaml` (versão 1): título
  (3 pontos; 1 quando o título não decide, como "DECISÃO") e fórmulas das primeiras 18 linhas
  ("Vistos e examinados", "É o relatório", "recebo a denúncia", "prisão preventiva",
  "CERTIFICO", "acordam"...). Abaixo de 2 pontos ou com margem < 1: `outros`, confiança 0,3,
  flag `tipo_ambiguo`.

## Medição (dez processos, gabarito `pecas[].tipo`)

| Cenário | Acurácia | Peças saída / gabarito |
|---|---|---|
| zip_por_peca | **100,0%** (2.825/2.825) | 2.825 / 2.825 (0% a mais) |
| pdf_indice | **100,0%** | 2.825 / 2.825 |
| pdf_liso | **100,0%** | 2.825 / 2.825 |

Nenhuma peça inventada (excesso 0%, limite 2%).

## Checklist

| Critério | Evidência |
|---|---|
| Acurácia ≥ 95% | 100% nos três cenários |
| Nenhuma peça inventada | 2.825 = 2.825 |
| Ambíguo vira `outros` baixo | `test_tipo_ambiguo_vira_outros_com_confianca_baixa` |

## Comandos

```
docker compose run --rm api python scripts/medir_extracao.py extrair semente_NN --lotes 8 --destino /medicao
docker compose run --rm api python scripts/medir_extracao.py pecas --destino /medicao
```
(volume Docker `lupa_medicao4e` montado em `/medicao`; nada copiado para o host)
