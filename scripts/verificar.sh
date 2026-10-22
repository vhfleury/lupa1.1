#!/usr/bin/env bash
# Roda lint, tipagem e testes em sequencia; falha no primeiro erro.
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PYTHON:-python}"
echo "== ruff check ==";        "$PY" -m ruff check src tests
echo "== ruff format --check =="; "$PY" -m ruff format --check src tests
echo "== mypy --strict ==";     "$PY" -m mypy src tests
echo "== pytest ==";            "$PY" -m pytest
echo "== ponta a ponta da ingestao (integracao, sem skip) =="
LUPA_EXIGIR_INTEGRACAO=1 "$PY" -m pytest -m integracao tests/ingestao/test_ponta_a_ponta.py --no-cov -q
echo "== regressao de injecao (corpus 4B.8, metas da 4D.5, sem skip) =="
LUPA_EXIGIR_INTEGRACAO=1 LUPA_METRICAS_INJECAO="${LUPA_METRICAS_INJECAO:-/tmp/metricas_injecao.json}"   "$PY" -m pytest -m injecao tests/ingestao/test_injecao_corpus.py --no-cov -q
"$PY" -c "import json,sys; m=json.load(open(sys.argv[1])); print({k: m[k] for k in ('versoes','recall','falso_positivo','injecoes_textuais','injecoes_detectadas','paginas_semente_01')})" "${LUPA_METRICAS_INJECAO:-/tmp/metricas_injecao.json}"
# Etapa 6: lint, typecheck e testes unitarios do front, sempre em conteiner. No host (com docker),
# reconstroi o estagio `verificacao` da imagem do front. Dentro do conteiner da API (sem node nem
# docker), confere o carimbo /verificacao.json do servico `front`: a imagem so existe se os tres
# passos passaram no build.
echo "== front =="
if command -v docker >/dev/null 2>&1 && [ -f front/package.json ]; then
  docker build --target verificacao -q front >/dev/null && echo "front: lint, typecheck e testes ok (build da imagem)"
elif command -v npm >/dev/null 2>&1 && [ -f front/package.json ]; then
  (cd front && npm ci --no-audit --no-fund && npm run verificar)
else
  "$PY" -c "import json,sys,urllib.request; c=json.load(urllib.request.urlopen(sys.argv[1], timeout=5)); assert c.get('verificado') is True and c.get('passos')==['lint','typecheck','test'], c; print('front: carimbo do build ok', c['fontes_sha256'][:12], c['em'])" "${LUPA_FRONT_URL:-http://front:8080}/verificacao.json"
fi
# Etapa 6.10: cabecalhos de seguranca do proxy (CSP, HSTS, Permissions-Policy, COOP...). Falha se
# faltar algum ou se a CSP afrouxar; com o proxy fora do ar so avisa (LUPA_EXIGIR_CABECALHOS=1 exige).
echo "== cabecalhos de seguranca =="
"$PY" scripts/verificar_cabecalhos.py --url "${LUPA_PROXY_URL:-https://proxy:8443}" ${LUPA_EXIGIR_CABECALHOS:+--exigir}
# Etapa 5.8: suite de injecao do agente sobre autos ingeridos (cliente falso roteirizado), sem skip.
echo "== suite de injecao do agente (Etapa 5.8, sem skip) =="
LUPA_EXIGIR_INTEGRACAO=1 LUPA_METRICAS_AGENTE="${LUPA_METRICAS_AGENTE:-/tmp/metricas_agente.json}" "$PY" -m pytest -m agente tests/agente --no-cov -q
"$PY" -c "import json,sys; m=json.load(open(sys.argv[1])); print({k: m[k] for k in ('versao_modelo','versao_prompt','cenarios','achados_suprimidos','achados_criados','vazamentos','embutidas_executadas','respostas_bloqueadas')})" "${LUPA_METRICAS_AGENTE:-/tmp/metricas_agente.json}"
