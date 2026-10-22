# Relatório — Etapa 4A.4 (sandbox de parsing)

20 de outubro de 2026 · executor da 4A

## O que foi feito

- `ingestao/sandbox.py`: `executar(modulo, argumentos, limites)` roda `python -I -c "...main()"`
  com `preexec_fn` que aplica `RLIMIT_AS`, `RLIMIT_CPU`, `RLIMIT_FSIZE=0`, `RLIMIT_NOFILE=64` e
  `RLIMIT_CORE=0`; tempo de parede por `subprocess.run(timeout=)`; ambiente mínimo (`PATH`,
  `HOME`, `LANG`, `TMPDIR`), sem nenhuma `LUPA_*`; diretório de trabalho temporário; stdout lido
  como JSON; stderr descartado. `inspecionar_pdf` é o atalho para o parser de PDF.
- `ingestao/parser_pdf.py` (roda só no filho): desabilita sockets, confere cabeçalho, `%%EOF` e
  `/ByteRange`, abre com PyMuPDF, recusa senha, decodifica o conteúdo de cada página
  (`read_contents`, o que expõe streams gigantes ao limite) e escreve um objeto JSON.
- Mapeamento: saída 3 → `limite_memoria`; `SIGXCPU`/`SIGKILL` → `limite_cpu`; timeout →
  `tempo_esgotado`; outro código ou JSON inválido → `erro_parser`. O worker grava o lote com o
  motivo e leva o job a `falho`.
- Compose: rede `ingestao` com `internal: true`; o `worker` está só nela (com `db`, `minio` e
  `redis`), sem rota para fora. Conferido: `urlopen('http://example.com')` no worker →
  `Temporary failure in name resolution`.

## Decisões não previstas

- O MuPDF sem memória lança `FzErrorSystem` com mensagem vazia; o parser trata
  `FzErrorSystem`/`FzErrorMemory` e `MemoryError` como falta de memória (saída 3).
- `python -I` ignora `PYTHONPATH`; o comando insere a raiz de `src` no `sys.path`.
- O worker precisa de banco, storage e Redis (é ele quem grava); "sem rede e sem banco" vale para
  o processo do parser: sem variáveis, sem credenciais e sem sockets.

## O que ficou de fora

- Isolamento de rede no nível do kernel para o filho (ele compartilha a rede interna do worker,
  sem credenciais). Documentado em `docs/ingestao.md`; um contêiner de parser sem rede fica para
  quando a decifragem por processo (fase 2, `requisitos-v1.md` §6) exigir worker separado.
- seccomp e namespaces (exigiriam privilégios no contêiner).

## Comandos e saída

`pytest tests/ingestao/test_sandbox.py` → 19 passed. Bomba de teste: PDF de cerca de 800 KB cujo
stream Flate descomprime em 768 MB; com limite de 512 MB o filho morre em cerca de 1 s.

## Critério de aceite

- [x] PDF com stream descomprimido gigante é morto pelo limite:
  `test_stream_descomprimido_gigante_e_morto_pelo_limite_de_memoria`.
- [x] Job marca `falho` com motivo, nunca `concluido`:
  `test_pdf_com_stream_gigante_e_morto_pelo_limite_e_job_falha` (`falho/limite_memoria`),
  `test_tempo_esgotado_no_sandbox_marca_falho`.
- [x] Parser sem rede e sem banco: `test_filho_nao_cria_sockets`,
  `test_ambiente_do_filho_nao_tem_variaveis_do_lupa`, `test_limites_aplicados_no_filho`.
- [x] Resultado por JSON em stdout: `test_pdf_valido_no_sandbox`,
  `test_saida_que_nao_e_objeto_json_vira_erro_parser`.

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
