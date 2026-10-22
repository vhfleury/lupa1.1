#!/usr/bin/env bash
# Backup diario cifrado (Etapa 7.8): banco (pg_dump custom) + objetos do bucket + (Etapa 8.1)
# armazenamento do Vault, num tar cifrado com a chave age do mes. Saida: o nome do arquivo gravado
# em LUPA_BACKUP_DIR. Ver docs/backup.md.
# Agendamento: em producao, o servico `backup-agendado` (docker-compose.prod.yml) faz isto todo
# dia; sem ele, cron do host: 0 2 * * * cd /caminho/Lupa1 && bash scripts/backup.sh && bash scripts/expurgar_backups.sh
#   --vault-frio  para o vault antes da copia e o sobe depois (copia fria garantida; o cofre volta
#                 SELADO e precisa de unseal: docs/operacao.md, secao 4.2).
source "$(dirname "$0")/backup_comum.sh"
if [ "${1:-}" = "--vault-frio" ]; then
  docker compose stop vault
  trap 'docker compose start vault; echo "backup: vault reiniciado; faca o unseal" >&2' EXIT
fi
backup_executar fazer
