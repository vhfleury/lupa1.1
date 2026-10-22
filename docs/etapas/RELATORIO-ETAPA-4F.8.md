# Relatório da Etapa 4F.8 — Cache e reprocessamento

## O que foi feito

- `lupa/ingestao/cache.py`: `fonte_em_cache` procura outro arquivo do MESMO gabinete (filtro
  explícito por `gabinete_id`, além da RLS) com o mesmo SHA-256 e todas as páginas gravadas na
  versão corrente do extrator de páginas; `copiar_paginas` copia as linhas de `pagina` (em blocos
  de 500, sob o lease do job de destino).
- Worker (`_extrair`): sem páginas prontas, tenta o cache antes de planejar a extração; com o
  cache, nenhuma tarefa é planejada e o job segue para índice, eventos e achados.
- Peças: recalculadas a partir das páginas copiadas (o índice é determinístico e leva segundos);
  correções manuais de peça não passam para outro processo.
- Mudar só a versão do extrator de eventos (`eventos.yaml`, `tipos_penais.yaml`):
  `processar_eventos` regrava fatos e achados sem tocar páginas e peças.
- Itens herdados da 4E: os testes de API da 4E (`test_pecas_api.py`) e os novos de eventos usam
  uma extração por sessão (`extracao_sessao` em `tests/ingestao/conftest.py`): o PDF sintético
  passa uma vez pelo OCR e cada teste recebe um processo novo do mesmo gabinete servido pelo
  cache. Os 4 testes da 4E caíram de ~45 s cada para ~1,5 s cada (35 s de OCR uma vez na sessão).

- Item herdado (logging com saída fechada): a causa era `configurar_logging` amarrar o
  `PrintLoggerFactory` ao `sys.stdout` do momento; os testes que chamam `configurar_logging`
  dentro de `capsys` (`tests/unit/test_logging.py`, `test_observabilidade.py`,
  `test_motor_e_regras.py`) deixavam o logger escrevendo num stream de captura já fechado.
  Corrigido na origem em `src/lupa/logging.py` (fábrica sem arquivo fixo: cada logger usa o
  `sys.stdout` corrente); removida a reconfiguração de contorno do `test_pecas_api.py`.

## Decisões não previstas

- O extrator de páginas subiu para `4f.0` (OCR de detecção em imagens de páginas nativas, ver
  4F.9 e `docs/ingestao.md`); páginas gravadas em `4e.0` não servem de cache para `4f.0`.

## O que ficou de fora

- Reaproveitar páginas de uma entrada de ZIP igual a um PDF já enviado (o cache é pelo hash do
  arquivo enviado, não por entrada).

## Comandos e saída resumida

```
docker compose run --rm api python -m pytest tests/ingestao/test_eventos_banco.py -k "cache or versao" --no-cov -q
3 passed
```

Segundo upload do mesmo PDF (48 páginas, 4 com OCR) em outro processo do gabinete: 1,5 s
(executor do sandbox trocado por um que falha se chamado). Nos processos de referência, ver
`RELATORIO-ETAPA-4F.9.md` (repetição de upload).

## Checklist

| Item | Evidência |
| --- | --- |
| Reaproveitamento por (sha256, versão do extrator) entre processos do mesmo gabinete | `test_segundo_upload_do_mesmo_arquivo_vem_do_cache_em_segundos` (< 30 s, sem chamar o sandbox) |
| Nunca entre gabinetes | `test_cache_nunca_atravessa_gabinete_nem_versao` (outro gabinete com RLS e sem RLS: nenhuma fonte) |
| Teste de versão | mesmo teste (versão diferente: nenhuma fonte); `test_reprocessar_mesma_versao_nao_duplica_e_nova_versao_refaz_so_os_eventos` (páginas e peças idênticas antes e depois) |
| Segundo upload conclui em segundos | idem acima; números dos processos de referência na 4F.9 |
