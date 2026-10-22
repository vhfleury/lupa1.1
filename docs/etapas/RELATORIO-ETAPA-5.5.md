# Relatório da Etapa 5.5 — Montagem de contexto e prompts

## O que foi feito

- `src/lupa/agente/contexto.py`: prompt de sistema versionado (`dados/prompt_sistema.md`,
  `versao_prompt = "1:<sha256[:16]>"`), `Delimitador` aleatório por chamada (`<<<AUTOS-hex16>>>`),
  cabeçalho de origem em todo bloco, instrução da tarefa depois do dado, `Pseudonimizador` (nome
  sem caixa e sem acento, espaços flexíveis; CPF com ou sem pontuação) aplicado à pergunta, à ficha
  e a todo resultado de ferramenta; `segmentos` com hash.
- Testes: `test_nome_real_do_reu_nunca_chega_ao_modelo` captura tudo o que o cliente falso recebe
  (prompts e resultados das sete ferramentas) e não encontra nome nem CPF; a suíte 5.8 repete a
  prova nos dois processos ingeridos pela pipeline.

## Decisões não previstas

- O hash citável é o do segmento enviado (linha do texto normalizado e pseudonimizado), porque o modelo não calcula SHA-256; a conferência recalcula os segmentos do texto gravado.

## O que ficou de fora

- Pseudonimização só do nome completo e do CPF; nome parcial (só sobrenome) passa. Fica com a anonimização na origem (TODO da seção 11 dos requisitos).

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
