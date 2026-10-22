# Relatório da Etapa 4F.7 — Execução do catálogo

## O que foi feito

- `lupa/ingestao/eventos/etapa.py`: ao fim da ingestão (no worker, depois do índice e dos
  fatos), lê os fatos gravados do processo (`listar_fatos_por_processo`), monta o modelo
  (`para_modelo`), roda `executar_catalogo(materia do processo, data de hoje)`, converte com
  `para_dominio` e grava com `salvar_achado`. Com mais de um réu, uma rodada por réu, com
  `valores.reu_id`.
- `repositorio_eventos.gravar_achados`: achados são imutáveis; só grava quando o resultado, os
  valores, a explicação ou a versão do catálogo diferem do último achado da mesma validação (e
  réu). `achados_vigentes` devolve o último de cada validação.
- `processo.status` vai para `pronto` (já era feito por `atualizar_status_processo` ao
  encerrar o job; agora com fatos e achados gravados antes).
- `GET /processos/{id}/achados` (`src/lupa/api/rotas/achados.py`): `{processo_id, status,
  achados}`; auditada por `auditar_rota(processo_aberto, conteudo=True)`; outro gabinete recebe
  404.
- `lupa/sinteticos/achados.py`: comparação com o `resultado_esperado` do gabarito (resultado e
  valores sem as chaves de id).

## Decisões não previstas

- O worker roda o catálogo com a data de hoje (`deps.relogio`); a comparação com o gabarito usa
  a `data_referencia` do gabarito (`achados_do_processo(..., referencia)`), porque prescrição e
  preventiva dependem da data de referência.
- "Valores principais" = todos os valores do achado menos os ids (datas, prazos, vencimento,
  intervalos, faixa do art. 109, redução do art. 115, cadeia da preventiva). É mais estrito que
  comparar só o resultado.

## O que ficou de fora

- Reexecução automática do catálogo quando o assessor corrige um fato (Etapa 6).

## Comandos e saída resumida

```
docker compose run --rm -v lupa_medicao4e:/m api python scripts/medir_extracao.py eventos --destino /m
consolidado.achados: iguais 78/90 (86,7%), resultado igual 81/90 (90,0%)
```

Por processo (iguais nos três cenários, que têm as mesmas folhas):

| Processo | Achados iguais | Diferença e causa |
| --- | --- | --- |
| semente_01, 02, 03, 06, 07, 08, 10 | 3/3 | — |
| semente_04 | 1/3 | tempestividade `atencao` → `verificar` (intimação da defesa perdida: página digitalizada forte sem o trecho); preventiva `atencao` → `verificar` (OCR leu 2020 em vez de 2017 numa revisão: data posterior à referência) |
| semente_05 | 2/3 | preventiva `conforme` → `atencao` (uma revisão perdida no OCR forte; o intervalo sem ela passa de 90 dias) |
| semente_09 | 2/3 | preventiva `atencao` = `atencao`, valores diferentes (uma revisão perdida no OCR forte) |

Todas as diferenças vêm de páginas digitalizadas com degradação forte. Nos dois casos de
`verificar`, o sistema não concluiu errado: pediu conferência.

## Checklist

| Item | Evidência |
| --- | --- |
| `para_modelo` + `executar_catalogo` + `para_dominio` + `salvar_achado` ao fim da ingestão | `etapa.processar_eventos`; `test_worker_grava_reus_fatos_e_achados_sem_nome_real` (3 achados) |
| `processo.status` atualizado | mesmo teste: `pronto` |
| `GET /processos/{id}/achados` auditada, isolada por gabinete | mesmo teste (evento `processo_aberto` com o caminho); `test_rota_de_achados_isolada_por_gabinete` |
| Achados batem com o `resultado_esperado` | sintético dos testes: 3/3 (`test_achados_batem_com_o_resultado_esperado_do_gabarito`); dez processos × três cenários: 78/90 iguais (86,7%), resultado igual 81/90 (90,0%); ponta a ponta pelo worker na 4F.9 |
