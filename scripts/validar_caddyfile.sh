#!/usr/bin/env bash
# Valida o proxy/Caddyfile nos tres modos de certificado (Etapa 8.1) com `caddy validate` num
# conteiner descartavel da mesma imagem do proxy. Para o modo `fornecido`, gera um certificado
# autoassinado descartavel so dentro do conteiner (nada e gravado no host).
set -euo pipefail
cd "$(dirname "$0")/.."
export MSYS_NO_PATHCONV=1
IMAGEM=caddy:2.8.4-alpine
validar() {
  local modo="$1"; shift
  docker run --rm -v "$PWD/proxy:/etc/caddy:ro" -e LUPA_TLS_MODO="$modo" "$@" \
    -e XDG_DATA_HOME=/tmp/d -e XDG_CONFIG_HOME=/tmp/c "$IMAGEM" sh -c '
      if [ "$LUPA_TLS_MODO" = fornecido ]; then
        mkdir -p /certs && apk add --no-cache openssl >/dev/null 2>&1 &&
        openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes -days 1 \
          -subj "/CN=$LUPA_DOMINIO" -keyout /certs/lupa.key -out /certs/lupa.crt 2>/dev/null
      fi
      saida=$(caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile 2>&1); rc=$?
      echo "$saida" | tail -n 1; exit $rc'
  echo "caddy validate modo=$modo: ok"
}
validar interno
validar acme -e LUPA_DOMINIO=lupa.exemplo.test -e LUPA_ACME_EMAIL=ti@exemplo.test
validar fornecido -e LUPA_DOMINIO=lupa.exemplo.test
