# Relatório da Etapa 6.4 — Lista e upload de processos

## Tarefa prévia: teste instável de observabilidade

`tests/ingestao/test_observabilidade.py::test_metricas_refletem_jobs_paginas_retries_e_falhas`
falhava às vezes na suíte completa. Causa: a idade da fila era comparada com um valor absoluto
(`>= 1`) enquanto os jobs do teste tinham `criado_em` do relógio real do banco (`now()`), e o
relógio injetado do teste (`Relogio`) nascia na fixture, antes da semeadura. Com a suíte
carregada, semear três jobs podia levar mais de 1 s, e `relogio() + 2 s − criado_em` ficava
abaixo de 1. Além disso, a métrica é o mínimo de `criado_em` em `recebido` no banco
compartilhado, que depende do que outros testes deixaram na fila.

Correção (só no teste, sem enfraquecer o que ele prova):

- `criado_em` dos três jobs do teste é FIXADO em `relogio() − 30 s` logo depois da semeadura;
  a idade passa a depender só do relógio injetado.
- O valor esperado é calculado de forma exata sobre o estado real da fila (`agora − min(criado_em)`
  dos jobs em `recebido`, que inclui o que outros testes deixaram) e comparado com
  `pytest.approx`; e continua valendo o piso `>= 32 s` (30 s semeados + 2 s avançados).
  Antes o teste provava "idade >= 1"; agora prova o valor exato da métrica e o piso.
- `test_fila_vazia_tem_idade_zero` já era determinístico (instante no ano 2000: idade negativa
  vira 0) e ficou como estava.

Duas execuções completas da suíte, depois da correção: ver "Verificação" abaixo.

## O que foi feito

API (`src/lupa/api/rotas/processos.py`):

- `GET /processos`: processos visíveis (RLS do gabinete; o administrador vê todos), mais recentes
  primeiro, com `ingestao: {situacao, por_estado, ultimo_envio}` calculado de `job_ingestao`
  (`sem_arquivos`, `processando`, `quarentena`, `falho`, `pendencias`, `concluido`). Exige
  `ver_processo`; auditado como `busca` (só metadados).
- `POST /processos`: cria no gabinete do ator (o administrador informa `gabinete_id`), número
  CNJ validado no servidor com dígito verificador (`lupa.dominio.cnj`), 409 para número repetido
  no gabinete, 403 auditado (`processo_criado` negado) para quem não tem `subir_processo` no
  gabinete-alvo, `processo_criado` gravado na transação.
- `GET /processos/{id}/arquivos`: arquivos do processo com o estado do job (estado, motivo de
  quarentena ou de falha, páginas), `exige_processo` (404 para outro gabinete), auditado como
  `processo_aberto` sem conteúdo.
- `GET /processos/{id}` passou a devolver também `sigiloso` e `criado_em`.

Front:

- `/processos` (`front/src/routes/processos/+page.svelte`): lista com número CNJ, classe,
  matéria, situação da ingestão e data; formulário de criação com máscara e validação do CNJ no
  cliente (`front/src/lib/processos/cnj.ts`, mesmo módulo 97 do servidor). Polling leve (4 s)
  só enquanto algum processo está `processando`.
- `/processos/[id]`: dados do processo, atalhos para dossiê, validações e visualizador, envio de
  PDF/ZIP e tabela de arquivos. O envio (`front/src/lib/processos/envio.ts`) usa
  `XMLHttpRequest` com o `File` como corpo (`application/octet-stream`, `?nome=`): o navegador
  lê o arquivo do disco em partes, sem carregar no JavaScript, e `upload.onprogress` alimenta a
  barra (`<progress>`, com bytes enviados e botão cancelar). Antes de enviar: extensão PDF/ZIP,
  arquivo vazio e limite de 512 MB (o servidor reconfere pelo conteúdo). Polling de 2,5 s só
  enquanto há arquivo em estado não final; quarentena e falha aparecem com motivo legível
  (`front/src/lib/processos/rotulos.ts`).
- Menu lateral: item "Processos" para quem tem `ver_processo` (acréscimo em `MenuLateral.svelte`;
  os testes do menu de 6.1–6.3 foram ajustados para o item novo).

