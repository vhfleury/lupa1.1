# Relatório da Etapa 4B.7 — Três cenários de empacotamento

20 de outubro de 2026 · agente executor da 4B

## O que foi feito

- `empacotamento.py` grava, para o mesmo conteúdo: `zip_por_peca/autos.zip` (um PDF por peça,
  `NNN_tipo_AAAA-MM-DD.pdf`), `pdf_indice/autos.pdf` (páginas "ÍNDICE DE MOVIMENTAÇÕES" com
  "Movimentação NNN - data - título - fls. X" e um bookmark por peça apontando para a página
  física) e `pdf_liso/autos.pdf`; cada pasta com seu `gabarito.json`.
- Diagnóstico esperado: `zip_por_peca`, `pdf_com_bookmarks_e_indice`, `pdf_liso`.
- Testes: conteúdo do gabarito (peças, folhas, eventos, resultado, injeções) idêntico nos três;
  diagnósticos distintos; nomes e quantidades de páginas do ZIP; bookmarks apontam para a folha de
  início de cada peça; PDF liso sem bookmarks e com texto igual a `texto_camada`.

## Decisões não previstas

- O índice traz a folha física já deslocada pelas páginas de índice; o gabarito marca essas
  páginas com `null` em `arquivos[0].folhas`.

## Como rodar os testes

```bash
docker compose exec api bash scripts/verificar.sh
# só a 4B, no host:
.venv/Scripts/python -m pytest tests/sinteticos --confcutdir=tests/sinteticos -o addopts="" --cov=lupa.sinteticos
```

Saída resumida (host, venv): `93 passed`; cobertura de `lupa.sinteticos` 99% (1.235 instruções, 4 não
cobertas). `ruff check`, `ruff format --check` e `mypy --strict` limpos em `src/lupa/sinteticos` e
`tests/sinteticos`. Resultado do `verificar.sh` completo: ver RELATORIO-ETAPA-4B.10.md.
