# Relatório da Etapa 4F.4 — Validação cruzada

## O que foi feito

- Toda data extraída é reconferida por `lupa.ingestao.datas.reconferir` contra o trecho da
  evidência (texto original). A reconferência não usa as expressões de busca: escreve a data em
  todas as formas aceitas (numérica com `/`, `.` e `-`, com e sem zero, ano de 4 e de 2 dígitos,
  extenso com dia e ano em algarismos ou por extenso, abreviada) e procura alguma delas no trecho
  dobrado, exigindo que não haja letra ou dígito colado nas pontas.
- Data que não está literalmente no trecho é rejeitada: `relatorio.eventos.datas_rejeitadas`
  por tipo e log `data_rejeitada` com `tipo`, `regra` e `pagina_id` (nenhum texto).
- Conflito entre peças: tipos que devem ser únicos (todos menos `data_revisao_preventiva`) com
  valores diferentes geram todos os fatos, cada um com a confiança multiplicada por 0,5, e o tipo
  entra em `relatorio.eventos.conflitos`; o motor de validações já devolve `verificar` com o
  conflito em `valores.conflitos`.

## Decisões não previstas

- A comparação de conflito é por réu (dois nascimentos de réus diferentes não conflitam).

## O que ficou de fora

- A reconferência não pega o erro de OCR que troca um dígito por outro (o literal errado está no
  texto). Foi a causa das 2 datas erradas da 4F.9 (semente_04, nível forte de degradação). Mitigação
  possível depois: cruzar a data com o dia da semana ou com a data da peça (4E.6).

## Comandos e saída resumida

```
docker compose run --rm api python -m pytest tests/ingestao/test_eventos.py -k "rejeitada or conflito" --no-cov -q
2 passed
```

## Checklist

| Item | Evidência |
| --- | --- |
| Data reconferida por expressão independente | `reconferir` escreve a data, não a interpreta; `test_reconferir_exige_a_data_literal_no_trecho` |
| Data que não existe literalmente é rejeitada | `test_data_que_nao_existe_literalmente_e_rejeitada_e_logada_sem_conteudo` (0 fatos, 1 rejeição) |
| Registrada em log sem conteúdo | mesmo teste: chaves do log = `event`, `log_level`, `tipo`, `regra`, `pagina_id`; a data do texto não aparece |
| Conflito: dois fatos, confiança reduzida, `verificar` | `test_conflito_entre_pecas_gera_os_dois_fatos_com_confianca_reduzida` (0,475 cada; prescrição `verificar`) |
