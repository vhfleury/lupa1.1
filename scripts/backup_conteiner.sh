#!/bin/sh
# Backup cifrado do Lupa (Etapa 7.8). Roda DENTRO do servico `backup` do compose (perfil `backup`),
# chamado por scripts/backup.sh, scripts/restaurar.sh e scripts/expurgar_backups.sh (ou os .ps1).
#
#   backup_conteiner.sh fazer                  pg_dump (custom) + espelho do bucket -> tar -> age
#   backup_conteiner.sh restaurar ARQUIVO      decifra, confere o manifesto e restaura em banco e
#                                              bucket de destino (LUPA_RESTAURAR_BANCO/_BUCKET)
#   backup_conteiner.sh expurgar               apaga backups com mais de LUPA_BACKUP_RETENCAO_DIAS
#                                              e destroi a chave do periodo sem backup vivo
#   backup_conteiner.sh listar                 lista backups e chaves
#
# Montagens (bind mounts do host, nunca volumes nem camada do conteiner): /backups (arquivos
# .age, o log backup.log e a area de trabalho temporaria .trabalho-*), /chaves (uma chave age por
# mes, fora do diretorio de backup), /scripts (so leitura). Nada e gravado na camada gravavel do
# conteiner: o dump e o espelho em claro ficam so durante a execucao em /backups/.trabalho-*
# (permissao 700, apagada ao fim, mesmo em falha). Antes de comecar, o tamanho e estimado e o
# backup e recusado sem espaco livre de 2x a estimativa + 2 GB no destino.
set -eu
umask 077

BACKUPS=/backups
CHAVES=/chaves
LOG="$CHAVES/destruicoes.log"
LOG_BACKUP="$BACKUPS/backup.log"
FOLGA_BYTES=$((2 * 1024 * 1024 * 1024))
RETENCAO_DIAS="${LUPA_BACKUP_RETENCAO_DIAS:-30}"
PGHOST="${PGHOST:-db}"
MINIO="${LUPA_BACKUP_MINIO_URL:-http://minio:9000}"
export PGHOST PGUSER="$POSTGRES_USER" PGPASSWORD="$POSTGRES_PASSWORD"
export HOME=/tmp/mc-home

falhar() {
  echo "backup: $*" >&2
  exit 1
}

agora_epoch() {
  # LUPA_BACKUP_AGORA (epoch) so para testes do expurgo; sem ela, o relogio do conteiner.
  if [ -n "${LUPA_BACKUP_AGORA:-}" ]; then echo "$LUPA_BACKUP_AGORA"; else date -u +%s; fi
}

trabalho_novo() {
  # Area de trabalho no bind mount do host (nunca na camada do conteiner).
  TRABALHO=$(mktemp -d "$BACKUPS/.trabalho-XXXXXX")
  trap 'rm -rf "$TRABALHO"' EXIT INT TERM
}

alias_minio() {
  mc alias set lupa "$MINIO" "$LUPA_MINIO_ACCESS_KEY" "$LUPA_MINIO_SECRET_KEY" >/dev/null
}

chave_do_periodo() {
  # Uma chave age por mes (AAAA-MM). Gerada na primeira vez que o mes e usado.
  periodo="$1"
  chave="$CHAVES/chave-$periodo.txt"
  if [ ! -f "$chave" ]; then
    age-keygen -o "$chave.tmp" 2>/dev/null
    mv "$chave.tmp" "$chave"
    echo "backup: chave nova do periodo $periodo" >&2
  fi
  echo "$chave"
}

registrar() {
  # Linha do log de destruicao encadeada: hash = sha256(hash_anterior + linha). Quem altera ou
  # remove uma linha rompe a corrente (mesma ideia da auditoria).
  linha="$1"
  anterior=$(tail -n 1 "$LOG" 2>/dev/null | sed -n 's/.*hash=\([0-9a-f]\{64\}\)$/\1/p')
  anterior="${anterior:-0000000000000000000000000000000000000000000000000000000000000000}"
  hash=$(printf '%s|%s' "$anterior" "$linha" | sha256sum | cut -d' ' -f1)
  printf '%s anterior=%s hash=%s\n' "$linha" "$anterior" "$hash" >>"$LOG"
}

log_backup() {
  printf '%s %s
' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >>"$LOG_BACKUP"
  echo "backup: $*" >&2
}

livre_bytes() {
  # Espaco livre (bytes) no sistema de arquivos do destino.
  echo $(($(df -Pk "$1" | awk 'NR==2 {print $4}') * 1024))
}

conferir_espaco() {
  # $1 = estimativa em bytes, $2 = rotulo. Exige livre >= 2 x estimativa + 2 GB.
  estimativa="$1"
  livre=$(livre_bytes "$BACKUPS")
  exigido=$((2 * estimativa + FOLGA_BYTES))
  log_backup "$2 estimativa_bytes=$estimativa livre_bytes=$livre exigido_bytes=$exigido"
  if [ "$livre" -lt "$exigido" ]; then
    log_backup "$2 RECUSADO: espaco livre insuficiente no destino"
    falhar "espaco livre insuficiente: livre=$livre exigido=$exigido (2 x $estimativa + 2 GB)"
  fi
}

