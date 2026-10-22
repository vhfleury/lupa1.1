# Revisão — Etapa 3 (autenticação, papéis e auditoria)

20 de outubro de 2026 · revisor

## 1. Verificação executada

Imagem reconstruída do zero e verificação completa, cobrindo também as Etapas 1, 2 e 4A.1 que ainda não tinham passado pelo `verificar.sh` com rebuild:

```
docker compose up -d --build --wait
docker compose exec -T api bash scripts/verificar.sh
```

Resultado: ruff sem avisos, mypy sem erros em 87 arquivos, 210 testes passaram, 1 pulado, 1 desmarcado (carga), cobertura 98,68%.

Teste de carga reproduzido pelo revisor: `pytest -m carga`, 1 milhão de eventos carregados em 71,7 s, consulta por usuário e intervalo com mediana de 3,2 ms e máximo de 16,6 ms. Meta de 200 ms atendida com folga.

Configuração do usuário de banco sem superusuário feita no ambiente de desenvolvimento: variáveis `LUPA_DB_USUARIO_APP` e `LUPA_DB_SENHA_APP` adicionadas ao `.env` local (valores fictícios), `scripts/criar_usuario_banco.py` executado, API reiniciada. `pg_roles` confirma `lupa_api` e `lupa_app` sem superusuário e sem BYPASSRLS. `POST /auth/login` com usuário inexistente responde 401, provando que a API opera sob o papel restrito.

## 2. Critérios de aceite

Todos os quatorze critérios do plano têm teste nomeado e passando; a tabela do `RELATORIO-ETAPA-3.md`, seção 8, foi conferida contra a lista de testes. Destaques verificados no código:

- Login em dois passos com desafio em tabela; sessão só nasce após o TOTP (`servico.py`, `sessoes.py`).
- Token de sessão de 256 bits; o banco guarda só o SHA-256 (`sessoes.py`).
- TOTP com janela de um passo e recusa de passo igual ou anterior ao último aceito (`mfa.py`).
- Argon2id com parâmetros fixos no código e `precisa_rehash` (`senhas.py`).
- Matriz de permissões como dados em `papeis.py`; nenhum `if` de papel espalhado; `exige_processo` responde 404 e registra a tentativa.
- Cadeia de auditoria por gabinete e cadeia global, com `sequencia` única, advisory lock e `FOR UPDATE` na função `lupa_travar_cadeia`; `UPDATE`, `DELETE` e `TRUNCATE` bloqueados por trigger e revogados do papel da aplicação.

## 3. Os cinco pontos herdados da Etapa 1

| Ponto | Solução | Avaliação |
| --- | --- | --- |
| Login sob RLS | Função `lupa_localizar_usuario` com SECURITY DEFINER devolvendo só id, gabinete e papel | Correta e mínima; `search_path` fixado |
| Administrador | Variável `lupa.papel` e política `_administrador` em todas as tabelas com RLS | Correta; o contexto é definido pela sessão, não pelo cliente |
| Eventos globais | Política de inserção sem gabinete e trava via SECURITY DEFINER | Correta |
| Membership do papel | `scripts/criar_usuario_banco.py` cria usuário com login, sem superusuário, membro de `lupa_app` | Correta; executada e conferida |
| Grants para tabelas novas | Grant explícito mais `ALTER DEFAULT PRIVILEGES` | Correta |

## 4. Incidente registrado pelo executor

Às 19:59 o executor copiou `src/lupa` e `tests` do contêiner para o host para rodar o formatador, sobrescrevendo por cerca de dois minutos arquivos que o agente da subetapa 4A.1 editava no host. O agente da 4A.1 percebeu e reaplicou suas edições; o estado final foi conferido nesta verificação completa. Lição para as próximas etapas: nenhum agente copia do contêiner para o host. O fluxo é host → contêiner, sempre.

## 5. Decisão

**Aprovado.** Etapas 4A (restante) e 4B liberadas.

## 6. Correções obrigatórias antes do piloto (não bloqueiam a próxima etapa)

1. **Auditoria automática gravada depois da resposta.** `auditoria_middleware` registra `processo_aberto`, `pagina_vista` e `busca` em sessão própria após `call_next`. Se essa gravação falhar, o usuário já recebeu o conteúdo e não há evento. Para o requisito "tudo tem que estar salvo em logs", o evento precisa ser gravado na transação da requisição antes da resposta, ou a falha de gravação precisa negar a resposta. Entra como item da Etapa 6 quando as rotas de conteúdo forem construídas, com teste que simula falha de gravação.
2. **Bloqueio de login por nome permite negação de serviço.** Cinco tentativas erradas contra um nome bloqueiam o usuário legítimo por 15 minutos, e o desbloqueio é manual. Sem e-mail, isso vira chamado ao desembargador. Mitigação a implementar: rate limit por IP além do por nome, e bloqueio progressivo em vez de fixo. Registrado pelo executor como fora de escopo; fica para a Etapa 6.10 (segurança do front) ou antes.

## 7. Pendências para Victor

- **GeoLite2.** A localização aproximada por IP depende da base da MaxMind, que exige conta gratuita e aceite de licença. Sem ela o campo fica `desconhecida`. O README explica como obter e onde colocar.
- **Variáveis de produção.** `LUPA_DB_USUARIO_APP`, `LUPA_DB_SENHA_APP`, `LUPA_ADMIN_USUARIO` e `LUPA_ADMIN_SENHA` precisam de valores reais no ambiente do piloto; no dev já estão configuradas com valores fictícios.
- **Dependências transitivas.** `geoip2` trouxe `aiohttp` e `requests`. Aceitável, mas aumenta a superfície; vale reavaliar na Etapa 7 se a resolução por arquivo `.mmdb` pode usar só `maxminddb`.

## 8. Observações menores

- Rota `GET /processos/{id}` criada como mínimo para os testes de 404 e de acesso do admin; será substituída pelas rotas reais da Etapa 6.
- QR code do MFA sai como URI `otpauth://`; a interface desenha. Correto para a API.
- `requirements*.txt` regenerados no Linux; o executor reinseriu `tzdata` e `colorama` para manter instalação no Windows. Conferir na Etapa 4A se o `pip-compile` passa a rodar sempre no contêiner, para evitar esse vaivém.
