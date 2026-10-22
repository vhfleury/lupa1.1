# Relatório da Etapa 6.7 — Tela de validações

## O que foi feito

API (`src/lupa/api/rotas/achados.py`, lógica em `src/lupa/dominio/correcoes.py`):

- `GET /processos/{id}/achados/historico`: todos os achados gravados (imutáveis), em ordem, com
  `vigente` marcado.
- `GET /processos/{id}/fatos`: fatos com evidências localizadas (arquivo, página, trecho,
  offsets), `vigente`, `substitui_fato_id` e `substituido_por`.
- `POST /processos/{id}/fatos/{fato_id}/corrigir` com `{status: "corrigido", valor}` ou
  `{status: "confirmado"}`: grava um fato NOVO com o status, `substitui_fato_id` = original,
  `extraido_por=assessor`, `versao_extrator=manual`, confiança 1 e as MESMAS evidências; o
  original não muda. Valor conferido contra o original (mesmo tipo: data por data, número por
  número; igual ao original é recusado, use confirmar); o envelope do réu (`reu_id`) é
  reaplicado. Fato já substituído: 409. Grava `fato_corrigido` e, depois de reexecutar o
  catálogo sobre os fatos vigentes (data de referência: hoje), `validacao_executada`; só os
  achados que mudaram são gravados (achados são imutáveis, os antigos ficam como histórico).
  Exige `anotar` no gabinete.
- `POST /processos/{id}/anotacoes` (`{achado_id | fato_id, texto}` até 2000 caracteres) e
  `GET /processos/{id}/anotacoes` (com o nome do autor). Alvo de outro processo: 404. Grava
  `anotacao` (só ids na auditoria, nunca o texto).
- Correção de fundo: o catálogo passa a ignorar fatos substituídos
  (`fatos_vigentes` em `lupa.ingestao.eventos.etapa.achados_do_processo`), também quando o
  worker reprocessa os eventos; antes, o fato original e o corrigido entrariam juntos e dariam
  conflito.

Front (`/processos/[id]/validacoes`):

- Cada achado vigente: validação, resultado (Conforme/Atenção/Verificar), explicação, valores
  completos (toda data, inclusive dentro de estruturas, com link para a página e a evidência do
  fato que a sustenta), versão do catálogo e data.
- Fatos usados: valor, status, link para cada evidência ("fl. N"), botões Confirmar e Corrigir
  (campo com o valor atual), anotações do fato e botão Anotar.
- Anotações do achado e botão Anotar.
- Histórico: achados anteriores (não vigentes) e fatos substituídos com o valor novo.

## Testes

- `tests/ingestao/test_validacoes_api.py`: correção grava fato novo `corrigido` ligado ao
  original, original intacto no banco, envelope do réu preservado, evidências iguais, achados
  antigos continuam no banco e no histórico (com não vigentes), vigentes coincidem com
  `/achados`, eventos `fato_corrigido` e `validacao_executada`, segunda correção 409;
  confirmação mantém o valor; tipo diferente, valor igual, sem valor e status automático (422);
  fato inexistente (404); anotações em achado e fato com autor e auditoria, alvo de outro
  processo (404), usuário de outro gabinete (404); administrador lê fatos com
  `admin_acesso_conteudo`; regras puras de `valor_corrigido`.
- E2E `6.7 corrigir fato gera fato novo ligado; achado antigo fica no histórico; anotar`: corrige
  uma data usada por um achado (11 anos antes), vê o aviso de reexecução, o status "Corrigido",
  o fato substituído e o achado anterior no histórico, e que o fato antigo não tem mais botão de
  correção; anota um achado e vê a nota.

## Critério de aceite

Correção gera novo fato ligado ao original; achado antigo permanece visível como histórico:
passando nos testes de API e no E2E.

## Fora do escopo

Desfazer correção (corrige-se de novo o fato vigente); editar ou apagar anotação; correção de
fato que não tenha evidência (todo fato tem ao menos uma); escolha da data de referência das
validações na tela (usa a data do dia).
