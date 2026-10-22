# Lupa — Roteiro das Etapas 4 a 8 em subetapas

20 de outubro de 2026 · Victor Hugo

Cada etapa grande está quebrada em dez subetapas pequenas. Cada subetapa é uma unidade de trabalho para um agente executor, com revisão separada, no mesmo formato do `plano-execucao-v1.md`: tarefas, critérios de aceite, relatório em `docs/etapas/RELATORIO-ETAPA-N.M.md` e revisão em `docs/etapas/REVISAO-ETAPA-N.M.md`. As regras comuns do plano v1 valem para todas.

Este roteiro define escopo, entregável e critério de saída de cada subetapa. A especificação detalhada (tarefas numeradas, estrutura de arquivos, casos de teste) é escrita imediatamente antes de cada subetapa começar, quando o estado real do código já é conhecido.

Legenda de dependência: **[S3]** depende da decisão sobre o object storage (MinIO ou substituto).

**Premissa de projeto (decisão de 20/10/2026):** a ingestão é desenhada para o pior caso e não espera o arquivo real do Projudi, mas decide caso a caso o que fazer com cada arquivo. Pior caso: PDF único de milhares de páginas sem delimitador de peça; mistura de páginas nativas, digitalizadas, híbridas e vazias; nenhum índice de movimentações. O sistema precisa funcionar nesse cenário construindo o próprio índice a partir do conteúdo. Mas todo arquivo passa primeiro por um diagnóstico que identifica o que ele realmente é e escolhe o caminho mais barato e confiável:

- ZIP com um PDF por peça, nomeado e datado: as fronteiras vêm dos arquivos, e o classificador de fronteira só confere.
- PDF único com marcadores (bookmarks) ou índice de movimentações legível: as fronteiras vêm do índice, e o classificador só confere.
- PDF único sem nada: o classificador de fronteira decide.
- Por página, independentemente do caso acima: nativa, digitalizada, híbrida ou vazia, cada uma com seu extrator.

O diagnóstico e a rota escolhida ficam registrados no processo, visíveis ao assessor. Quando o processo real chegar, ele entra como caso de teste e calibração do diagnóstico, não como pré-requisito.

---

## Etapa 4 — Pipeline de ingestão

> **Substituída.** A Etapa 4 foi quebrada em seis etapas (4A a 4F, sessenta subetapas) em `roteiro-etapa-4.md`. A tabela abaixo fica como resumo histórico; a especificação válida é a do outro arquivo.

Objetivo: transformar um PDF ou ZIP em páginas com texto, peças classificadas, índice do processo e fatos com evidência, gravados no modelo da Etapa 1. Sem modelo de linguagem. Projetada para PDF único, páginas de todos os tipos e sem índice de origem.

