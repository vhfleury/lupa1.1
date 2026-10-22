# Relatório da Etapa 5.6 — Conferência de citações

## O que foi feito

- `src/lupa/agente/citacoes.py`: esquema estrito (uma nova tentativa quando a saída vem fora do
  esquema); bloqueio da resposta inteira por instrução refletida (`padroes_instrucao.yaml` da
  ingestão e URLs) ou identificador de outro processo (CNJ diferente ou UUID que não é do
  processo); cada citação conferida (página do processo, trecho literal no segmento cujo hash veio,
  ou hash do próprio trecho com o trecho literal no texto da página). Citação inválida é removida,
  contada em `conversa.citacoes_descartadas` e avisada; sem nenhuma válida, `sem_evidencia`.
- Testes em `test_citacoes.py` e `test_chat_api.py` (citação inventada chega sem a citação, com
  aviso e contador por conversa).

## Decisões não previstas

- Resposta bloqueada vira `chamada_modelo` com resultado `bloqueada` e evento de auditoria com resultado `bloqueado` (o registro do incidente).

## O que ficou de fora

- Marcar o processo `em revisão` no incidente (prompt-injection.md §8): o status do processo é da ingestão; fica para o painel da Etapa 6.

## Comandos e saída resumida

```
docker compose up -d --build --wait
docker compose exec api alembic -c src/lupa/migrations/alembic.ini upgrade head
docker compose exec api bash scripts/verificar.sh
```

```
== ruff check ==
All checks passed!
== ruff format --check ==
234 files already formatted
== mypy --strict ==
Success: no issues found in 234 source files
== pytest ==
test session starts
TOTAL                                                     9039    116    99%
Required test coverage of 90% reached. Total coverage: 98.72%
766 passed, 1 skipped, 3 deselected in 499.00s (0:08:19)
== ponta a ponta da ingestao (integracao, sem skip) ==
1 passed in 4.31s
== regressao de injecao (corpus 4B.8, metas da 4D.5, sem skip) ==
2 passed in 185.85s (0:03:05)
{'versoes': {'saneamento': '4d.1', 'homoglifos': '1', 'padroes_instrucao': '1', 'idiomas': '1', 'densidade': '1'}, 'recall': 1.0, 'falso_positivo': 0.0, 'injecoes_textuais': 16, 'injecoes_detectadas': 16, 'paginas_semente_01': 196}
== front ==
front: carimbo do build ok ad0b6d353349 2026-10-21T11:27:16.764Z
== suite de injecao do agente (Etapa 5.8, sem skip) ==
9 passed, 54 deselected in 50.07s
{'versao_modelo': 'cliente_falso_roteirizado', 'versao_prompt': '1:1c739e84a6337f5a', 'cenarios': 14, 'achados_suprimidos': 0, 'achados_criados': 0, 'vazamentos': 0, 'embutidas_executadas': 0, 'respostas_bloqueadas': 10}
```
