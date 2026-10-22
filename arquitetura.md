# Arquitetura — Validação Processual Criminal (Gabinete)

Oct 16, 2026 · @Victor Hugo

## Visão geral

O sistema recebe os autos de um processo criminal em 2º grau (até \~10 mil páginas), extrai os fatos processuais relevantes com a página de origem de cada um, e devolve ao gabinete um relatório de validações (admissibilidade, prescrição, prisão, dosimetria, enfrentamento de teses). Ele não decide, não minuta e não sugere resultado; ele aponta onde olhar.

**O que o sistema faz**

- Ingere PDFs/ZIPs exportados do PJe, eproc ou SAJ e separa os autos em peças classificadas
- Extrai eventos datados (fato, denúncia, recebimento, sentença, publicação, intimação, interposição) com página e trecho de origem
- Executa um catálogo de validações sobre esses dados e marca cada item como conforme, atenção ou verificar manualmente
- Entrega um relatório navegável onde cada achado leva à página exata do PDF

**O que o sistema não faz**

- Não emite juízo de mérito, não redige voto ou minuta, não propõe resultado
- Não aprende com os dados dos processos (nenhum dado de autos é usado para treinar ou ajustar modelos)
- Não envia autos para fora do perímetro controlado pelo tribunal sem contrato e base legal expressos
- Não substitui a conferência humana: todo achado é uma hipótese a confirmar por assessor

**Princípios de desenho**

1. Rastreabilidade total: nenhum achado existe sem página, trecho e hash do documento de origem.
2. Determinismo onde importa: prazos, prescrição e aritmética de pena são código, não modelo de linguagem.
3. Minimização: o modelo de linguagem recebe apenas os trechos necessários para a tarefa, nunca os autos inteiros.
4. Dado criminal é dado sensível por padrão: segredo de justiça, vítimas, menores e dados de saúde tratados no nível mais restritivo, sem exceção por processo.
5. Auditoria como produto: toda leitura, extração e inferência fica registrada de forma imutável e consultável pelo gabinete.
6. Nada sai do tribunal sem decisão explícita: a arquitetura funciona 100% on-premise; nuvem é opção, não premissa.

## Modelo de ameaças e requisitos de segurança/LGPD

O ativo protegido são autos criminais: dados pessoais de réus, vítimas, testemunhas e menores, frequentemente sob segredo de justiça. Pela LGPD (art. 5º, II e art. 11), dados sobre vida sexual, saúde, origem racial, religião e dados de crianças exigem tratamento reforçado; dados de processos penais são tratados no mesmo patamar por analogia e por recomendação do CNJ (Resolução 332/2020 sobre IA no Judiciário).

| Ameaça | Vetor | Impacto | Controle principal |
| --- | --- | --- | --- |
| Vazamento de autos sigilosos | API externa, logs, backups, exportação | Violação de segredo de justiça; responsabilização do tribunal | Perímetro on-premise; criptografia em repouso e trânsito; logs sem conteúdo; exportação auditada |
| Acesso indevido por usuário interno | Credencial compartilhada, privilégio excessivo | Consulta a processo fora da alçada do gabinete | SSO do tribunal, RBAC por gabinete e processo, trilha de auditoria imutável |
| Uso de dados para treino de modelo | Fornecedor de LLM retém prompts | Perda de controle sobre dados sensíveis | Modelo local ou contrato zero-retention assinado; nunca fine-tuning com autos |
| Alucinação apresentada como fato | Saída do LLM sem âncora | Assessor confia em data ou tese inexistente | Toda saída obrigatoriamente ancorada em página/trecho; validação cruzada determinística |
| Injeção de prompt via conteúdo dos autos | Texto malicioso dentro de uma peça | Modelo executa instrução oculta, extrai dados errados | Conteúdo dos autos tratado como dado, nunca como instrução; prompts com delimitação estrita; sem ferramentas de ação para o modelo |
| Supply chain (OCR, libs, imagens) | Dependência comprometida | Execução de código no servidor com os autos | SBOM, imagens assinadas, registry interno, scanner de vulnerabilidades no CI |
| Retenção além do necessário | Dados ficam após o julgamento | Violação do princípio da necessidade (art. 6º, III) | Política de retenção por fase processual; descarte com comprovação |
| Exfiltração por saída do próprio sistema | Relatório exportado em PDF/e-mail | Cópia fora do controle | Relatório só dentro do sistema; exportação com marca d'água, registro e aprovação |

