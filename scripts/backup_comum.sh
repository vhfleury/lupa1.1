#!/usr/bin/env bash
# Funcao comum aos scripts de backup do host (Etapa 7.8): roda backup_conteiner.sh no servico
# `backup` (perfil `backup`) do compose. Variaveis LUPA_BACKUP_* e LUPA_RESTAURAR_* do ambiente
# do host passam ao conteiner; nada e gravado em claro no host.
set -euo pipefail
cd "$(dirname "$0")/.."
# Git Bash no Windows: nao converter /scripts/... em caminho do Windows.
export MSYS_NO_PATHCONV=1
backup_executar() {
  local pasta
  for pasta in "${LUPA_BACKUP_DIR:-./.backups}" "${LUPA_BACKUP_CHAVES_DIR:-./.backup-chaves}"; do
    mkdir -p "$pasta"
    chmod 700 "$pasta" 2>/dev/null || true
  done
  docker compose --profile backup run --rm -T \
    -e LUPA_BACKUP_BANCO -e LUPA_BACKUP_BUCKET -e LUPA_BACKUP_AGORA -e LUPA_BACKUP_ESTIMATIVA_BYTES \
    -e LUPA_RESTAURAR_BANCO -e LUPA_RESTAURAR_BUCKET -e LUPA_RESTAURAR_SOBRESCREVER \
    backup /scripts/backup_conteiner.sh "$@"
}
