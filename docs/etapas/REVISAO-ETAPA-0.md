# Revisão — Etapa 0 (esqueleto do projeto)

20 de outubro de 2026 · revisor

## 1. Verificação executada

Comando, dentro do contêiner `api` com a stack do compose no ar:

```
docker compose exec -T api bash scripts/verificar.sh
```

Saída resumida:

- ruff check e ruff format --check: sem avisos.
- mypy --strict: sem erros em 22 arquivos.
- pytest: 18 passaram, cobertura 100%.

Conferências diretas:

- `docker compose ps`: `api`, `db` e `minio` em estado `healthy`.
- `curl http://127.0.0.1:18000/saude`: 200 com `{"api":"ok","db":"ok","minio":"ok"}`.
- `docker compose exec api whoami`: `lupa`.
- `docker compose exec db whoami`: `root`.
- `docker compose exec minio id`: `uid=0(root)`.
- `docker manifest inspect minio/minio:latest` e `quay.io/minio/minio:latest`: ambos indisponíveis, confirmando o relato do executor.
- `requirements.txt`: 485 linhas com `--hash`.
- `.env` local difere do exemplo apenas na porta (18000).

## 2. Critérios de aceite

| Critério | Resultado | Evidência |
| --- | --- | --- |
| `docker compose up` sobe os três serviços saudáveis em menos de dois minutos | ok | `up --wait` em 12,8 s segundo o executor; `docker compose ps` confirma healthy. Não medido sem cache de imagens, o que é aceitável para o piloto. |
| `GET /saude` responde 200 com api, db e minio ok | ok | curl acima e teste de integração passando no contêiner |
| `scripts/verificar.sh` passa sem avisos de lint e sem erros de tipagem | ok | saída acima |
| Teste prova que o logger rejeita chave proibida | ok | `test_logger_rejeita_chave_proibida_em_modo_estrito`, parametrizado nos 7 campos |
| Teste prova que a aplicação não inicia sem variável obrigatória | ok | `test_aplicacao_nao_inicia_sem_variavel_obrigatoria`; `Settings` não lê arquivo `.env`, então o teste é real |
| Nenhuma imagem roda como root | **falhou** | `minio` roda como uid 0. `db` abre o shell como root; o processo do PostgreSQL em si roda como `postgres`, mas o critério pede o contêiner. Só `api` atende. |
| `.env` no `.gitignore` e `.env.example` sem valor real | ok | `.gitignore` cobre `.env` e `.env.*` com exceção do exemplo; valores do exemplo são fictícios |

## 3. Regras comuns

- Estilo, docstrings Google, tipagem estrita, testes nomeados por comportamento: atendidos.
- Contêineres com usuário não root: atendido só na `api` (ver critério acima).
- Segurança: nenhum segredo em código ou imagem; `.dockerignore` exclui `.env`, PDFs e DOCX. Logger rejeita campos sensíveis.
- Imagem de produção inclui `tests/` e `scripts/`: documentado pelo executor como decisão para o revisor; aceitável no piloto, a remover antes de produção.

## 4. Decisão

**Aprovado com correções obrigatórias antes do início das Etapas 1 e 2.**

Correções:

1. `db` e `minio` devem rodar sem root no compose. Para o PostgreSQL, definir `user` com o uid do usuário `postgres` da imagem alpine, garantindo que o volume nomeado continue gravável. Para o MinIO, definir `user` não root e garantir permissão no volume `/data`. Se alguma imagem não permitir isso sem quebrar, registrar a exceção no relatório com o motivo e deixar o critério como exceção aceita, não como ok.
2. Remover o `healthcheck` fictício `["CMD", "true"]` do serviço `minio-init`. Um serviço que termina não precisa de healthcheck, e `service_completed_successfully` já cobre a dependência.
3. Registrar no `README.md`, na seção de serviços, que a imagem do MinIO é um fork comunitário fixado por digest e que a escolha do object storage está em aberto (ver riscos abaixo).

## 4.1 Reverificação após as correções

Conferido pelo revisor com a stack recriada:

- `api`: uid 10001 (lupa). `db`: uid 70 (postgres). `minio`: uid 10002. Nenhum root.
- `GET /saude`: 200 com todos os componentes ok.
- `minio-init` sem healthcheck; dependência por `service_completed_successfully`.
- README registra o fork do MinIO e a decisão em aberto.

**Decisão final: aprovado.** Etapas 1 e 2 liberadas.

## 5. Riscos observados fora dos critérios

- **MinIO deixou de ser mantido.** As imagens oficiais sumiram do Docker Hub e do Quay, o repositório aparece como arquivado em 2026, e a última imagem publicada carrega CVE conhecida. O executor usou o fork `pgsty/minio` fixado por digest, que é uma escolha razoável de curto prazo, mas é dependência de terceiro sem garantia de manutenção. O código da aplicação só conversa com a API S3, então trocar o servidor é barato agora e caro depois. Decisão para o responsável técnico antes da Etapa 4 (ingestão), que é a primeira que grava objetos.
- **Portas 8000 e 8080 ocupadas na máquina do piloto.** Sem impacto no código; o `.env` local usa 18000.
- **Log de acesso do uvicorn fora do JSON.** Sem conteúdo sensível por ora; unificar quando houver rotas com dados.
- **Alembic não inicializado.** Correto, porque não há modelos. A Etapa 1 deve criar `alembic.ini` e a pasta de migrações.
