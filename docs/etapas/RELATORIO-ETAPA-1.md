# Relatório — Etapa 1 (esquemas de dados)

## O que foi feito

| Arquivo | Conteúdo |
| --- | --- |
| `src/lupa/dominio/enums.py` | Enums com docstring por valor: matéria, status do processo, tipo/método/origem de peça, tipo e flags de página, tipo e status de fato, resultado de achado, papel de usuário |
| `src/lupa/dominio/cnj.py` | Validação do número CNJ (formato + dígito verificador módulo 97) |
| `src/lupa/dominio/esquemas.py` | Esquemas pydantic de todas as entidades (imutáveis, `extra="forbid"`). **Contrato com a Etapa 2:** `from lupa.dominio.esquemas import Fato, Evidencia` |
| `src/lupa/dominio/tabelas.py` | Tabelas SQLAlchemy 2.0 com índices, CHECKs e FKs compostas |
| `src/lupa/dominio/sessao.py` | `definir_gabinete` (`set_config('lupa.gabinete_id', ..., true)`) e `assumir_papel_aplicacao` (`SET LOCAL ROLE lupa_app`) |
| `src/lupa/dominio/repositorios.py` | `salvar_fato`, `listar_fatos_por_processo`, `salvar_achado`, `listar_achados` |
| `src/lupa/migrations/` | Alembic: `alembic.ini`, `env.py`, `ambiente.py`, `esquema_v0001.py` (migração escrita à mão), `versions/v0001_inicial.py` |
| `alembic.ini` (raiz) | Atalho para uso fora do contêiner |
| `tests/conftest.py` | Fixtures novas: `engine_teste` (database efêmero migrado), `sessao` (rollback ao fim), `fabrica_processo`, `processo_id`, `pagina_id`, `fabrica_fato`, `gerar_numero_cnj`, `criar_pagina`, `migrar`. As fixtures da Etapa 0 ficaram intactas |
| `tests/dominio/test_esquemas.py` | 15 testes sem banco |
| `tests/dominio/test_banco.py` | 13 testes `integracao` contra PostgreSQL real |
| `docs/modelo-de-dados.md` | Diagrama Mermaid, regras impostas pelo banco, RLS e como a API define a variável |

Campos de `Fato` e `Evidencia` seguem exatamente a tabela do plano. Facilidades para quem consome:
`id` e `criado_em` têm valor padrão; `Evidencia.hash_trecho` é calculado se omitido e conferido se
informado; `Fato.evidencias` é `tuple[Evidencia, ...]` com `min_length=1`; `Fato.valor` é `Any`
(gravado como JSONB via `model_dump(mode="json")`, então datas voltam do banco como string ISO).

## Decisões não previstas no plano

1. **Organização (tarefa 1):** um módulo `esquemas.py` (pydantic) e um `tabelas.py` (SQLAlchemy) para
   todas as entidades, em vez de um submódulo por entidade. Motivo: as entidades se referenciam muito
   (FKs, enums) e um ponto único de import evita ciclos e dá à Etapa 2 um único lugar de import.
2. **`gabinete_id` desnormalizado** em todas as tabelas que pertencem a um gabinete (arquivo, pagina,
   peca, evidencia, fato, fato_evidencia, reu, reu_identidade, achado, anotacao), para a RLS filtrar
   sem junções. Consistência garantida por FKs compostas `(x_id, gabinete_id)`. Os esquemas pydantic
   **não** têm esse campo (ficam iguais ao plano); o repositório o obtém do processo.
3. **Tabela de associação `fato_evidencia`** (N:N): uma evidência pode sustentar mais de um fato.
4. **"Fato sem evidência" no banco** é um `CONSTRAINT TRIGGER ... DEFERRABLE INITIALLY DEFERRED`
   (o fato precisa ser inserido antes das associações). Também é recusado apagar a última associação.
5. **Enums como `text` + `CHECK`**, não `ENUM` nativo do PostgreSQL, para estender sem `ALTER TYPE`.
6. **Papel `lupa_app` (NOLOGIN)** criado pela migração: superusuários ignoram RLS, então a aplicação
   (e os testes de RLS) operam sob esse papel. `FORCE ROW LEVEL SECURITY` também ligado. O
   `downgrade` não remove o papel (é global ao cluster).
7. **`arquivo` também é imutável** (mesmo trigger do achado), já que o plano o declara imutável.
8. **Local das migrações:** `src/lupa/migrations/` (e não `migrations/` na raiz), porque o
   `Dockerfile` da Etapa 0 só copia `src`, `tests` e `scripts`; assim a migração vai na imagem sem
   alterar o `Dockerfile`. Comando: `alembic -c src/lupa/migrations/alembic.ini upgrade head`.
9. **Migração dividida em dois arquivos:** o conteúdo está em `lupa.migrations.esquema_v0001` e
   `versions/v0001_inicial.py` só reexporta `upgrade`/`downgrade`. Motivo: o Alembic carrega os
   arquivos de revisão por caminho com nome de módulo fora de `lupa`, e o `--cov=lupa` não os mede;
   com a lógica em módulo do pacote, a migração entra na cobertura (100%). O teste
   `test_migracao_coincide_com_tabelas` compara banco migrado × `tabelas.py` com
   `alembic.autogenerate.compare_metadata` (diferença vazia).
