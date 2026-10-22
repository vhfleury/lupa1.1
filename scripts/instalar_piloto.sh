#!/usr/bin/env bash
# Instalacao do Lupa do zero (Etapa 8.1): torna executavel a secao 2 do docs/operacao.md.
# Idempotente: cada passo confere se ja foi feito; passos que sobrescrevem algo pedem confirmacao.
#
#   bash scripts/instalar_piloto.sh            producao (perfil docker-compose.prod.yml)
#   bash scripts/instalar_piloto.sh --dev      desenvolvimento (so docker-compose.yml)
#   LUPA_SIM=1 ...                             responde "sim" as confirmacoes (nao as perguntas
#                                              de valor nem as partes do Vault)
#
# Passos: 1 pre-requisitos e disco · 2 .env (pergunta os valores, gera os segredos aleatorios,
# nunca os mostra) · 3 pastas de dados, backup e segredos · 4 build · 5 Vault (init/unseal e
# AppRole; em producao 3 partes, limiar 2) · 6 subida completa · 7 migracoes · 8 usuario de banco
# restrito · 9 administrador · 10 conferencia (scripts/conferir_piloto.py).
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PYTHON:-python3}"
command -v "$PY" >/dev/null 2>&1 || PY=python
MODO=producao
if [ "${1:-}" = "--dev" ]; then MODO=desenvolvimento; fi
if [ "$MODO" = producao ]; then
  export COMPOSE_FILE=docker-compose.yml:docker-compose.prod.yml
  export LUPA_COMPOSE="-f docker-compose.yml -f docker-compose.prod.yml"
fi
MIN_LIVRE_GB=15

passo() { printf '\n== %s ==\n' "$*"; }
confirmar() {
  if [ "${LUPA_SIM:-0}" = "1" ]; then return 0; fi
  local r; read -r -p "$1 [s/N] " r; [ "$r" = "s" ] || [ "$r" = "S" ]
}
valor_env() { grep -E "^$1=" .env 2>/dev/null | tail -n 1 | cut -d= -f2- || true; }
definir_env() {
  # definir_env CHAVE VALOR: troca ou acrescenta a linha no .env, sem eco do valor.
  "$PY" - "$1" "$2" <<'PYEOF'
import sys
from pathlib import Path
chave, valor = sys.argv[1], sys.argv[2]
p = Path(".env")
linhas = p.read_text(encoding="utf-8").splitlines() if p.exists() else []
saida = [l for l in linhas if l.split("=", 1)[0].strip() != chave] + [f"{chave}={valor}"]
p.write_bytes(("\n".join(saida) + "\n").encode("utf-8"))
PYEOF
}
aleatorio() { "$PY" -c "import secrets; print(secrets.token_urlsafe(${1:-24}))"; }
perguntar() {
  # perguntar CHAVE "texto" [padrao]: so pergunta se o .env ainda nao tem valor proprio.
  local atual; atual=$(valor_env "$1")
  if [ -n "$atual" ] && ! grep -qxF "$1=$atual" .env.example; then return 0; fi
  local r; read -r -p "$2 [${3:-}]: " r; definir_env "$1" "${r:-${3:-}}"
}
segredo() {
  # segredo CHAVE: gera valor aleatorio se ainda for o ficticio do .env.example ou vazio.
  local atual; atual=$(valor_env "$1")
  if [ -z "$atual" ] || grep -qxF "$1=$atual" .env.example; then
    definir_env "$1" "$(aleatorio)"; echo "  $1: gerado"
  else echo "  $1: mantido"; fi
}

passo "1. pre-requisitos ($MODO)"
docker compose version >/dev/null || { echo "Docker Compose v2 nao encontrado" >&2; exit 1; }
livre_gb=$(df -Pk . | awk 'NR==2 {print int($4/1024/1024)}')
echo "  disco livre: ${livre_gb} GB"
[ "$livre_gb" -ge "$MIN_LIVRE_GB" ] || { echo "abaixo de $MIN_LIVRE_GB GB livres: pare" >&2; exit 1; }

passo "2. arquivo .env"
if [ ! -f .env ]; then
  cp .env.example .env; chmod 600 .env; echo "  .env criado a partir do .env.example"
elif ! confirmar "  .env ja existe; completar so o que falta (nada e apagado)?"; then
  echo "  .env mantido como esta"
fi
chmod 600 .env 2>/dev/null || true
definir_env LUPA_AMBIENTE "$MODO"
for chave in POSTGRES_PASSWORD LUPA_MINIO_SECRET_KEY LUPA_DB_SENHA_APP LUPA_METRICAS_TOKEN; do
  segredo "$chave"
done
if [ "$(valor_env LUPA_MINIO_ACCESS_KEY)" = "lupa-minio-ficticio" ]; then
  definir_env LUPA_MINIO_ACCESS_KEY "lupa-$(aleatorio 6)"