| # | Subetapa | Entregável | Pronta quando |
| --- | --- | --- | --- |
| 4.1 | Adaptador validações ↔ domínio | `lupa/validacoes/adaptador.py` com `para_modelo` e `para_dominio`; remoção dos esquemas locais de `modelo.py` | Teste de ida e volta com `fabrica_fato` passa; `executar_catalogo` roda sobre fatos vindos do banco |
| 4.2 | Gerador de autos sintéticos difíceis | `scripts/gerar_autos.py`: monta PDF único de centenas a milhares de páginas com peças de tipos variados em sequência realista, páginas nativas, digitalizadas (renderizadas em imagem com ruído e rotação), híbridas e vazias, carimbos e cabeçalhos, sem índice; gera o gabarito junto (limites de peça, tipo, datas, páginas) | Gerador reproduzível por semente; gabarito em JSON; dez processos de referência gerados e versionados em repositório separado |
| 4.3 | Recepção e lacre **[S3]** | `lupa/ingestao/recepcao.py`: upload, validação de tipo e tamanho, SHA-256, gravação cifrada-ready no object storage, registro em `arquivo` | Mesmo arquivo duas vezes não duplica; arquivo corrompido vai para quarentena; evento de auditoria `arquivo_enviado` |
| 4.4 | Inventário, diagnóstico e sandbox | `lupa/ingestao/inventario.py`: extração segura de ZIP (sem path traversal, limites de tamanho e quantidade), manifesto com hash por arquivo; `lupa/ingestao/diagnostico.py`: identifica o cenário do arquivo (ZIP por peça, PDF com bookmarks ou índice, PDF sem nada) e escolhe a rota de split, registrando o diagnóstico no processo; worker de parsing isolado por subprocesso com limite de memória, tempo e sem rede; fila com jobs idempotentes por lote de páginas | Cada um dos três cenários sintéticos é diagnosticado corretamente e roteado; ZIP malicioso rejeitado; PDF patológico morto pelo limite com falha explícita, nunca sucesso silencioso |
| 4.5 | Triagem de páginas | `lupa/ingestao/paginas.py`: por página, sinais combinados (caracteres imprimíveis, cobertura de texto, área de imagem, fragmentação, orientação) para classificar nativa, digitalizada, híbrida ou vazia; página ambígua é marcada e vai para OCR integral | Matriz de confusão do roteador sobre os autos sintéticos; o falso negativo perigoso (nativa com conteúdo em imagem) medido e abaixo de 1% |
| 4.6 | Texto nativo e OCR | PyMuPDF para texto com coordenadas; Tesseract por-BR nas páginas digitalizadas e híbridas com correção de rotação; caixas convertidas para coordenadas de página; nas híbridas, texto nativo e OCR guardados e comparados; `pagina` gravada com `hash_texto` e tipo | CER medido por tipo de página nos autos sintéticos; divergência OCR × nativo gera flag; OCR roda em paralelo por lote e o tempo por mil páginas é registrado |
| 4.7 | Controles de injeção na ingestão | `lupa/ingestao/saneamento.py`: texto oculto, metadados e anotações descartados, normalização Unicode, blocos codificados, padrões de instrução, idioma inesperado; flags em `pagina.flags` | Corpus de injeção por vetor do `prompt-injection.md` gera as flags esperadas; peças legítimas com frases imperativas não são bloqueadas |
| 4.8 | Detecção de fronteiras de peça | `lupa/ingestao/fronteiras.py`: classificador sequencial de "esta página começa uma peça nova" por sinais de cabeçalho, título, reinício de numeração, assinatura digital, mudança de layout e padrão de protocolo; primeiro por regras, com pontuação. Quando o diagnóstico encontrou arquivos por peça, bookmarks ou índice, essas fronteiras são a fonte principal e o classificador só aponta divergências | Precisão e recall de fronteira ≥ 95% no cenário sem índice; nos cenários com índice, toda divergência entre índice e classificador é marcada; fronteira incerta vai ao assessor, nunca é forçada |
| 4.9 | Classificação de peças e construção do índice | `lupa/ingestao/pecas.py`: tipo de cada peça por regras com confiança; origem (juízo, MP, defesa, terceiro); `lupa/ingestao/indice.py` monta o índice do processo (peça, tipo, páginas, data da peça, confiança), que é o que o dossiê exibe | Precisão de tipo ≥ 95% nos sintéticos; peça ambígua fica `outros` com confiança baixa; índice exportável em JSON e reclassificável pelo assessor com registro |
| 4.10 | Extração de eventos por regra e ponta a ponta | `lupa/ingestao/eventos.py`: datas e tipos de fato por expressões regulares e padrões por tipo de peça; cada fato com evidência (trecho, offsets, hash); gravação via `salvar_fato`; execução do catálogo ao final; quando o processo real do Projudi existir, entra aqui como caso de calibração | Processo sintético ponta a ponta: upload até achados, zero fato sem evidência, datas com precisão ≥ 99% contra o gabarito; tempo total por mil páginas registrado |

---

## Etapa 5 — Agente e chat

Objetivo: agente com Claude Agent SDK que consulta o processo estruturado, responde perguntas de localização e extração com citação conferida por código, e recusa valoração, tipificação e conclusão jurídica.

