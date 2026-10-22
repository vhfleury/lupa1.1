# Termos de uso do Lupa

> **MINUTA para revisão de advogado; não é parecer jurídico.** Versão 0.1 · 21 de outubro de 2026 · subetapa 8.2. Trechos marcados "a confirmar pelo advogado" dependem de decisão jurídica.

## 1. Partes e objeto

- **Fornecedor e responsável técnico:** Victor Hugo Fleury Barreto ("fornecedor"), titular do Lupa e controlador dos dados pessoais tratados no sistema.
- **Usuários:** o desembargador do gabinete e os assessores que ele cadastrar.
- **Tribunal:** não é parte destes termos, não tem acesso ao sistema e não participa do piloto.
- **Objeto:** uso privado do Lupa como ferramenta de apoio à conferência de processos judiciais em 2º grau, na hipótese do art. 19, § 2º, da Resolução CNJ 615/2025 (contratação privada quando o tribunal não oferece solução corporativa), observadas as condições do § 3º do mesmo artigo.

## 2. Finalidade: apoio, nunca decisão

O Lupa organiza os autos, monta a linha do tempo, roda validações objetivas e responde perguntas de localização, sempre apontando a página de origem. Ele **não decide, não opina, não valora prova, não tipifica fatos e não redige atos**. A conclusão jurídica é sempre do assessor ou do magistrado. As finalidades ficam dentro das de baixo risco do Anexo da Resolução (BR1, BR4, BR5 e BR8) e fora das de alto risco (AR1 a AR5), cujo uso com ferramenta privada é vedado (art. 19, § 3º, V).

## 3. O que o sistema faz e o que não faz

| Faz (sempre com citação da página) | Não faz (recusa e explica) |
| --- | --- |
| Localizar peças e atos nos autos | Valorar prova (AR2) |
| Extrair datas, partes (por pseudônimo), dispositivos citados, nomes de peças | Tipificar fatos ou apontar qualificadora (AR3) |
| Resumir peça ou trecho sem juízo de valor | Concluir sobre aplicação de norma, súmula ou precedente (AR4) |
| Relacionar eventos do processo | Opinar sobre o resultado do recurso ou a pena |
| Explicar achados das validações, repetindo os valores calculados | Redigir voto, decisão, ementa ou despacho |
| Rodar as validações determinísticas (tempestividade, prescrição) | Calcular prazo ou prescrição "por conta própria" no chat |

Detalhes técnicos: `docs/agente.md`, seções 2, 6 e 7.

## 4. Responsabilidade do magistrado e dever de conferência

1. O uso é auxiliar e complementar; o magistrado permanece **integralmente responsável** pelas decisões e pelas informações nelas contidas (art. 19, § 3º, II).
2. Todo achado, data, cálculo e citação do Lupa deve ser **conferido pelo usuário na página indicada dos autos** antes de ser usado. O sistema pode errar (leitura de página digitalizada, data mal extraída, calendário desatualizado).
3. O assessor responde perante o desembargador pela conferência do que levar à minuta.
4. Se o Lupa auxiliar a redação de ato judicial, a menção no corpo da decisão fica a critério do magistrado (art. 19, § 6º). Como o registro em sistema interno do tribunal previsto no mesmo parágrafo se aplica a uso privado: a confirmar pelo advogado.
5. O art. 19, § 3º, I, prevê capacitação dos usuários conforme programa de letramento do tribunal; a leitura dos guias do Lupa não substitui essa capacitação (a confirmar pelo advogado como comprovar).

## 5. Processos sigilosos

Na primeira versão é **vedado inserir processo ou peça em segredo de justiça** ou com dados sigilosos (art. 19, § 3º, IV). O sistema bloqueia o que reconhece como sigiloso, mas o bloqueio automático não substitui o cuidado do usuário: na dúvida, não envie.

## 6. Conta, senha e MFA

- Cada usuário tem conta **pessoal e intransferível**; é proibido compartilhar usuário, senha ou o aplicativo autenticador.
- O MFA por aplicativo autenticador (TOTP) é obrigatório.
- Perda de senha ou de MFA: o desembargador (para assessores) ou o fornecedor gera credencial temporária, com troca obrigatória no primeiro acesso. Tudo fica registrado.
- Suspeita de uso da conta por outra pessoa: avise o desembargador e o fornecedor **no mesmo dia**.

## 7. Registro de acesso (auditoria)

Todo acesso e toda ação ficam registrados: quem, quando, **endereço IP, localização aproximada derivada do IP**, processo, ação, resultado e versão do modelo quando há chamada ao agente. Os registros não guardam o conteúdo dos autos nem o texto das perguntas e respostas. O desembargador vê a auditoria do gabinete; o acesso do fornecedor a conteúdo de autos aparece em destaque. Ao aceitar estes termos, o usuário declara ciência desse registro.

## 8. Limites de uso

Há tetos técnicos por pergunta, conversa e processo (tamanho da pergunta, tokens, turnos do agente, páginas por conversa), descritos em `docs/agente.md`, seção 7. Ao estourar um teto a conversa é encerrada com aviso. É vedado tentar contornar recusas, testar ataques ou inserir instruções nos autos ou nas perguntas.

## 9. Modelo de linguagem externo

O chat e os resumos usam modelo da Anthropic por API. Vão ao modelo apenas trechos dos autos **pseudonimizados** (sem nome e CPF do réu). O contrato do fornecedor do modelo deve vedar o uso dos dados para treinamento ou outros fins não autorizados (art. 19, § 3º, III); a conferência desses termos é condição do piloto (`checklist-piloto.md`).

## 10. Suporte e incidentes

- Suporte: diretamente com o fornecedor, pelo canal combinado com o gabinete ([a preencher]). Nunca envie trecho de autos por mensagem ou e-mail.
- Incidentes (acesso estranho, processo "em revisão", suspeita de vazamento): seguir `plano-de-incidentes.md`.
- Disponibilidade e responsabilidade por indisponibilidade no piloto: a confirmar pelo advogado.
- Remuneração ou gratuidade do piloto: a confirmar pelo advogado.

## 11. Informação ao tribunal

O magistrado deve prestar informações ao tribunal sobre o uso, na forma do regulamento (art. 19, § 7º). O sistema oferece o relatório de uso para isso (`relatorio-uso-tribunal.md`).

## 12. Encerramento e descarte

- O desembargador desativa imediatamente o assessor que deixar o gabinete. A desativação não apaga o histórico de auditoria.
- Ao fim do piloto ou a pedido do desembargador, os processos são descartados pela destruição da chave de cada processo; cópias em backup cifrado deixam de existir em até 30 dias (retenção padrão do backup).
- Os registros de auditoria são mantidos por prazo maior que o dos dados dos processos (prazo exato: a confirmar pelo advogado).

## 13. Aceite

Declaro que li estes termos, o guia do meu papel (`guia-assessor.md` ou `guia-desembargador.md`) e o `aviso-de-tratamento.md`, e que concordo com eles.

| Nome | Papel | Usuário no Lupa | Data | Assinatura |
| --- | --- | --- | --- | --- |
| | Desembargador | | | |
| | Assessor | | | |

Forma do aceite (papel, assinatura eletrônica ou tela no sistema): a confirmar pelo advogado.
