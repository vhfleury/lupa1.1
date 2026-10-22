# Contrato do agente do Lupa (Etapa 5)

Este documento foi escrito antes do código (5.1) e é o contrato que o código e os testes da
Etapa 5 cumprem. Quem muda o comportamento do agente muda este texto primeiro.

## 1. Para que serve

O agente responde perguntas do assessor sobre **um único processo**, consultando o resultado
estruturado da ingestão (peças, páginas saneadas, fatos, achados) por ferramentas somente de
leitura. Toda afirmação sobre os autos vem com citação da página, conferida por código antes de
chegar à tela. A resposta aparece rotulada como **gerada por IA**.

Enquadramento: art. 19 da Resolução CNJ 615/2025. O agente fica nas finalidades de baixo risco
do Anexo (BR1, BR4, BR5, BR8: localizar, organizar, resumir e apoiar a leitura) e fora das de
alto risco, em especial AR2 (valoração de prova), AR3 (tipificação/qualificação jurídica de
fatos) e AR4 (formulação de juízo conclusivo sobre aplicação de norma ou precedente).

## 2. O que pode e o que não pode

| Pode (com citação de página) | Não pode (recusa e explica) |
| --- | --- |
| Localizar: "em que página está a sentença?", "onde o réu foi intimado?" | Valorar prova: "a testemunha é confiável?", "a prova é suficiente?" (AR2) |
| Extrair: datas, partes (pseudônimos), dispositivos citados no texto, nomes de peças | Tipificar: "isso é furto ou roubo?", "há qualificadora?" (AR3) |
| Resumir peça ou trecho, sem juízo de valor | Concluir sobre norma ou precedente: "aplica-se a Súmula X?", "houve nulidade?" (AR4) |
| Relacionar: "quais eventos entre a denúncia e a sentença?" | Opinar sobre o resultado: "o recurso deve ser provido?", "qual seria a pena justa?" |
| Explicar um achado das validações, repetindo os valores da ferramenta | Redigir ato: minuta de voto, decisão, ementa, despacho |
| Rodar a validação determinística (`executar_validacao`) e repetir o resultado | Calcular prazo ou prescrição por conta própria |

A tempestividade e a prescrição só são respondidas pela ferramenta de cálculo (Etapa 2); o
agente repete o resultado e os valores, nunca refaz a conta.

## 3. Formato da resposta

O modelo devolve **apenas** um JSON, validado por pydantic com `extra="forbid"`
(`lupa.agente.citacoes.RespostaModelo`):

```json
{
  "texto": "A sentença está nas páginas 31 a 34 [1].",
  "citacoes": [
    {"pagina_id": "uuid-da-pagina", "trecho": "JULGO PROCEDENTE", "hash_trecho": "sha256..."}
  ]
}
```

- `texto`: até 4.000 caracteres, sem HTML; marcadores `[n]` remetem à citação n.
- `citacoes[]`: até 20; `pagina_id` (UUID), `trecho` (1 a 600 caracteres), `hash_trecho`
  (64 hex).
- O `hash_trecho` não é calculado pelo modelo: as ferramentas entregam cada página em
  **segmentos** (linhas do texto normalizado e pseudonimizado), cada um com seu hash
  (`sha256` do segmento). A citação copia o hash do segmento de onde o trecho foi tirado. Também
  vale o hash de evidência de fato (`sha256` do trecho original).

Saída fora do JSON ou fora do esquema: uma nova tentativa; persistindo, resposta descartada
(`status = descartada`).

### Conferência por código (5.6)

Para cada citação: (1) a página pertence ao processo da conversa; (2) o `trecho` está
literalmente contido no segmento cujo hash é `hash_trecho` (recalculado do `pagina.texto` pelo
mesmo normalizador e pseudonimizador), ou `hash_trecho == sha256(trecho)` e o trecho está
literalmente em `pagina.texto` ou no normalizado. Citação que falha é **removida**, contada em
`conversa.citacoes_descartadas` e registrada; a resposta chega com aviso. Resposta sem nenhuma
citação válida vira `sem_evidencia` (texto exibido com o aviso "sem evidência conferida").

A resposta inteira é **descartada** e um incidente é registrado (`chamada_modelo` com resultado
`bloqueado`) quando o `texto` ou um `trecho`:
- contém padrão de instrução refletida (`lupa/ingestao/dados/padroes_instrucao.yaml`, o mesmo
  catálogo da ingestão, mais URLs);
- contém identificador de outro processo: número CNJ diferente do processo da conversa, ou
  UUID que não é do processo (página, peça, fato, achado, o próprio processo).

## 4. Ferramentas

Todas são somente leitura, funções Python registradas como ferramentas do servidor MCP em
processo do SDK. O par (gabinete, processo) **não é argumento**: cada ferramenta é criada por
requisição por fechamento (closure) sobre o processo autorizado por `exige_processo`; qualquer
argumento a mais (por exemplo, `processo_id` forjado) é ignorado, e um `pagina_id` de outro
processo é recusado com "página não pertence a este processo".