| # | Subetapa | Entregável | Pronta quando |
| --- | --- | --- | --- |
| 5.1 | Contrato do agente | `docs/agente.md`: o que o agente pode e não pode fazer, formato de resposta com citações, lista de ferramentas, política de recusa, limites de tokens e páginas | Documento aprovado antes de qualquer código |
| 5.2 | Ferramentas de leitura estruturada | `lupa/agente/ferramentas/`: `listar_pecas`, `ler_pagina_estruturada`, `buscar_texto`, `listar_fatos`, `listar_achados`; todas somente leitura e travadas no par (gabinete, processo) da sessão | Teste prova que a ferramenta não devolve dados de outro processo mesmo com id forjado no argumento |
| 5.3 | Ferramenta de cálculo | `executar_validacao` que chama o motor da Etapa 2 como ferramenta; resultado devolvido com valores completos | Agente consegue responder "o recurso é tempestivo?" só com a ferramenta, sem calcular por conta própria |
| 5.4 | Válvula de escape | `ler_pagina_original`: renderiza texto da página do PDF original, limite de N páginas por conversa, registrada em auditoria | Limite excedido gera recusa clara; cada uso gera evento |
| 5.5 | Montagem de contexto e prompts | Prompt de sistema versionado com hash; texto dos autos entre delimitadores aleatórios por chamada, rotulado por origem e flags; pseudonimização antes do envio | Teste prova que nome real de réu não aparece em nenhum prompt enviado |
| 5.6 | Conferência de citações | `lupa/agente/citacoes.py`: cada citação da resposta é conferida contra o texto real da página por hash e substring; citação inválida é removida e registrada | Resposta com citação inventada chega ao usuário sem a citação e com aviso; contador de descartes por conversa |
| 5.7 | Política de recusa | Classificador de intenção por regras mais instrução no prompt; recusa com explicação do limite para perguntas de valoração de prova, tipificação e conclusão jurídica | Corpus de 50 perguntas (25 permitidas, 25 vedadas) com recall de recusa 100% nas vedadas e falso positivo ≤ 10% nas permitidas |
| 5.8 | Suíte de injeção do agente | Corpus de autos sintéticos com injeções por vetor; metas: zero achado suprimido, zero achado criado, zero vazamento de identificador | Suíte roda em `scripts/verificar.sh` com marcador próprio; relatório por versão de modelo e prompt |
| 5.9 | Registro e custo | Cada chamada registra versão de modelo, hash de prompt, hash de entrada e saída, tokens e latência; teto de tokens por conversa e por processo | Evento `chamada_modelo` na auditoria; estouro de teto encerra a conversa com mensagem |
| 5.10 | Dossiê gerado | Fluxo que produz o dossiê em esquema fixo (índice de peças, linha do tempo, ficha, alertas) a partir dos dados estruturados, com o agente só preenchendo campos de texto curto e citados | Dossiê do processo sintético validado contra gabarito; nenhuma frase livre sem rótulo "gerado" |

---

## Etapa 6 — Interface web

Objetivo: aplicação web usada por assessores e desembargador, cobrindo login, upload, dossiê, visualizador com evidência, chat e auditoria.

