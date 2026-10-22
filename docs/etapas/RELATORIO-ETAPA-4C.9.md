# Relatório da Etapa 4C.9 — Gravação de páginas

## O que foi feito

- `repositorio.gravar_paginas`: upsert em `pagina` por `(arquivo_id, numero)` com o fencing token conferido; grava `tipo`, `texto`, `hash_texto`, `flags`, `sinais`, `coordenadas` (blocos/linhas com caixas e offsets), `extracao` (rota, versão do roteador, tempo, OCR, divergência), `texto_nativo`, `texto_ocr`, `versao_extrator`, `origem_arquivo`, `pagina_origem`.
- Idempotência: antes de cada execução, `paginas_prontas(arquivo, VERSAO_EXTRATOR)`; páginas já gravadas na versão corrente não são reextraídas. Mudar `extrator_paginas.VERSAO_EXTRATOR` (hoje `4c.1`) refaz todas, no mesmo id de linha.
- Estados: `validado → em_extracao → concluido | parcial | falho`; relatório gravado no job.
- **Item 2 da revisão 4A**: retry por motivo (`tempo_esgotado` e `erro_parser` voltam a `recebido` até 2 vezes, `LUPA_MAX_RETENTATIVAS`; `limite_memoria` e `limite_cpu` nunca; lotes falhos de validação são apagados para a nova tentativa) e `processo.status` (`em_ingestao` ao entrar na extração, `pronto` quando nenhum job está em andamento e algum terminou `concluido`/`parcial`).

## Decisões não previstas

- A chave de idempotência é `(arquivo_id, versão)`; como o arquivo é único por `(processo, sha256)`, equivale a `(sha256, versão)` dentro do processo. Reaproveitar páginas do mesmo sha256 em outro processo é cache da 4F.8.
- `concluido` é final na máquina de estados; reprocessar um job concluído com nova versão exige reabrir o job (feito no teste por SQL). O gatilho de reprocessamento por versão é da 4F.8.
- A fixture `deps` dos testes da 4A passou a `extrair=False, max_retentativas=0` (comportamento da fundação); os testes 4C usam `deps_extracao`. Arquivo de outra etapa alterado: `tests/ingestao/conftest.py`, e o ponta a ponta (`test_ponta_a_ponta.py`) agora vai até `concluido`.

## Comandos

`pytest tests/ingestao/test_worker_extracao.py`.

## Critério

| Critério | Evidência |
|---|---|
| Página gravada com tipo, texto, hash, coordenadas, sinais e flags | `test_pdf_sintetico_com_indice_vai_a_concluido...` |
| Reprocessar não duplica | `test_reprocessar_nao_duplica_e_nova_versao_do_extrator_refaz`: segunda execução não chama nenhum filho; ids e hashes iguais |
| Versão nova reprocessa | mesmo teste: todas as páginas refeitas, `versao_extrator` novo, mesmas linhas (5) |
| `parcial` com páginas faltando | `test_lote_que_falha_deixa_job_parcial_com_paginas_faltando` |
| Retry por motivo | `test_falha_retentavel_volta_a_recebido_duas_vezes_e_depois_falha`, `test_falha_por_memoria_nunca_e_retentada` |
| `processo.status` | `pronto` verificado nos testes de conclusão e parcial |
