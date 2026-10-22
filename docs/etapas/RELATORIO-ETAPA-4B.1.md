# Relatório da Etapa 4B.1 — Esquema do gabarito

20 de outubro de 2026 · agente executor da 4B

## O que foi feito

- `src/lupa/sinteticos/gabarito.py`: esquema pydantic `Gabarito` versionado (`versao_esquema = "1"`),
  imutável e com `extra="forbid"`. Partes: `ProcessoGabarito` (número CNJ validado por
  `validar_numero_cnj`, matéria, `cenario`, `diagnostico_esperado`, semente, `data_referencia`),
  `PecaGabarito` (tipo em `TipoPeca`, origem em `OrigemPeca`, título, página inicial e final, data,
  `tipo_data`), `PaginaGabarito` (número, peça, tipo em `TipoPagina`, `composicao`, degradação, DPI,
  rotação, elementos, `texto` e `texto_camada`), `EventoGabarito` (tipo em `TipoFato`, valor, página,
  trecho, `inicio`/`fim`), `ResultadoEsperado` (validação, `conforme`/`atencao`/`verificar`, valores,
  explicação), `ArquivoGabarito` e `InjecaoGabarito`.
- Regras de consistência: folhas numeradas 1..N; peças contíguas, em ordem, sem sobreposição e
  cobrindo todas as folhas; cada folha pertence à peça indicada; `texto[inicio:fim] == trecho`;
  composição coerente com o tipo (nativa/capa → `nativa`; digitalizada/híbridas → `ocr`; vazia →
  `vazia`); degradação exigida só e sempre em folhas com imagem; vazia sem texto; digitalizada sem
  camada; arquivos cobrem cada folha uma vez; as três validações criminais presentes; diagnóstico
  coerente com o cenário.
- Teste: o gabarito gerado passa e faz ida e volta em JSON; 22 mutações (offset errado, peça com
  lacuna, CNJ inválido, tipo de fato desconhecido, validação faltando etc.) são rejeitadas.

## Decisões não previstas

- `TipoPagina` só tem `nativa`, `ocr` e `vazia`. Para registrar como a folha foi fabricada criei a
  enumeração local `Composicao` (nativa, digitalizada, hibrida_corpo, hibrida_assinatura, vazia,
  capa); `tipo` continua em `TipoPagina` e diz o que a pipeline deve concluir (híbrida → `ocr`).
- Folhas são numeradas pela folha de conteúdo (igual nos três cenários); a posição física em cada
  arquivo fica em `arquivos[].folhas` (com `null` para páginas de índice). Assim o conteúdo do
  gabarito é idêntico entre cenários.
- Dois textos por folha: `texto` (visível, alvo do OCR, base dos offsets) e `texto_camada`
  (exatamente o `get_text()`), porque marca d'água e injeções ocultas ficam só na camada.
- `resultado_esperado` é calculado pelo próprio motor do Lupa (`executar_catalogo`) a partir dos
  eventos do gabarito, com ids determinísticos (uuid5); `valores` guarda o que o motor devolveu.

## O que ficou de fora

- Nada do escopo.

## Como rodar os testes

```bash
docker compose exec api bash scripts/verificar.sh
# só a 4B, no host:
.venv/Scripts/python -m pytest tests/sinteticos --confcutdir=tests/sinteticos -o addopts="" --cov=lupa.sinteticos
```

Saída resumida (host, venv): `93 passed`; cobertura de `lupa.sinteticos` 99% (1.235 instruções, 4 não
cobertas). `ruff check`, `ruff format --check` e `mypy --strict` limpos em `src/lupa/sinteticos` e
`tests/sinteticos`. Resultado do `verificar.sh` completo: ver RELATORIO-ETAPA-4B.10.md.
