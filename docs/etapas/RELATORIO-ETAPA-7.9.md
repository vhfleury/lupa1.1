# Relatório da subetapa 7.9: guias do assessor e do desembargador

## Entregas

- `docs/guia-assessor.md`: o que faz e não faz; primeiro acesso e autenticador; criar processo e
  enviar autos (estados, quarentena, sigiloso); dossiê e significado de cada marca (pseudônimos,
  selo de correção, confiança, flags e alertas de saneamento, rótulo GERADO); visualizador pela
  evidência; leitura de alerta e conta à mão com exemplo numérico para tempestividade, prescrição
  e preventiva (incluindo a regra da sexta-feira e a data de referência); corrigir fato e o efeito
  nos achados; chat (o que recusa e por quê, pelo enquadramento do CNJ sem citar artigo, citações,
  sem evidência, descartes, em revisão, limite); auditoria e quem vê; pedido de reclassificação de
  peça (não há tela: via desembargador → administrador); o que fazer quando algo parece errado;
  limitações.
- `docs/guia-desembargador.md`: gestão de assessores, reset de senha e autenticador, liberar
  processo em revisão, auditoria do gabinete (filtros, exportação, integridade), relatório de uso
  e dever de informar o tribunal.
- `front/e2e/capturas.spec.ts`, `front/e2e/capturas.config.ts` (projeto `capturas` que depende de
  `fluxos`; não altera a suíte existente) e `front/scripts/capturas.sh` (preparo do `e2e.sh` e
  PNGs gravados em `docs/imagens/` por bind mount `-v`, sem cópia do contêiner).

## Teste de leitura (subagente Sonnet, só os dois guias, 10 perguntas práticas)

| Rodada | Acertos | Observações |
| --- | --- | --- |
| antes | 8 completos + 2 parciais (Q2 sexta-feira, Q4 data de referência) | faltavam: regra da intimação na sexta, data de referência, preventiva sem revisão, forma do pedido de reclassificação, como achar `processo_em_revisao` na auditoria |
| depois das correções | 10/10 | restou só dúvida se a segunda é dia 1 na regra da sexta; acrescentado exemplo numérico (12/09 sexta → 19/09) |

## Capturas de tela

`bash front/scripts/capturas.sh`: 25 testes passando (fluxos + capturas), 11 PNGs em
`docs/imagens/` (auditoria, chat, corrigir-fato, dossie, login, processo, processos,
relatorio-uso, usuarios, validacoes, visualizador; de 14 a 155 KB, 1,05 MB no total), todos sobre
processos e contas sintéticos.

Correções da revisão: (1) o script reduzia o upload do fluxo para 5 MB, e o teste de progresso
de `processos.spec.ts` falhava (a barra não chegava a mostrar valor intermediário), bloqueando o
projeto `capturas`; agora usa o tamanho padrão do E2E. (2) O passo do chat contava mensagens antes
de o histórico carregar; agora espera a rede assentar e conta só a conversa atual.

`bash front/scripts/e2e.sh` depois disso: **36 passando** (7,3 min). Disco: 122 GB livres antes,
121 GB depois.

## Pendente

- Leitura por um assessor humano de fora do projeto (critério do roteiro) continua a fazer no piloto.
