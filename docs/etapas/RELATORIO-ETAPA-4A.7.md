# Relatório — Etapa 4A.7 (inventário de zip)

20 de outubro de 2026 · executor da 4A

## O que foi feito

- `ingestao/inventario.py`: `conferir` (pelo diretório central, antes de extrair): caminho
  relativo sem `..`, sem absoluto, sem unidade (`C:`), sem barra invertida nem NUL; sem link
  simbólico (modo Unix nos atributos externos); sem bit de criptografia; nomes únicos; até
  `LUPA_ZIP_MAX_ENTRADAS`; razão descomprimido/comprimido até `LUPA_ZIP_MAX_RAZAO` por entrada;
  soma declarada até `LUPA_ZIP_MAX_DESCOMPRIMIDO_BYTES`. `inventariar` extrai para nomes opacos
  (`entrada-00001`), contando os **bytes efetivamente lidos** contra o limite (cabeçalho mentiroso
  não passa), e devolve o manifesto ordenado por nome com ordem, nome, tamanho e SHA-256.
- O worker grava cada entrada no storage pela chave do seu hash e guarda o manifesto em
  `job_ingestao.manifesto`.

## Decisões não previstas

- Erros viram `ZipRecusadoError(motivo, detalhe)`: `zip_malicioso` para as regras de segurança,
  `senha` para entrada cifrada, `corrompido` para ZIP ilegível, CRC errado ou compressão
  desconhecida, `tipo_invalido` para ZIP sem arquivos. Entrada que não é PDF vira `tipo_invalido`
  no worker.
- Diretórios dentro do ZIP são ignorados.

## O que ficou de fora

- ZIP dentro de ZIP não é aberto (a entrada não é PDF, logo `tipo_invalido`).

## Comandos e saída

`pytest tests/ingestao/test_inventario.py` → 18 passed.

## Critério de aceite

- [x] ZIP malicioso rejeitado com motivo: `test_caminho_com_ponto_ponto_e_zip_malicioso`,
  `test_caminho_inseguro` (6 variantes), `test_link_simbolico_recusado`,
  `test_quantidade_de_entradas_acima_do_limite`, `test_nomes_repetidos_e_zip_vazio`.
- [x] Zip bomb detectada pela razão de compressão:
  `test_zip_bomb_detectada_pela_razao_de_compressao`.
- [x] Limite de tamanho descomprimido: `test_tamanho_total_descomprimido_acima_do_limite`,
  `test_limite_imposto_sobre_bytes_lidos_mesmo_com_cabecalho_mentiroso`.
- [x] Manifesto ordenado por nome com hash por entrada:
  `test_manifesto_ordenado_por_nome_com_hash_e_tamanho`,
  `test_zip_por_peca_vira_um_lote_por_entrada_em_ordem_de_nome`.

## Verificação

Verificação final (todas as subetapas, imagem reconstruída):

```
docker compose up -d --build --wait          # db, minio, redis, api, worker healthy; minio-init exited 0
docker compose exec api alembic -c src/lupa/migrations/alembic.ini upgrade head   # 0003 (head)
docker compose exec api bash scripts/verificar.sh
== ruff check ==            All checks passed!
== ruff format --check ==   137 files already formatted
== mypy --strict ==         Success: no issues found in 137 source files
== pytest ==                476 passed, 1 skipped, 1 deselected; TOTAL 99% (lupa.ingestao: 99-100% por módulo)
== ponta a ponta da ingestao (integracao, sem skip) ==   1 passed
```