**Requisitos não negociáveis**

- Base legal: tratamento para o exercício regular de direitos em processo judicial e cumprimento de obrigação legal pelo Poder Judiciário (art. 7º, II e VI; art. 11, II, "a" e "d" para dados sensíveis).
- Controlador é o tribunal; o fornecedor do sistema é operador e só age sob instrução documentada (art. 39).
- Relatório de Impacto à Proteção de Dados (RIPD, art. 38) elaborado antes do piloto, não depois.
- Encarregado (DPO) do tribunal envolvido desde o desenho.
- Criptografia: AES-256 em repouso com chaves em HSM ou KMS do tribunal; TLS 1.3 em todo tráfego interno; chave por tenant (gabinete).
- Segregação: ambiente de produção isolado de desenvolvimento; dados reais nunca em dev/homologação (usar autos sintéticos ou anonimizados).
- Logs: registram quem, quando, qual processo e qual ação; nunca registram conteúdo dos autos.
- Incidente: plano de resposta com comunicação à ANPD e ao titular em prazo compatível com o art. 48.

## Topologia de implantação

A implantação de referência é on-premise, dentro do datacenter do tribunal, sem saída para a internet a partir das zonas que tocam os autos. Nuvem só entra como alternativa negociada (nuvem governamental ou VPC dedicada no Brasil, com contrato de operador e chaves controladas pelo tribunal).

&#91;embedded content: topologia · 5 zonas dentro do perímetro do tribunal\]

A equipe entra só pela zona de apresentação via SSO; os autos descem da apresentação até os dados sem nunca sair do perímetro, e a zona de inferência não tem rota externa.

| Zona | O que roda | Regra de rede |
| --- | --- | --- |
| Apresentação | Web app, API gateway, WAF | Única zona alcançável pela rede do tribunal; só via SSO; TLS 1.3 |
| Aplicação | API de validações, orquestrador de jobs, fila | Fala com apresentação, processamento e dados; nunca com a internet |
| Processamento | Workers de OCR, split e extração em sandbox (gVisor/bubblewrap, sem rede) | Recebe páginas da fila, grava resultado em dados; sem acesso de saída |
| Inferência | Servidor de LLM local (GPU) | Só aceita chamadas da zona de aplicação; nenhuma rota externa; sem disco persistente de prompts |
| Dados | PostgreSQL cifrado, object storage dos autos, KMS/HSM, logs de auditoria append-only | Acesso só das zonas aplicação e processamento; backup cifrado com chave própria |

**Decisões de isolamento**

- Um tenant por gabinete, com chave de criptografia própria no KMS; perda ou revogação da chave inutiliza os dados daquele gabinete sem afetar os demais.
- Os workers de processamento rodam sem rede e sem acesso ao banco principal: recebem páginas por fila, devolvem JSON. Um PDF malicioso não alcança nada além do sandbox.
- A zona de inferência não tem rota para fora e não persiste prompts; se um dia houver LLM externo, ele entra atrás de um gateway de saída com DLP, zero-retention contratual e aprovação do DPO.
- Ambientes de desenvolvimento e homologação ficam fora do perímetro e só recebem autos sintéticos ou anonimizados.

**Alternativa em nuvem (se o tribunal aceitar)**

- Região Brasil obrigatória; VPC sem IP público; chaves gerenciadas pelo tribunal (BYOK/HYOK); contrato de operador com cláusulas da LGPD; auditoria SOC 2 ou ISO 27001 do provedor; inferência em instância dedicada, nunca em API compartilhada que retenha dados.

