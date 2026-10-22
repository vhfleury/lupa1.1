# Relatório da Etapa 4E.2 — Classificador de fronteira por regras

## O que foi feito

- `src/lupa/ingestao/fronteiras.py`: `pontuar(sinais_pagina_anterior, sinais_pagina) -> float`
  (pura), `nivel`, `sinais_ativos`, `segmentar`. Pesos e limiares em
  `dados/fronteiras.yaml` (versão 1): título 0,5; título de seção 0,25; assinatura na página
  anterior 0,45; reinício de numeração 0,3; cabeçalho novo 0,15; protocolo no topo 0,1;
  fonte e layout 0,05. Forte ≥ 0,8; fraca ≥ 0,45 → peça com confiança baixa (pontuação × 0,5)
  e flag `fronteira_fraca`. Versos em branco são pulados (ficam com a peça anterior).

## Medição (cenário `pdf_liso`, dez processos, `scripts/medir_extracao.py pecas` → `medir`)

Fronteira: precisão **100,0%** (2.825/2.825), recall **100,0%** (2.825/2.825); nenhuma
fronteira faltando ou sobrando. 22 fronteiras saíram fracas (todas corretas).

Erros mais comuns (antes da calibração e nas fracas restantes): assinatura destruída pelo
OCR ("eletronicame:«e", "eletron* ar ente") — resolvido com reconhecimento tolerante; páginas
lidas fora de ordem no `linhas.json` (lotes paralelos) — resolvido ordenando por número; peça
depois da capa (capa não tem assinatura) e peça cuja assinatura sumiu no OCR forte ficam
fracas (só título).

## Decisões não previstas

- Fraca também cria peça (com flag), em vez de só avisar, seguindo "Peca.metodo = regra com
  confiança baixa e flag". `RAZÕES DE APELAÇÃO` é título de seção (0,25, nunca fronteira
  sozinho).

## Comandos

```
docker compose run --rm api python scripts/medir_extracao.py extrair semente_NN --lotes 8 --destino /medicao
docker compose run --rm api python scripts/medir_extracao.py pecas --destino /medicao
```
(volume Docker `lupa_medicao4e` montado em `/medicao`; nada copiado para o host)

## Checklist

| Critério | Evidência |
|---|---|
| Precisão ≥ 95% no liso | 100,0% (2.825/2.825) |
| Recall ≥ 95% no liso | 100,0% (2.825/2.825) |
| Pesos em YAML versionado | `fronteiras.yaml` versão 1 |
| Testes | `tests/ingestao/test_fronteiras.py` (11 testes) |
