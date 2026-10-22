# Relatório da Etapa 7.5: cifra de colunas

## O que foi feito

- `TextoCifrado`/`JsonCifrado` (`seguranca/tipos.py`) em `pagina.texto`, `texto_normalizado`,
  `texto_nativo`, `texto_ocr`, `trechos_ocultos`, `trechos_suspeitos`, `evidencia.trecho` e
  `mensagem.texto` (formato `lupa1:`, AAD com coluna e processo). `texto_nativo`/`texto_ocr`
  entraram além do roteiro: guardam o mesmo texto da página.
- Migração 0010 (`esquema_v0010.py`, `down_revision = "0009"`): coluna da DEK, `descartado` no
  CHECK, trechos JSONB → texto, funções `lupa_chave_processo` e `lupa_descartar_processo`, e
  conversão em lotes de 500 dos dados existentes (idempotente: pula `lupa1:`/`vault:`; reversível;
  processos de gabinete com chave destruída ficam como estão). Aplicada no banco de
  desenvolvimento com o Vault real: 30 de 30 páginas cifradas.
- `ingestao/repositorio.resumo_paginas`: `jsonb_array_length` → `len()` em Python.
- `agente/ferramentas/leitura.buscar_texto`: busca em memória por processo, em blocos de 200,
  até 20 acertos ou `LUPA_BUSCA_MAX_PAGINAS` (padrão 5000).

## Testes

- `test_dump_logico_nao_contem_sentinelas_em_claro`: dump lógico de todas as tabelas do banco de
  teste (`pg_dump --data-only` se houver no contêiner, senão `COPY ... TO STDOUT` de cada tabela,
  que é o que o pg_dump de dados produz; a imagem da API não tem pg_dump) sem as sentinelas de
  página, trecho, mensagem e nome do réu.
- `test_migracao_cifra_dados_existentes_idempotente_e_reversivel`: banco próprio na 0009 com dados
  em claro → head (cifrado e legível pela aplicação) → 0009 (claro de volta) → head.
- `test_busca_em_memoria_respeita_o_teto_de_paginas`, `test_texto_gravado_cifrado_e_lido_em_claro`.

## Desempenho (contêiner da API, banco do compose, 1000 páginas de 2500 caracteres, 3 colunas de texto + 2 JSON por página)

Medido com um script de rascunho (`medir_cifra.py`, fora do repositório) num processo sintético,
duas rodadas de cada (após aquecimento):

| | gravar 1000 páginas (ORM) | ler texto de 1000 páginas |
|---|---|---|
| sem cifra | 0,37 s / 0,39 s | 0,015 s |
| com cifra | 0,70 s / 0,45 s | 0,09 s / 0,06 s |

Custo: cerca de +0,1 a +0,3 s por mil páginas na gravação e +0,05 a +0,08 s na leitura, ínfimo
perto da extração (segundos por página com OCR). Objeto de 1 MB: cifrar + decifrar em 0,5 a 1,2 ms.

## O que ficou de fora

- Busca por índice (sem ILIKE não há índice de texto; o teto limita o custo em processos grandes).
- `hash_texto`/`hash_trecho` continuam em claro (SHA-256 necessário às citações).