fi
# A URL do dono (scripts e migracoes) repete a senha: refeita a partir das variaveis.
definir_env LUPA_DATABASE_URL "postgresql+psycopg://$(valor_env POSTGRES_USER):$(valor_env POSTGRES_PASSWORD)@db:5432/$(valor_env POSTGRES_DB)"
if [ "$MODO" = producao ]; then
  definir_env API_PORTA_HOST ""
  perguntar LUPA_DOMINIO "Dominio publico (ex.: lupa.tribunal.jus.br)" ""
  perguntar LUPA_TLS_MODO "Certificado: acme (automatico) ou fornecido" "acme"
  if [ "$(valor_env LUPA_TLS_MODO)" = "acme" ]; then
    perguntar LUPA_ACME_EMAIL "E-mail de contato do ACME" ""
  else
    perguntar LUPA_TLS_CERT "Caminho do certificado (PEM, cadeia completa)" ""
    perguntar LUPA_TLS_CHAVE "Caminho da chave privada (PEM)" ""
  fi
  perguntar LUPA_DADOS_DIR "Pasta dos dados (outro disco)" "/srv/lupa/dados"
  perguntar LUPA_BACKUP_DIR "Pasta dos backups (OUTRO disco)" "/srv/lupa-backup/backups"
  perguntar LUPA_BACKUP_CHAVES_DIR "Pasta das chaves de backup (fora da de backup)" "/srv/lupa-chaves"
fi
perguntar LUPA_ADMIN_USUARIO "Usuario do administrador inicial" "admin"
if [ -z "$(valor_env LUPA_ADMIN_SENHA)" ] || grep -qxF "LUPA_ADMIN_SENHA=$(valor_env LUPA_ADMIN_SENHA)" .env.example; then
  read -r -s -p "Senha inicial do administrador (vazio = gerar e mostrar uma vez): " s; echo
  if [ -z "$s" ]; then s=$(aleatorio 18); echo "  senha inicial gerada (anote AGORA, sera trocada no 1o acesso): $s"; fi
  definir_env LUPA_ADMIN_SENHA "$s"; s=""
fi

passo "3. pastas"
SEG="${LUPA_SEGREDOS_DIR:-./.segredos}"
mkdir -p "$SEG" && chmod 700 "$SEG"
printf '%s' "$(valor_env LUPA_METRICAS_TOKEN)" >"$SEG/metricas_token"
[ -f "$SEG/grafana_senha" ] || aleatorio 18 | tr -d '\n' >"$SEG/grafana_senha"
chmod 600 "$SEG"/* 2>/dev/null || true
# O Prometheus (usuario 65534) e o Grafana (472) leem os segredos montados.
for pasta in "$(valor_env LUPA_BACKUP_DIR)" "$(valor_env LUPA_BACKUP_CHAVES_DIR)"; do
  if [ -n "$pasta" ]; then mkdir -p "$pasta" && chmod 700 "$pasta"; fi
done
if [ "$MODO" = producao ]; then
  DADOS=$(valor_env LUPA_DADOS_DIR)
  # dono de cada volume = usuario da imagem (db 70, minio 10002, vault 100, caddy 10001,
  # prometheus 65534, grafana 472)
  for par in db:70 minio:10002 vault:100 caddy:10001 prometheus:65534 grafana:472; do
    d="$DADOS/${par%%:*}"; u="${par##*:}"
    if [ ! -d "$d" ]; then
      if confirmar "  criar $d (dono $u)?"; then sudo install -d -o "$u" -g "$u" -m 700 "$d"; fi
    fi
  done
fi

passo "4. build das imagens"
docker compose build

passo "5. Vault"
docker compose up -d vault
for _ in $(seq 1 30); do
  rc=0; docker compose exec -T vault vault status >/dev/null 2>&1 || rc=$?
  if [ "$rc" -ne 1 ]; then break; fi; sleep 2
done
if docker compose exec -T vault vault status >/dev/null 2>&1; then echo "  ja destravado"
else bash scripts/vault_inicializar.sh; fi
if [ "$(valor_env LUPA_VAULT_SECRET_ID)" = "preenchido-pelo-script-vault-inicializar" ]; then
  bash scripts/vault_inicializar.sh
fi

passo "6. subida completa"
docker compose up -d --wait

passo "7. migracoes"
docker compose exec -T api alembic -c src/lupa/migrations/alembic.ini upgrade head
docker compose exec -T api alembic -c src/lupa/migrations/alembic.ini current

passo "8. usuario de banco restrito"
docker compose exec -T api python scripts/criar_usuario_banco.py
docker compose up -d --wait api worker

passo "9. administrador"
docker compose exec -T api python scripts/criar_admin.py
if confirmar "  apagar LUPA_ADMIN_SENHA do .env agora (recomendado, depois de anotada)?"; then
  "$PY" - <<'PYEOF'
from pathlib import Path
p = Path(".env")
linhas = [l for l in p.read_text(encoding="utf-8").splitlines() if not l.startswith("LUPA_ADMIN_SENHA=")]
p.write_bytes(("\n".join(linhas) + "\n").encode("utf-8"))
PYEOF
fi

passo "10. conferencia"
"$PY" scripts/conferir_piloto.py || true
echo
echo "Proximos passos manuais: primeiro acesso do administrador (TOTP), gabinete, desembargador"
echo "(docs/operacao.md, secao 2.2, passos 6 a 8). Monitoramento: docker compose --profile monitoramento up -d"
