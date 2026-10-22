# Relatório da Etapa 4C.3 — Sinais por página

## O que foi feito

- `src/lupa/ingestao/sinais.py` (`medir_sinais`), executado no filho do sandbox (`extrator_paginas`): `caracteres_imprimiveis`, `caracteres_substituicao` (U+FFFD), `caracteres_invisiveis` (fonte < 4 pt, cor branca, fora da página), `cobertura_texto`, `area_imagem`, `area_imagem_opaca`, `imagens`, `palavras`, `fragmentacao`, `rotacao` declarada, `tinta` (pixels < 160 num pixmap cinza de 24 DPI) e `visualmente_vazia` (tinta < 0,05%).
- Gravados em `pagina.sinais` (JSONB, migração 0004).

## Decisões não previstas

- **Área de imagem opaca separada da total**: carimbos (PNG com transparência) aparecem em 1.290 páginas nativas dos processos de referência com área até 2,7%, enquanto a assinatura digitalizada das híbridas ocupa 2,0 a 4,7%. Só a máscara de transparência separa os dois; imagem opaca é tratada como conteúdo digitalizado.
- **Texto invisível** (fora da página exige `clip=INFINITE_RECT` e sem `TEXT_MEDIABOX_CLIP`) entrou como sinal porque é o que permite levar a página de camada manipulada ao OCR (4C.7).

## Comandos

`pytest tests/ingestao/test_paginas.py` (sinais reproduzíveis, carimbo vs. imagem opaca, invisíveis, rotação, página vazia).

## Critério

| Critério | Evidência |
|---|---|
| Sinais gravados por página | `pagina.sinais` preenchido em todas as páginas (`test_pdf_sintetico_com_indice_vai_a_concluido...`) |
| Reproduzíveis | `test_rotacao_declarada_e_sinais_reproduziveis`; valores arredondados a 4 casas |
