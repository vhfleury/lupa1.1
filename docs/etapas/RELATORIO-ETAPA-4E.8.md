# Relatório da Etapa 4E.8 — Reclassificação manual

## O que foi feito

- `POST /processos/{id}/pecas/{peca_id}/reclassificar` com `tipo`, `origem`, `dividir_em`
  (página do arquivo onde começa a parte nova; `tipo`/`origem` valem para ela) ou `unir_com`
  (peça vizinha vigente). Grava linhas novas `metodo = manual`, confiança 1,
  `substitui_peca_id` (e `classificacao.substitui` com todas as substituídas na união), desliga
  `vigente` nas anteriores (nada mais é alterado nelas) e registra `peca_reclassificada` (ação
  nova no enum) por peça nova. Exige permissão de anotar; 422 para pedido incoerente.
- `GET /processos/{id}/pecas/{peca_id}` devolve classificação e histórico.

## Decisões não previstas

- Ação nova `peca_reclassificada` em vez de `fato_corrigido` (peça não é fato).
- Colunas novas `vigente`, `flags`, `classificacao` além de `substitui_peca_id`: a união
  substitui duas peças e precisa da lista; o índice filtra por `vigente`.
- A data acompanha a parte que contém a página da evidência; a outra parte fica sem data.

## Checklist

| Critério | Evidência |
|---|---|
| Divisão e união com histórico | `test_reclassificar_tipo_origem_dividir_e_unir_preserva_historico_e_audita` (4 eventos, 4 linhas novas, histórico com as três anteriores) |
| Índice reflete a correção | mesmo teste |
| Pedidos inválidos | `test_reclassificacao_invalida_e_recusada` |

## Comandos

```
docker compose up -d --build --wait
docker compose exec api alembic -c src/lupa/migrations/alembic.ini upgrade head   # 0006 (head)
docker compose exec api bash scripts/verificar.sh
```
Saída final no relatório 4E.10.
