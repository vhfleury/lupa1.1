# Relatório da Etapa 4F.9 — Ponta a ponta nos processos de referência

## O que foi feito

- `scripts/ponta_a_ponta.py`: para cada processo e cenário, lacra o arquivo no MinIO do compose
  num processo novo do banco de desenvolvimento e roda `processar_job` (o código do worker:
  validação no sandbox, diagnóstico, páginas ou cache, índice, eventos, achados). Lê do banco
  peças, fatos e achados e mede com `lupa.sinteticos.medicao.medir` (agora com `datas`) e
  `lupa.sinteticos.achados.comparar` (achados na `data_referencia` do gabarito).
- `scripts/medir_extracao.py eventos`: a mesma medição sem banco, nos 30 arquivos, sobre as
  páginas do volume `lupa_medicao4e`.
- Upload "pelo worker com o arquivo no storage" (opção prevista no roteiro), não por HTTP: a
  rota de upload exige sessão com MFA e o caminho depois do lacre é idêntico.

## O que foi reaproveitado do volume `lupa_medicao4e`

O OCR dos dez processos leva cerca de 64 min (15.647 folhas a ~245 s/mil na 4E), acima de uma
hora. Por isso:

1. **OCR real, ponta a ponta**: semente_01 (196 folhas) e semente_02 (294 folhas) nos três
   cenários (`pdf_liso`, `zip_por_peca`, `pdf_indice`), extrator `4f.0`, sem nada reaproveitado.
2. **Páginas do volume**: semente_03 a semente_10, cenário `pdf_liso`. As linhas
   `DIR/<processo>/pdf_liso/linhas.json.gz` (extração 4E, versão `4e.0`) foram gravadas como
   páginas de um arquivo-fonte do mesmo gabinete com o SHA-256 do PDF e a versão corrente
   (`4f.0`), e o upload do PDF real recebeu essas páginas pelo cache da 4F.8. Validação no
   sandbox, diagnóstico, índice, eventos, achados e gravação rodaram de verdade. A diferença
   4e.0 → 4f.0 é só o OCR de detecção em imagens de páginas nativas (não muda texto).
3. **Sem banco, 30 arquivos**: `medir_extracao.py eventos` sobre as mesmas linhas do volume, com
   o diagnóstico real de cada cenário (ZIP e `pdf_indice` dos dez processos).

## Resultados

### Ponta a ponta pelo worker (14 uploads)

| Processo | Cenário | Folhas | Tempo (s) | s/mil folhas | Eventos P | Eventos R | Datas P | Achados iguais | 2º upload (s) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| semente_01 | pdf_liso | 196 | 159,9 | 816 | 23/23 | 23/23 | 20/20 | 3/3 | 3,6 |
| semente_01 | zip_por_peca | 196 | 167,0 | 852 | 23/23 | 23/23 | 20/20 | 3/3 | 5,2 |
| semente_01 | pdf_indice | 196 | 162,3 | 828 | 23/23 | 23/23 | 20/20 | 3/3 | 3,6 |
| semente_02 | pdf_liso | 294 | 212,7 | 723 | 48/48 | 48/48 | 45/45 | 3/3 | 5,1 |
| semente_02 | zip_por_peca | 294 | 228,5 | 777 | 48/48 | 48/48 | 45/45 | 3/3 | 7,9 |
| semente_02 | pdf_indice | 294 | 218,8 | 744 | 48/48 | 48/48 | 45/45 | 3/3 | 4,6 |
| semente_03 | pdf_liso (volume) | 450 | 7,1 | — | 12/12 | 12/13 | 9/9 | 3/3 | 6,8 |
| semente_04 | pdf_liso (volume) | 643 | 8,9 | — | 28/30 | 28/31 | 25/27 | 1/3 | 9,4 |
| semente_05 | pdf_liso (volume) | 891 | 11,1 | — | 21/21 | 21/22 | 18/18 | 2/3 | 12,0 |
| semente_06 | pdf_liso (volume) | 1200 | 14,7 | — | 50/50 | 50/50 | 47/47 | 3/3 | 14,9 |
| semente_07 | pdf_liso (volume) | 1598 | 17,7 | — | 13/13 | 13/13 | 10/10 | 3/3 | 17,2 |
| semente_08 | pdf_liso (volume) | 2198 | 22,5 | — | 30/30 | 30/30 | 27/27 | 3/3 | 21,9 |
| semente_09 | pdf_liso (volume) | 3189 | 31,8 | — | 49/49 | 49/50 | 46/46 | 2/3 | 31,7 |
| semente_10 | pdf_liso (volume) | 4988 | 44,8 | — | 25/25 | 25/25 | 22/22 | 3/3 | 46,6 |