E2E: `scripts/e2e_processos.py` (chamado por `front/scripts/e2e.sh` e `e2e.ps1`, depois do
`e2e_preparar.py`) cria gabinete, assessor (senha temporária) e um processo criminal sintético
(`lupa.sinteticos`, 18 folhas nativas), lacra os autos no storage real e enfileira o job no
worker real. As variáveis `LUPA_E2E_PROC_*` foram acrescentadas ao serviço `e2e` do compose.

## Testes

- `tests/api/test_processos_lista.py`: criação com auditoria, CNJ com dígito errado (422),
  formato inválido (422), duplicado (409); admin sem gabinete (422) e com gabinete (201);
  desembargador de outro gabinete (403 auditado); lista isolada por gabinete com situação e
  contagem por estado, evento `busca`; arquivos com estado e 404 para outro gabinete; resumo da
  situação por estados (parametrizado).
- `front/src/lib/processos/processos.test.ts`: CNJ (dígito, máscara), validação do arquivo antes
  do envio, formatação de tamanho, motivos de quarentena.
- E2E (`front/e2e/testes/processos.spec.ts`):

| Teste | Cobre |
| --- | --- |
| `6.4 lista mostra o processo sintético e o status acompanha a fila` | processo enfileirado pelo preparo aparece e chega a "Concluído" pela tela |
| `6.4 cria processo (CNJ validado), envia PDF e o status muda; quarentena legível` | dígito errado recusado no cliente; criação; envio de PDF gerado no teste; a sequência de estados vista na tela muda (ex.: Na fila → Concluído); PDF truncado vai para quarentena com "O PDF está incompleto…" |
| `6.4 upload de 500 MB com progresso sem travar a interface` | arquivo sintético de 500 MB gerado no teste, em disco; barra avança; maior intervalo entre quadros medido no navegador durante o envio < 500 ms; tempo registrado |

## Critério de aceite

- Upload de 500 MB não trava a interface: **500 MB enviados em 7,3 s; maior intervalo entre
  quadros durante o envio: 17 ms** (anotação do teste E2E; stack local). O arquivo sintético
  termina em quarentena (`truncado`), como esperado.
- Status muda conforme a fila avança: o teste registra os estados vistos por polling e exige
  pelo menos duas situações distintas terminando em `concluido`/`em_revisao`.

## Fora do escopo

Arrastar e soltar; vários arquivos em paralelo (um envio por vez); retomar envio interrompido
(o envio é refeito do zero; o SHA-256 evita duplicar o conteúdo já lacrado); websockets (o
polling para quando nada está em processamento). O processo novo fica com `status=criado` até o
worker atualizá-lo; a situação mostrada vem de `job_ingestao`.

## Verificação (6.4 a 6.7)

- Suíte Python completa, duas execuções seguidas depois da correção do teste instável (contêiner
  descartável da imagem da API com o código atual): **804 passed, 1 skipped** nas duas
  (9 min 57 s e 9 min 31 s), cobertura 98,59%.
- `docker compose exec api bash scripts/verificar.sh`: passando (ruff, format, mypy strict,
  804 testes, cobertura 98,59%, ponta a ponta da ingestão, regressão de injeção, carimbo do
  front, suíte de injeção do agente).
- `bash front/scripts/e2e.sh`: os 7 testes de `processos.spec.ts` e os 8 de `fluxos.spec.ts`
  passando (o item de menu "Processos" exigiu ajustar a lista esperada do menu do assessor em
  `fluxos.spec.ts` e `componentes.test.ts`). A suíte de 6.8/6.9 (`chat-auditoria.spec.ts`) é de
  outro agente, em andamento no mesmo momento.
- Observação: numa terceira execução de `verificar.sh` (com o outro agente reconstruindo a stack
  em paralelo), `tests/ingestao/test_pecas_api.py::test_reclassificacao_invalida_e_recusada`
  falhou uma vez com "janela TOTP esgotada" (o mesmo assessor da sessão logado várias vezes no
  mesmo passo de 30 s). É instabilidade pré-existente desse arquivo, não deste trabalho; os testes
  novos usam um assessor novo do mesmo gabinete por teste justamente para não gastar a janela.
