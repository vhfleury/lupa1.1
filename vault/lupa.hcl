# Vault do Lupa (Etapa 7.2): servidor real, storage em arquivo, sem modo dev. Escuta só na rede
# interna do compose; TLS desligado porque o tráfego não sai das redes `interna`/`ingestao`
# (em produção: TLS e auto-unseal, ver docs/criptografia.md).
storage "file" {
  path = "/vault/file"
}

listener "tcp" {
  address     = "0.0.0.0:8200"
  tls_disable = true
}

api_addr      = "http://vault:8200"
disable_mlock = true
ui            = false
