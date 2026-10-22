# Revisão — Subetapas 6.4 a 6.9 (processos, dossiê, visualizador, validações, chat, auditoria)

21 de outubro de 2026 · revisor

## 1. Verificação executada

Com os dois agentes encerrados, stack reconstruída (api, db, minio, redis, worker, front, proxy), banco em `0009 (head)`:

```
docker compose exec -T api bash scripts/verificar.sh
   ruff e mypy limpos; 804 testes passaram, 1 pulado, 3 desmarcados; cobertura 98,59%;
   ponta a ponta da ingestão, regressão de injeção da ingestão, front e suíte do agente: ok
bash front/scripts/e2e.sh
   22 de 22 testes Playwright contra a stack real (8 de 6.1-6.3, 7 de 6.4-6.7, 7 de 6.8-6.9), 3,5 min
```

Código lido: `ingestao/renderizacao.py` (camadas opcionais desligadas, recorte à CropBox, sem anotações, execução no sandbox, cache no storage), `api/rotas/visualizador.py` (`exige_processo`, `auditar_rota` como `pagina_vista` com conteúdo, `Cache-Control: private`), `api/rotas/revisao.py` (`exige_processo` mais permissão `ver_auditoria`), `agente/dados/precos.yaml` (versionado, com fonte e aviso de estimativa). Testes novos listados e conferidos por nome.

Após o E2E, a API fica com o cliente de modelo falso ativo (variável exportada pelo script); o revisor recriou o serviço `api` e confirmou `LUPA_AGENTE_CLIENTE` de volta ao padrão.

## 2. Critérios de saída

| Subetapa | Resultado | Evidência |
| --- | --- | --- |
| Tarefa prévia: teste instável | ok | causa real encontrada (`criado_em` vindo do `now()` do banco); teste reescrito com relógio fixo e comparação exata; duas execuções completas verdes; mais forte que antes |
| 6.4 lista e upload | ok | `GET`/`POST /processos` com CNJ validado e 409 em duplicado; upload de 500 MB em 7 a 14 s com quadros de no máximo 17 ms; status acompanha a fila; quarentena legível |
| 6.5 dossiê e linha do tempo | ok | E2E: clique no evento abre o visualizador na página certa |
| 6.6 visualizador | ok | página renderizada como PNG no servidor dentro do sandbox, sem OCG, sem anotações, recortada à CropBox, auditada; `bbox` da evidência calculado dos blocos gravados (fecha o item da 4F); E2E: evidência de cada fato e achado abre e destaca |
| 6.7 validações | ok | correção cria fato novo com `substitui_fato_id`, reexecuta o catálogo versionado, achados antigos ficam como histórico; anotações; catálogo ignora fatos substituídos |
| 6.8 chat | ok | citações clicáveis abrem a página; aviso de conteúdo gerado; descartes contados; recusa explicada; teto encerra a conversa; incidente põe o processo `em_revisao` até liberação auditada por desembargador ou admin (item 3 da revisão 5) |
| 6.9 auditoria | ok | filtros, cursor, exportação CSV e JSON, verificação da cadeia, relatório de uso com custo estimado de tabela versionada (item 5 da revisão 5); desembargador só vê o próprio gabinete; consulta em 140 a 180 ms sobre 1 milhão de eventos, limite 1 s |

## 3. Decisões dos executores endossadas

- Visualizador por imagem renderizada no servidor, não pdf.js com o PDF cru: o PDF nunca chega ao navegador, e o texto oculto por camada ou fora da área não é desenhado. Limitação registrada: conteúdo visível no PDF aparece como está.
- Modo de teste do agente (`LUPA_AGENTE_CLIENTE=falso`) recusado em produção, com teste. Necessário para E2E sem chave.
- Migração numerada 0009 com `down_revision` 0007, porque a 0008 nunca existiu. Linear e aplicada.
- Correção de bug no histórico do chat (ordem de pergunta e resposta na mesma transação), com teste.

## 4. Decisão

**Aprovado.** Subetapa 6.10 liberada.

## 5. Itens para a 6.10 e para a Etapa 7

1. `test_pecas_api::test_reclassificacao_invalida_e_recusada` falhou uma vez por "janela TOTP esgotada": o teste faz login real e o código TOTP pode virar entre a geração e o uso. Corrigir com relógio injetado no login do teste. 6.10.
2. `front/scripts/e2e.sh` deixa a API com o cliente falso após rodar. O script deve recriar o serviço `api` sem a variável ao terminar, mesmo em falha. 6.10.
3. O banco de desenvolvimento acumulou 74 gabinetes sintéticos (calibração, ponta a ponta, carga) e 1 milhão de eventos de carga. Criar `scripts/limpar_dev.py` que remove dados sintéticos por prefixo de nome, recusando rodar fora de desenvolvimento. 6.10.
4. Destaque da evidência cobre a linha inteira, sem precisão de caractere. Aceitável; registrar no guia do assessor (7.9).
5. Upload sem retomada e sem paralelismo; validações sem desfazer correção; filtros de auditoria por id. Melhorias para depois do piloto.
6. O E2E não loga como admin na tela de auditoria porque `fluxos.spec.ts` é dono da senha do admin. "Admin vê todos" fica coberto pelos testes de API. 6.10 pode compartilhar a credencial entre arquivos pela fixture global.
7. Custo dos resumos do dossiê não entra no relatório por usuário. Pequeno; 6.10 ou 7.
