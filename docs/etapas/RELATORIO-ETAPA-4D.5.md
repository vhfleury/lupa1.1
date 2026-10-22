# Relatório da Etapa 4D.5 — Padrões de instrução

## O que foi feito

- `src/lupa/ingestao/dados/padroes_instrucao.yaml` (versão 1), português e inglês, 19 padrões em 5 categorias: `dirigido_a_sistema`, `ignorar_instrucoes`, `revelar_dados`, `alterar_resultado` e `marcacao_de_prompt` (`system:`, tokens de chat, `[INST]`, cabeçalhos e tags).
- `deteccao.encontrar_padroes` roda sobre o normalizado em minúsculas e sem acentos (`dobrar`, mesmo tamanho, offsets preservados). Cada ocorrência vira trecho `{inicio, fim, inicio_original, fim_original, hash, categoria, padrao, origem}` em `pagina.trechos_suspeitos`; nada é removido. `FlagPagina.PADRAO_INSTRUCAO`.
- Os mesmos padrões classificam textos ocultos (4D.1), metadados (4D.2) e blocos decodificados (4D.4).

## Decisões não previstas

- Os padrões exigem destinatário de máquina, pedido de ignorar instruções, regras ou laudo, pedido de revelar dados ou ordem dirigida (`declare`, `registre que`, `classifique ... como`), nunca imperativo genérico: peças legítimas usam "registre-se", "considere-se", "requer seja declarada".

## Métricas (versão 1 dos YAML)

| Métrica | Meta | Medido |
| --- | --- | --- |
| Recall nas injeções textuais do corpus | ≥ 90% | **100%** (16/16; as 2 de `imagem_com_texto` não chegam a texto algum, ver 4D.10) |
| Falso positivo, páginas de `semente_01` | ≤ 5% | **0%** (0/196) |
| Falso positivo, frases legítimas do teste | ≤ 5% | **0%** (0/20: "o sistema processual deve", "ignora-se a tese", "assistente de acusação", "o modelo de certidão", citação em inglês, "habeas corpus", "in dubio pro reo", "requereu seja declarada a prescrição", "Registre-se. Publique-se.", rodapé com hash e outras) |

Testes: `test_saneamento.py::test_padroes_detectam_cada_injecao_textual` (12 instruções, incluindo marcações de chat) e `::test_frases_legitimas_nao_disparam_padroes_nem_idioma`.

## Comandos e saída

```
docker compose up -d --build --wait
docker compose exec api bash scripts/verificar.sh
```

Saída resumida (21/10/2026): ruff e `ruff format --check` limpos; `mypy --strict` sem erros em 165 arquivos; pytest **588 passed, 1 skipped** (o skip é anterior à 4D; eram 551 testes), cobertura **98,66%**; ponta a ponta 1 passed; regressão de injeção 2 passed (159 s), `recall 1.0`, `falso_positivo 0.0`.
