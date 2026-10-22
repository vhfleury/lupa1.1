# Inicializa o Vault do compose para DESENVOLVIMENTO (Etapa 7.2), no Windows PowerShell.
# Mesmo fluxo de scripts/vault_inicializar.sh: init (1 parte), unseal, Transit, AppRole, politica
# minima e role_id/secret_id gravados so no .env. Idempotente. Em producao NAO: auto-unseal.
$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
$Dir = '.vault-dev'
$Init = Join-Path $Dir 'init.json'
$EnvArq = if ($env:LUPA_ENV_ARQUIVO) { $env:LUPA_ENV_ARQUIVO } else { '.env' }

if ((Test-Path $EnvArq) -and (Select-String -Path $EnvArq -Pattern '^LUPA_AMBIENTE=producao' -Quiet)) {
    Write-Error 'vault_inicializar.ps1: so desenvolvimento; em producao use scripts/vault_inicializar.sh (3 partes, limiar 2)'
}

function Invoke-Vault([string[]]$Argumentos, [string]$Token = '') {
    $base = @('compose', 'exec', '-T')
    if ($Token) { $base += @('-e', "VAULT_TOKEN=$Token") }
    $saida = & docker @($base + @('vault', 'vault') + $Argumentos)
    return ($saida -join "`n")
}

$estado = Invoke-Vault @('status', '-format=json') | ConvertFrom-Json
if (-not $estado.initialized) {
    New-Item -ItemType Directory -Force $Dir | Out-Null
    Invoke-Vault @('operator', 'init', '-key-shares=1', '-key-threshold=1', '-format=json') |
        Out-File -Encoding ascii $Init
    icacls $Init /inheritance:r /grant:r "$($env:USERNAME):(R,W)" | Out-Null
    Write-Output "vault: inicializado (chave de unseal e token raiz em $Init)"
}
if (-not (Test-Path $Init)) { Write-Error "vault ja inicializado mas $Init nao existe" }
$dados = Get-Content $Init -Raw | ConvertFrom-Json
$chave = $dados.unseal_keys_b64[0]
$raiz = $dados.root_token

$estado = Invoke-Vault @('status', '-format=json') | ConvertFrom-Json
if ($estado.sealed) {
    Invoke-Vault @('operator', 'unseal', $chave) | Out-Null
    Write-Output 'vault: unseal ok'
}

if ((Invoke-Vault @('secrets', 'list', '-format=json') $raiz) -notmatch '"transit/"') {
    Invoke-Vault @('secrets', 'enable', 'transit') $raiz | Out-Null
}
if ((Invoke-Vault @('auth', 'list', '-format=json') $raiz) -notmatch '"approle/"') {
    Invoke-Vault @('auth', 'enable', 'approle') $raiz | Out-Null
}
# Etapa 8.1: chave Transit de verificacao do GET /saude (componente `cofre`).
if ((Invoke-Vault @('list', '-format=json', 'transit/keys') $raiz) -notmatch '"lupa-saude"') {
    Invoke-Vault @('write', '-f', 'transit/keys/lupa-saude') $raiz | Out-Null
}
Get-Content 'vault/politicas/lupa.hcl' -Raw |
    docker compose exec -T -e "VAULT_TOKEN=$raiz" vault vault policy write lupa - | Out-Null
Invoke-Vault @('write', 'auth/approle/role/lupa', 'token_policies=lupa', 'token_ttl=1h',
    'token_max_ttl=4h', 'secret_id_ttl=0') $raiz | Out-Null
$roleId = (Invoke-Vault @('read', '-format=json', 'auth/approle/role/lupa/role-id') $raiz |
    ConvertFrom-Json).data.role_id
$secretId = (Invoke-Vault @('write', '-format=json', '-f', 'auth/approle/role/lupa/secret-id') $raiz |
    ConvertFrom-Json).data.secret_id

$novos = [ordered]@{
    'LUPA_COFRE_BACKEND'   = 'vault'
    'LUPA_VAULT_ROLE_ID'   = $roleId
    'LUPA_VAULT_SECRET_ID' = $secretId
}
$linhas = if (Test-Path $EnvArq) { Get-Content $EnvArq } else { @() }
$saida = @($linhas | Where-Object { -not $novos.Contains(($_ -split '=', 2)[0].Trim()) })
foreach ($k in $novos.Keys) { $saida += "$k=$($novos[$k])" }
[System.IO.File]::WriteAllText((Resolve-Path -LiteralPath '.').Path + "\$EnvArq",
    (($saida -join "`n") + "`n"), (New-Object System.Text.UTF8Encoding $false))
Write-Output "vault: Transit, politica 'lupa' e AppRole prontos; role_id/secret_id gravados em $EnvArq"
Write-Output 'rode: docker compose up -d api worker'
