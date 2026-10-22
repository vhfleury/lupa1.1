# Roda lint, tipagem e testes em sequencia; falha no primeiro erro.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
$py = if ($env:PYTHON) { $env:PYTHON } else { "python" }
$passos = @(
    @("ruff", "check", "src", "tests"),
    @("ruff", "format", "--check", "src", "tests"),
    @("mypy", "src", "tests"),
    @("pytest")
)
foreach ($passo in $passos) {
    Write-Host "== $($passo -join ' ') =="
    & $py -m @passo
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
Write-Host "== ponta a ponta da ingestao (integracao, sem skip) =="
$env:LUPA_EXIGIR_INTEGRACAO = "1"
try {
    & $py -m pytest -m integracao tests/ingestao/test_ponta_a_ponta.py --no-cov -q
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally {
    Remove-Item Env:LUPA_EXIGIR_INTEGRACAO -ErrorAction SilentlyContinue
}
Write-Host "== regressao de injecao (corpus 4B.8, metas da 4D.5, sem skip) =="
$env:LUPA_EXIGIR_INTEGRACAO = "1"
if (-not $env:LUPA_METRICAS_INJECAO) { $env:LUPA_METRICAS_INJECAO = Join-Path ([IO.Path]::GetTempPath()) "metricas_injecao.json" }
try {
    & $py -m pytest -m injecao tests/ingestao/test_injecao_corpus.py --no-cov -q
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Get-Content $env:LUPA_METRICAS_INJECAO -TotalCount 12
} finally {
    Remove-Item Env:LUPA_EXIGIR_INTEGRACAO -ErrorAction SilentlyContinue
}
# Etapa 6: lint, typecheck e testes unitarios do front, em conteiner (estagio `verificacao` da
# imagem do front; o build falha se algum dos tres falhar).
Write-Host "== front =="
docker build --target verificacao -q front | Out-Null
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "front: lint, typecheck e testes ok (build da imagem)"
# Etapa 6.10: cabecalhos de seguranca do proxy publicado no host (falha se faltar algum ou se a
# CSP afrouxar; proxy fora do ar so avisa, a menos que LUPA_EXIGIR_CABECALHOS esteja definido).
Write-Host "== cabecalhos de seguranca =="
$urlProxy = if ($env:LUPA_PROXY_URL) { $env:LUPA_PROXY_URL } else { "https://localhost:8443" }
$argsCab = @("scripts/verificar_cabecalhos.py", "--url", $urlProxy)
if ($env:LUPA_EXIGIR_CABECALHOS) { $argsCab += "--exigir" }
& $py @argsCab
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
# Etapa 5.8: suite de injecao do agente sobre autos ingeridos (cliente falso roteirizado), sem skip.
Write-Host "== suite de injecao do agente (Etapa 5.8, sem skip) =="
$env:LUPA_EXIGIR_INTEGRACAO = "1"
if (-not $env:LUPA_METRICAS_AGENTE) { $env:LUPA_METRICAS_AGENTE = Join-Path ([IO.Path]::GetTempPath()) "metricas_agente.json" }
try {
    & $py -m pytest -m agente tests/agente --no-cov -q
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Get-Content $env:LUPA_METRICAS_AGENTE -TotalCount 12
} finally {
    Remove-Item Env:LUPA_EXIGIR_INTEGRACAO -ErrorAction SilentlyContinue
}
# Etapa 6.10: suite E2E (Playwright) opcional, so no host (precisa de docker; nao roda dentro do
# conteiner da API). Ative com LUPA_VERIFICAR_E2E=1; usa front/scripts/e2e.ps1, que sobe a stack com
# o cliente falso do agente e, ao terminar (mesmo em falha), recria a API sem ele.
if ($env:LUPA_VERIFICAR_E2E -eq "1") {
    Write-Host "== e2e =="
    & (Join-Path $PSScriptRoot "..\front\scripts\e2e.ps1")
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} else {
    Write-Host "== e2e == (pulado; defina LUPA_VERIFICAR_E2E=1 para rodar a suite Playwright)"
}
# Etapa 7.8: backup cifrado, restauracao em ambiente limpo e expurgo, opcional e so no host (precisa
# de docker). Usa banco e bucket de TESTE pequenos criados pelo proprio teste, nunca lupa/lupa-autos.
# Ative com LUPA_VERIFICAR_BACKUP=1. Ver docs/backup.md.
if ($env:LUPA_VERIFICAR_BACKUP -eq "1") {
    Write-Host "== backup cifrado e restauracao =="
    & $py -m pytest -m backup tests/backup --no-cov -q --confcutdir=tests/backup
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} else {
    Write-Host "== backup == (pulado; defina LUPA_VERIFICAR_BACKUP=1 para testar backup e restauracao)"
}
