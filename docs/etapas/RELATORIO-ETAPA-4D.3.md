# Relatório da Etapa 4D.3 — Normalização Unicode

## O que foi feito

- `src/lupa/ingestao/saneamento.py`: `normalizar(texto) -> TextoNormalizado` com NFKC por aglomerado (base + marcas combinantes), remoção das categorias Cc, Cf, Co e Cs (inclui U+200B a U+200F, U+202A a U+202E, U+2066 a U+2069 e hífen suave), preservando `\n` e `\t`, e troca de homóglifos por `dados/homoglifos.yaml` (61 pares: cirílico, grego, armênio, latinos IPA; versão 1).
- `TextoNormalizado.para_original(inicio, fim)` converte qualquer intervalo do normalizado no intervalo do original; `substituir` mantém o mapa quando a 4D.4 troca blocos.
- Migração **0005** (`esquema_v0005.py`, `versions/v0005_saneamento.py`): `pagina.texto_normalizado` (TEXT), `pagina.trechos_ocultos` e `pagina.trechos_suspeitos` (JSONB `[]`), `diagnostico_arquivo.metadados_descartados` (JSONB `[]`). `pagina.texto` continua o original.
- `FlagPagina.HOMOGLIFOS` quando houve troca.

## Decisões não previstas

- O mapa de offsets não é gravado: `normalizar` é determinística para a mesma versão do YAML, então o mapa é recalculado a partir de `pagina.texto` quando preciso (`hash_trecho_normalizado`). Cada trecho suspeito já grava os offsets nos dois textos.
- NFKC aplicado por aglomerado, e não no texto inteiro, para que cada caractere normalizado aponte para um intervalo exato do original.

## Critério

| Critério | Evidência |
| --- | --- |
| Homóglifos viram ASCII no normalizado | regressão: `injecao_todos` p. 51 com `homoglifos` e nenhum cirílico no normalizado; `test_normalizar_troca_homoglifos_remove_controles_e_mapeia_offsets` (4 trocas, 2 controles removidos) |
| Evidência sobre o normalizado resolve para o original | `test_evidencia_sobre_o_normalizado_resolve_para_o_original_com_hash_do_dominio`: o trecho original volta com o cirílico e o hash é igual ao de `Evidencia` |
| Migração reversível | `tests/dominio/test_banco.py` (compare_metadata sem diferença; downgrade base e upgrade head) |

Na variante `injecao_homoglifos` isolada a folha é digitalizada e o OCR devolve letras latinas, então não sobra homóglifo; a instrução é pega pelo padrão (4D.5).

## Comandos e saída

```
docker compose up -d --build --wait
docker compose exec api bash scripts/verificar.sh
```

Saída resumida (21/10/2026): ruff e `ruff format --check` limpos; `mypy --strict` sem erros em 165 arquivos; pytest **588 passed, 1 skipped** (o skip é anterior à 4D; eram 551 testes), cobertura **98,66%**; ponta a ponta 1 passed; regressão de injeção 2 passed (159 s), `recall 1.0`, `falso_positivo 0.0`.
