# Relatório da Etapa 7.1: decisão do object storage

## O que foi feito

- `docs/decisoes/object-storage.md`: comparação entre `pgsty/minio` (atual), Chainguard
  (`cgr.dev/chainguard/minio`), Garage e RustFS (origem, compatibilidade S3 com o `boto3`, `mc` na
  imagem, usuário não root, fixação por digest, cadência de correções, mudança no compose, risco).
  Decisão marcada **pendente de assinatura do responsável técnico**.
- `docker-compose.yml`: a imagem de `minio` e `minio-init` passou a `${STORAGE_IMAGEM:-pgsty/minio@sha256:...}`
  (padrão inalterado). `STORAGE_IMAGEM` documentada no `.env.example`.

## Recomendação

Manter `pgsty/minio` por digest como padrão. A Chainguard baixa sem login (MinIO
RELEASE.2026-09-22, nonroot), mas não traz `mc`: o healthcheck (`mc ready local`), o `minio-init`
(`mc mb`) e o estágio `mc` do serviço `backup` (7.8) quebrariam. Plano B (Chainguard + healthcheck
HTTP + imagem só com `mc`) e plano C (Garage) descritos no documento. Como desde a 7.4 os objetos
já saem cifrados da aplicação, trocar de storage é copiar bytes opacos.

## Disco

Nenhuma imagem de storage baixada nesta etapa (só a do Vault, na 7.2).

## O que ficou de fora

- Assinatura do responsável técnico.
- Teste de compatibilidade do `ArmazenamentoS3` contra Garage/RustFS (só se o plano C for adotado).
