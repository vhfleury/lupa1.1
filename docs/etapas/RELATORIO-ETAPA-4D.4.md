# Relatório da Etapa 4D.4 — Blocos codificados

## O que foi feito

- `deteccao.detectar_blocos`: base64 (40 ou mais do alfabeto, padding plausível, com algarismo, `+`, `/` ou caixa mista), hex (40 ou mais), URL-encoded (10 ou mais `%XX`) e, para texto de OCR, base64/hex **fragmentado** (dois ou mais tokens do alfabeto com troca interna de caixa ou de letra/algarismo, somando 40 ou mais).
- `saneamento_pagina.sanear` troca cada bloco por `[bloco codificado removido]` no normalizado (original intacto), grava trecho `bloco_codificado` com o hash do original e, se o bloco decodifica para texto legível, roda os padrões da 4D.5 no decodificado (trechos `decodificado:<id>`). `FlagPagina.BLOCO_CODIFICADO`.

## Heurística de rodapé (fica intacto, sem flag)

Bloco que **não** decodifica para texto legível, com tamanho de resumo criptográfico (hex de 32, 40, 56, 64, 96 ou 128, com tolerância de 3 caracteres, uma só caixa e aceitando as letras que o OCR troca por algarismos; base64 de 24, 28, 44, 64 ou 88) e precedido, a até 60 caracteres, de "autenticação", "verificação", "hash", "assinatura", "chave", "código", "protocolo", "certificado", "sha" ou "md5". Bloco legível nunca é rodapé.

## Decisões não previstas

- O OCR parte o código de autenticação de 40 hex dos sintéticos em pedaços e troca letras (`0`→`O`, `5`→`S`, `1`→`I`): a primeira medição em `semente_01` deu 53 de 196 páginas sinalizadas. A tolerância de tamanho e o alfabeto de uma só caixa zeraram isso sem perder a injeção (o base64 da instrução tem minúsculas).

## Critério

| Critério | Evidência |
| --- | --- |
| Bloco não chega ao texto de análise; página sinalizada | regressão: `base64` (2 casos) com `bloco_codificado` e marcador no normalizado. Em `injecao_todos` (nativa) o decodificado dispara `ignorar_instrucoes` e `alterar_resultado`; em `injecao_base64` (folha OCR, bloco partido) o fragmentado é removido |
| Rodapé legítimo intacto | 0 das 196 páginas de `semente_01` (todas com código de autenticação) com `bloco_codificado`; `test_codigo_de_autenticacao_de_rodape_fica_intacto_mesmo_com_erro_de_ocr` |
| Hex e URL-encoded | `test_hex_e_url_encoded_sao_removidos`, `test_base64_partido_pelo_ocr_e_detectado` |

## Comandos e saída

```
docker compose up -d --build --wait
docker compose exec api bash scripts/verificar.sh
```

Saída resumida (21/10/2026): ruff e `ruff format --check` limpos; `mypy --strict` sem erros em 165 arquivos; pytest **588 passed, 1 skipped** (o skip é anterior à 4D; eram 551 testes), cobertura **98,66%**; ponta a ponta 1 passed; regressão de injeção 2 passed (159 s), `recall 1.0`, `falso_positivo 0.0`.
