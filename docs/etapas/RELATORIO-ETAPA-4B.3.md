# Relatório da Etapa 4B.3 — Renderização nativa

20 de outubro de 2026 · agente executor da 4B

## O que foi feito

- `paginacao.py`: quebra de linhas só em espaços simples (o texto da folha preserva os offsets do
  parágrafo), cada peça começa em folha nova, parágrafo com evento nunca é dividido entre folhas.
  Cabeçalho "PODER JUDICIÁRIO - COMARCA DE VILA ESPERANÇA" e "Vara Criminal - Processo nº ...",
  rodapé "Fls. N" e código de autenticação; última folha de cada peça com "Documento assinado
  eletronicamente por NOME, CARGO, em dd/mm/aaaa."
- `render.py`: texto com `fitz.TextWriter` e fontes Nimbus Roman/Bold embutidas (Type0, Identity-H;
  reaproveitadas entre páginas).
- Testes: em toda folha nativa e na capa, `page.get_text()` é igual a `texto_camada` e começa com
  `texto` (igual quando não há marca d'água nem injeção); `get_text()[inicio:fim] == trecho` para
  todo evento em folha nativa; fontes embutidas (`ext != "n/a"`).

## Decisões não previstas

- `texto_camada` é lido do próprio PDF gerado; o teste prova que o texto montado pelo gerador
  (`texto`) é prefixo exato da camada.

## O que ficou de fora

- Leiaute em duas colunas (fica para o teste de ordem de leitura da 4C.5).

## Como rodar os testes

```bash
docker compose exec api bash scripts/verificar.sh
# só a 4B, no host:
.venv/Scripts/python -m pytest tests/sinteticos --confcutdir=tests/sinteticos -o addopts="" --cov=lupa.sinteticos
```

Saída resumida (host, venv): `93 passed`; cobertura de `lupa.sinteticos` 99% (1.235 instruções, 4 não
cobertas). `ruff check`, `ruff format --check` e `mypy --strict` limpos em `src/lupa/sinteticos` e
`tests/sinteticos`. Resultado do `verificar.sh` completo: ver RELATORIO-ETAPA-4B.10.md.
