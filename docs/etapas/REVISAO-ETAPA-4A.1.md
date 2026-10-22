# Revisão — Subetapa 4A.1 (adaptador validações ↔ domínio)

20 de outubro de 2026 · revisor

## Verificação executada

Arquivos copiados para o contêiner `api` (Etapa 3 ainda em execução, sem rebuild) e, dentro dele:

```
ruff check src/lupa/validacoes tests/validacoes      -> sem avisos
mypy src/lupa/validacoes tests/validacoes            -> sem erros em 21 arquivos
pytest tests/validacoes --no-cov                     -> 74 passaram, 1 pulado (comparação com docs/, ausente na imagem)
python -m lupa.validacoes --fatos ... --referencia 2026-10-20 -> 3 achados, todos conforme
```

O teste de ida e volta pelo banco (`test_ida_e_volta_pelo_banco`) rodou contra o PostgreSQL do compose e passou.

## Critério de aceite

| Critério | Resultado | Evidência |
| --- | --- | --- |
| Ida e volta com `fabrica_fato` passa; `executar_catalogo` roda sobre fatos lidos do banco | ok | `tests/validacoes/test_adaptador.py::test_ida_e_volta_pelo_banco` |

## Decisão do executor endossada

Opção (a): as validações consomem `lupa.dominio.esquemas.Fato` e `Evidencia` diretamente; os esquemas locais foram removidos de `modelo.py`. Sobrou `AchadoValidacao`, que não é cópia do `Achado` do domínio: não tem id, processo nem data, porque o motor não conhece o processo. `para_dominio` faz a vinculação. É a separação certa.

`data_de` aceita string ISO e `date`, e recusa `datetime` para não descartar a hora em silêncio. Correto.

## Decisão

**Aprovado.**

## Observações

- O `.venv` do host está sem `pyotp`, `argon2-cffi` e `geoip2`, que a Etapa 3 adicionou. O `verificar.sh` no host só volta a passar quando a Etapa 3 instalar as dependências no venv ou quando o revisor reinstalar. Dentro do contêiner, após rebuild, não há esse problema.
- O executor relatou edições que "não ficaram gravadas" durante o trabalho e precisaram ser reaplicadas. O estado final foi conferido aqui. Causa provável: sincronização do OneDrive sobre a pasta do projeto enquanto dois agentes escrevem. Vale considerar mover o repositório para fora do OneDrive antes das etapas com muitos arquivos (4B gera PDFs grandes).
