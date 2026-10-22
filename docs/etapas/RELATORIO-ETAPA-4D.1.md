# Relatório da Etapa 4D.1 — Texto oculto

## O que foi feito

- `src/lupa/ingestao/oculto.py` (roda no filho do sandbox): `motivo_oculto(span, area)` classifica cada span da camada de texto como `fonte_pequena` (< 4 pt), `cor_do_fundo` (RGB igual ao fundo branco), `opacidade_zero` (alfa 0), `fora_da_area_visivel` (caixa fora de `page.rect`, que é a CropBox) ou visível; `trechos_em_camadas_desligadas` compara a extração normal com a de uma cópia do documento com todas as OCGs ligadas e devolve o que só aparece ligado (`camada_desligada`). Cada trecho vira item `{texto, bbox, motivo, hash, categorias}` (categorias de instrução da 4D.5) em `pagina.trechos_ocultos`.
- `texto_nativo.ler_blocos` passa a descartar spans ocultos: o texto oculto sai de `texto_nativo`, da fusão com o OCR e de `pagina.texto`. Linha que só tinha texto oculto desaparece; linha mista mantém os spans visíveis com a caixa recalculada.
- `FlagPagina.TEXTO_OCULTO` ligada quando há trecho oculto.

## Decisões não previstas

- No PyMuPDF 1.25 a cor do span vem com o byte de alfa (`-1` = branco opaco); a comparação usa `cor & 0xFFFFFF`. Isso mostra que o sinal `caracteres_invisiveis` da 4C (que compara `color == 0xFFFFFF`) só pega texto branco quando ele também é pequeno ou está fora da página; não alterei o sinal da 4C para não mexer no roteamento calibrado (fica para a revisão decidir).
- Trocar o estado das OCGs com `set_layer` não muda a extração do documento aberto; é preciso regravar e reabrir. A cópia com tudo ligado é feita uma vez por documento e só quando há OCG desligada.
- Texto girado é visível ao assessor: não é tratado como oculto (a 4C já o tira do fluxo de leitura). Registrado na docstring e em `docs/ingestao.md`.
- Testes da 4C ajustados (arquivos de outra etapa, registrado aqui): `test_hibridas.py::test_camada_de_texto_manipulada_e_separada_como_texto_oculto` (antes `..._gera_texto_divergente`: o texto branco agora é separado antes da fusão, então a página tem `texto_oculto` em vez de `texto_divergente`); `test_paginas.py::test_texto_nativo_igual_a_camada_do_gabarito_com_offsets` (a linha oculta do gabarito não está mais no texto); `test_worker_extracao.py` passou a exigir `texto_oculto` onde exigia `texto_divergente`.

## O que ficou de fora

- Fundo de outra cor (texto da cor de um retângulo desenhado atrás): não detectado; a divergência OCR × nativo da 4C cobre parte. Comparar com a cor do pixel renderizado fica para quando houver caso real.

## Critério

| Critério | Evidência |
| --- | --- |
| `texto_branco` (1 pt, branco) e `fora_da_pagina` detectados e página sinalizada | regressão: 4/4 casos (2 variantes + `injecao_todos`) com `texto_oculto`; motivos `fonte_pequena` e `fora_da_area_visivel` |
| Texto oculto fora de `pagina.texto` | regressão: texto do gabarito ausente de `texto` e `texto_normalizado` nos 4 casos e presente em `trechos_ocultos` |
| OCG desligada, alfa zero, CropBox, span oculto no meio da linha | `test_saneamento.py`: `test_camada_opcional_desligada_e_detectada`, `test_motivos_de_texto_oculto`, `test_texto_branco_pequeno_e_fora_da_cropbox_saem_do_texto`, `test_linha_com_trecho_oculto_no_meio_preserva_o_visivel` |
| Sem falso positivo | 0 das 196 páginas de `semente_01` com `texto_oculto` |

## Comandos e saída

```
docker compose up -d --build --wait
docker compose exec api bash scripts/verificar.sh
```

Saída resumida (21/10/2026): ruff e `ruff format --check` limpos; `mypy --strict` sem erros em 165 arquivos; pytest **588 passed, 1 skipped** (o skip é anterior à 4D; eram 551 testes), cobertura **98,66%**; ponta a ponta 1 passed; regressão de injeção 2 passed (159 s), `recall 1.0`, `falso_positivo 0.0`.
