# Relatório da Etapa 4D.10 — Painel de flags e regressão

## O que foi feito

- `qualidade.resumo_saneamento`: versões dos YAML, páginas por flag, páginas sinalizadas (número, flags, quantidades de trechos), trechos ocultos, trechos suspeitos por categoria, metadados descartados e `metadado_suspeito`. Entra em `job_ingestao.relatorio.saneamento` (extensão da 4C.10; `resumo_paginas` passou a ler a contagem de ocultos e os trechos suspeitos, sem texto; o worker passa os metadados do diagnóstico).
- `repositorio.alertas_arquivo` e `GET /processos/{id}/arquivos/{arquivo_id}/alertas` (auditada como `processo_aberto`, sem conteúdo): resumo, metadados suspeitos (só hash) e, por página sinalizada, flags, trechos ocultos sem o texto e trechos suspeitos.
- `tests/ingestao/test_injecao_corpus.py` (`integracao` e `injecao`; marcador novo no `pyproject.toml`): extrai pelo sandbox as páginas com injeção das 10 variantes e confere, por injeção do gabarito, a flag do vetor e que o objetivo não se materializa na ingestão (oculto e metadado fora de `texto` e do normalizado, oculto presente em `trechos_ocultos`, bloco trocado pelo marcador, nenhum cirílico no normalizado); mede recall e falso positivo (`semente_01` inteira) e grava as métricas em `$LUPA_METRICAS_INJECAO`.
- Passo próprio em `scripts/verificar.sh` e `scripts/verificar.ps1` (`LUPA_EXIGIR_INTEGRACAO=1`, imprime as métricas).

## Métricas por versão

| Versões | Recall | Injeções textuais | Falso positivo `semente_01` |
| --- | --- | --- | --- |
| saneamento 4d.1; homoglifos 1; padroes_instrucao 1; idiomas 1; densidade 1 | **1,0** | 16/16 | **0,0** (0/196) |

Flags na página da injeção, por variante: anotacao → `metadado_suspeito`; base64 → `bloco_codificado`; fora_da_pagina → `texto_oculto`; homoglifos (folha OCR) → `padrao_instrucao`; idioma_alternado → `idioma_inesperado`, `padrao_instrucao`; metadado_xmp → `metadado_suspeito` (página 1); texto_branco → `texto_oculto`; transcricao_citada → `padrao_instrucao`; todos → todas as injeções textuais sinalizadas; imagem_com_texto → nenhuma (abaixo).

## Decisões não previstas

- `imagem_com_texto` conta como **não textual** (2 casos): a página é roteada como nativa, não vai ao OCR e a instrução da imagem não chega a texto nenhum. O objetivo não se materializa na ingestão, mas também não há alerta. Se o OCR passar a ler imagens embutidas em páginas nativas, o teste passa a exigir `padrao_instrucao`.
- A regressão também roda dentro do `pytest` geral (marcador `integracao`, pula sem corpus); o passo próprio repete sem skip e grava as métricas. Custo: cerca de 160 s cada.

## O que ficou de fora

- Resumo por **peça** para o dossiê: peças só existem na 4E; o resumo por arquivo e por página está pronto.
- A migração 0005 não foi aplicada ao banco de desenvolvimento (que está na 0003): rodar `docker compose exec api alembic -c src/lupa/migrations/alembic.ini upgrade head` antes de usar o worker com ele. Os testes migram o banco de teste até a 0005.

## Critério

| Critério | Evidência |
| --- | --- |
| Suíte com marcador próprio | `pytest -m injecao`: 2 passed |
| Metas da 4D.5 medidas por versão | tabela acima, gravada em `/tmp/metricas_injecao.json` pelo `verificar.sh` |
| Painel na API | `test_worker_extracao.py::test_rotas_de_diagnostico_e_relatorio_sao_auditadas_e_isoladas` (PDF com instrução visível, oculta, em anotação e em XMP: 1 página sinalizada, metadados `xmp` e `anotacao`, nenhum texto oculto ou de metadado na resposta, 404 de outro processo); `test_origem.py::test_alertas_do_arquivo_sem_texto_dos_autos` |

## Comandos e saída

```
docker compose up -d --build --wait
docker compose exec api bash scripts/verificar.sh
```

Saída resumida (21/10/2026): ruff e `ruff format --check` limpos; `mypy --strict` sem erros em 165 arquivos; pytest **588 passed, 1 skipped** (o skip é anterior à 4D; eram 551 testes), cobertura **98,66%**; ponta a ponta 1 passed; regressão de injeção 2 passed (159 s), `recall 1.0`, `falso_positivo 0.0`.
