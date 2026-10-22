# Relatório da Etapa 4F.6 — Gravação de fatos

## O que foi feito

- `lupa/ingestao/repositorio_eventos.gravar_fatos`: grava com `salvar_fato` só os fatos cujo id
  ainda não existe, na transação do chamador (um lote por processo, num savepoint do worker).
  Fatos com `status = automatico`, `extraido_por = "regra"` e `versao_extrator` =
  `<versão de eventos.yaml>+tp<versão de tipos_penais.yaml>` (hoje `4f.1+tp1`).
- Idempotência pela chave natural: id do fato = `uuid5(processo, tipo, valor, ids das
  evidências)` e id da evidência = `uuid5(página, início, fim)`. Reprocessar com a mesma versão
  não grava nada.
- Versão nova: `remover_fatos_obsoletos` apaga os fatos automáticos da regra de outra versão,
  exceto os que têm anotação e os substituídos por correção humana (que manteriam a cascata da
  anotação); depois grava os da versão nova.
- Worker: `_gravar_eventos` no fim de `_concluir_extracao`, em `session.begin_nested()`; falha
  vira `relatorio.eventos.erro` sem desfazer páginas e índice.

## Decisões não previstas

- Fato anotado de uma versão antiga cujo valor e evidência continuam iguais não é duplicado na
  versão nova (mesma chave natural): fica o antigo, com a anotação.
- `reu.id` não tem default no banco; o repositório gera o UUID.

## O que ficou de fora

- Gravação em lote com um único `INSERT` (cada fato usa `salvar_fato`, que já é a interface do
  domínio; o maior processo de referência tem 50 fatos).

## Comandos e saída resumida

```
docker compose run --rm api python -m pytest tests/ingestao/test_eventos_banco.py --no-cov -q
8 passed
```

## Checklist

| Item | Evidência |
| --- | --- |
| `salvar_fato` em transação por lote, `automatico`, `regra`, versão do YAML | `test_worker_grava_reus_fatos_e_achados_sem_nome_real` |
| Reprocessar com a mesma versão não duplica | `test_reprocessar_mesma_versao_nao_duplica_e_nova_versao_refaz_so_os_eventos`: 0 gravados, 0 removidos, contagens iguais |
| Versão nova troca os fatos e preserva o anotado | mesmo teste: removidos = total − 1, gravados = total − 1 |
| Falha nos eventos não desfaz a ingestão | `test_falha_nos_eventos_nao_desfaz_paginas_nem_indice` |