## Pipeline de ingestão

Um processo de 10 mil páginas nunca é lido de uma vez: ele é quebrado em peças, cada peça em páginas, cada página em texto com coordenadas, e só então o sistema monta um modelo de dados do processo. O LLM entra tarde e com pouco texto por chamada.

1. **Recepção e lacre.** O assessor faz upload do PDF/ZIP exportado do PJe/eproc (ou o sistema puxa via integração MNI/API quando o TJ permitir). O arquivo recebe hash SHA-256, é cifrado com a chave do gabinete e gravado no object storage. O hash entra na trilha de auditoria: qualquer achado posterior aponta para este hash.
2. **Split por documento.** O índice de movimentos do PJe/eproc (quando presente) e os marcadores de página definem os limites de cada peça. Sem índice, um classificador de quebra de documento (cabeçalhos, numeração, assinatura digital) faz o corte. Saída: lista de peças com intervalo de páginas.
3. **Triagem de páginas.** Cada página é marcada como texto nativo, imagem digitalizada ou em branco/capa. Só as digitalizadas vão para OCR (Tesseract por-BR ou modelo de layout); as nativas extraem texto com coordenadas via pdfplumber/PyMuPDF. Em um processo típico, 30–60% das páginas são certidões repetidas, capas e juntadas sem conteúdo útil; elas são indexadas mas não processadas adiante.
4. **Classificação de peças.** Cada peça recebe um tipo: denúncia, recebimento, decisão sobre prisão, laudo, termo de depoimento, sentença, certidão de intimação/publicação, recurso, contrarrazões, acórdão. Primeiro por regras (padrões textuais estáveis), depois por LLM só nas peças ambíguas, com confiança registrada.
5. **Extração estruturada.** Para cada tipo de peça, um esquema fixo define o que extrair: datas, partes, crimes imputados (artigo, inciso, qualificadoras), pena aplicada em cada fase, regime, decisão de prisão, teses do recurso. O LLM recebe só o trecho relevante da peça e deve devolver JSON onde cada campo traz página, posição e citação literal de origem. Campo sem citação é descartado.
6. **Validação cruzada.** Datas extraídas são conferidas contra o texto por regex independente; uma data que o LLM retornou mas que não existe literalmente na página indicada é rejeitada. Conflitos entre peças (duas datas de sentença) ficam marcados para o assessor.
7. **Montagem do modelo do processo.** Os campos validados compõem a linha do tempo processual e a ficha de cada réu. Esse modelo, não o PDF, é o que o motor de validações consome.
8. **Execução das validações e relatório.** O motor roda o catálogo sobre o modelo e grava cada achado com evidências. O relatório é gerado sob demanda, sempre a partir dos achados persistidos, nunca de uma nova inferência.

**Escala e custo**

- Cada etapa é um job idempotente na fila; 10 mil páginas se dividem em lotes de \~50 páginas processados em paralelo pelos workers. Reprocessar uma peça não reprocessa o processo.
- Resultado intermediário (texto por página, classificação) é cacheado pelo hash do arquivo: o mesmo processo subindo duas vezes não custa duas vezes.
- Tempo alvo para 10 mil páginas: ingestão completa em minutos com 4–8 workers de OCR; o gargalo é OCR de páginas digitalizadas, não o LLM.
- Todo job registra início, fim, versão do código e do modelo, e página de entrada/saída. Isso permite reproduzir qualquer achado meses depois.

## Modelo de dados e evidências

A regra central: nenhum fato existe no sistema sem uma evidência apontando para documento, página e trecho. O modelo separa o que foi lido (evidência), o que foi inferido (fato) e o que foi concluído (achado).

