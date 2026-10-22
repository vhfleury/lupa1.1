# Relatório da Etapa 4B.9 — Processos de referência

20 de outubro de 2026 · agente executor da 4B

## O que foi feito

- `src/lupa/sinteticos/referencia.py`: dez configurações fixas (`semente_01` a `semente_10`,
  sementes 1001 a 1010), tamanhos de 200 a 5.000 folhas, mistura indo de 90% digitalizado (o menor)
  a 90% nativo (o maior), resultados das validações variados.
- Gerados com `python scripts/gerar_autos.py referencia` (host, venv) em
  `C:\Users\vh15f\OneDrive\projetos\Lupa1\.sinteticos\referencia\` (fora do git), três cenários
  cada, com `gabarito.json` por cenário e `resumo.json` com tempo e tamanhos.
- Tamanho real ajustado automaticamente ao alvo (o gerador refaz o roteiro até ficar a ±2%).

| Processo | Folhas | Peças | Digit./nativa | Tempo (s) | ZIP (MB) | PDF índice (MB) | PDF liso (MB) | Temp./Presc./Prev. |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| semente_01 | 196 | 51 | 86% / 2% | 24,8 | 57,7 | 56,4 | 56,3 | conforme/conforme/atenção |
| semente_02 | 294 | 84 | 78% / 13% | 36,2 | 78,7 | 75,8 | 75,7 | atenção/atenção/conforme |
| semente_03 | 450 | 79 | 66% / 24% | 50,2 | 114,2 | 109,8 | 109,7 | conforme/atenção/verificar |
| semente_04 | 643 | 120 | 57% / 32% | 69,1 | 150,2 | 142,8 | 142,7 | atenção/conforme/atenção |
| semente_05 | 891 | 172 | 50% / 41% | 75,8 | 174,3 | 162,4 | 162,3 | conforme/conforme/conforme |
| semente_06 | 1.200 | 240 | 40% / 50% | 89,4 | 206,4 | 188,8 | 188,7 | atenção/atenção/atenção |
| semente_07 | 1.598 | 286 | 28% / 62% | 86,9 | 215,8 | 191,0 | 190,9 | conforme/conforme/verificar |
| semente_08 | 2.198 | 384 | 20% / 71% | 86,7 | 236,0 | 202,6 | 202,5 | atenção/conforme/conforme |
| semente_09 | 3.189 | 531 | 15% / 76% | 107,4 | 276,0 | 229,5 | 229,3 | conforme/atenção/atenção |
| semente_10 | 4.988 | 878 | 2% / 89% | 84,8 | 237,5 | 156,9 | 156,6 | atenção/conforme/conforme |

Tempo total cerca de 12 minutos; volume total da pasta `.sinteticos` (referência + injeção) 4,7 GB.
Todos os dez têm carimbo, marca d'água, rodapé de autenticação, cabeçalho repetido, híbridas e
versos em branco (4B.6). Corpus de injeção (`.sinteticos/injecao/`, PDF liso): 10 variantes de 29 a
58 folhas, 1,6 a 3,8 MB cada, cerca de 1,5 s cada.

## Decisões não previstas

- O maior processo ficou com 5.000 folhas (não foi preciso reduzir para 2.000): a geração é rápida
  porque ele é quase todo nativo. Inverter a mistura (o maior mais digitalizado) passaria de 3 GB
  só nele, numa pasta sincronizada pelo OneDrive.
- "Repositório separado versionado": a reprodutibilidade vem da semente e da versão do código (teste
  prova que mesma semente → gabarito idêntico byte a byte). Os PDFs ficam fora do git; versionar os
  binários em outro repositório é decisão do gabinete.
- Variantes pequenas (alvo de 30 folhas) saem com 50 a 60 quando há muitas revisões da preventiva:
  as peças obrigatórias já passam do alvo.
- A pasta `.sinteticos/` está no OneDrive: 4,7 GB vão sincronizar. Sugiro excluí-la do OneDrive ou
  usar `LUPA_SINTETICOS_DIR` fora dele.

## O que ficou de fora

- Geração dentro do contêiner (rodou no host para gravar direto na pasta do host sem copiar do
  contêiner, como pedem as regras).
