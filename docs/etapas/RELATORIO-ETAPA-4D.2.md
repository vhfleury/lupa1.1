# Relatório da Etapa 4D.2 — Metadados e anotações

## O que foi feito

- `src/lupa/ingestao/metadados.py` (filho do sandbox): lê Info dict (title, author, subject, keywords, creator, producer), nós de texto do XMP (por regex, sem parser XML sobre conteúdo não confiável), bookmarks, nomes de arquivos embutidos, anotações (content, title, subject) e campos de formulário (nome e valor). Cada valor vira `{origem, chave, pagina, hash, caracteres, categorias}`; o valor nunca sai do filho e nunca entra no texto da página.
- `parser_pdf.inspecionar` devolve `metadados` (documento + anotações e campos de todas as páginas, até 500 itens); o worker repassa e o diagnóstico grava em `diagnostico_arquivo.metadados_descartados` (com `entrada` = nome do PDF ou da entrada do ZIP) e `sinais.metadado_suspeito`.
- No extrator, cada página registra os itens dela (anotações e campos) e a página 1 de cada PDF registra também os do documento, em `extracao.metadados_descartados`; com categoria de instrução, `FlagPagina.METADADO_SUSPEITO` na página (a da anotação; a primeira para XMP, Info e bookmark).

## Decisões não previstas

- **`arquivo.metadados_descartados` virou `diagnostico_arquivo.metadados_descartados`**: `arquivo` é imutável (trigger `arquivo_imutavel`, 0001) e é gravado antes do parsing. O diagnóstico é um por arquivo e já guarda o que a inspeção do PDF descobre.

## O que ficou de fora

- Links (URI) e JavaScript do PDF não são listados (também não entram no texto).

## Critério

| Critério | Evidência |
| --- | --- |
| Instrução em XMP não aparece em nenhuma `pagina.texto` | regressão: `metadado_xmp` (2 casos) com `metadado_suspeito` na página 1 e item `xmp` com `ignorar_instrucoes`, `revelar_dados`; texto ausente de `texto` e do normalizado |
| Instrução em anotação não aparece em `pagina.texto` | regressão: `anotacao` (2 casos) com `metadado_suspeito` na página da anotação; texto ausente |
| Só hash | `test_saneamento.py::test_metadados_do_documento_e_da_pagina_registram_hash_sem_valor`; a resposta de `/alertas` não contém o texto do XMP (`test_worker_extracao.py`) |

## Comandos e saída

```
docker compose up -d --build --wait
docker compose exec api bash scripts/verificar.sh
```

Saída resumida (21/10/2026): ruff e `ruff format --check` limpos; `mypy --strict` sem erros em 165 arquivos; pytest **588 passed, 1 skipped** (o skip é anterior à 4D; eram 551 testes), cobertura **98,66%**; ponta a ponta 1 passed; regressão de injeção 2 passed (159 s), `recall 1.0`, `falso_positivo 0.0`.
