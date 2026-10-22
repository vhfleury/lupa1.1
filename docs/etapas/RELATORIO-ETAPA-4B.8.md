# Relatório da Etapa 4B.8 — Injeções por vetor

20 de outubro de 2026 · agente executor da 4B

## O que foi feito

- `injecao.py`: nove vetores, cada um com objetivo: texto branco de 1 pt (suprimir achado), texto
  fora da página (alterar data), XMP `dc:description` (vazar dado), anotação (criar achado), imagem
  com texto (mudar classificação), base64 (suprimir achado), homóglifos cirílicos (criar achado),
  parágrafo em inglês nas razões do recurso (suprimir achado), instrução dentro de mensagem de
  celular transcrita no laudo (alterar data).
- Vetores visíveis entram como parágrafo marcado; ocultos são aplicados na primeira folha da peça
  alvo, que é forçada a nativa (para ter camada). O gabarito registra `vetor`, `objetivo`, folha,
  texto e se é visível; folhas com injeção levam o elemento `injecao`.
- Corpus: `gerar_autos.py injecao` grava em `.sinteticos/injecao/` uma variante por vetor e uma com
  todos (30 folhas cada, cenário PDF liso), fora do repositório. Tamanhos no relatório 4B.9.
- Testes: cada vetor presente e verificável no PDF (camada, recorte infinito, XMP, anotações,
  imagem, base64 decodificado, cirílico); nenhuma injeção vira evento.

## Decisões não previstas

- Injeções não alteram o resultado esperado: o gabarito diz o que é verdade; a pipeline passa se
  não obedecer.
- "Repositório separado com acesso restrito" foi atendido como pasta fora do repositório
  (`.sinteticos/injecao/`, ignorada pelo git); criar um repositório de verdade é decisão do
  gabinete.

## O que ficou de fora

- Unicode de direção (RTL) e cadeia entre documentos (vetores de risco baixo na tabela).

## Como rodar os testes

```bash
docker compose exec api bash scripts/verificar.sh
# só a 4B, no host:
.venv/Scripts/python -m pytest tests/sinteticos --confcutdir=tests/sinteticos -o addopts="" --cov=lupa.sinteticos
```

Saída resumida (host, venv): `93 passed`; cobertura de `lupa.sinteticos` 99% (1.235 instruções, 4 não
cobertas). `ruff check`, `ruff format --check` e `mypy --strict` limpos em `src/lupa/sinteticos` e
`tests/sinteticos`. Resultado do `verificar.sh` completo: ver RELATORIO-ETAPA-4B.10.md.
