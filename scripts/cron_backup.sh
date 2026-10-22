#!/bin/sh
# Agendador do backup (Etapa 8.1). Roda DENTRO do servico `backup-agendado` (imagem do backup) e
# usa o crond do BusyBox: diario `backup_conteiner.sh fazer` e semanal `expurgar` (horarios em
# LUPA_BACKUP_CRON_DIARIO / LUPA_BACKUP_CRON_EXPURGO, formato cron). O crond nao repassa o
# ambiente do conteiner aos jobs: ele e salvo em /tmp (tmpfs, memoria, modo 600) e carregado por
# cada job. Nada vai a camada gravavel; a saida vai para /backups/cron.log.
set -eu
umask 077
export -p >/tmp/cron.env
mkdir -p /tmp/crontabs
cat >/tmp/crontabs/root <<CRON
${LUPA_BACKUP_CRON_DIARIO:-0 2 * * *} . /tmp/cron.env; /bin/sh /scripts/backup_conteiner.sh fazer >>/backups/cron.log 2>&1
${LUPA_BACKUP_CRON_EXPURGO:-30 3 * * 0} . /tmp/cron.env; /bin/sh /scripts/backup_conteiner.sh expurgar >>/backups/cron.log 2>&1
CRON
echo "cron_backup: agenda diario='${LUPA_BACKUP_CRON_DIARIO:-0 2 * * *}' expurgo='${LUPA_BACKUP_CRON_EXPURGO:-30 3 * * 0}'"
exec crond -f -l 8 -c /tmp/crontabs