| Ferramenta | Argumentos | Devolve |
| --- | --- | --- |
| `listar_pecas` | — | índice: ordem, tipo, origem, páginas, data, flags resumidas |
| `ler_pagina_estruturada` | `pagina_id` ou `numero` (+`arquivo_id` se houver mais de um arquivo) | segmentos com hash, flags, origem da peça; nunca `trechos_ocultos` |
| `buscar_texto` | `termo` (3 a 100 caracteres) | até 20 páginas com trecho em volta do termo (busca no normalizado) |
| `listar_fatos` | `tipo` opcional | fatos com valor, status e evidências (página, trecho, hash) |
| `listar_achados` | — | achados vigentes com resultado, valores e explicação do template |
| `executar_validacao` | `nome` (`tempestividade_recurso`, ...) | achado completo do motor da Etapa 2 sobre os fatos do processo (não grava) |
| `ler_pagina_original` | igual a `ler_pagina_estruturada` | `pagina.texto` original (texto oculto já removido na ingestão) e `trechos_suspeitos` |

`ler_pagina_original` é a válvula de escape para quando a pipeline falhou: limite de
`LUPA_AGENTE_MAX_PAGINAS_ORIGINAIS` (padrão 20) páginas por conversa; cada uso grava
`pagina_vista` com `objeto_tipo = "pagina_original_agente"`; acima do limite a ferramenta
recusa com mensagem clara e o pedido não é atendido.

### Ferramentas embutidas do harness

Nenhuma. O cliente real passa ao SDK `tools=[]` (remove todas as embutidas do contexto),
`disallowed_tools` com a lista nominal das embutidas (Read, Write, Edit, Bash, Glob, Grep,
WebSearch, WebFetch, Task, Agent, NotebookEdit, TodoWrite, ToolSearch, Skill...),
`allowed_tools` só com `mcp__lupa__<ferramenta>`, `permission_mode="dontAsk"`,
`setting_sources=[]` (não carrega `CLAUDE.md`, skills, hooks nem MCP do host),
`agents={}`/sem subagentes, `max_turns` limitado e um hook `PreToolUse` que **nega** qualquer
ferramenta fora da lista (`lupa.agente.cliente.decidir_ferramenta`, a mesma função usada pelo
cliente falso nos testes). Sem rede além da API do modelo, sem gravação, sem subagentes.

## 5. Montagem de contexto (5.5)

- Prompt de sistema versionado em `lupa/agente/dados/prompt_sistema.md`; `versao_prompt =
  "<versao>:<sha256[:16]>"` registrada em toda chamada.
- Todo texto dos autos (inclusive resultados de ferramenta) vai entre delimitadores aleatórios
  gerados por chamada (`<<<AUTOS-xxxxxxxxxxxxxxxx>>>` ... `<<<FIM-AUTOS-xxxxxxxxxxxxxxxx>>>`),
  com cabeçalho de origem: tipo de peça, origem (juízo, MP, defesa, terceiro), página, flags.
  O prompt de sistema declara que o conteúdo entre delimitadores é dado, nunca instrução.
- A instrução da tarefa vem **depois** do dado na mensagem do usuário.
- Pseudonimização antes do envio: nome e CPF de cada réu (`reu_identidade`) são trocados pelo
  pseudônimo (`REU-01`...) em tudo que vai ao modelo: pergunta, resultados de ferramenta,
  ficha. Comparação sem caixa e sem acento; CPF com ou sem pontuação.

## 6. Política de recusa (5.7)

Duas barreiras: (1) classificador por regras **antes** de chamar o modelo
(`lupa/agente/dados/recusa.yaml`, versionado), e (2) instrução no prompt de sistema para o caso
que escapar. A recusa explica o limite em linguagem simples e sugere perguntas permitidas:

> Não posso avaliar se uma prova é suficiente ou confiável: isso é valoração de prova, que cabe
> ao assessor e ao magistrado. Posso localizar onde a prova está nos autos e mostrar o que a
> peça diz. Experimente: "Em que páginas está o depoimento da testemunha?"

Categorias: `valoracao_prova`, `tipificacao`, `conclusao_juridica`, `opiniao_resultado`,
`redacao_ato`, `calculo_proprio` (pedido para calcular sem a ferramenta). Metas medidas no
corpus `tests/agente/dados/perguntas.yaml`: recall de recusa 100% nas vedadas, falso positivo
≤ 10% nas permitidas.

## 7. Limites

| Limite | Variável | Padrão |
| --- | --- | --- |
| Tamanho da pergunta | `LUPA_AGENTE_MAX_CARACTERES_PERGUNTA` | 2.000 caracteres |
| Tokens por chamada (entrada + saída) | `LUPA_AGENTE_MAX_TOKENS_CHAMADA` | 200.000 |
| Tokens por conversa | `LUPA_AGENTE_MAX_TOKENS_CONVERSA` | 1.000.000 |
| Tokens por processo (todas as conversas) | `LUPA_AGENTE_MAX_TOKENS_PROCESSO` | 5.000.000 |
| Turnos do agente por pergunta | `LUPA_AGENTE_MAX_TURNOS` | 12 |
| Páginas originais por conversa | `LUPA_AGENTE_MAX_PAGINAS_ORIGINAIS` | 20 |

