# Relatório da Etapa 4C.7 — Páginas híbridas

## O que foi feito

- Abstenção do roteador (híbridas, nativas com imagem opaca, texto invisível, texto ilegível): o extrator guarda `texto_nativo` e `texto_ocr` e grava em `texto` a fusão (`hibridas.fundir`): toda linha nativa horizontal entra; linha do OCR coberta em ≥ 50% por linhas nativas é descartada (dedup geométrico); ordem por topo e esquerda.
- `hibridas.comparar`: para cada linha nativa com ≥ 8 caracteres, junta as palavras do OCR cujo centro cai na caixa da linha (folga de 2 pt); similaridade < 0,5 → linha divergente → `FlagPagina.TEXTO_DIVERGENTE` (novo valor do enum) e caixa em `extracao.divergencia.trechos`. A distância somada é o CER estimado da página.

## Decisões não previstas

- Linhas não horizontais do nativo (marca d'água) ficam fora do texto fundido e fora da comparação; continuam em `texto_nativo`. Texto oculto girado fica para a 4D.1.
- Texto fora da página não entra no texto nativo (o PyMuPDF recorta), mas o sinal `caracteres_invisiveis` leva a página à abstenção; a marcação dele é da 4D.1.

## Comandos

`pytest tests/ingestao/test_hibridas.py`.

## Critério

| Critério | Evidência |
|---|---|
| Nativo e OCR guardados; fusão sem duplicar | `test_fusao_nao_duplica_o_que_as_duas_camadas_leram`; colunas `texto_nativo`/`texto_ocr` |
| Camada de texto manipulada gera a flag | `test_camada_de_texto_manipulada_gera_texto_divergente[texto_branco]`: página com instrução em branco, 1 pt → rota `abstencao`, flag `texto_divergente`; o mesmo no fluxo completo do worker (`test_pdf_sintetico_com_indice_vai_a_concluido...`) e na página 25 de `.sinteticos/injecao/injecao_texto_branco` (mesmo gerador) |
| Híbrida limpa não diverge | `test_pagina_hibrida_limpa_nao_diverge`; nas 1.273 híbridas dos dez processos, ver flags no relatório 4C.10 |
