#!/usr/bin/env bash
# Retencao (Etapa 7.8): apaga backups com mais de LUPA_BACKUP_RETENCAO_DIAS (padrao 30) e destroi a
# chave de cada mes que nao tem mais backup vivo, registrando a destruicao no log encadeado
# (LUPA_BACKUP_CHAVES_DIR/destruicoes.log). Ver docs/backup.md.
source "$(dirname "$0")/backup_comum.sh"
backup_executar expurgar