| # | Subetapa | Entregável | Pronta quando |
| --- | --- | --- | --- |
| 6.1 | Escolha e esqueleto do front | Decisão registrada (Next.js ou SvelteKit); projeto com build em contêiner, lint, testes de componente, tema e layout base | `docker compose up` serve o front atrás da API; página em branco autenticada carrega |
| 6.2 | Login e MFA | Telas de login em dois passos, confirmação de MFA no primeiro acesso, troca de senha obrigatória, logout | Fluxo completo testado ponta a ponta com Playwright contra a API real |
| 6.3 | Gestão de usuários | Telas do desembargador para criar, desativar, reativar assessores e resetar senha ou MFA; tela do admin para gabinetes e desembargadores | Matriz de permissões da Etapa 3 refletida na interface e reconfirmada no servidor |
| 6.4 | Lista e upload de processos | Lista por gabinete com status de processamento; upload com progresso, validação de tipo e tamanho, feedback de quarentena | Upload de 500 MB não trava a interface; status muda conforme a fila avança |
| 6.5 | Dossiê e linha do tempo | Tela do dossiê: índice de peças, ficha, linha do tempo clicável, alertas de ingestão | Clique em evento abre o visualizador na página certa |
| 6.6 | Visualizador de PDF com evidência | pdf.js renderizando a página como imagem com destaque do trecho (bounding box); navegação por página; texto oculto não aparece | Evidência de cada fato e achado abre na página e destaca o trecho |
| 6.7 | Tela de validações | Lista de achados com resultado, valores completos e explicação; botão de anotar; marcação de fato confirmado ou corrigido | Correção gera novo fato ligado ao original; achado antigo permanece visível como histórico |
| 6.8 | Chat | Conversa por processo com citações clicáveis, aviso de conteúdo gerado, contador de citações descartadas, recusas explicadas | Citação clicada abre a página; resposta sem citação válida aparece marcada |
| 6.9 | Tela de auditoria | Consulta com filtros, exportação CSV e JSON, verificação de integridade da cadeia, relatório de uso por processo e por usuário | Desembargador vê só o próprio gabinete; admin vê todos; consulta responde em menos de 1 s na interface |
| 6.10 | Acessibilidade, segurança do front e testes ponta a ponta | Cabeçalhos de segurança (CSP, HSTS), sem renderização de HTML vindo dos autos, navegação por teclado, contraste; suíte Playwright cobrindo os fluxos principais | Scanner de cabeçalhos sem alerta; suíte E2E no `scripts/verificar.sh` |

---

## Etapa 7 — Criptografia em repouso e guia dos assessores

Objetivo: fechar a fase 2 da seção 6 dos requisitos e entregar a documentação em linguagem simples.

| # | Subetapa | Entregável | Pronta quando |
| --- | --- | --- | --- |
| 7.1 | Decisão do object storage **[S3]** | `docs/decisoes/object-storage.md`: MinIO fork, Chainguard, Garage ou RustFS, com critérios (manutenção, API S3, SSE, licença) | Decisão assinada por Victor; compose atualizado se mudar |
| 7.2 | Cofre de chaves | Vault em contêiner com Transit; chave mestra por gabinete; procedimento de inicialização e unseal documentado | Chave por gabinete criada pelo admin via API; segredo de acesso ao Vault fora do `.env` |
| 7.3 | Chave por processo | Derivação ou envelope de chave por processo a partir da chave do gabinete; metadados em `gabinete.chave_criptografia_ref` e campo novo em `processo` | Processo novo recebe chave própria; chave de um processo não abre outro |
| 7.4 | Cifra dos originais | PDF cifrado antes de qualquer parser abrir; SSE do object storage com chave do processo; worker decifra cópia temporária em memória ou disco efêmero | Objeto no storage é ilegível sem a chave; teste prova que a cópia temporária é apagada ao fim do job |
| 7.5 | Cifra do texto e dos índices | `pagina.texto`, `evidencia.trecho` e índice de busca cifrados com pgcrypto ou cifra na aplicação; busca por índice separado protegido | Dump do banco não expõe texto de autos em claro |
| 7.6 | Cifra da tabela de identidades | `reu_identidade` com chave própria por gabinete; acesso só pela camada de apresentação, registrado | Consulta direta à tabela devolve bytes cifrados |
| 7.7 | Exclusão criptográfica | Rotina de descarte por processo: destruição da chave, remoção dos objetos, limpeza de índices e caches, registro assinado | Após descarte, nenhum derivado do processo é recuperável; evento de auditoria com hash do registro |
| 7.8 | Backup cifrado | Backup diário do banco e do storage com chave do período; restauração testada; chaves expiram com o backup | Restauração em ambiente limpo recupera um processo sintético |
| 7.9 | Guia dos assessores | `docs/guia-assessor.md`: o que a ferramenta faz e não faz, como ler um alerta e refazer a conta, como conferir uma citação, limites do chat, o que fica registrado, como pedir correção | Lido por um assessor de fora do projeto que consegue executar cada tarefa descrita sem ajuda |
| 7.10 | Documentação de operação | `docs/operacao.md`: subir, atualizar, rotacionar chaves, restaurar backup, responder incidente, exportar relatório de uso para o tribunal | Procedimento de incidente ensaiado uma vez com cenário simulado |

