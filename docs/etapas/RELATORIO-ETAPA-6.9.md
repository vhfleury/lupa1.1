# Relatório da Etapa 6.9: tela de auditoria (com o item 5 da revisão 5)

## O que foi feito

- **Tela** `front/src/routes/auditoria/+page.svelte` e `front/src/lib/auditoria/auditoria.ts`:
  filtros (gabinete só para o admin, usuário, processo, ação, intervalo, IP) validados no
  cliente; tabela com paginação por cursor ("Carregar mais"); tempo da consulta exibido;
  exportação CSV e JSON por link de download do filtro aplicado; verificação da cadeia com
  resultado claro (íntegra com total, ou quebrada com o primeiro evento e o motivo); relatório de
  uso por processo ou por usuário (contagem por ação, primeiro/último acesso, versões de
  modelo/prompt, custo estimado), acionável também clicando no usuário/processo de um evento.
  Menu "Auditoria" só para quem tem `ver_auditoria`.
- **Item 5 da revisão 5**: `src/lupa/agente/dados/precos.yaml` (versão `2026-10-06`, fonte: tabela
  pública da API da Anthropic; `claude-opus-5-5` US$ 4 entrada / US$ 20 saída por milhão;
  também opus-5, sonnet-5-5, haiku-5-5; "Estimativa a confirmar na fatura"),
  `lupa/agente/precos.py` e `consulta.custo_estimado`, incluído em `GET /auditoria/relatorio-uso`
  (`custo_estimado`: total, moeda, versão e fonte da tabela, por modelo; modelo fora da tabela
  com custo nulo).
- Ações novas no filtro e no enum: `processo_em_revisao`, `revisao_liberada`.

## Desempenho

1 milhão de eventos sintéticos carregados no banco de desenvolvimento pelo gerador de
`tests/auditoria/test_carga.py` (via `scripts/e2e_semear_chat.py --carga`, 56 s, só na primeira
vez; 40 gabinetes "carga"). Medido pelo Playwright, do clique em "Consultar" até a tabela
renderizada, desembargador, 5 repetições: **140 a 180 ms, mediana 151 a 176 ms** (duas
execuções). Critério < 1 s: atendido.

## Critérios de aceite

- Desembargador vê só o próprio gabinete: E2E confere que todas as linhas têm o gabinete da
  sessão, que não há seletor de gabinete e que `GET /api/auditoria?gabinete_id=<outro>` dá 403.
- Admin vê todos: coberto pelos testes de API existentes (`tests/auditoria/test_consulta.py`). O
  E2E não loga como admin nesta suíte porque o `fluxos.spec.ts` faz o primeiro acesso do admin e
  a senha não é compartilhada entre arquivos.

## O que ficou de fora

- Seleção de usuário/processo por nome (a API de auditoria trabalha com ids).
- Custo dos resumos do dossiê não entra no relatório por usuário (não têm conversa).

## Testes

- Backend: `tests/auditoria/test_custo.py` (4).
- Front unitário: `src/lib/auditoria/auditoria.test.ts` (8, inclui o item do menu).
- E2E: 2 testes 6.9 em `front/e2e/testes/chat-auditoria.spec.ts` (escopo e tempo; filtros,
  paginação, exportação, verificação, relatório com custo). Passando.

## Verificação final

`docker compose exec api bash scripts/verificar.sh`: ruff, format e mypy limpos; **804 passed,
1 skipped**, cobertura **98,59%**; ponta a ponta da ingestão, regressão de injeção, carimbo do
front e suíte de injeção do agente (14 cenários, 0 vazamentos) passando.
`bash front/scripts/e2e.sh`: os 7 testes de `chat-auditoria.spec.ts` passando. Na mesma execução
falharam um teste de `fluxos.spec.ts` (passa isolado, 8/8) e um de `processos.spec.ts` (6.6, do
outro agente, em andamento).