| Entidade | Campos principais | Observação |
| --- | --- | --- |
| Processo | número CNJ, classe, órgão, tenant (gabinete), status, data de ingestão | Chave de criptografia herdada do tenant |
| Arquivo | hash SHA-256, tamanho, origem (upload/integração), quem subiu, quando | Imutável; novo upload = novo arquivo |
| Peça | arquivo, tipo, página inicial/final, confiança da classificação, método (regra/LLM) | Reclassificável pelo assessor com registro |
| Página | peça, número, tipo (nativa/OCR/vazia), texto, mapa de coordenadas | Texto cifrado em repouso; busca via índice separado |
| Evidência | página, bounding box, citação literal, hash do trecho | Única fonte permitida para qualquer fato |
| Fato | tipo (data\_sentença, pena\_base, regime, tese\_recurso...), valor, evidências, extraído\_por (regra/LLM + versão), confiança, status (automático/confirmado/corrigido) | Um fato sem evidência é rejeitado na gravação |
| Réu | processo, identificador interno, fatos associados | Dados pessoais pseudonimizados: nome real fica em tabela separada, cifrada, acessada só na UI |
| Achado | validação, resultado (conforme/atenção/verificar), fatos usados, explicação, versão do catálogo | Gerado só por código; nunca editado, só anotado |
| Anotação | achado, assessor, texto, data | Registro humano sobre o achado; não altera o achado |

**Rastreabilidade por página**

- A UI abre o PDF na página e destaca o bounding box da evidência. O assessor confere em segundos.
- Fatos corrigidos manualmente geram um novo fato com status `corrigido`, ligado ao original; o histórico nunca é sobrescrito.
- Reexecutar uma validação com catálogo novo gera novo achado versionado; o anterior permanece para auditoria.

**Pseudonimização**

- Nomes, CPFs e dados de vítimas e menores são substituídos por identificadores internos em todas as tabelas analíticas, logs e prompts. A tabela de resolução fica cifrada com chave própria e só a camada de apresentação a consulta.
- Prompts enviados ao LLM já saem pseudonimizados; o modelo nunca vê o nome real de uma vítima.

**Busca**

- Índice de texto completo (PostgreSQL FTS) e vetorial (pgvector) por página, dentro do mesmo banco cifrado, com filtro obrigatório por tenant e processo na consulta. Um assessor só encontra páginas de processos que seu gabinete pode ver.

## Motor de validações

Cada validação é uma função pura: recebe o modelo do processo, devolve um achado com resultado, fatos usados e explicação. O catálogo é versionado em código, revisado pelo gabinete e testado contra processos de referência antes de entrar em produção.

**Três classes de validação**

| Classe | Como decide | Exemplos | Confiabilidade |
| --- | --- | --- | --- |
| Determinística | Aritmética e regras sobre fatos datados | Tempestividade, prescrição, prazo de preventiva, regime compatível com a pena, detração | Alta: resultado reproduzível, auditável linha a linha |
| Estrutural | Presença/ausência de elementos em peças | Sentença tem as 3 fases da dosimetria? Há certidão de intimação? Recurso tem razões? | Alta a média: depende da classificação correta das peças |
| Semântica | LLM compara trechos | Cada tese do recurso foi enfrentada na sentença? A fundamentação da preventiva cita fatos concretos? | Média: sempre marcada como "verificar", nunca como "conforme" |

Validações semânticas só podem produzir atenção ou verificar. O sistema nunca declara que uma tese foi enfrentada; ele diz onde parece ter sido e onde não encontrou.

**Catálogo inicial (a confirmar com o gabinete)**