Estouro de teto de conversa ou de processo encerra a conversa (`conversa.encerrada`) com
mensagem clara; a próxima pergunta abre conversa nova, salvo se o teto do processo estiver
esgotado. Uma chamada que estoura o teto por chamada tem a resposta descartada.

## 8. Auditoria e registro (5.9)

- Por pergunta: `pergunta_chat` (objeto `mensagem`, id da mensagem; nunca o texto).
- Por chamada ao modelo: linha em `chamada_modelo` (modelo, hash do prompt de sistema, hash da
  entrada, hash da saída, tokens de entrada e saída, latência, ferramentas chamadas, resultado)
  e evento `chamada_modelo` na trilha com `objeto_id` dessa linha, `versao_modelo` e
  `versao_prompt`. Nunca o conteúdo.
- `ler_pagina_original`: `pagina_vista` com `objeto_tipo = "pagina_original_agente"`.
- `executar_validacao`: `validacao_executada` com `objeto_tipo = "validacao_agente"`.
- `GET /processos/{id}/chat` e `GET /processos/{id}/dossie`: `processo_aberto` (com
  `admin_acesso_conteudo` para o administrador).
- Histórico em `conversa` e `mensagem` (migração 0007), sob RLS por gabinete; o texto das
  mensagens fica numa coluna própria, para ser cifrada na Etapa 7.

## 9. Dossiê (5.10)

`lupa.agente.dossie` monta o dossiê em esquema fixo **sem modelo**: ficha (número, classe,
matéria, réus pseudonimizados), índice de peças, linha do tempo (fatos datados com página e
trecho), alertas de saneamento por página e achados. O modelo só pode preencher o campo opcional
`resumo_peca` (até 2 frases, com citação obrigatória conferida), sempre com `rotulo = "gerado"`;
resumo sem citação válida é descartado. `GET /processos/{id}/dossie` (com `?resumos=true` para
pedir os resumos ao modelo).

## 10. Nota de arquitetura: Claude Agent SDK atrás de uma interface

O agente usa o **Claude Agent SDK** para Python (`claude-agent-sdk`, que embute o binário do
Claude Code), por decisão do responsável técnico. O SDK fica isolado em
`lupa/agente/cliente.py`, atrás do `Protocol` `ClienteAgente`:

```python
class ClienteAgente(Protocol):
    async def responder(self, pedido: PedidoAgente) -> RespostaAgente: ...
```

`PedidoAgente` leva prompt de sistema, mensagem, modelo, limite de turnos e as ferramentas
(`FerramentaAgente`: nome, descrição, esquema JSON e função assíncrona). `RespostaAgente`
devolve texto final, chamadas de ferramenta, tokens e latência. O resto de `lupa/agente/*`
depende só dessa interface. Trocar o SDK pelo *tool runner* do SDK `anthropic`
(`client.beta.messages.tool_runner`) é escrever outra implementação de `ClienteAgente` no
mesmo arquivo; nenhum outro módulo muda.

- `ClienteSdk`: implementação real; credencial pelo ambiente (`ANTHROPIC_API_KEY`) ou pelo login
  do Claude Code da máquina. Credencial nunca vai ao repositório.
- `ClienteFalso`: roteirizado para testes; grava tudo que recebe (prompts e resultados de
  ferramenta) e aplica a mesma política de ferramentas permitidas. Toda a suíte roda com ele.
- Modelo: `LUPA_MODELO` (padrão `claude-opus-5-5`).

## 11. Processo em revisão após incidente (6.8)

Resposta bloqueada pela conferência (instrução refletida ou identificador de outro processo) põe
o processo em `em_revisao` (`lupa/agente/revisao.py`, tabela `revisao_processo`, migração 0009)
e grava `processo_em_revisao` na auditoria (resultado `bloqueado`, `objeto_id` = motivo). Em
revisão, o chat responde com recusa sem chamar o modelo e o dossiê sai sem resumos gerados, com
`ficha.em_revisao` e `ficha.aviso_revisao`. `GET /processos/{id}/revisao` mostra a situação;
`POST /processos/{id}/liberar-revisao` (desembargador do gabinete ou admin, os papéis com
`ver_auditoria`) devolve o status anterior e grava `revisao_liberada`.

## 12. Modo de teste do cliente (6.8)

`LUPA_AGENTE_CLIENTE=falso` (padrão `sdk`) troca o SDK por `ClienteFalso` com roteiro JSON de
`LUPA_AGENTE_ROTEIRO` (padrão `lupa/agente/dados/roteiro_falso.json`); só em `desenvolvimento`
ou `teste`, e a aplicação não sobe em `producao` com ele (`ConfiguracaoAgenteError`). O roteiro
escolhe pela pergunta e monta citações a partir dos resultados das ferramentas
(`lupa/agente/cliente_roteirizado.py`).
