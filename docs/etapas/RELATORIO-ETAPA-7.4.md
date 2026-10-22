# Relatório da Etapa 7.4: cifra dos originais

## O que foi feito

- `StorageCifrado` (`ingestao/storage.py`) embrulha qualquer `ObjectStorage`; `criar_storage`
  sempre o devolve. Gravação em stream (`LeitorCifrado`, blocos de 64 KiB, formato `LUPAOBJ` v1)
  com a DEK do processo tirada da chave `.../processo/<id>/...`; leitura decifra. Objeto legado em
  claro ainda é lido, com aviso no log. Chave sem processo é recusada.
- Recepção: SHA-256 calculado sobre o claro em stream (o `sha256` e a chave do objeto continuam os
  do claro); a cifra acontece em `lacrar`, antes de qualquer parser.
- Worker: o original decifrado vai para o diretório efêmero do job (0700), arquivo criado com
  `O_EXCL` e modo 0600; o `TemporaryDirectory` some ao fim do job, inclusive em exceção. Entradas
  de ZIP gravadas pelo worker e o cache de PNG/medidas do visualizador passam pelo mesmo
  `StorageCifrado` (todas as chaves levam o processo). Renderização: temporário 0600 (antes 0644).

## Testes

- `test_storage_cifrado_nao_guarda_pdf_em_claro`: o objeto no storage começa com `LUPAOBJ`, não
  `%PDF`; a leitura devolve o claro; legado; chave sem processo.
- `test_worker_decifra_em_temporario_0600_e_apaga_mesmo_em_falha`: lacre real com
  `StorageCifrado`, falha forçada no meio do job; o original estava 0600 e o diretório de trabalho
  ficou vazio.
- `tests/seguranca/test_envelope.py`: ida e volta em 0, 1, 64 KiB±1 e 3 blocos; truncamento em
  fronteira de bloco, DEK errada e versão desconhecida recusados.

## O que ficou de fora

- Objetos gravados em claro antes da 7.4 no MinIO de desenvolvimento não foram recifrados (são
  lidos como legado); reenvio ou descarte resolve.
- `ArmazenamentoS3.ler` continua lendo o objeto inteiro em memória (comportamento anterior).
