# Backup diario cifrado (Etapa 7.8); equivalente ao backup.sh. Ver docs/backup.md.
. (Join-Path $PSScriptRoot "backup_comum.ps1")
Invoke-LupaBackup fazer