fazer() {
  banco="${LUPA_BACKUP_BANCO:-$POSTGRES_DB}"
  bucket="${LUPA_BACKUP_BUCKET:-$LUPA_MINIO_BUCKET}"
  epoch=$(agora_epoch)
  carimbo=$(date -u -d "@$epoch" +%Y%m%dT%H%M%SZ)
  periodo=$(date -u -d "@$epoch" +%Y-%m)
  alias_minio
  if [ -n "${LUPA_BACKUP_ESTIMATIVA_BYTES:-}" ]; then
    # So para testes (Etapa 7.10): forca a estimativa e pula a medicao do banco e do bucket.
    conferir_espaco "$LUPA_BACKUP_ESTIMATIVA_BYTES" "fazer banco=$banco bucket=$bucket estimativa_forcada=1"
  fi
  tam_banco=$(psql -d postgres -tAc "SELECT pg_database_size('$banco')") ||
    falhar "banco $banco nao encontrado"
  tam_bucket=$(mc du --json "lupa/$bucket" | sed -n 's/.*"size":\([0-9]*\).*/\1/p' | tail -n 1)
  tam_bucket="${tam_bucket:-0}"
  conferir_espaco $((tam_banco + tam_bucket)) "fazer banco=$banco bucket=$bucket banco_bytes=$tam_banco bucket_bytes=$tam_bucket"
  chave=$(chave_do_periodo "$periodo")
  destinatario=$(age-keygen -y "$chave")
  trabalho_novo
  mkdir -p "$TRABALHO/conteudo/objetos"

  echo "backup: banco $banco" >&2
  pg_dump --format=custom --no-password --dbname="$banco" --file="$TRABALHO/conteudo/banco.dump"

  echo "backup: bucket $bucket" >&2
  # Os bytes vao como estao: se a 7.4 cifrou os objetos, o backup leva o objeto cifrado.
  mc mirror --quiet --preserve "lupa/$bucket" "$TRABALHO/conteudo/objetos" >/dev/null

  (
    cd "$TRABALHO/conteudo"
    {
      echo "# lupa-backup 1"
      echo "# carimbo $carimbo"
      echo "# periodo $periodo"
      echo "# banco $banco"
      echo "# bucket $bucket"
      echo "# pg_dump $(pg_dump --version)"
    } >metadados.txt
    find . -type f ! -name manifesto.sha256 | sort | xargs -r sha256sum >manifesto.sha256
  )

  # Etapa 8.1: copia do armazenamento do Vault (storage `file`, volume montado so leitura em
  # /vault-dados). O conteudo ja e cifrado pela barreira do Vault: sem as partes de unseal nao
  # serve. Copia a quente: o Vault so grava ao criar/rotacionar/apagar chave e ao emitir token
  # (raro); para uma copia fria garantida use `scripts/backup.sh --vault-frio` (para o vault).
  if [ -d /vault-dados ] && [ "${LUPA_BACKUP_VAULT:-1}" = "1" ]; then
    echo "backup: armazenamento do vault" >&2
    tar -C /vault-dados -cf "$TRABALHO/conteudo/vault.tar" .
    (cd "$TRABALHO/conteudo" && sha256sum ./vault.tar >>manifesto.sha256)
  fi

  nome="lupa-$periodo-$carimbo.tar.age"
  tar -C "$TRABALHO/conteudo" -cf - . | age -r "$destinatario" -o "$BACKUPS/$nome.parcial"
  mv "$BACKUPS/$nome.parcial" "$BACKUPS/$nome"
  log_backup "gravado $nome bytes=$(wc -c <"$BACKUPS/$nome")"
  echo "$nome"
}

