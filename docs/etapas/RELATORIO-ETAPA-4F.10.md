# Relatório da Etapa 4F.10 — Calibração com o processo real

## O que foi feito

O arquivo do Projudi ainda não existe. Entregue o roteiro e a ferramenta para o dia em que ele
chegar:

- `docs/calibracao-projudi.md`: como montar o arquivo no contêiner sem copiá-lo para o
  repositório, comando, o que o relatório traz, instruções de conferência para o assessor, o que
  medir (com a referência sintética de cada medida), onde ajustar cada tipo de erro e qual versão
  subir, limpeza e a tabela "Registro" a preencher (acertou, errou, mudou).
- `scripts/calibrar.py <arquivo>` sobre `lupa/ingestao/calibracao.py`: cria um gabinete de
  calibração, lacra e processa o arquivo pelo código do worker e grava `relatorio.md` (diagnóstico,
  páginas, peças, eventos com trecho, achados, colunas "Confere?") e `relatorio.json` em `/tmp`
  do contêiner.
- `tests/ingestao/test_calibracao.py`: o mesmo caminho sobre o processo sintético dos testes.

## Teste com processo sintético

```
docker compose exec -T api python scripts/calibrar.py \
    /app/.sinteticos/referencia/semente_01/pdf_indice/autos.pdf --saida /tmp/calibracao --titulo "semente_01 pdf_indice"
rc=0
Cenário pdf_com_bookmarks_e_indice; 198 páginas (7 nativas, 184 OCR, 7 vazias); 16 abstidas;
CER estimado 0,0104; 160,5 s de extração (811 s por mil); 90 linhas de tabela no relatório;
achados: tempestividade conforme, preventiva atencao, prescrição atencao.
```

A prescrição sai `atencao` porque o worker usa a data de hoje (2026) como referência; no
gabarito (referência 17/07/2016) ela é `conforme`, e a 4F.9 confirma 3/3 nessa data.

## Decisões não previstas

- O relatório contém trechos dos autos: fica no contêiner e o roteiro proíbe versioná-lo.

## O que ficou de fora

- A calibração em si (depende do arquivo real); a seção "Registro" está vazia.

## Checklist

| Item | Evidência |
| --- | --- |
| Roteiro pronto (comandos, o que medir, comparar com o assessor, onde registrar) | `docs/calibracao-projudi.md` |
| `scripts/calibrar.py` gera o relatório Markdown | execução acima, `rc=0` |
| Testado com processo sintético | acima e `test_calibracao_de_processo_sintetico_gera_relatorio_para_conferencia` |
