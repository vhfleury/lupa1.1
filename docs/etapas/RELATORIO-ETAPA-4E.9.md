# Relatório da Etapa 4E.9 — Medição contra gabarito

## O que foi feito

- `PecaSaida.data` (opcional) em `saida_pipeline`; `medir` ganhou `data_peca` (acurácia; sem
  data prevista conta como erro) e a linha no Markdown.
- `scripts/medir_extracao.py extrair --destino` grava também `linhas.json.gz`; subcomando
  `pecas` monta o índice nos três cenários e mede com `medir`.

## Decisões não previstas

- Só o `pdf_liso` foi extraído (OCR, ~55 min no total); as folhas são as mesmas nos três
  cenários, então o texto é reaproveitado pelo mapa `arquivos[].folhas` do gabarito; as páginas
  do índice do `pdf_indice` são lidas por texto nativo e o diagnóstico (fronteiras da origem)
  de cada cenário roda de verdade. Por isso tipo, origem e data são iguais nos três.
- A medição de peças envia páginas sem texto ao `medir` (o CER em Python puro levaria horas;
  ele já foi medido na 4C.10).

## Por processo e cenário

| Processo | Cenário | Fonte | Peças gab./saída | Fronteira P | Fronteira R | Tipo | Origem | Data | Divergências | Fracas | Desconhecida | Sem data |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| semente_01 | zip_por_peca | manifesto | 51/51 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 1 | 0 | 0 | 0 |
| semente_01 | pdf_indice | bookmark | 51/51 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 1 | 0 | 0 | 0 |
| semente_01 | pdf_liso | regras | 51/51 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 0 | 1 | 0 | 0 |
| semente_02 | zip_por_peca | manifesto | 84/84 | 100.0% | 100.0% | 100.0% | 100.0% | 98.8% | 2 | 0 | 0 | 1 |
| semente_02 | pdf_indice | bookmark | 84/84 | 100.0% | 100.0% | 100.0% | 100.0% | 98.8% | 2 | 0 | 0 | 1 |
| semente_02 | pdf_liso | regras | 84/84 | 100.0% | 100.0% | 100.0% | 100.0% | 98.8% | 0 | 2 | 0 | 1 |
| semente_03 | zip_por_peca | manifesto | 79/79 | 100.0% | 100.0% | 100.0% | 100.0% | 98.7% | 1 | 0 | 0 | 0 |
| semente_03 | pdf_indice | bookmark | 79/79 | 100.0% | 100.0% | 100.0% | 100.0% | 98.7% | 1 | 0 | 0 | 0 |
| semente_03 | pdf_liso | regras | 79/79 | 100.0% | 100.0% | 100.0% | 100.0% | 98.7% | 0 | 1 | 0 | 0 |
| semente_04 | zip_por_peca | manifesto | 120/120 | 100.0% | 100.0% | 100.0% | 100.0% | 98.3% | 1 | 0 | 0 | 1 |
| semente_04 | pdf_indice | bookmark | 120/120 | 100.0% | 100.0% | 100.0% | 100.0% | 98.3% | 1 | 0 | 0 | 1 |
| semente_04 | pdf_liso | regras | 120/120 | 100.0% | 100.0% | 100.0% | 100.0% | 98.3% | 0 | 1 | 0 | 1 |
| semente_05 | zip_por_peca | manifesto | 172/172 | 100.0% | 100.0% | 100.0% | 98.3% | 96.5% | 4 | 0 | 3 | 2 |
| semente_05 | pdf_indice | bookmark | 172/172 | 100.0% | 100.0% | 100.0% | 98.3% | 96.5% | 4 | 0 | 3 | 2 |
| semente_05 | pdf_liso | regras | 172/172 | 100.0% | 100.0% | 100.0% | 98.3% | 96.5% | 0 | 4 | 3 | 2 |
| semente_06 | zip_por_peca | manifesto | 240/240 | 100.0% | 100.0% | 100.0% | 99.6% | 99.6% | 2 | 0 | 1 | 1 |
| semente_06 | pdf_indice | bookmark | 240/240 | 100.0% | 100.0% | 100.0% | 99.6% | 99.6% | 2 | 0 | 1 | 1 |
| semente_06 | pdf_liso | regras | 240/240 | 100.0% | 100.0% | 100.0% | 99.6% | 99.6% | 0 | 2 | 1 | 1 |
| semente_07 | zip_por_peca | manifesto | 286/286 | 100.0% | 100.0% | 100.0% | 99.3% | 99.0% | 4 | 0 | 2 | 2 |
| semente_07 | pdf_indice | bookmark | 286/286 | 100.0% | 100.0% | 100.0% | 99.3% | 99.0% | 4 | 0 | 2 | 2 |
| semente_07 | pdf_liso | regras | 286/286 | 100.0% | 100.0% | 100.0% | 99.3% | 99.0% | 0 | 4 | 2 | 2 |
| semente_08 | zip_por_peca | manifesto | 384/384 | 100.0% | 100.0% | 100.0% | 98.7% | 98.7% | 2 | 0 | 5 | 1 |
| semente_08 | pdf_indice | bookmark | 384/384 | 100.0% | 100.0% | 100.0% | 98.7% | 98.7% | 2 | 0 | 5 | 1 |
| semente_08 | pdf_liso | regras | 384/384 | 100.0% | 100.0% | 100.0% | 98.7% | 98.7% | 0 | 2 | 5 | 1 |
| semente_09 | zip_por_peca | manifesto | 531/531 | 100.0% | 100.0% | 100.0% | 99.8% | 98.7% | 4 | 0 | 1 | 1 |
| semente_09 | pdf_indice | bookmark | 531/531 | 100.0% | 100.0% | 100.0% | 99.8% | 98.7% | 4 | 0 | 1 | 1 |
| semente_09 | pdf_liso | regras | 531/531 | 100.0% | 100.0% | 100.0% | 99.8% | 98.7% | 0 | 4 | 1 | 1 |
| semente_10 | zip_por_peca | manifesto | 878/878 | 100.0% | 100.0% | 100.0% | 100.0% | 99.1% | 1 | 0 | 0 | 3 |
| semente_10 | pdf_indice | bookmark | 878/878 | 100.0% | 100.0% | 100.0% | 100.0% | 99.1% | 1 | 0 | 0 | 3 |
| semente_10 | pdf_liso | regras | 878/878 | 100.0% | 100.0% | 100.0% | 100.0% | 99.1% | 0 | 1 | 0 | 3 |

