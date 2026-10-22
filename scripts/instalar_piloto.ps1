# Instalacao do Lupa do zero (Etapa 8.1) no Windows PowerShell 5.1: mesmo roteiro do
# scripts/instalar_piloto.sh (docs/operacao.md, secao 2). Idempotente; pede confirmacao antes de
# alterar o .env existente. No Windows so o modo DESENVOLVIMENTO (o Vault de producao, com 3 partes
# e limiar 2, e inicializado pelo vault_inicializar.sh num host Linux).
#   powershell -File scripts/instalar_piloto.ps1 [-Sim]
param([switch]$Sim)
$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
$Utf8 = New-Object System.Text.UTF8Encoding $false

function Passo([string]$t) { Write-Output "`n== $t ==" }
function Confirmar([string]$t) { if ($Sim) { return $true }; (Read-Host "$t [s/N]") -match '^[sS]$' }
function Linhas { if (Test-Path .env) { @(Get-Content .env) } else { @() } }
function ValorEnv([string]$k) {
    $l = Linhas | Where-Object { $_ -like "$k=*" } | Select-Object -Last 1
    if ($l) { ($l -split '=', 2)[1] } else { '' }
}
function DefinirEnv([string]$k, [string]$v) {
    $saida = @(Linhas | Where-Object { ($_ -split '=', 2)[0].Trim() -ne $k }) + "$k=$v"
    [IO.File]::WriteAllText((Join-Path (Get-Location) '.env'), (($saida -join "`n") + "`n"), $Utf8)
}
function Aleatorio([int]$n = 24) {
    $b = New-Object byte[] $n
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b)
    [Convert]::ToBase64String($b).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}
function Ficticio([string]$k, [string]$v) {
    (-not $v) -or (Select-String -Path .env.example -Pattern ("^" + [regex]::Escape("$k=$v") + "$") -Quiet)
}
function Dk { & docker.exe @args; if ($LASTEXITCODE -ne 0) { throw "docker $($args -join ' ') falhou ($LASTEXITCODE)" } }

Passo '1. pre-requisitos'
Dk compose version | Out-Null
$livre = [int]((Get-PSDrive (Get-Location).Drive.Name).Free / 1GB)
Write-Output "  disco livre: $livre GB"
if ($livre -lt 15) { throw 'abaixo de 15 GB livres: pare' }

Passo '2. arquivo .env'
if (-not (Test-Path .env)) { Copy-Item .env.example .env; Write-Output '  .env criado' }
elseif (-not (Confirmar '  .env ja existe; completar so o que falta (nada e apagado)?')) { Write-Output '  mantido' }
DefinirEnv 'LUPA_AMBIENTE' 'desenvolvimento'
foreach ($k in 'POSTGRES_PASSWORD', 'LUPA_MINIO_SECRET_KEY', 'LUPA_DB_SENHA_APP', 'LUPA_METRICAS_TOKEN', 'LUPA_ADMIN_SENHA') {
    if (Ficticio $k (ValorEnv $k)) { DefinirEnv $k (Aleatorio); Write-Output "  ${k}: gerado" } else { Write-Output "  ${k}: mantido" }
}
DefinirEnv 'LUPA_DATABASE_URL' ("postgresql+psycopg://{0}:{1}@db:5432/{2}" -f (ValorEnv POSTGRES_USER), (ValorEnv POSTGRES_PASSWORD), (ValorEnv POSTGRES_DB))

Passo '3. pastas e segredos'
New-Item -ItemType Directory -Force .segredos, .backups, .backup-chaves | Out-Null
[IO.File]::WriteAllText((Join-Path (Get-Location) '.segredos\metricas_token'), (ValorEnv LUPA_METRICAS_TOKEN), $Utf8)
if (-not (Test-Path .segredos\grafana_senha)) {
    [IO.File]::WriteAllText((Join-Path (Get-Location) '.segredos\grafana_senha'), (Aleatorio 18), $Utf8)
}

Passo '4. build'
Dk compose build

Passo '5. Vault'
Dk compose up -d vault
Start-Sleep -Seconds 3
& powershell -NoProfile -File scripts/vault_inicializar.ps1
if ($LASTEXITCODE -ne 0) { throw 'vault_inicializar falhou' }

Passo '6. subida completa'
Dk compose up -d --wait

Passo '7. migracoes'
Dk compose exec -T api alembic -c src/lupa/migrations/alembic.ini upgrade head

Passo '8. usuario de banco restrito'
Dk compose exec -T api python scripts/criar_usuario_banco.py
Dk compose up -d --wait api worker

Passo '9. administrador'
Dk compose exec -T api python scripts/criar_admin.py
Write-Output '  senha inicial em LUPA_ADMIN_SENHA no .env; apague a linha depois do primeiro acesso'

Passo '10. conferencia'
& python scripts/conferir_piloto.py
