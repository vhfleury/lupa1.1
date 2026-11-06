#!/usr/bin/env bash
# Roda os testes ponta a ponta do front (Playwright) contra a stack real do compose.
# O preparo (stack, contas sinteticas, restauracao da api ao sair) fica em preparar-e2e.sh.
# Uso: bash front/scripts/e2e.sh [argumentos do playwright]
set -euo pipefail
source "$(dirname "$0")/preparar-e2e.sh"

preparar_e2e
docker compose --profile e2e run --rm e2e "$@"
