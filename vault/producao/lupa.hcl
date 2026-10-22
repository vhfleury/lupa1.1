# Vault do Lupa em PRODUCAO (Etapa 8.1, montado pelo docker-compose.prod.yml no lugar de
# vault/lupa.hcl): mlock LIGADO (memoria do Vault nunca vai para swap; exige cap IPC_LOCK).
# TLS no listener desligado de proposito: rede interna de um host so (docs/operacao.md 4.6).
storage "file" {
  path = "/vault/file"
}

listener "tcp" {
  address     = "0.0.0.0:8200"
  tls_disable = true
}

api_addr      = "http://vault:8200"
disable_mlock = false
ui            = false
