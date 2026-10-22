# Política mínima do AppRole da aplicação: só o Transit, só chaves `lupa-gabinete-*`.
# Criar/ler/configurar/rotacionar/apagar a chave e cifrar, decifrar e recifrar (rewrap).
# Nada de exportar chave, nada de outros engines, nada de sys/.
path "transit/keys/lupa-gabinete-*" {
  capabilities = ["create", "read", "update", "delete"]
}
path "transit/encrypt/lupa-gabinete-*" {
  capabilities = ["update"]
}
path "transit/decrypt/lupa-gabinete-*" {
  capabilities = ["update"]
}
path "transit/rewrap/lupa-gabinete-*" {
  capabilities = ["update"]
}
# Etapa 8.1: chave de verificação de saúde. Só cifrar e decifrar (a chave é criada pelo
# vault_inicializar com o token raiz; a aplicação não a cria nem apaga).
path "transit/encrypt/lupa-saude" {
  capabilities = ["update"]
}
path "transit/decrypt/lupa-saude" {
  capabilities = ["update"]
}