## Por cenário (micro-média)

| Cenário | Peças gab./saída | Fronteira P | Fronteira R | Tipo | Origem | Data | tipo_data igual | Divergências | Fracas | Desconhecida | Sem data |
|---|---|---|---|---|---|---|---|---|---|---|---|
| zip_por_peca | 2825/2825 | 100.0% (2825/2825) | 100.0% (2825/2825) | 100.0% (2825) | 99.6% (2813) | 98.8% (2791) | 31.3% | 22 | 0 | 12 | 12 |
| pdf_indice | 2825/2825 | 100.0% (2825/2825) | 100.0% (2825/2825) | 100.0% (2825) | 99.6% (2813) | 98.8% (2791) | 31.3% | 22 | 0 | 12 | 12 |
| pdf_liso | 2825/2825 | 100.0% (2825/2825) | 100.0% (2825/2825) | 100.0% (2825) | 99.6% (2813) | 98.8% (2791) | 31.3% | 0 | 22 | 12 | 12 |

## Comandos

```
docker compose run --rm api python scripts/medir_extracao.py extrair semente_NN --lotes 8 --destino /medicao
docker compose run --rm api python scripts/medir_extracao.py pecas --destino /medicao
```
(volume Docker `lupa_medicao4e` montado em `/medicao`; nada copiado para o host)