| Validação | Classe | Fatos necessários |
| --- | --- | --- |
| Tempestividade do recurso | Determinística | data de publicação/intimação, data de interposição, tipo de recurso, feriados do TJ |
| Prescrição da pretensão punitiva (abstrata e retroativa) | Determinística | data do fato, recebimento da denúncia, publicação da sentença, pena máxima/aplicada, idade do réu, causas interruptivas e suspensivas |
| Prazo da prisão preventiva e revisão de 90 dias | Determinística | data da decretação, datas das revisões, data atual |
| Regime inicial compatível com a pena e reincidência | Determinística | pena definitiva, reincidência, regime fixado |
| Detração computada | Estrutural + determinística | períodos de prisão provisória, menção à detração na sentença |
| Dosimetria em três fases presente | Estrutural | sentença classificada, marcadores de cada fase |
| Bis in idem na dosimetria | Semântica | circunstâncias usadas em cada fase |
| Teses do recurso enfrentadas na sentença | Semântica | lista de teses do recurso, seções da sentença |
| Pedido do recurso dentro do efeito devolutivo | Semântica | pedidos do recurso, dispositivo da sentença |
| Certidão de intimação da defesa e do MP presente | Estrutural | peças classificadas como certidão |
| Reconhecimento de pessoa conforme art. 226 CPP | Estrutural + semântica | termos de reconhecimento, descrição do procedimento |
| Cadeia de custódia de prova digital documentada | Estrutural | laudos, autos de apreensão, termos de extração |

**Regras do motor**

- Toda validação declara os fatos de que depende; se um fato falta, o resultado é "verificar: fato não localizado", com link para onde o sistema procurou.
- O catálogo tem testes com processos sintéticos cobrindo cada regra; uma mudança de regra sem teste não entra.
- Feriados, suspensões de prazo e tabelas de prescrição ficam em dados versionados, não em código.
- O resultado de cada validação é explicado em linguagem natural a partir de template, não de LLM: "Sentença publicada em 12/03/2026 (p. 4.212), apelação interposta em 20/03/2026 (p. 4.301), prazo de 5 dias vence 19/03/2026: intempestiva, verificar."

## Uso de LLM

O modelo de linguagem é um extrator e um comparador de trechos, nunca o decisor. Ele aparece em três pontos: classificar peças ambíguas, extrair campos estruturados com citação, e comparar teses com fundamentação. Tudo o mais é código.

**Onde o modelo roda**

- Padrão: modelo open-weight hospedado na zona de inferência (ex.: Qwen, Llama ou Gemma em vLLM, 1–2 GPUs de 24–80 GB conforme o modelo). Dados nunca saem do perímetro.
- Opcional, só com aprovação formal: API externa com contrato de zero-retention, região Brasil, sem uso para treino, atrás de gateway de saída com DLP e pseudonimização obrigatória. Deve constar no RIPD e no contrato de operador.
- A escolha do modelo é registrada por versão; trocar de modelo exige rodar a suíte de regressão nos processos de referência.

**Guardrails por chamada**

1. Entrada mínima: só o trecho da peça necessário (poucas páginas), já pseudonimizado; nunca o processo inteiro.
2. Conteúdo dos autos é dado, não instrução: o prompt delimita o texto do processo e instrui o modelo a ignorar qualquer comando dentro dele. Testes de injeção fazem parte da regressão.
3. Saída obrigatoriamente em JSON validado por esquema (pydantic); campo fora do esquema é rejeitado.
4. Toda data, número ou citação devolvida é conferida contra o texto da página indicada; se não existir literalmente, o campo é descartado e o evento é logado.
5. O modelo não tem ferramentas: não navega, não executa código, não grava. Ele só responde.
6. Temperatura zero e prompts versionados em repositório; a mesma entrada produz a mesma saída dentro da versão.
7. Cada chamada registra: versão do prompt, versão do modelo, hash da entrada, hash da saída, latência. Nunca o conteúdo.

**Fontes externas de direito (jurisprudência, legislação)**

- O sistema não consulta a internet em tempo de execução. Legislação e tabelas (prescrição, feriados, súmulas relevantes) entram como dados versionados, revisados pelo gabinete.
- Se o gabinete quiser sugestão de jurisprudência, isso é módulo separado, com base própria carregada offline a partir de fontes oficiais (STF, STJ, TJ) e com link para o acórdão original em toda citação. Jurisprudência sem link não é exibida.

**Avaliação contínua**

- Conjunto de processos de referência anotados pelo gabinete (gabarito humano) para medir precisão e recall de cada extração e validação.
- Metas de aceite do piloto: extração de datas processuais com precisão ≥ 99% (erro aqui invalida prescrição e prazo); classificação de peças ≥ 95%; zero fatos sem evidência.
- Correções feitas pelos assessores alimentam o gabarito, não o modelo.