restaurar() {
  arquivo="${1:-}"
  [ -n "$arquivo" ] || falhar "informe o arquivo (nome em $BACKUPS)"
  caminho="$BACKUPS/$(basename "$arquivo")"
  [ -f "$caminho" ] || falhar "backup nao encontrado: $arquivo"
  periodo=$(basename "$caminho" | sed -n 's/^lupa-\([0-9]\{4\}-[0-9]\{2\}\)-.*\.tar\.age$/\1/p')
  [ -n "$periodo" ] || falhar "nome fora do padrao lupa-AAAA-MM-<carimbo>.tar.age"
  chave="$CHAVES/chave-$periodo.txt"
  [ -f "$chave" ] || falhar "chave do periodo $periodo nao existe (destruida ou fora de $CHAVES)"
  banco="${LUPA_RESTAURAR_BANCO:-}"
  bucket="${LUPA_RESTAURAR_BUCKET:-}"
  [ -n "$banco" ] && [ -n "$bucket" ] || falhar "defina LUPA_RESTAURAR_BANCO e LUPA_RESTAURAR_BUCKET"

  # O conteudo em claro ocupa ~ o tamanho do arquivo cifrado (tar sem compressao).
  conferir_espaco "$(wc -c <"$caminho")" "restaurar arquivo=$(basename "$caminho") banco=$banco bucket=$bucket"
  trabalho_novo
  mkdir -p "$TRABALHO/conteudo"
  age -d -i "$chave" "$caminho" | tar -C "$TRABALHO/conteudo" -xf -
  (cd "$TRABALHO/conteudo" && sha256sum -c manifesto.sha256 >/dev/null) ||
    falhar "manifesto nao confere: backup corrompido"
  echo "backup: manifesto conferido" >&2

  existe=$(psql -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = '$banco'")
  if [ "$existe" = "1" ]; then
    tabelas=$(psql -d "$banco" -tAc \
      "SELECT count(*) FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema')")
    [ "$tabelas" = "0" ] || [ "${LUPA_RESTAURAR_SOBRESCREVER:-0}" = "1" ] ||
      falhar "banco $banco nao esta vazio (LUPA_RESTAURAR_SOBRESCREVER=1 para apagar e recriar)"
    if [ "$tabelas" != "0" ]; then
      psql -d postgres -qc "DROP DATABASE \"$banco\" WITH (FORCE)"
      existe=""
    fi
  fi
  [ "$existe" = "1" ] || createdb "$banco"
  echo "backup: restaurando banco em $banco" >&2
  pg_restore --no-password --exit-on-error --dbname="$banco" "$TRABALHO/conteudo/banco.dump"

  alias_minio
  mc mb --ignore-existing "lupa/$bucket" >/dev/null
  echo "backup: restaurando objetos em $bucket" >&2
  mc mirror --quiet --preserve "$TRABALHO/conteudo/objetos" "lupa/$bucket" >/dev/null
  if [ -f "$TRABALHO/conteudo/vault.tar" ]; then
    # Etapa 8.1: o armazenamento do Vault NAO e reposto sozinho (exige parar o vault e as partes
    # de unseal da epoca); fica em /backups/vault-<arquivo>.tar para o procedimento manual
    # (docs/operacao.md, secao 4.4).
    destino_vault="$BACKUPS/vault-$(basename "$caminho" .tar.age).tar"
    cp "$TRABALHO/conteudo/vault.tar" "$destino_vault"
    echo "backup: armazenamento do vault em $(basename "$destino_vault") (reposicao manual)" >&2
  fi
  log_backup "restaurado $(basename "$caminho") em banco=$banco bucket=$bucket"
}

expurgar() {
  agora=$(agora_epoch)
  limite=$((agora - RETENCAO_DIAS * 86400))
  periodo_atual=$(date -u -d "@$agora" +%Y-%m)
  for caminho in "$BACKUPS"/lupa-*.tar.age; do
    [ -f "$caminho" ] || continue
    carimbo=$(basename "$caminho" | sed -n 's/^lupa-[0-9-]\{7\}-\([0-9T]\{15\}Z\)\.tar\.age$/\1/p')
    [ -n "$carimbo" ] || continue
    quando=$(date -u -D %Y%m%dT%H%M%SZ -d "$carimbo" +%s)
    if [ "$quando" -lt "$limite" ]; then
      rm -f "$caminho"
      echo "backup: expurgado $(basename "$caminho")" >&2
    fi
  done
  for chave in "$CHAVES"/chave-*.txt; do
    [ -f "$chave" ] || continue
    periodo=$(basename "$chave" | sed -n 's/^chave-\([0-9]\{4\}-[0-9]\{2\}\)\.txt$/\1/p')
    [ -n "$periodo" ] || continue
    [ "$periodo" != "$periodo_atual" ] || continue
    if ls "$BACKUPS"/lupa-"$periodo"-*.tar.age >/dev/null 2>&1; then continue; fi
    # Sem backup vivo do periodo: destroi a chave. A impressao digital (sha256 da chave publica)
    # fica no log para provar qual chave foi destruida, sem guardar a chave.
    impressao=$(age-keygen -y "$chave" | sha256sum | cut -d' ' -f1)
    tamanho=$(wc -c <"$chave")
    dd if=/dev/urandom of="$chave" bs="$tamanho" count=1 conv=notrunc 2>/dev/null
    sync
    rm -f "$chave"
    registrar "$(date -u -d "@$agora" +%Y-%m-%dT%H:%M:%SZ) destruida periodo=$periodo impressao=$impressao motivo=sem_backup_vivo retencao_dias=$RETENCAO_DIAS"
    echo "backup: chave do periodo $periodo destruida" >&2
  done
}

listar() {
  echo "backups:"
  ls -1 "$BACKUPS" 2>/dev/null | grep '\.tar\.age$' || true
  echo "chaves:"
  ls -1 "$CHAVES" 2>/dev/null | grep '^chave-' || true
}

comando="${1:-}"
[ $# -gt 0 ] && shift
case "$comando" in
  fazer) fazer ;;
  restaurar) restaurar "$@" ;;
  expurgar) expurgar ;;
  listar) listar ;;
  *) falhar "uso: backup_conteiner.sh fazer|restaurar ARQUIVO|expurgar|listar" ;;
esac
