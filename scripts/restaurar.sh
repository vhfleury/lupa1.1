#!/usr/bin/env bash
# Restaura um backup cifrado (Etapa 7.8) num banco e num bucket de destino.
# Uso: LUPA_RESTAURAR_BANCO=lupa_restaurado LUPA_RESTAURAR_BUCKET=lupa-restaurado \
#        bash scripts/restaurar.sh lupa-AAAA-MM-<carimbo>.tar.age
# Recusa banco de destino com tabelas, salvo LUPA_RESTAURAR_SOBRESCREVER=1. Ver docs/backup.md.
source "$(dirname "$0")/backup_comum.sh"
[ $# -eq 1 ] || { echo "uso: restaurar.sh ARQUIVO.tar.age" >&2; exit 2; }
backup_executar restaurar "$1"
