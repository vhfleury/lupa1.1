# Relatório da Etapa 4E.1 — Sinais de fronteira

## O que foi feito

- `src/lupa/ingestao/sinais_fronteira.py` (funções puras sobre texto e coordenadas gravados):
  cabeçalho/rodapé repetidos descobertos no arquivo (máscaras das 3 primeiras e 3 últimas
  linhas presentes em ≥ 30% das páginas, comparação aproximada para OCR); por página
  `titulo`/`titulo_tipo`/`titulo_secao`/`titulo_linha`, `numero_folha`, `reinicio_numeracao`,
  `assinatura_fim` (tolerante a OCR, recusa o rodapé "Código de autenticação"),
  `protocolo_topo`, `cabecalho`, `altura_linha` (fonte dominante), `margem_esquerda`, `colunas`.
- Lista versionada de títulos em `src/lupa/ingestao/dados/titulos_peca.yaml` (versão 1).
- Migração 0006: `pagina.sinais_fronteira` (JSONB); o worker grava os sinais de todas as páginas
  ao montar o índice (páginas de índice de movimentações recebem `{"indice": true}`).

## Decisões não previstas

- Sinais calculados no processo do worker a partir do texto e das caixas já gravados, não no
  filho do sandbox: evita reabrir o PDF e dá o mesmo resultado para nativo e OCR. A "fonte
  dominante" é a altura mediana das caixas de linha (o nome da fonte não está gravado), e a
  mudança de fonte só conta entre páginas do mesmo tipo (nativo × OCR têm alturas diferentes).
- Só as zonas de topo e fim contam como repetidas: na primeira versão os parágrafos de
  enchimento repetidos eram tirados do corpo (e o cálculo levava 4 s por 40 páginas).

## O que ficou de fora

- Reinício de numeração e cabeçalho novo não ocorrem nos sintéticos (folhas contínuas,
  cabeçalho único); estão implementados e testados com páginas fabricadas.

## Comandos

```
docker compose run --rm api python scripts/medir_extracao.py extrair semente_NN --lotes 8 --destino /medicao
docker compose run --rm api python scripts/medir_extracao.py pecas --destino /medicao
```
(volume Docker `lupa_medicao4e` montado em `/medicao`; nada copiado para o host)

## Checklist

| Item | Evidência |
|---|---|
| Sinais gravados por página | `test_worker_grava_indice_sinais_e_divergencias`: toda página com sinais |
| Títulos com variação e OCR | `test_titulo_reconhecido_com_variacao_e_erro_de_ocr` |
| Assinatura × rodapé | `test_assinatura_tolera_ocr_e_recusa_rodape_de_autenticacao` |
| Layout e fonte | `test_layout_em_duas_colunas_e_fonte_dominante` |
| Custo | 0,73 s (196 págs) a 19,9 s (4.988 págs) para sinais + índice inteiro |
