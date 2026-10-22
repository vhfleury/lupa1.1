# Decisão: imagem do object storage (Etapa 7.1)

**Situação: PENDENTE DE ASSINATURA DO RESPONSÁVEL TÉCNICO.** Enquanto não houver assinatura, vale o
padrão abaixo (pgsty/minio por digest), trocável sem mexer em código pela variável `STORAGE_IMAGEM`.

## Contexto

A MinIO Inc. deixou de publicar imagens e binários comunitários atualizados em 2025 (o código
segue AGPL, mas sem builds oficiais livres com correções). O Lupa precisa de um armazenamento S3
local para o piloto que (1) receba correções de segurança, (2) tenha imagem fixável por digest,
(3) rode sem root, (4) traga o cliente `mc` (usado no healthcheck, no `minio-init` e no serviço
`backup` da 7.8) ou equivalente, e (5) fale S3 com o `boto3` sem mudança no `ArmazenamentoS3`.

Desde a Etapa 7.4 o conteúdo gravado no storage já sai cifrado da aplicação (`StorageCifrado`,
AES-256-GCM com a DEK do processo). O storage não precisa oferecer cifra própria: quem tiver acesso
ao bucket vê só objetos `LUPAOBJ`. Isso reduz o peso de critérios como SSE/KMS do servidor.

## Opções avaliadas

| Critério | pgsty/minio (atual) | cgr.dev/chainguard/minio | Garage | RustFS |
|---|---|---|---|---|
| Origem | Build comunitário do código MinIO (Pigsty) | Build Chainguard (wolfi), mínimo | Projeto próprio (Deuxfleurs), Rust | Projeto próprio, Rust |
| Compatibilidade S3 com o `boto3` do Lupa | Total (é o MinIO) | Total (é o MinIO, RELEASE.2026-09-22) | Boa para o subconjunto usado (put/get/head/delete/list v2); sem várias APIs avançadas | Alta segundo o projeto; maturidade menor |
| `mc` na imagem | Sim | **Não** (quebra healthcheck, `minio-init` e `backup`) | Não (CLI própria `garage`) | Não |
| Usuário não root | Sim (`10002`) | Sim (nonroot) | Sim | Sim |
| Login para baixar | Não | Não (tag `latest` pública) | Não | Não |
| Fixação por digest | Sim (já fixado) | Sim, mas só `latest` é gratuito (tags de versão exigem assinatura) | Sim | Sim |
| Cadência de correções | Acompanha releases do MinIO | Rebuild contínuo, CVEs baixos | Releases regulares | Releases frequentes, projeto jovem |
| Mudança no compose | Nenhuma | Healthcheck via `curl`/HTTP, `minio-init` e `backup` precisam de outra imagem com `mc` | Serviço novo, layout/zonas, chaves via CLI própria | Serviço novo |
| Risco | Depende de um mantenedor comunitário | Precisaria de 2 imagens (servidor + `mc`) | Migração de dados e operação diferentes | Maturidade e licença a acompanhar |

Fatos levantados nesta etapa: `cgr.dev/chainguard/minio:latest` baixa sem login (MinIO
RELEASE.2026-09-22, nonroot), mas não tem `mc`; com ele, o healthcheck `mc ready local`, o
`minio-init` (`mc mb`) e o estágio `mc` do serviço `backup` (7.8) quebrariam. Nenhuma imagem além
do Vault foi baixada nesta etapa (disciplina de disco).

## Recomendação

1. **Manter `pgsty/minio` fixado por digest como padrão**, agora parametrizado:
   `image: ${STORAGE_IMAGEM:-pgsty/minio@sha256:b6bf...2372}` nos serviços `minio` e `minio-init`.
2. Revisar o digest a cada mês (ou a cada CVE do MinIO) junto com as outras imagens.
3. Plano B documentado: Chainguard para o servidor, com healthcheck HTTP (`/minio/health/ready`)
   e uma imagem só com `mc` para `minio-init`/`backup`. Plano C, se o MinIO comunitário parar de
   receber correções: Garage, com teste de compatibilidade do `ArmazenamentoS3` antes.
4. Como os objetos já são cifrados pela aplicação, uma troca de storage é cópia de bytes opacos
   (`mc mirror`), sem recifrar nada.

## Assinatura

| Papel | Nome | Data | Decisão |
|---|---|---|---|
| Responsável técnico | _pendente_ | _pendente_ | _pendente_ |