Totais: eventos 441/443 corretos (precisão 99,5%), recall 441/447 (98,7%); **datas 399/401
(99,5%)**; achados iguais 38/42 (90,5%); 0 fato sem evidência e 0 evidência não literal.

### Sem banco, 30 arquivos (`medir_extracao.py eventos`)

| Medida | Valor |
| --- | --- |
| Eventos: precisão | 897/903 = 99,34% |
| Eventos: recall | 897/915 = 98,03% |
| **Datas: precisão** | **807/813 = 99,26%** (meta ≥ 99%) |
| Datas: recall | 807/825 = 97,82% |
| Achados iguais (resultado e valores) | 78/90 = 86,7%; resultado igual 81/90 = 90,0% |
| Fatos sem evidência | 0 |
| Evidências cujo trecho difere de `texto[inicio:fim]` | 0 |
| Tempo da extração de eventos | 1,4 s por mil folhas |

Os três cenários dão o mesmo resultado por processo (mesmas folhas). Os únicos erros de data
(2, na semente_04, contados nos três cenários) são leituras do OCR em degradação forte
(2017 → 2020, 02 → 12); as perdas de recall são páginas digitalizadas fortes em que o trecho
saiu ilegível. Detalhe por processo em `RELATORIO-ETAPA-4F.7.md`.

### Tempo por mil páginas e dimensionamento do worker

Configuração: 1 worker, 12 CPUs no host Docker, `paginas_por_lote=8`, `lotes_por_job=4`,
`lotes_por_gabinete=4`, sandbox 1024 MB / 60 s de CPU por lote, Tesseract com uma thread, sem
fatiar.

| Medida | s por mil páginas |
| --- | --- |
| Nativo (1000 páginas, extrator 4f.0 com OCR de detecção em imagens) | 35,8 |
| Digitalizado (100 páginas) | 911,9 |
| Processo misto real (semente_01/02, 85–94% OCR), do upload aos achados | 723 a 852 |
| Segundo upload do mesmo arquivo (cache), do upload aos achados | 9 a 26 (dominado pela validação no sandbox) |
| Eventos + catálogo | ~1,4 (eventos) + < 1 (catálogo) |

## Decisões não previstas

- `imagem_com_texto` (revisão 4D §6.2): implementado o OCR só de detecção em imagens com área
  acima de 2% da página nativa (`lupa/ingestao/imagem_nativa.py`, extrator `4f.0`). Custo medido
  antes de implementar: 21 a 27 s por mil páginas nativas (semente_04 e semente_06); depois, o
  nativo completo ficou em 35,8 s por mil. A injeção do corpus é detectada
  (`dirigido_a_sistema`, `alterar_resultado`). Registrado em `docs/ingestao.md`.
- Dimensionamento (revisão 4C §5.1): registrado acima e em `docs/ingestao.md`.

## O que ficou de fora

- OCR real dos processos 03 a 10 (reaproveitado, como descrito).
- Upload pela rota HTTP.

## Comandos

```
docker compose run --rm -T api python scripts/ponta_a_ponta.py \
    --processos semente_01,semente_02 --cenarios pdf_liso,zip_por_peca,pdf_indice --repetir
docker compose run --rm -T -v lupa_medicao4e:/m api python scripts/ponta_a_ponta.py \
    --processos semente_03,...,semente_10 --cenarios pdf_liso --volume /m --repetir
docker compose run --rm -T -v lupa_medicao4e:/m api python scripts/medir_extracao.py eventos --destino /m
docker compose run --rm -T api python scripts/medir_extracao.py tempo --nativas 1000 --digitalizadas 100
```

## Checklist

| Item | Evidência |
| --- | --- |
| Dez processos no `pdf_liso` até achados | 10/10 `concluido` (2 com OCR real, 8 com páginas do volume) |
| ≥ 2 no ZIP e ≥ 2 no `pdf_indice` | semente_01 e semente_02 nos dois, OCR real |
| Harness com eventos: P/R de eventos e precisão de datas | `medir` com `datas`; tabelas acima |
| Datas ≥ 99% de precisão | 99,5% (ponta a ponta) e 99,26% (30 arquivos) |
| Zero fato sem evidência | 0 em 443 (ponta a ponta) e 0 em 903 (30 arquivos) |
| Tempo por mil páginas | 35,8 s nativo, 911,9 s digitalizado, 723–852 s misto |
| Reaproveitamento documentado | seção "O que foi reaproveitado" |
