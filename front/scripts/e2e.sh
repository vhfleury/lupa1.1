#!/usr/bin/env bash
# Roda os testes ponta a ponta do front (Playwright) contra a stack real do compose.
# 1. sobe a stack; 2. prepara o admin (senha temporaria gerada agora, so em memoria);
# 3. roda `npm run e2e` no conteiner `e2e`, que fala com o proxy em https://proxy:8443.
# 4. (6.10) ao terminar, mesmo em falha ou Ctrl+C, recria o servico `api` sem o cliente falso.
set -euo pipefail
cd "$(dirname "$0")/../.."

restaurar_api() {
  local codigo=$?
  trap - EXIT INT TERM
  echo "e2e: recriando a api sem LUPA_AGENTE_CLIENTE=falso" >&2
  env -u LUPA_AGENTE_CLIENTE -u LUPA_E2E_ADMIN_SENHA -u LUPA_E2E_PROC_SENHA -u LUPA_E2E_CHAT_SENHA \
    docker compose up -d --no-deps --force-recreate --wait api >&2 || codigo=1
  exit "$codigo"
}
trap restaurar_api EXIT
trap 'exit 130' INT TERM

# Etapa 6.8: a API do E2E usa o modelo falso roteirizado (sem chave, sem rede); recusado em producao.
export LUPA_AGENTE_CLIENTE=falso
docker compose up -d --build --wait
# 6.10: o Caddyfile entra por bind mount de arquivo; recriar o proxy garante os cabecalhos atuais.
docker compose up -d --no-deps --force-recreate --wait proxy
credenciais="$(docker compose exec -T api python scripts/e2e_preparar.py)"
LUPA_E2E_ADMIN_USUARIO="$(printf '%s\n' "$credenciais" | sed -n 1p)"
LUPA_E2E_ADMIN_SENHA="$(printf '%s\n' "$credenciais" | sed -n 2p)"
export LUPA_E2E_ADMIN_USUARIO LUPA_E2E_ADMIN_SENHA
# Etapas 6.4 a 6.7: gabinete, assessor e processo sinteticos (autos enfileirados no worker real).
processos="$(docker compose exec -T api python scripts/e2e_processos.py)"
LUPA_E2E_PROC_USUARIO="$(printf '%s\n' "$processos" | sed -n 1p)"
LUPA_E2E_PROC_SENHA="$(printf '%s\n' "$processos" | sed -n 2p)"
LUPA_E2E_PROC_ID="$(printf '%s\n' "$processos" | sed -n 3p)"
export LUPA_E2E_PROC_USUARIO LUPA_E2E_PROC_SENHA LUPA_E2E_PROC_ID
# Etapas 6.8 a 6.10: desembargador, processo do chat e processo com texto hostil (6.10); 1 milhao
# de eventos de carga na auditoria (so na primeira vez).
chat="$(docker compose exec -T api python scripts/e2e_semear_chat.py --carga)"
LUPA_E2E_CHAT_USUARIO="$(printf '%s\n' "$chat" | sed -n 1p)"
LUPA_E2E_CHAT_SENHA="$(printf '%s\n' "$chat" | sed -n 2p)"
LUPA_E2E_CHAT_PROCESSO="$(printf '%s\n' "$chat" | sed -n 3p)"
LUPA_E2E_HOSTIL_PROCESSO="$(printf '%s\n' "$chat" | sed -n 4p)"
export LUPA_E2E_CHAT_USUARIO LUPA_E2E_CHAT_SENHA LUPA_E2E_CHAT_PROCESSO LUPA_E2E_HOSTIL_PROCESSO
docker compose --profile e2e build e2e
docker compose --profile e2e run --rm e2e "$@"