## Identidade, acesso e auditoria

Ninguém entra sem a identidade do tribunal, ninguém vê processo fora do seu gabinete, e tudo que alguém vê ou faz fica registrado de forma que não pode ser apagada.

**Identidade**

- Autenticação exclusiva via SSO do tribunal (SAML/OIDC com o AD ou Keycloak institucional); sem contas locais, sem senha própria do sistema.
- MFA obrigatório, herdado da política do tribunal.
- Sessões curtas (ex.: 8 h) com reautenticação para ações sensíveis: exportar relatório, confirmar/corrigir fato, dar acesso a outro usuário.

| Papel | Pode | Não pode |
| --- | --- | --- |
| Assessor | Subir processo, ver relatório e evidências, anotar e corrigir fatos, do próprio gabinete | Exportar sem aprovação; ver outros gabinetes |
| Desembargador / chefe de gabinete | Tudo do assessor + aprovar exportação, convidar usuário ao gabinete | Administrar sistema |
| Administrador do tribunal (TI) | Gerir tenants, chaves, versões, ver logs técnicos | Ver conteúdo de autos ou achados |
| Auditor / DPO | Consultar trilha de auditoria de qualquer tenant | Alterar qualquer coisa |
| Fornecedor (operador) | Suporte sob chamado, com acesso temporário aprovado e logado | Acesso permanente; acesso a conteúdo sem autorização escrita |

Autorização é verificada no servidor em toda requisição, pelo par (tenant, processo); o front-end nunca é a barreira.

**Trilha de auditoria**

- Evento por ação: login, abertura de processo, visualização de página, busca, anotação, correção, exportação, mudança de permissão, job executado, chamada a LLM.
- Cada evento guarda: quem, quando, de onde (IP interno), tenant, processo, ação, objeto (id de página/fato/achado), resultado. Nunca o conteúdo.
- Armazenamento append-only com encadeamento de hash (cada evento referencia o hash do anterior) e cópia diária assinada enviada para repositório sob controle do auditor. Alterar o passado quebra a cadeia e é detectável.
- Retenção dos logs de auditoria mais longa que a dos dados (ex.: 5 anos), pois eles provam o que foi feito mesmo depois do descarte dos autos.
- Relatórios de uso por gabinete disponíveis ao DPO sem intervenção do fornecedor.

**Segurança da aplicação**

- Segredos em cofre (Vault), nunca em variável de ambiente ou código; rotação automática.
- Imagens de contêiner assinadas, registry interno, SBOM gerado no CI, scanner de CVE bloqueando deploy.
- Dependências de OCR e parsing de PDF rodam em sandbox sem rede e sem acesso ao banco, pois são a superfície de ataque mais histórica (PDFs maliciosos).
- Teste de intrusão externo antes do piloto e a cada versão maior; relatório entregue ao tribunal.

## Ciclo de vida dos dados

Os autos entram para uma tarefa específica (apoiar a análise de um recurso) e saem quando ela termina. O sistema não é repositório de processos; o repositório é o PJe.

| Dado | Retenção padrão | Gatilho de descarte | Como descarta |
| --- | --- | --- | --- |
| PDF original dos autos | Até o julgamento + 30 dias | Baixa do processo no gabinete ou pedido do assessor | Exclusão criptográfica (destruição da chave) + remoção física do objeto |
| Texto por página e índices | Igual ao PDF | Mesmo gatilho | Exclusão das linhas e reindexação; vetores removidos |
| Fatos e achados | Até o julgamento + 30 dias | Mesmo gatilho | Exclusão; sobrevive só o resumo estatístico anonimizado (quantas validações, quais resultados) |
| Tabela de resolução de pseudônimos | Igual ao PDF | Mesmo gatilho | Exclusão criptográfica com chave própria |
| Logs de auditoria | 5 anos | Prazo | Expurgo em lote com registro assinado |
| Backups | 30 dias rotativos | Prazo | Backup cifrado com chave do período; chave destruída na expiração |
| Gabarito de avaliação | Enquanto o contrato durar | Fim do contrato | Só com autos sintéticos ou anonimizados; nunca autos reais |

