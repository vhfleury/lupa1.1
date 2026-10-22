# Revisão — Etapa 4A (fundações da ingestão, subetapas 4A.2 a 4A.10)

21 de outubro de 2026 · revisor

## 1. Verificação executada

Com a stack reconstruída pelo executor (api, db, minio, redis, worker saudáveis; banco em `0003 (head)`):

```
docker compose exec -T api python -m pytest tests/ingestao --no-cov   -> 173 passaram
docker compose exec -T worker python -c "socket.create_connection(('1.1.1.1', 53))"
    -> OSError: Network is unreachable   (worker sem saída externa, confirmado)
docker compose exec -T api alembic current                            -> 0003 (head)
```

A verificação completa com `scripts/verificar.sh` relatada pelo executor (476 testes, cobertura 99%) será repetida pelo revisor na revisão da Etapa 4B, quando nenhum agente estiver reconstruindo a imagem.

Código lido: `sandbox.py`, `inventario.py`, `recepcao.py` (parcial), `docker-compose.yml`.

## 2. Critérios de saída por subetapa

| Subetapa | Resultado | Evidência |
| --- | --- | --- |
| 4A.2 esquemas e estados | ok | `estados.py` com `transicao()` pura; matriz de 64 pares testada; migração 0003 com RLS, política de admin e grants |
| 4A.3 fila e worker | ok | Redis e worker no compose sem porta no host; lease, heartbeat e fencing token na tabela; testes de morte do worker e de worker antigo que não grava |
| 4A.4 sandbox | ok | subprocesso com `python -I`, `RLIMIT_AS`, `RLIMIT_CPU`, `RLIMIT_FSIZE=0`, `RLIMIT_NOFILE`, ambiente sem `LUPA_*`, stderr descartado; PDF de 768 MB descomprimidos morto com limite de 512 MB e job `falho/limite_memoria`; rede do worker `internal: true` conferida |
| 4A.5 object storage | ok | interface com S3 (boto3) e memória; teste de contrato nas duas |
| 4A.6 recepção e lacre | ok | SHA-256 em stream, tipo por bytes mágicos, limite de tamanho, não duplica, evento `arquivo_enviado` |
| 4A.7 inventário de ZIP | ok | recusa `..`, absoluto, barra invertida, link simbólico, criptografia, entradas repetidas, razão de compressão, tamanho descomprimido contado nos bytes lidos |
| 4A.8 quarentena | ok | estado final com motivo enumerado |
| 4A.9 observabilidade | ok | `GET /metricas` só para admin; teste de sentinela prova que log do worker não carrega texto de autos |
| 4A.10 ponta a ponta | ok | PDF e ZIP até `validado` passando por API, MinIO, Redis e worker; no `verificar.sh` |

## 3. Decisões do executor endossadas

- Upload como corpo binário com nome em query, sem multipart, para não adicionar dependência. Adequado à API; a interface da Etapa 6 envia assim.
- Processo sigiloso recebe 403 na ingestão: cumpre a regra da primeira versão (só processos públicos).
- Migrações 0001 e 0002 passaram a importar uma tupla congelada com os nomes originais, para que `TABELAS_COM_GABINETE` possa crescer sem reescrever SQL antigo. Correto.
- `requirements` regenerados dentro do contêiner. Resolve a divergência Windows/Linux apontada na revisão da Etapa 3.

## 4. Decisão

**Aprovado.** Etapa 4C liberada assim que a 4B for aprovada.

## 5. Itens para etapas seguintes

1. `scripts/verificar.ps1` não recebeu o passo ponta a ponta. Corrigir na 4C.
2. Jobs `falho` não são retentados automaticamente; `processo.status` não é atualizado. A 4C define a política de retry por motivo e atualiza o status do processo ao concluir.
3. Assinatura digital conferida só pela estrutura (`/ByteRange`), sem validação criptográfica. Registrado como limitação; entra na Etapa 7 ou fica documentado como fora de escopo.
4. O subprocesso do parser compartilha a rede interna do worker (sem credenciais, sem sockets abertos pelo filho). Aceitável no piloto, porque a rede não tem saída; se o worker um dia ganhar rota externa, o sandbox precisa de namespace de rede próprio.
5. Fixture autouse em `tests/conftest.py` remove `LUPA_DB_USUARIO_APP` do ambiente de testes, então a suíte roda como dono das tabelas, exceto os testes dedicados ao usuário restrito. Aceitável, mas a Etapa 6 deve ter ao menos um fluxo ponta a ponta sob o usuário restrito.
6. 57 avisos de depreciação vindos do `pymupdf` (swig). Filtrar no `pyproject.toml` para manter a saída do pytest limpa.