10. **Banco de teste:** em vez de um compose de teste separado, a fixture `engine_teste` cria um
    database `lupa_teste_<pid>` no serviço `db` existente, aplica `upgrade head`, e o apaga no fim.
    O sufixo pelo PID evita colisão com execuções paralelas (por exemplo, da Etapa 2).
    `docker-compose.yml` não foi alterado.
11. Validações extras no pydantic: `Pagina.hash_texto` = sha256(texto), `Anotacao` com exatamente um
    alvo, só administrador sem gabinete, `confianca` em [0, 1], `Arquivo.sha256` hexadecimal.

## O que ficou de fora e por quê

- Lógica de administrador multi-gabinete na RLS (gabinete nulo): é tema da Etapa 3; hoje o
  administrador não vê nada sob `lupa_app`. `usuario` e `evento_auditoria` já têm RLS pela mesma
  política.
- A dependência FastAPI que abre transação e chama `definir_gabinete` por requisição: depende da
  autenticação (Etapa 3). O procedimento está documentado em `docs/modelo-de-dados.md`.
- Cifra de `reu_identidade` e chave por gabinete: só a referência (`gabinete.chave_criptografia_ref`).
- Nenhuma dependência nova foi necessária.

## Arquivos de outras etapas alterados

Só `tests/conftest.py` (acréscimos; nada removido). `pyproject.toml`, `Dockerfile`,
`docker-compose.yml` e arquivos da Etapa 2 não foram tocados.

**Atenção para a revisão:** a imagem `api` copia o código no build. Durante o trabalho os arquivos
foram copiados para o contêiner em execução com `docker compose cp`; para verificar do zero, rode
`docker compose up -d --build --wait` antes do script.

## Comandos e saída resumida

```text
$ docker compose exec api bash scripts/verificar.sh
== ruff check ==
All checks passed!
== ruff format --check ==
37 files already formatted
== mypy --strict ==
Success: no issues found in 37 source files
== pytest ==
tests/api/test_saude.py ......
tests/dominio/test_banco.py .............
tests/dominio/test_esquemas.py ...............
tests/unit/test_config.py ...
tests/unit/test_logging.py .........
src/lupa/migrations/ambiente.py         72%   (ramo sem conexão: exercido pela CLI)
src/lupa/migrations/env.py               0%   (carregado pelo Alembic fora do pacote)
src/lupa/migrations/versions/v0001_inicial.py  0%  (idem; só reexporta)
demais módulos de lupa/dominio e migrations/esquema_v0001.py: 100%
TOTAL 98%  — Required test coverage of 90% reached. Total coverage: 98.05%
46 passed
```

(Também no host, sobre todo `src tests`, inclusive os arquivos da Etapa 2 existentes no momento:
`ruff check` ok e `mypy` "no issues found in 55 source files".)

```text
$ docker compose exec api alembic -c src/lupa/migrations/alembic.ini upgrade head
$ docker compose exec db psql -U lupa -d lupa -Atc "select count(*) from pg_tables where schemaname='public'"
15      # 14 tabelas + alembic_version
$ docker compose exec api alembic -c src/lupa/migrations/alembic.ini downgrade base
$ (mesma consulta)
1       # só alembic_version
$ docker compose exec api alembic -c src/lupa/migrations/alembic.ini upgrade head
$ docker compose exec api alembic -c src/lupa/migrations/alembic.ini current
0001 (head)
```

O banco `lupa` do compose ficou em `0001 (head)`.

## Critérios de aceite

| Critério | Situação | Evidência |
| --- | --- | --- |
| `Fato` sem evidência rejeitado pelo pydantic e pelo banco | ok | `test_fato_sem_evidencia_e_rejeitado_pelo_pydantic`; `test_fato_sem_evidencia_e_rejeitado_pelo_banco`; `test_remover_ultima_evidencia_de_fato_e_rejeitado_pelo_banco` |
| CNJ com dígito errado rejeitado | ok | `test_numero_cnj_com_digito_errado_e_rejeitado`; `test_processo_com_cnj_de_digito_errado_e_rejeitado_pelo_pydantic` |
| RLS: com `lupa.gabinete_id` = A, nada de B | ok | `test_rls_isola_gabinetes`; também `test_rls_sem_gabinete_definido_nao_mostra_nada`, `test_rls_impede_gravar_em_outro_gabinete`, `test_rls_ativa_em_todas_as_tabelas_com_gabinete` |
| `Achado` não pode ser atualizado | ok | `test_achado_nao_pode_ser_atualizado` (trigger `achado_imutavel`) |
| `upgrade head` cria tudo; `downgrade base` remove | ok | `test_downgrade_base_remove_e_upgrade_head_recria` e a execução da CLI acima (15 → 1 → 15 tabelas) |
| Diagrama Mermaid coerente com o código | ok | `docs/modelo-de-dados.md`; coerência migração × tabelas em `test_migracao_coincide_com_tabelas` |
| Nome real só em `ReuIdentidade` e `Usuario` | ok | `test_nome_real_so_existe_em_reu_identidade_e_usuario` (`gabinete.nome` é nome de órgão) |
