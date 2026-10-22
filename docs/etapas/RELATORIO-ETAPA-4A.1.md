# Relatório — Etapa 4A.1 (adaptador validações ↔ domínio)

## Decisão: (a), com um resultado intermediário

As validações passam a consumir **diretamente** `lupa.dominio.esquemas.Fato`/`Evidencia` (ids
`UUID`, `tipo` como `TipoFato`, `evidencias` em tupla). Os esquemas locais `Fato`, `Evidencia`
e `Achado` de `modelo.py` foram removidos; `modelo.py` reexporta `Fato`/`Evidencia` do domínio.

Por quê: a lógica das validações não mudou, só tipos. `TipoFato` é `StrEnum`, então os índices
por tipo e as comparações com strings continuam funcionando; `UUID` é ordenável, então a ordem
determinística por id continua.

A saída do motor não pode ser o `Achado` do domínio diretamente, porque ele exige
`processo_id` e o motor não conhece o processo. Por isso há `AchadoValidacao` (sem `id`,
`processo_id`, `criado_em`; `resultado` usa o enum do domínio; `fatos_usados: tuple[UUID, ...]`).
Não é cópia do esquema do domínio: `para_dominio` o vincula ao processo.

## O que mudou

- `src/lupa/validacoes/adaptador.py` (novo): `para_modelo(fatos) -> ModeloProcesso` e
  `para_dominio(achado_validacao, processo_id) -> dominio.Achado`. Importa só `esquemas`.
- `modelo.py`: sem esquemas duplicados; `AchadoValidacao`; `ResultadoAchado` passou a ser apenas
  o alias `Literal` usado nas validações; `ConflitoDeFatosError.fato_ids` em string.
- `apoio.py`: `data_de` aceita string ISO (banco/JSONB) e `date` (código Python); `datetime` é
  recusado. `rastrear` grava `fato_id`, `evidencia_id(s)` e `tipo` como string; `criar_achado`
  devolve `fatos_usados` como tupla ordenada de `UUID`.
- `prescricao.py`, `tempestividade.py`: ids e tipo em `valores` como string (JSON serializável).
- `Achado` → `AchadoValidacao` em `catalogo.py`, `motor.py` e validações.
- CLI `python -m lupa.validacoes`: lê `list[dominio.Fato]` e usa `para_modelo`.
- `docs/exemplos/fatos.json` e `tests/validacoes/fatos_exemplo.json` (idênticos): ids UUID (uuid5
  determinístico), `hash_trecho` omitido.
- `tests/validacoes/conftest.py`: `criar_fato` produz `dominio.Fato` (ids via `id_sintetico`).
- `tests/validacoes/test_motor_e_regras.py`: teste de AST permite só `lupa.dominio.esquemas` e
  `lupa.dominio.enums`.
- `tests/validacoes/test_adaptador.py` (novo): `data_de` com str e `date`; `para_dominio` puro;
  ida e volta pelo banco (`integracao`) com `fabrica_fato`, `criar_pagina`, `salvar_fato`,
  `listar_fatos_por_processo`, `para_modelo`, `executar_catalogo`, `para_dominio`,
  `salvar_achado`, `listar_achados`, comparando o achado salvo e o lido (exceto `criado_em`).
- `docs/validacoes.md`: formato de entrada atualizado.

## Comandos e saída

- Host: `PYTHON=.venv/Scripts/python bash scripts/verificar.sh` → ruff check OK, ruff format OK;
  mypy acusa 18 erros, **todos fora do escopo** (`pyotp`, `argon2`, `geoip2` ausentes do `.venv`
  do host, usados por `acesso`/`auditoria`/`tests/conftest.py` da Etapa 3). `mypy --strict
  src/lupa/validacoes tests/validacoes` → só os 2 erros de `tests/conftest.py` (pyotp). No host
  o pytest não carrega por falta de `pyotp` no `.venv`.
- Contêiner (sem rebuild): `docker compose cp src/lupa/validacoes api:/app/src/lupa/`,
  `docker compose cp tests/validacoes api:/app/tests/`,
  `docker compose exec api python -m pytest tests/validacoes --no-cov` → **74 passed, 1 skipped**
  (skip: comparação com `docs/`, que não existe na imagem; no host os arquivos são idênticos).
  `test_ida_e_volta_pelo_banco` PASSED contra o PostgreSQL do compose.
- CLI no host com `docs/exemplos/fatos.json` → 3 achados.

## Critério de aceite

- [x] Ida e volta com `fabrica_fato` passa (contêiner, banco real).
- [x] `executar_catalogo` roda sobre fatos lidos do banco (`listar_fatos_por_processo`).
- [x] `modelo.py` sem cópias dos esquemas do domínio.
- [x] `valores` serializável em JSON; `fatos_usados` como `tuple[UUID, ...]`.
- [x] Validações importam do domínio só `esquemas`/`enums` (teste de AST).

## Pendência

- O `.venv` do host precisa das dependências da Etapa 3 (`pyotp`, `argon2-cffi`, `geoip2`) para o
  `verificar.sh` passar inteiro no host; não instalado aqui (restrição de dependências).
