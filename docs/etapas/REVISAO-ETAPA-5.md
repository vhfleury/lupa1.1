# Revisão — Etapa 5 (agente e chat, subetapas 5.1 a 5.10)

21 de outubro de 2026 · revisor

## 1. Verificação executada

Stack reconstruída com front e proxy, banco em `0007 (head)`:

```
docker compose exec -T api bash scripts/verificar.sh
```

Primeira execução: ruff e mypy limpos em 234 arquivos, 765 passaram e **1 falhou**, cobertura 98,65%. Repetição completa da suíte (`pytest --no-cov -rf`): 766 passaram, 1 pulado, 3 desmarcados. Terceira execução do `verificar.sh` inteiro: 765 passaram, 1 falhou, e desta vez o nome foi capturado: `tests/ingestao/test_observabilidade.py::test_metricas_refletem_jobs_paginas_retries_e_falhas`, da Etapa 4A.9. Rodado isolado, passa em 2 s. O teste tem asserções absolutas sobre a idade da fila (`>= 1` numa amostra e `== 0` em outra) que dependem de tempo e da ordem dos demais testes na mesma sessão; com a suíte maior (766 testes, worker e front na stack), a janela de tempo não se cumpre sempre. Não é defeito do código da Etapa 5 nem da observabilidade; é teste instável, e fica como item 6.1. Nenhum outro teste falhou em três execuções.

Código lido: `cliente.py` (opções do SDK), `citacoes.py`, estrutura de `recusa.py`, `contexto.py`, `servico.py`; `docs/agente.md`; lista completa dos testes de `tests/agente/`.

## 2. Critérios de saída por subetapa

| Subetapa | Resultado | Evidência |
| --- | --- | --- |
| 5.1 contrato | ok | `docs/agente.md` com pode/não pode mapeado a AR2, AR3 e AR4, formato, ferramentas, recusa, limites, auditoria, nota de arquitetura do SDK atrás de `ClienteAgente` |
| 5.2 ferramentas de leitura | ok | par (gabinete, processo) por fechamento criado por requisição; `test_toda_ferramenta_ignora_processo_forjado_no_argumento`, `test_pagina_de_outro_processo_e_recusada_mesmo_com_id_real` |
| 5.3 ferramenta de cálculo | ok | `executar_validacao` chama o motor da Etapa 2; `test_tempestividade_respondida_so_com_a_ferramenta_de_calculo` |
| 5.4 válvula de escape | ok | `ler_pagina_original` com limite por conversa e evento por uso; `test_pagina_original_tem_limite_por_conversa_e_cada_uso_e_auditado` |
| 5.5 contexto e pseudonimização | ok | delimitadores aleatórios por chamada, dado antes da instrução; `test_nome_real_do_reu_nunca_chega_ao_modelo`, `test_cpf_some_em_qualquer_formato...` |
| 5.6 conferência de citações | ok | esquema estrito; citação por hash de segmento pseudonimizado ou por hash do trecho original; instrução refletida e identificador de outro processo bloqueiam a resposta; `sem_evidencia` quando nada confere |
| 5.7 recusa | ok | corpus 30 permitidas e 30 vedadas; recall 100%, falso positivo 0%; recusa explica e sugere pergunta permitida; classificação antes do modelo |
| 5.8 injeção do agente | ok | 14 execuções com modelo manipulado simulado sobre dois processos ingeridos pela pipeline real: zero achado suprimido, zero criado, zero vazamento, nenhuma ferramenta embutida executada, 10 respostas descartadas com incidente na auditoria; passo próprio no `verificar.sh` |
| 5.9 registro e custo | ok | tabela `chamada_modelo` (hashes, tokens, latência) apontada pelo evento de auditoria; tetos por chamada, conversa e processo com testes de estouro |
| 5.10 dossiê | ok | esquema fixo sem modelo; resumo opcional de até duas frases com citação obrigatória e rótulo `gerado`; `test_dossie_do_processo_sintetico_bate_com_o_gabarito` |

## 3. Segurança do uso do Claude Agent SDK

Conferido em `cliente.py`: `allowed_tools` só com as ferramentas do Lupa, `disallowed_tools` com todas as embutidas, `permission_mode="dontAsk"`, `setting_sources=[]` (não carrega configuração do host), `max_turns`, `cwd` controlado, mais um hook que nega e registra qualquer tentativa de ferramenta embutida. Testes: `test_opcoes_do_sdk_removem_todas_as_embutidas_e_nao_carregam_configuracao_do_host`, `test_guarda_nega_embutida_e_registra_a_tentativa`.

**O smoke test com o modelo real não rodou.** Não há `ANTHROPIC_API_KEY` neste ambiente e o binário embutido no SDK não enxerga o login do aplicativo Claude da máquina. Os dois testes `llm` (`test_cliente_real_usa_so_a_ferramenta_do_lupa`, `test_cliente_real_nao_le_arquivo_nem_executa_comando`) estão prontos e precisam ser executados pelo responsável técnico com a chave no ambiente antes de qualquer uso real. Até lá, a garantia de que o harness não executa ferramentas embutidas vem das opções do SDK e do hook, testados sem rede.

## 4. Decisões do executor endossadas

- O modelo cita copiando o hash do segmento que a ferramenta entregou; a conferência recalcula os segmentos do texto gravado. Evita pedir ao modelo um SHA-256 e mantém a barreira em código.
- `pydantic` de 2.10.4 para 2.11.10, exigido pelo SDK; suíte inteira passa. Registrado.
- Busca por ILIKE no texto normalizado, para casar exatamente com o que pode ser citado.
- Hashes e tokens em tabela própria em vez de campo livre na auditoria: mantém o esquema da auditoria fixo.

## 5. Decisão

**Aprovado, condicionado à execução do smoke test real pelo responsável técnico antes do piloto.**

## 6. Itens para as etapas seguintes

1. Corrigir o teste instável `test_metricas_refletem_jobs_paginas_retries_e_falhas` (4A.9): substituir as asserções absolutas de idade da fila por asserções relativas com relógio injetado, ou isolar o estado da fila na fixture. Primeira tarefa da próxima etapa que tocar `tests/ingestao`.
2. Pseudonimização cobre nome completo e CPF; sobrenome isolado passa. Estender com tokens do nome como palavra inteira quando tiverem 4 ou mais letras, medindo falsos positivos. Etapa 7.
3. Processo não é marcado "em revisão" após incidente; só a auditoria registra. O `prompt-injection.md`, seção 8, pede bloqueio do relatório até análise. Implementar na 6.8 (tela do chat) com estado visível ao desembargador.
4. Sem limite de tokens por chamada no SDK; o teto é conferido depois e a resposta descartada. Aceitável, mas o custo da chamada já foi pago. Avaliar `max_tokens` quando o SDK expuser.
5. Custo em dinheiro não é gravado, só tokens. Converter no relatório de uso (6.9) a partir de tabela de preços versionada.
6. A imagem da API cresceu cerca de 300 MB com o CLI embutido no SDK. Registrar na Etapa 7 e avaliar imagem separada para o serviço de chat.
7. `tests/agente/test_smoke_llm.py` exige `--noconftest`; documentar no README como rodar no host.
