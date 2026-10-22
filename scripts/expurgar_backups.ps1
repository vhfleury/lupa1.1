# Retencao de 30 dias e destruicao das chaves sem backup vivo (Etapa 7.8); equivalente ao
# expurgar_backups.sh. Ver docs/backup.md.
. (Join-Path $PSScriptRoot "backup_comum.ps1")
Invoke-LupaBackup expurgar
