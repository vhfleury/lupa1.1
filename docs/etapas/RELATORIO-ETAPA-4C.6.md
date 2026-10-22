# Relatório da Etapa 4C.6 — OCR

## O que foi feito

- `Dockerfile` (imagem de runtime): `tesseract-ocr=5.5.0-1+b1`, `tesseract-ocr-por`, `-osd`, `-eng` `=1:4.1.0-2` (Debian trixie); o build confere `por.traineddata` sha256 `c4932b937207a9514b7514d518b931a99938c02a28a5a5a553f8599ed58b7deb`.
- `src/lupa/ingestao/ocr.py`: chama o binário (sem dependência Python nova) dentro do filho do sandbox; imagem PNG cinza por stdin, `tsv` por stdout, `OMP_THREAD_LIMIT=1`, tempo máximo de 90 s. Raster de 300 DPI; `--psm 0` (OSD) no mesmo raster; confiança ≥ 2 → rasteriza de novo girado. Caixas em pixels → pontos pela inversa da matriz de rasterização (inclui rotação e origem do recorte), registrada em `extracao.ocr.matriz_pixel_para_ponto`.
- Falha do Tesseract (`OcrIndisponivelError`) deixa a página sem resultado (job `parcial`).

## Decisões não previstas

- OSD a 150 DPI dava confiança 1,9 numa página deitada (abaixo do limiar); passou a usar o raster de 300 DPI, sem custo extra de rasterização quando a página está de pé.
- `.sinteticos` entrou no `.dockerignore` (4,7 GB no contexto de build) e é montado só leitura no `api`.

## Comandos e saída

```
docker compose run --rm api python scripts/medir_extracao.py ocr --por-nivel 6
```
Amostra estratificada: 6 páginas digitalizadas por nível em cada um dos dez processos (180 páginas, semente 20261020), OCR completo (OSD + TSV), CER contra `paginas[].texto` com espaços normalizados.

| Nível | Páginas | Caracteres | CER | Datas no gabarito | Encontradas literalmente | Taxa | s/página (1 filho) |
|---|---|---|---|---|---|---|---|
| leve (300 DPI) | 60 | 134.742 | **1,41%** | 317 | 298 | **94,0%** | 2,7 |
| media (200 DPI) | 60 | 146.351 | **2,80%** | 345 | 313 | **90,7%** | 3,5 |
| forte (150 DPI, contraste baixo) | 60 | 138.153 | **10,28%** | 359 | 291 | **81,1%** | 3,4 |

Medição completa (todas as páginas OCR dos dez processos) no relatório 4C.10.

## Metas (definidas a partir da medição; fecha a pendência 4B.4)

| Nível | CER máximo | Datas literais mínimas |
|---|---|---|
| leve | 3% | 90% |
| media | 5% | 85% |
| forte | 15% | 75% |

As metas cumprem-se na amostra. Datas não reconhecidas no nível forte são o risco relevante: a extração de fatos (4F.4) só aceita data que exista literalmente na página, então uma data mal lida vira fato ausente (vai ao assessor), não fato errado.

## Critério

| Critério | Evidência |
|---|---|
| Tesseract por-BR em subprocesso dentro do sandbox | `extrator_paginas` → `ocr.executar_tesseract`; teste `test_lotes_reais_rodam_em_processos_filhos` e worker |
| Rotação detectada e corrigida | `test_pagina_deitada_tem_orientacao_detectada_e_corrigida` (texto a 90°, data lida, caixa sobre a palavra nativa) |
| Caixas raster → pontos com transformação registrada | `test_ocr_le_texto_e_datas_com_caixas_sobre_as_palavras_nativas`, `test_rasterizacao_registra_a_transformacao_de_volta` |
| CER por nível dentro da meta | tabela acima |
