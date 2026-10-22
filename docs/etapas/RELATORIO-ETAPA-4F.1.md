# Relatório da Etapa 4F.1 — Padrões de data

## O que foi feito

- `src/lupa/ingestao/datas.py`: reconhecimento de datas com normalização para ISO e offsets no
  texto original.
  - numérico `dd/mm/aaaa`, `dd.mm.aaaa`, `dd-mm-aaaa` (dia e mês com 1 ou 2 dígitos), e
    `dd/ mm/aaaa` com espaço junto da barra (erro comum do OCR, visto nos processos de referência);
  - numérico com ano de 2 dígitos, com pivô fixo 50 (`00`–`49` → 20xx, `50`–`99` → 19xx) e a
    ocorrência marcada `ano_dois_digitos`;
  - por extenso com dia e ano em algarismos ou por extenso (`1º de março de 2016`, `quinze de
    maio de dois mil e catorze`, `mil novecentos e oitenta e cinco`, `catorze`/`quatorze`,
    `primeiro`);
  - abreviado (`15/mai/2014`, `15-mai-2014`, `15 mai. 2014`, `15 mai 2014`, `15 de mai. de 2014`);
  - com e sem dia da semana antes (o dia da semana não entra no literal).
- A busca é no texto normalizado da 4D.3 (NFKC, homóglifos, sem controle) "dobrado" caractere a
  caractere (minúsculas, sem acento, mesmo comprimento); o intervalo volta ao original pelo mapa
  `TextoNormalizado.para_original`. `TextoAnalise` guarda original, normalizado e dobrado de uma
  página para os extratores.
- `reconferir(trecho, data)`: conferência independente para a 4F.4 (escreve a data em todas as
  formas aceitas e procura no trecho, com fronteira de número).
- `tests/ingestao/test_datas.py`: suíte de 24 formatos, 10 datas impossíveis, ano bissexto,
  pivô, offsets com dígitos de largura total e caracteres invisíveis, número CNJ/CPF/hora,
  reconferência e ida e volta dos números por extenso de 1 a 2100.

## Decisões não previstas

- Ano de 2 dígitos: pivô fixo 50 em vez de janela relativa à data de referência, para o mesmo
  texto dar sempre a mesma data; quem usa a ocorrência multiplica a confiança por 0,8 (4F.2).
- `data_peca.py` (4E.6) continua com as suas expressões; não foi trocado para não mudar a
  medição aprovada da 4E. Pode passar a usar `datas.py` numa próxima versão do índice.

## O que ficou de fora

- Datas sem ano ("15 de maio") e intervalos ("de 10 a 15/05/2014") não são datas para a
  extração; o segundo dá só `15/05/2014`.

## Comandos e saída resumida

```
docker compose run --rm api python -m pytest tests/ingestao/test_datas.py --no-cov -q
43 passed
```

## Checklist

| Item | Evidência |
| --- | --- |
| Numérico, extenso e abreviado, com e sem dia da semana | 24 casos em `FORMATOS` |
| Suíte de formatos com 100% de acerto | `test_suite_de_formatos_tem_cem_por_cento_de_acerto`: 24/24 |
| Rejeição de datas impossíveis (31/02) | `test_rejeita_data_impossivel`: 10/10 rejeitadas; 29/02/2016 aceita |
| Ano de 2 dígitos documentado | `docs/ingestao.md`, seção "Datas (4F.1)"; teste do pivô |
| Offsets sobre o texto original | `test_offsets_apontam_para_o_texto_original_mesmo_com_normalizacao` |
