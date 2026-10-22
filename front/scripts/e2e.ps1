# Roda os testes ponta a ponta do front (Playwright) contra a stack real do compose.
# 1. sobe a stack; 2. prepara o admin (senha temporaria gerada agora, so em memoria);
# 3. roda `npm run e2e` no conteiner `e2e`, que fala com o proxy em https://proxy:8443.
# 4. (6.10) ao terminar, mesmo em falha, recria o servico `api` sem o cliente falso.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..\..")
$codigo = 1
try {
    # Etapa 6.8: a API do E2E usa o modelo falso roteirizado (recusado em producao).
    $env:LUPA_AGENTE_CLIENTE = "falso"
    docker compose up -d --build --wait
    if ($LASTEXITCODE -ne 0) { throw "docker compose up falhou" }
    # 6.10: o Caddyfile entra por bind mount de arquivo; recriar o proxy garante os cabecalhos atuais.
    docker compose up -d --no-deps --force-recreate --wait proxy
    if ($LASTEXITCODE -ne 0) { throw "recriar o proxy falhou" }
    $credenciais = @(docker compose exec -T api python scripts/e2e_preparar.py)
    if ($LASTEXITCODE -ne 0) { throw "e2e_preparar falhou" }
    $env:LUPA_E2E_ADMIN_USUARIO = $credenciais[0]
    $env:LUPA_E2E_ADMIN_SENHA = $credenciais[1]
    # Etapas 6.4 a 6.7: gabinete, assessor e processo sinteticos (autos no worker real).
    $processos = @(docker compose exec -T api python scripts/e2e_processos.py)
    if ($LASTEXITCODE -ne 0) { throw "e2e_processos falhou" }
    $env:LUPA_E2E_PROC_USUARIO = $processos[0]
    $env:LUPA_E2E_PROC_SENHA = $processos[1]
    $env:LUPA_E2E_PROC_ID = $processos[2]
    # Etapas 6.8 a 6.10: desembargador, processo do chat e processo com texto hostil; carga (1a vez).
    $chat = @(docker compose exec -T api python scripts/e2e_semear_chat.py --carga)
    if ($LASTEXITCODE -ne 0) { throw "e2e_semear_chat falhou" }
    $env:LUPA_E2E_CHAT_USUARIO = $chat[0]
    $env:LUPA_E2E_CHAT_SENHA = $chat[1]
    $env:LUPA_E2E_CHAT_PROCESSO = $chat[2]
    $env:LUPA_E2E_HOSTIL_PROCESSO = $chat[3]
    docker compose --profile e2e build e2e
    if ($LASTEXITCODE -ne 0) { throw "build do e2e falhou" }
    docker compose --profile e2e run --rm e2e @args
    $codigo = $LASTEXITCODE
} finally {
    Remove-Item Env:LUPA_E2E_ADMIN_SENHA -ErrorAction SilentlyContinue
    Remove-Item Env:LUPA_E2E_ADMIN_USUARIO -ErrorAction SilentlyContinue
    Remove-Item Env:LUPA_E2E_PROC_SENHA -ErrorAction SilentlyContinue
    Remove-Item Env:LUPA_E2E_CHAT_SENHA -ErrorAction SilentlyContinue
    Remove-Item Env:LUPA_AGENTE_CLIENTE -ErrorAction SilentlyContinue
    Write-Host "e2e: recriando a api sem LUPA_AGENTE_CLIENTE=falso"
    docker compose up -d --no-deps --force-recreate --wait api
    if ($LASTEXITCODE -ne 0) { $codigo = 1 }
}
exit $codigo