A retenção padrão é configurável por tribunal; o gabinete pode encurtar, nunca estender além do fim da finalidade sem nova base legal.

**Direitos dos titulares (arts. 18–22 da LGPD)**

- Réus, vítimas e testemunhas não interagem com o sistema; os pedidos chegam ao tribunal (controlador) e o fornecedor atende sob instrução.
- O sistema entrega, por processo, um relatório de que dados pessoais foram tratados e quais achados os usaram, para o tribunal responder ao titular.
- Pedido de eliminação por titular não se aplica enquanto o tratamento for necessário ao exercício de direitos em processo judicial (art. 16, I e III), mas o sistema registra o pedido e descarta assim que a finalidade cessar.

**Minimização em cada etapa**

- O relatório final não reproduz dados sensíveis desnecessários; cita página e trecho mínimo.
- Exportação (quando aprovada) gera PDF com marca d'água nominal e registro; o conteúdo exportado nunca inclui páginas inteiras dos autos.
- Dados de menores e de vítimas de crimes sexuais ficam com flag de sigilo reforçado: não aparecem em busca, só na evidência do achado que os exige.

## Governança LGPD e institucional

O tribunal é o controlador, o fornecedor é o operador, e nada entra em produção antes do RIPD e do contrato. Além da LGPD, o projeto precisa atender a Resolução CNJ 332/2020 (ética e transparência no uso de IA no Judiciário) e a Resolução CNJ 615/2025, que atualizou essas regras.

| Papel | Quem | Responsabilidade |
| --- | --- | --- |
| Controlador | Tribunal de Justiça | Define finalidade, aprova RIPD, responde aos titulares e à ANPD |
| Encarregado (DPO) | DPO do tribunal | Revisa RIPD, aprova mudanças de tratamento, recebe relatórios de auditoria |
| Operador | Fornecedor do sistema | Trata só sob instrução escrita; mantém controles técnicos; notifica incidentes em até 24 h ao controlador |
| Responsável técnico | Victor (fornecedor) | Arquitetura, catálogo, versões, resposta a incidentes |
| Gestor do piloto | Chefe de gabinete | Define validações, valida gabarito, aceita ou rejeita entregas |

**Documentos antes do piloto**

- [ ] RIPD (art. 38) cobrindo fluxo de dados, riscos e medidas deste documento
- [ ] Contrato de operador com cláusulas: finalidade, sigilo, proibição de uso para treino, subcontratação vedada sem anuência, auditoria, descarte ao fim, responsabilidade por incidente
- [ ] Termo de confidencialidade individual de quem acessa o ambiente pelo fornecedor
- [ ] Política de retenção aprovada pelo DPO
- [ ] Plano de resposta a incidentes com fluxo para ANPD (art. 48) e para o CNJ
- [ ] Registro das operações de tratamento (art. 37)
- [ ] Parecer da TI do tribunal sobre a topologia e o uso de GPU interna

**Exigências do CNJ sobre IA judicial que a arquitetura atende**

- Supervisão humana: nenhum resultado é decisão; relatório explicita que é apoio e exige confirmação.
- Transparência e explicabilidade: cada achado mostra regra aplicada, fatos usados e evidência.
- Não discriminação: o sistema não usa dados demográficos do réu em nenhuma validação; isso é verificável no catálogo.
- Registro no Sinapses (plataforma do CNJ para modelos de IA) quando o tribunal decidir institucionalizar; cabe à área de TI do tribunal, mas o fornecedor entrega a documentação.
- Segurança e governança de dados conforme as seções anteriores.

**Caminho institucional**

