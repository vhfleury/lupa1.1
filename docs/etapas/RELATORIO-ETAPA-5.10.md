# Relatório da Etapa 5.10 — Dossiê gerado

## O que foi feito

- `src/lupa/agente/dossie.py`: dossiê em esquema fixo pydantic (`Dossie`: ficha com réus
  pseudonimizados, índice de peças, linha do tempo com página e trecho, alertas de saneamento,
  achados), montado sem modelo. `resumo_peca` opcional pelo modelo, sem ferramentas, até 2 frases,
  com citação conferida obrigatória e `rotulo = "gerado"`.
- `GET /processos/{id}/dossie` (`?resumos=true`), auditada como `processo_aberto`.
- Testes: dossiê do processo semeado; resumo aceito e descartado (sem citação, 3 frases); dossiê do
  processo sintético ingerido contra o gabarito (tipos e extensão das peças iguais, linha do tempo
  ≥ 95% igual aos eventos do gabarito, achados = vigentes); nenhuma frase livre fora de `trecho`,
  `explicacao` (template), valores do motor e blocos `gerado`.

## Decisões não previstas

- As páginas do arquivo diferem das folhas do gabarito por deslocamento constante (capa/índice); o teste confere tipos, extensões e que o deslocamento é único.

## O que ficou de fora

- Resumo narrativo do processo inteiro: fora (só por peça).

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
