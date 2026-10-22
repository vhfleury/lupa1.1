# Relatório da Etapa 4B.10 — Harness de medição

20 de outubro de 2026 · agente executor da 4B

## O que foi feito

- `src/lupa/sinteticos/saida_pipeline.py`: esquema `SaidaPipeline` que a pipeline deve gravar —
  peças (tipo, origem, início e fim), páginas (tipo e texto final) e eventos (tipo, valor, página,
  trecho), sempre por `(arquivo, página física)`, mais `tempo_segundos` opcional.
- `src/lupa/sinteticos/medicao.py` e `scripts/medir.py`: converte páginas físicas em folhas pelo
  `arquivos` do gabarito e calcula precisão/recall/F1 de fronteira de peça, acurácia de tipo e de
  origem, acurácia de tipo de página, precisão/recall/F1 de eventos (tipo, valor e folha), CER por
  composição e por nível de degradação (Levenshtein em Python puro, espaços normalizados) e tempo
  por mil páginas. Saída em JSON e Markdown.
- `saida_perfeita(gabarito)` gera a saída ideal (exemplo do formato e referência de 100%).
- Testes: saída perfeita dá 100% e CER 0 nos três cenários; saída com erros injetados (peça faltando,
  tipo trocado, evento com valor errado, evento em arquivo inexistente, página faltando, texto
  corrompido, tipo de página errado) baixa cada métrica no valor exato esperado; saída vazia não
  quebra; CLIs de gerar e medir testadas.

## Decisões não previstas

- Página do índice (folha `null`) usada como início de peça conta como erro de fronteira.
- Página sem texto na saída entra no CER com tudo faltando.
- Levenshtein descarta prefixo e sufixo comuns antes da programação dinâmica; em folhas muito
  divergentes custa alguns segundos por folha.

## O que ficou de fora

- Matriz de confusão de tipo de página (fica para a 4C.4, que precisa dela).

## Verificação

```bash
docker compose up -d --build --wait api
docker compose exec api bash scripts/verificar.sh
```

Saída resumida: ruff, ruff format e mypy --strict limpos; `476 passed, 1 skipped, 1 deselected`;
cobertura total 99,11%; `lupa.sinteticos` 99% (4 linhas não cobertas de 1.235); ponta a ponta da
ingestão (4A) `1 passed`. Nos testes da 4B, 93 casos em cerca de 30 s.

## Arquivos tocados fora de `src/lupa/sinteticos/`

- No início, com acréscimos apenas: `pyproject.toml` (`pymupdf==1.25.1`, `pillow==11.0.0`,
  `numpy==2.2.1` e override do mypy para `fitz`/`pymupdf` sem tipos), `requirements.in`;
  `requirements.txt` e `requirements-dev.txt` recompilados no contêiner com as flags do cabeçalho.
- `.gitignore` (`.sinteticos/`), `README.md` (seção nova), `scripts/gerar_autos.py`,
  `scripts/medir.py`, `tests/sinteticos/`, `docs/sinteticos.md`.
