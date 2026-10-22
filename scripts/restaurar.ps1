# Restaura um backup cifrado (Etapa 7.8); equivalente ao restaurar.sh. Exige
# $env:LUPA_RESTAURAR_BANCO e $env:LUPA_RESTAURAR_BUCKET. Ver docs/backup.md.
param([Parameter(Mandatory = $true)][string]$Arquivo)
. (Join-Path $PSScriptRoot "backup_comum.ps1")
Invoke-LupaBackup restaurar $Arquivo