---

## Etapa 8 — Piloto

Objetivo: usar o sistema com processo real, medir utilidade e ajustar.

| # | Subetapa | Entregável | Pronta quando |
| --- | --- | --- | --- |
| 8.1 | Ambiente de piloto | Infra própria isolada, HTTPS com certificado válido, domínio, backups ligados, monitoramento básico | Checklist de segurança da seção 6 dos requisitos conferido item a item |
| 8.2 | Conformidade do piloto | Termos de uso do sistema, aviso de tratamento de dados, registro das operações de tratamento, modelo de relatório de uso para o art. 19, §7º da Res. CNJ 615/2025 | Documentos revisados por Victor e entregues ao desembargador |
| 8.3 | Cadastro e treinamento | Contas do desembargador e assessores criadas, MFA ativado, sessão de treinamento com o guia | Cada usuário faz login, abre um processo sintético e confere um achado sem ajuda |
| 8.4 | Primeiro processo real | Ingestão do processo público já disponível; conferência de cada peça, evento e achado por um assessor | Taxa de classificação correta de peças e de datas medida e registrada |
| 8.5 | Gabarito humano | Conjunto de referência com 5 a 10 processos públicos anotados pelos assessores (peças, datas, resultado esperado das validações) | Gabarito versionado em repositório separado; suíte de regressão roda contra ele |
| 8.6 | Ajuste de regras | Correção de padrões de extração, calendários e regras de borda a partir do gabarito e da confirmação do gabinete | Precisão de datas ≥ 99% no gabarito; calendários oficiais do TJGO carregados |
| 8.7 | Uso acompanhado | Duas a quatro semanas de uso real com registro de achados confirmados, rejeitados e tempo economizado por processo | Planilha de medição preenchida por processo |
| 8.8 | Revisão de segurança | Teste de intrusão externo ou revisão independente cobrindo autenticação, isolamento por gabinete, injeção via autos e exfiltração | Relatório recebido; itens críticos corrigidos antes de continuar |
| 8.9 | Relatório do piloto | `docs/relatorio-piloto.md`: métricas, achados confirmados, falsos alertas, feedback dos assessores, custo por processo | Apresentado ao desembargador |
| 8.10 | Decisão de continuidade | Lista de ajustes para a versão 2 (cível, validações semânticas, anonimização para sigilo, mais gabinetes) priorizada com o gabinete | Backlog da v2 escrito e aprovado |

---

## Ordem sugerida e paralelismo

- 4.1 pode começar assim que a Etapa 3 for aprovada. 4.2 (gerador de autos sintéticos) vem logo em seguida, porque todas as demais subetapas da ingestão são medidas contra ele. Nenhuma subetapa espera o processo real do Projudi; ele entra em 4.10 e em 8.4 como calibração.
- 5.1 e 5.2 podem começar em paralelo com a Etapa 4 a partir de 4.1, porque consomem o modelo de dados, não a ingestão.
- 6.1 a 6.3 dependem só da Etapa 3 e podem andar em paralelo com 4 e 5.
- 7.1 deve ser decidida antes de 4.3, porque a recepção grava no object storage.
- A Etapa 8 começa quando 4, 5 e 6 estiverem completas e 7.1 a 7.4 implementadas. 7.5 a 7.8 podem entrar durante o piloto, desde que antes de qualquer processo sigiloso.

## Contagem

Cinco etapas, cinquenta subetapas. Somadas às quatro já planejadas, o caminho até o fim do piloto tem 54 unidades de trabalho com revisão.
