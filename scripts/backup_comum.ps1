# Funcao comum aos scripts de backup do host em PowerShell (Etapa 7.8); equivalente ao
# backup_comum.sh. Roda backup_conteiner.sh no servico `backup` (perfil `backup`) do compose.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
function Invoke-LupaBackup {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Argumentos)
    $backups = if ($env:LUPA_BACKUP_DIR) { $env:LUPA_BACKUP_DIR } else { "./.backups" }
    $chaves = if ($env:LUPA_BACKUP_CHAVES_DIR) { $env:LUPA_BACKUP_CHAVES_DIR } else { "./.backup-chaves" }
    foreach ($pasta in @($backups, $chaves)) { New-Item -ItemType Directory -Force $pasta | Out-Null }
    $repassar = @("LUPA_BACKUP_BANCO", "LUPA_BACKUP_BUCKET", "LUPA_BACKUP_AGORA", "LUPA_BACKUP_ESTIMATIVA_BYTES",
        "LUPA_RESTAURAR_BANCO", "LUPA_RESTAURAR_BUCKET", "LUPA_RESTAURAR_SOBRESCREVER")
    $extra = @()
    foreach ($nome in $repassar) { $extra += @("-e", $nome) }
    & docker compose --profile backup run --rm -T @extra backup /scripts/backup_conteiner.sh @Argumentos
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
