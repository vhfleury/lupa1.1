# Relatório da Etapa 4F.2 — Extratores por tipo de peça

## O que foi feito

- Pacote `src/lupa/ingestao/eventos/`, um módulo por tipo de peça relevante:
  `denuncia.py`, `recebimento.py`, `decisao_prisao.py`, `sentenca.py`, `certidao.py`,
  `recurso.py`; motor comum em `base.py` (regra de gatilho e janela) e leitura dos padrões em
  `padroes.py`.
- Padrões versionados em `src/lupa/ingestao/dados/eventos.yaml` (versão `4f.1`): para cada tipo
  de fato, os tipos de peça, os gatilhos (sobre o texto dobrado), a janela até a data, a
  confiança, `ultima` e `por_reu`. Peça `outros` passa só pelas regras que a listam.
- Tabela mínima de tipos penais em `src/lupa/ingestao/dados/tipos_penais.yaml` (versão 1,
  "a confirmar pelo gabinete"): arts. 121, 129, 147, 155, 157, 171, 180 do CP, 33 da Lei
  11.343, 14 da Lei 10.826 e 306 do CTB, pena máxima do caput em meses.
- Fatos por peça:

| Peça | Fatos |
| --- | --- |
| Denúncia | `data_fato`, `data_nascimento_reu` (por réu), `data_denuncia`, `pena_maxima_abstrata` |
| Recebimento | `data_recebimento_denuncia` |
| Decisão de prisão | `data_decretacao_preventiva` ou `data_revisao_preventiva`, pelo verbo |
| Sentença | `data_sentenca`, `reincidente`; pena máxima pelo artigo só como reserva |
| Certidão | `data_publicacao_sentenca`, `data_intimacao_defesa`, `data_intimacao_mp`, `data_intimacao_reu` (por réu) |
| Recurso | `tipo_recurso` `{"tipo", "recorrente"}`, `data_interposicao_recurso` |

- Pena máxima: a pena transcrita na denúncia ("de 1 (um) a 4 (quatro) anos", "de 3 (três) meses
  a 1 (um) ano") vale, com confiança 0,9; sem ela, a tabela pelo artigo citado (0,6); pena e
  tabela divergentes, 0,5.
- Recorrente do recurso: "por seu defensor"/defensoria no começo da peça é defesa; "Ministério
  Público" é MP; sem pista, a origem da peça (4E.5); sem recorrente, `tipo_recurso` não é gerado.
- `tests/ingestao/test_eventos.py`: cada extrator roda sobre as peças do seu tipo em três
  processos sintéticos gerados pelo 4B (sementes 1101 a 1103, com preventiva) e precisa devolver
  exatamente os eventos do gabarito daquelas peças; mais casos de pena, recurso, decretação ×
  revisão, peça `outros` e ano de 2 dígitos.

## Decisões não previstas

- `data_denuncia` (existe em `TipoFato` e no gabarito) também é extraída: linha "Local, data."
  no fim da denúncia (`ultima: true`).
- Pena aplicada não é gravada: `TipoFato` não tem tipo para ela e nenhuma validação a usa. Fica
  registrada aqui; entra se o catálogo ganhar a prescrição pela pena aplicada (revisão 2, item 3).
- Gatilho de `data_sentenca` aceita vírgula no lugar do ponto ("Publique-se, Registre-se,"), erro
  de OCR visto na medição da 4F.9.
- Fatos de um tipo por réu: só nascimento e intimação do réu (os que dependem da pessoa).

## O que ficou de fora

- Causas de aumento e diminuição e concurso de crimes na pena máxima (limitação já documentada
  nas validações).
- Recurso do assistente de acusação e prazos especiais (o catálogo não conhece).

## Comandos e saída resumida

```
docker compose run --rm api python -m pytest tests/ingestao/test_eventos.py --no-cov -q
23 passed
```

## Checklist

| Item | Evidência |
| --- | --- |
| Denúncia: data do fato, pena (tabela YAML "a confirmar"), nascimento, qualificação | `test_extrator_do_tipo_acha_os_eventos_do_gabarito[denuncia]`, `test_pena_maxima_pelo_texto_pela_tabela_e_divergente`, 4F.5 |
| Recebimento | `[recebimento]` |
| Decretação × revisão pelo texto | `[decisao_prisao]`, `test_decretacao_e_revisao_sao_distinguidas_pelo_texto` |
| Sentença (data; pena aplicada registrada como fora) | `[sentenca]`, `test_pena_da_sentenca_so_vale_sem_pena_da_denuncia` |
| Certidão: publicação e três intimações | `[certidao]` |
| Recurso: `{"tipo", "recorrente"}` e interposição | `[recurso]`, `test_recurso_especie_e_recorrente` |
| Cada extrator com testes nos textos sintéticos do tipo | 6 tipos × 3 processos, igualdade exata com o gabarito |
