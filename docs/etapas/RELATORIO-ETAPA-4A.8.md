# Relatório — Etapa 4A.8 (quarentena e falhas)

20 de outubro de 2026 · executor da 4A

## O que foi feito

- `MotivoQuarentena` enumerado: `corrompido`, `senha`, `truncado`, `assinatura_invalida`,
  `tipo_invalido`, `zip_malicioso`; `job_ingestao.motivo_quarentena` com CHECK.
- `ingestao/quarentena.py`: `DESCRICOES`/`descrever` (texto legível para a tela futura),
  `motivo_do_parser` (lê o JSON do sandbox) e `pode_extrair` (só `validado`).
- Quarentena é estado final e `adquirir_lease` não toma job final; logo nada em quarentena volta à
  fila nem entra na extração.
- Falhas de processamento (limites, erro do parser, objeto ausente, tentativas esgotadas) vão
  para `falho` com `MotivoFalha`.

## Decisões não previstas

- `assinatura_invalida` é conferida **estruturalmente**: se o arquivo tem `/ByteRange` e nenhum
  começa em 0 e termina no fim do arquivo, houve alteração depois da assinatura. A validação
  criptográfica (certificado, cadeia ICP-Brasil) fica fora.
- `truncado` é falta de `%%EOF` nos últimos 1024 bytes, conferida antes de abrir o PDF, porque o
  MuPDF repara arquivos truncados em silêncio.
- PDF com cifra só de dono (abre sem senha) não é quarentena; só `needs_pass`.
- O lote de uma entrada recusada é gravado com estado `falho` e o motivo no resultado.

## O que ficou de fora

- A tela de quarentena (vai ler `motivo_quarentena` e `DESCRICOES`).

## Comandos e saída

`pytest tests/ingestao/test_worker.py -k quarentena` → 10 passed (9 parametrizados + link
simbólico).

## Critério de aceite

- [x] Cada tipo de falha tem teste e motivo legível:
  `test_cada_falha_vai_para_quarentena_com_motivo_e_nao_avanca` (senha, truncado, corrompido,
  assinatura, tipo, zip_malicioso, zip_senha, zip_cifrado, zip_corrompido),
  `test_parser_classifica_cada_defeito`, `test_quarentena_tem_texto_legivel_para_cada_motivo`.
- [x] Nada em quarentena entra na extração: o mesmo teste confere `pode_extrair` falso e que um
  segundo worker, uma hora depois, não toma o job; `test_concluido_e_quarentena_sao_finais`.

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
