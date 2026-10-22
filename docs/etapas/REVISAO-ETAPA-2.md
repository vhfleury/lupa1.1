# Revisão — Etapa 2 (motor de validações e as três validações do piloto)

20 de outubro de 2026 · revisor

## 1. Verificação executada

A Etapa 3 estava em execução no mesmo diretório, então a imagem não foi reconstruída. A verificação foi feita no host, com o venv da Etapa 0, limitada ao escopo da etapa (o pacote não depende de banco):

```
ruff check src/lupa/validacoes tests/validacoes
ruff format --check src/lupa/validacoes tests/validacoes
mypy src/lupa/validacoes tests/validacoes
pytest tests/validacoes --no-cov
python -m lupa.validacoes --fatos docs/exemplos/fatos.json --materia criminal --referencia 2026-10-20
```

Saída: ruff sem avisos, 19 arquivos formatados, mypy sem erros em 19 arquivos, 72 testes passaram. A CLI devolve os três achados com `fatos_usados`, `valores` rastreáveis (data, tipo, fato_id, evidencia_id) e explicação por template.

A verificação completa com `scripts/verificar.sh` e imagem reconstruída fica para a revisão da Etapa 3.

## 2. Critérios de aceite

| Critério | Resultado | Evidência |
| --- | --- | --- |
| Funções puras, mesma entrada produz o mesmo achado | ok | `test_validacoes_sao_puras_mesma_entrada_mesmo_achado`; dados carregados com `lru_cache`, sem estado |
| Achado `atencao` ou `conforme` traz todas as datas com id de fato e de evidência | ok | `rastrear()` em `apoio.py`; `test_achados_conclusivos_trazem_datas_com_fato_e_evidencia` |
| Nenhuma validação importa de ingestão, agente ou API | ok | teste por AST; o executor também excluiu `lupa.dominio`, o que é correto enquanto o adaptador não existe |
| Dados jurídicos só em YAML com `versao` e `fonte` | ok | seis arquivos, todos validados por pydantic com `extra="forbid"`; teste por AST confirma ausência de números de prazo em `.py` |
| Explicações por template com teste da frase inteira | ok | dez templates `.txt`; testes `test_explicacao_*_com_frase_inteira` nas três validações |
| Motor sobrevive a exceção em uma validação | ok | `_executar_protegido` devolve `verificar` com `motor_erro`; teste dedicado |
| CLI funciona com o exemplo | ok | execução acima e `test_cli_imprime_achados_do_exemplo` |
| `docs/validacoes.md` em linguagem simples | ok | fatos usados, regra numerada, base legal, o que conferir à mão e limitações, por validação |

Casos de teste mínimos do plano: todos presentes, nomeados pelo comportamento. Tabela do art. 109 conferida contra o texto legal: faixas e bordas corretas (pena de 12 meses cai no inciso V, 24 meses no V, 25 no IV).

## 3. Regras comuns

- Estilo, docstrings, tipagem: atendidos. Nenhum `print` fora da CLI.
- Dependência nova: `pyyaml` e `types-PyYAML`, com `requirements*.txt` regenerados com hashes. Dentro do permitido.
- Nenhum arquivo de outra etapa alterado.

## 4. Decisões do executor que o revisor endossa

- Esquemas de entrada locais em `modelo.py` com os mesmos nomes da Etapa 1. Necessário para o paralelismo.
- `tipo_recurso` com `{"tipo", "recorrente"}`: o modelo de dados não tinha quem recorre, e o prazo depende disso.
- Tabelas injetáveis como terceiro argumento: permite feriados sintéticos nos testes sem tocar nos YAML.
- Regras de borda declaradas e marcadas para confirmação do gabinete, em vez de escolhidas em silêncio.

## 5. Decisão

**Aprovado.**

## 6. Trabalho pendente gerado por esta etapa

1. **Adaptador validações ↔ domínio (pequeno, antes da Etapa 4).** O executor diz que basta trocar o import, mas não é exato: em `lupa.dominio.esquemas`, `id` é `UUID` e não `str`, `evidencias` é tupla, `Achado` exige `processo_id` e `id`, e `Fato.valor` volta do banco com datas como string ISO. É preciso uma função `para_modelo(fatos_dominio) -> ModeloProcesso` e outra `para_dominio(achado, processo_id) -> Achado`, com teste de ida e volta usando a fixture `fabrica_fato` do `tests/conftest.py`. Só então os esquemas locais de `modelo.py` podem ser removidos.
2. **Tempestividade quando a defesa recorre exige as duas intimações (réu e defensor).** Faltando uma, o resultado é `verificar`. É a leitura conservadora do art. 392 e está documentada, mas vai gerar muitos "verificar" em réu solto intimado só pelo defensor. O gabinete decide se mantém.
3. **Prescrição após a sentença usa a pena em abstrato.** Depois da sentença condenatória, a prescrição que importa costuma ser pela pena aplicada (retroativa e intercorrente). Como a pena em abstrato é maior ou igual à aplicada, o cálculo atual nunca gera alarme falso, mas pode deixar de apontar prescrição. A limitação está no guia; a validação pela pena aplicada é candidata à próxima rodada do catálogo.
4. **Calendários provisórios.** `tjgo.yaml` está marcado como provisório e `nacionais.yaml` cobre só 2026. Antes do piloto com autos reais, o gabinete substitui pelos calendários oficiais e o recesso do art. 798-A recebe as exceções de réu preso.
5. **Súmula 310 do STF e prazos especiais** não são aplicados, e o guia avisa. Entram como regras de dados quando o gabinete confirmar o texto.
