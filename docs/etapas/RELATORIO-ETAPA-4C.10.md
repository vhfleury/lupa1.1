# Relatório da Etapa 4C.10 — Relatório de qualidade por arquivo

## O que foi feito

- `src/lupa/ingestao/qualidade.py`: `relatorio_qualidade` (páginas por tipo e rota, abstidas, faltando com lista e motivo, flags, CER estimado onde há nativo e OCR da mesma página, confiança média do OCR, rotações corrigidas, tempos de parede, soma por página e por mil páginas) e `para_saida_pipeline` (formato de `lupa.sinteticos.saida_pipeline`, só páginas).
- Gravado em `job_ingestao.relatorio` ao fim da extração (parcial entre fatias); exposto em `GET /processos/{id}/arquivos/{arquivo_id}/relatorio` (auditada como `processo_aberto`, sem conteúdo).
- `scripts/medir_extracao.py extrair <processo>` roda a mesma pipeline (sandbox, lotes paralelos, relatório) sem banco e grava `saida.json`, medido por `scripts/medir.py`.
- Itens herdados: `scripts/verificar.ps1` ganhou o passo ponta a ponta; avisos `DeprecationWarning` do swig/pymupdf (e `utcnow` do botocore) filtrados no `pyproject.toml`.

## Decisões não previstas

- Os relatórios dos dez processos foram gerados pelo script (mesmas funções do worker) e não pelo upload no MinIO, para não carregar 1,9 GB no storage de desenvolvimento; o caminho com banco é coberto por `test_pdf_sintetico_com_indice_vai_a_concluido...` e pelo ponta a ponta.
- Paralelismo das medições: 8 lotes de 8 páginas (12 CPUs). O tempo com o padrão de produção (4 lotes) está no relatório 4C.8.
- Só o cenário `pdf_liso` foi extraído por completo (as páginas são as mesmas nos três cenários; o diagnóstico dos três está em 4C.1).

## Comandos e saída

```
docker compose run --rm api sh -c 'python scripts/medir_extracao.py extrair semente_NN --lotes 8 &&
  python scripts/medir.py --gabarito .../semente_NN/pdf_liso/gabarito.json \
    --saida /tmp/medicao-4c/semente_NN/pdf_liso/saida.json --json ... --markdown ...'
```

## Resumo por processo (relatório de qualidade + `medir.py`)

| Processo | Páginas | Nativa / OCR / vazia | Abstidas | Faltando | `texto_divergente` | CER estimado | Confiança OCR | Parede (s) | s / mil págs | Tipo de página (medir) |
|---|---|---|---|---|---|---|---|---|---|---|
| semente_01 | 196 | 5 / 184 / 7 | 16 | 0 | 0 | 1,04% | 92,4 | 104 | 533 | 196/196 |
| semente_02 | 294 | 40 / 250 / 4 | 20 | 0 | 0 | 0,97% | 92,2 | 138 | 471 | 294/294 |
| semente_03 | 450 | 107 / 338 / 5 | 41 | 0 | 0 | 1,57% | 92,3 | 197 | 438 | 450/450 |
| semente_04 | 643 | 204 / 431 / 8 | 65 | 0 | 0 | 1,18% | 92,4 | 256 | 398 | 643/643 |
| semente_05 | 891 | 362 / 518 / 11 | 74 | 0 | 0 | 1,14% | 92,1 | 317 | 355 | 891/891 |
| semente_06 | 1.200 | 600 / 579 / 21 | 99 | 0 | 0 | 1,09% | 92,5 | 356 | 297 | 1.200/1.200 |
| semente_07 | 1.598 | 993 / 577 / 28 | 133 | 0 | 0 | 1,03% | 92,2 | 387 | 242 | 1.598/1.598 |
| semente_08 | 2.198 | 1.556 / 614 / 28 | 173 | 0 | 0 | 1,18% | 92,4 | 429 | 195 | 2.198/2.198 |
| semente_09 | 3.189 | 2.425 / 721 / 43 | 251 | 0 | 0 | 1,25% | 92,3 | 557 | 175 | 3.189/3.189 |
| semente_10 | 4.988 | 4.426 / 487 / 75 | 401 | 0 | 0 | 0,97% | 93,0 | 485 | 97 | 4.988/4.988 |

Total: 15.647 páginas, nenhuma faltando, nenhuma falha de lote, nenhum falso `texto_divergente` nas 1.273 híbridas limpas. Acurácia de tipo de página pelo `medir.py`: **100%** nos dez. Fronteiras e eventos vazios (4E e 4F): precisão/recall 0 por construção.

## CER medido pelo `medir.py` (todas as páginas, dez processos)

| Grupo | Páginas | CER |
|---|---|---|
| leve | 1.889 | 1,65% |
| media | 1.857 | 2,12% |
| forte | 953 | 7,58% |
| digitalizada | 3.426 | 3,56% |
| hibrida_corpo | 1.190 | 1,73% |
| hibrida_assinatura | 83 | 0,37% |
| nativa | 10.708 | 1,15% (marca d'água está na camada e fora do `texto` visível do gabarito) |
| capa / vazia | 10 / 230 | 0% |

Datas dd/mm/aaaa do gabarito encontradas literalmente no texto final das páginas com imagem: leve 9.895/10.677 (**92,7%**), media 9.567/10.518 (**91,0%**), forte 4.564/5.351 (**85,3%**). Todas dentro das metas definidas em 4C.6.

## Verificação final

```
docker compose up -d --build --wait
docker compose exec api bash scripts/verificar.sh
```
ruff check: All checks passed · ruff format: 154 files already formatted · mypy --strict: no issues in 154 files
pytest: 551 passed, 1 skipped, 1 deselected (carga) em 140 s; cobertura total 99% (mínimo 90%)
ponta a ponta (integração, sem skip): 1 passed (upload PDF e ZIP → concluido com páginas)

## Critério

| Critério | Evidência |
|---|---|
| Relatório gravado e exposto | `job_ingestao.relatorio`; rota GET auditada (`test_rotas_de_diagnostico_e_relatorio_sao_auditadas_e_isoladas`) |
| Gerado para os dez processos de referência | tabela acima |
| Saída mensurável por `scripts/medir.py` | `saida.json` medido nos dez |
