# Relatório da Etapa 5.1 — Contrato do agente

## O que foi feito

- `docs/agente.md` escrito antes do código: o que o agente pode (localizar, extrair, resumir,
  relacionar com citação) e não pode (valorar prova, tipificar, concluir sobre norma ou
  precedente, opinar sobre resultado, redigir ato, calcular prazo sem a ferramenta; AR2, AR3 e AR4
  do Anexo da Res. CNJ 615/2025), formato JSON da resposta (`texto`, `citacoes[]` com `pagina_id`,
  `trecho`, `hash_trecho`; esquema pydantic `RespostaModelo` com `extra="forbid"`), lista de
  ferramentas, política de recusa, limites (tokens por chamada, conversa e processo; páginas
  originais por conversa), auditoria, pseudonimização e a nota de arquitetura do SDK.
- `src/lupa/agente/cliente.py`: `Protocol` `ClienteAgente`, `ClienteSdk` (real, sobre o SDK) e
  `ClienteFalso` (roteirizado, grava tudo o que recebe). O resto de `lupa/agente/*` só conhece a
  interface; trocar pelo tool runner do SDK `anthropic` é outra implementação no mesmo arquivo.

### Documentação do SDK lida (21/10/2026)

- https://code.claude.com/docs/en/agent-sdk/overview, `/python`, `/custom-tools`, `/hooks`.
- Pacote: `claude-agent-sdk==0.2.170` (PyPI), que embute o Claude Code CLI `2.1.306`
  (`claude_agent_sdk/_bundled/claude`, ~290 MB; wheel manylinux de 125 MB). Exige `mcp>=1.23`.
- Assinaturas usadas: `query(*, prompt, options) -> AsyncIterator[Message]`;
  `ClaudeAgentOptions(tools=[], allowed_tools=[...], disallowed_tools=[...],
  permission_mode="dontAsk", system_prompt=str, model=str, mcp_servers={"lupa": servidor},
  strict_mcp_config=True, max_turns=int, setting_sources=[], agents={}, plugins=[], cwd=str,
  env={...}, hooks={"PreToolUse": [HookMatcher(matcher=None, hooks=[guarda])]})`;
  `SdkMcpTool(name, description, input_schema, handler)` e
  `create_sdk_mcp_server(name, version, tools)`; o handler devolve
  `{"content": [{"type": "text", "text": ...}]}`; o modelo vê `mcp__lupa__<nome>`; hook
  `async (input_data, tool_use_id, context)` devolvendo `{"hookSpecificOutput": {"hookEventName":
  "PreToolUse", "permissionDecision": "deny", ...}}`; mensagens `AssistantMessage(content, model,
  error, usage)`, `ResultMessage(subtype, is_error, usage, result, ...)`, `TextBlock`,
  `ToolUseBlock`; erros `ClaudeSDKError` (base), `ResultError`, `CLINotFoundError`,
  `ProcessError`.
- `tools=[]` remove todas as embutidas do contexto (documentado em custom-tools); reforçado por
  `disallowed_tools` com os nomes das embutidas, `permission_mode="dontAsk"`, `setting_sources=[]`
  (nada de `CLAUDE.md`, skills, hooks ou MCP do host), `strict_mcp_config`, `agents={}` (sem
  subagentes), `cwd` temporário vazio, `env` sem tráfego não essencial e o hook que nega qualquer
  ferramenta fora de `mcp__lupa__*` (a mesma `decidir_ferramenta` aplicada pelo cliente falso).
- Testes em `tests/agente/test_cliente.py`: opções montadas sem nenhuma embutida, hook nega `Read`,
  cliente falso nega `Read`/`Bash` e registra a tentativa; mensagens do SDK convertidas sem rede.

### Smoke do cliente real

`tests/agente/test_smoke_llm.py` (marcador `llm`, fora da suíte padrão). Rodado no host
(Windows, SDK 0.2.170): **pulado** — sem `ANTHROPIC_API_KEY` no ambiente e o binário do SDK
respondeu "Not logged in" (o login do aplicativo Claude da máquina não é visto pelo CLI embutido).
Dentro do contêiner não há credencial: pulado lá também. Para rodar, defina `ANTHROPIC_API_KEY`
no ambiente do host (nunca em arquivo) e use
`pytest -m llm --no-cov --noconftest tests/agente/test_smoke_llm.py`.

## Decisões não previstas

- O SDK exige `mcp>=1.23`, que exige `pydantic>=2.11`: `pydantic` passou de 2.10.4 para
  2.11.10 (`pydantic-core` 2.33.2) em `requirements.in`, `pyproject.toml` e nos `requirements*.txt`
  regenerados com `pip-compile --generate-hashes` num contêiner `python:3.12-slim` descartável
  (escrita pelo volume montado). Mudança em arquivo comum, registrada aqui; suíte inteira verde.
- O binário do Claude Code vem dentro do wheel: o `Dockerfile` não precisou mudar; a imagem da API
  cresce cerca de 300 MB.
- A documentação diz que terceiros não podem oferecer login do claude.ai em produtos feitos com o
  SDK: no piloto a credencial deve ser `ANTHROPIC_API_KEY` vinda de cofre.
- Marcadores novos no `pyproject.toml`: `agente` e `llm`; `addopts` passa a excluir `llm`.

## O que ficou de fora

- Aprovação formal do contrato pelo responsável técnico.

## Comandos e saída resumida

```
docker compose up -d --build --wait
docker compose exec api alembic -c src/lupa/migrations/alembic.ini upgrade head
docker compose exec api bash scripts/verificar.sh
```

```
== ruff check ==
All checks passed!
== ruff format --check ==
234 files already formatted
== mypy --strict ==
Success: no issues found in 234 source files
== pytest ==
test session starts
TOTAL                                                     9039    116    99%
Required test coverage of 90% reached. Total coverage: 98.72%
766 passed, 1 skipped, 3 deselected in 499.00s (0:08:19)
== ponta a ponta da ingestao (integracao, sem skip) ==
1 passed in 4.31s
== regressao de injecao (corpus 4B.8, metas da 4D.5, sem skip) ==
2 passed in 185.85s (0:03:05)
{'versoes': {'saneamento': '4d.1', 'homoglifos': '1', 'padroes_instrucao': '1', 'idiomas': '1', 'densidade': '1'}, 'recall': 1.0, 'falso_positivo': 0.0, 'injecoes_textuais': 16, 'injecoes_detectadas': 16, 'paginas_semente_01': 196}
== front ==
front: carimbo do build ok ad0b6d353349 2026-10-21T11:27:16.764Z
== suite de injecao do agente (Etapa 5.8, sem skip) ==
9 passed, 54 deselected in 50.07s
{'versao_modelo': 'cliente_falso_roteirizado', 'versao_prompt': '1:1c739e84a6337f5a', 'cenarios': 14, 'achados_suprimidos': 0, 'achados_criados': 0, 'vazamentos': 0, 'embutidas_executadas': 0, 'respostas_bloqueadas': 10}
```