- Piloto em um gabinete sob termo de cooperação ou contratação direta de baixo valor, com autos reais só após RIPD aprovado.
- Expansão para outros gabinetes do mesmo TJ exige procedimento de contratação pública (licitação ou inexigibilidade), e o produto precisa estar pronto para isso: documentação, auditoria, plano de transição e saída (exportação de dados e descarte comprovado ao fim).

## Stack sugerida e roadmap do piloto

A stack aproveita o que já existe no harness-juridico-br (extração DOCX/PDF, validador de evidências, motor de prazos, sandbox com bubblewrap) e troca o Claude Code por um serviço próprio com LLM local.

| Camada | Escolha | Por quê |
| --- | --- | --- |
| Linguagem/API | Python 3.12, FastAPI, pydantic | Esquemas de extração validados; ecossistema de PDF/OCR |
| Fila e jobs | Redis + RQ ou Celery (Airflow só se o TJ já tiver) | Jobs idempotentes por lote de páginas |
| PDF/OCR | PyMuPDF, pdfplumber, Tesseract por-BR; opcional modelo de layout (Docling) | Texto com coordenadas; OCR só onde precisa |
| Sandbox | gVisor ou bubblewrap, sem rede | Isola parsing de PDF |
| Banco | PostgreSQL 16 com pgcrypto, FTS e pgvector; RLS por tenant | Um banco, isolamento por linha, busca sem serviço extra |
| Storage | MinIO (S3 compatível) on-premise, SSE com KMS | Objetos cifrados, versionamento, object lock para logs |
| Chaves/segredos | HashiCorp Vault (Transit + KV) ou HSM do TJ | Chave por tenant, rotação, auditoria |
| LLM | vLLM servindo modelo open-weight; abstração para trocar de modelo | Sem saída de dados; benchmark antes de fixar modelo |
| Front | Next.js ou SvelteKit + visualizador PDF (pdf.js) com destaque de bounding box | Evidência clicável |
| Identidade | OIDC/SAML com Keycloak ou AD do TJ | SSO e MFA institucionais |
| Observabilidade | OpenTelemetry + Grafana/Loki; logs sem conteúdo | Métricas por job e por validação |
| Infra | Docker Compose para piloto; Kubernetes (k3s) se houver mais de um gabinete; Terraform/Ansible | Reprodutível no datacenter do TJ |

**Roadmap do piloto**

| Fase | Entrega | Critério de saída |
| --- | --- | --- |
| 0. Descoberta | Catálogo de validações acordado com o gabinete; 10 processos de referência escolhidos; parecer da TI sobre topologia | Gabinete assina o catálogo; TI aprova on-premise ou nuvem |
| 1. Fundação | Ingestão, split, OCR, classificação, modelo de dados, SSO, auditoria; tudo com autos sintéticos | Pipeline processa 10 mil páginas sintéticas ponta a ponta |
| 2. Validações determinísticas | Tempestividade, prescrição, preventiva, regime, detração | 100% de acerto nos processos de referência sintéticos |
| 3. Extração com LLM | Esquemas por tipo de peça, citação obrigatória, validação cruzada | Datas ≥ 99% de precisão no gabarito; zero fato sem evidência |
| 4. RIPD e contrato | RIPD aprovado pelo DPO; contrato de operador assinado; pentest | Autorização formal para autos reais |
| 5. Piloto com autos reais | 20–30 processos reais do gabinete; assessores conferem cada achado | Taxa de achados confirmados e tempo economizado medidos; relatório ao gabinete |
| 6. Validações semânticas | Teses enfrentadas, bis in idem, fundamentação da preventiva | Gabinete valida utilidade; sempre marcadas como verificar |

**Perguntas abertas para o gabinete**

- O TJ permite GPU no datacenter ou prefere nuvem governamental?
- Os autos chegam por exportação manual do PJe ou existe integração (MNI) liberada?
- Quais validações o gabinete faz hoje de cabeça que mais consomem tempo?
- Quem no tribunal assina como controlador e quem é o DPO?
- Existe iniciativa de IA no TJ (ou no CNJ) com a qual o projeto precise se alinhar ou registrar?
