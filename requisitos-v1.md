# Lupa — Requisitos da primeira versão

20 de outubro de 2026 · Victor Hugo

Este documento consolida as decisões tomadas na discussão de projeto. Ele substitui, para a primeira versão, as partes do `arquitetura.md` que foram tratadas como sugestão. O `catalogo-validacoes.md` e o `prompt-injection.md` continuam como referência.

## 1. Objetivo

Ferramenta web privada que auxilia um desembargador e seus assessores a conferir processos judiciais em 2º grau. O sistema recebe os autos, organiza as peças, monta a linha do tempo, roda validações objetivas e responde perguntas de localização sobre o processo. Toda informação exibida aponta para a página de origem.

A ferramenta é apenas de apoio. Ela não decide, não opina, não valora prova, não tipifica fatos e não redige atos. A conclusão jurídica é sempre do assessor ou do magistrado.

## 2. Contexto e enquadramento

- Produto 100% do fornecedor (Victor). O tribunal não tem acesso ao sistema e não participa do piloto.
- O desembargador atua hoje em câmara criminal e pode migrar para cível nas próximas semanas. O núcleo do sistema é genérico; as validações são módulos por matéria.
- Os autos vêm exportados do Projudi/PJD do TJGO, em PDF ou ZIP. O formato real será examinado com um processo público antes do desenho final da pipeline.
- Enquadramento normativo: art. 19 da Resolução CNJ 615/2025 (uso de IA generativa privada por magistrado e servidor). O produto deve se manter nas finalidades de baixo risco do Anexo (BR1, BR4, BR5, BR8) e fora das de alto risco (AR1 a AR5).
- O fornecedor é controlador dos dados pessoais contidos nos autos perante a LGPD.

## 3. Usuários e acesso

| Papel | Vê | Faz |
| --- | --- | --- |
| Assessor | Processos do próprio gabinete | Sobe processo, usa dossiê, validações e chat, anota |
| Desembargador | Tudo do assessor mais a auditoria do gabinete | Adiciona, desativa e reativa assessores; reseta senha e MFA deles |
| Administrador (Victor) | Mesma visão do desembargador, em todos os gabinetes | Cria desembargadores; gerencia sistema, chaves e versões |

Regras:

- Acesso somente pela web, com autenticação obrigatória.
- Login por usuário e senha. Não há e-mail no cadastro nem no fluxo de login.
- MFA obrigatório por aplicativo autenticador (TOTP).
- Recuperação de senha e de MFA é manual: o desembargador (para assessores) ou o administrador gera credencial temporária com troca obrigatória no primeiro acesso. Toda reset fica registrada.
- Desativar usuário não apaga seu histórico de auditoria.
- Autorização verificada no servidor em toda requisição, pelo par (gabinete, processo). A interface nunca é a barreira.
- Todo acesso do administrador a conteúdo de autos aparece em destaque na auditoria do gabinete.

## 4. Funcionalidades da primeira versão

### 4.1 Ingestão

- Upload de PDF ou ZIP de um processo pela interface.
- Cada arquivo recebe hash SHA-256 no recebimento. O original nunca é alterado.
- Separação em páginas, extração de texto nativo com coordenadas, OCR só nas páginas digitalizadas.
- Separação em peças e classificação por tipo (denúncia, sentença, recurso, certidão etc.), primeiro por regras, com confiança registrada.
- Extração de eventos datados (fato, denúncia, recebimento, sentença, publicação, intimação, interposição, decisões sobre prisão) com página e trecho de origem.
- Resultado gravado em formato estruturado por processo. Cada fato carrega evidência: página, trecho literal, hash do trecho.
- Fato sem evidência é descartado.

### 4.2 Dossiê navegável

- Índice das peças com tipo, intervalo de páginas e confiança da classificação.
- Linha do tempo processual, cada evento ligado à página de origem.
- Ficha do processo: número, classe, partes (pseudonimizadas na camada analítica), situação prisional.
- Visualizador de PDF que abre na página citada e destaca o trecho.
- O assessor pode reclassificar peça ou corrigir fato; a correção gera novo registro ligado ao original, sem sobrescrever.

### 4.3 Validações

Três validações no piloto, todas determinísticas:

1. Tempestividade do recurso.
2. Prescrição da pretensão punitiva pela pena em abstrato.
3. Revisão da prisão preventiva a cada 90 dias.

Regras de saída:

- O alerta pode ser conclusivo (ex.: "intempestivo"), mas sempre acompanhado de todos os valores usados: datas, prazo aplicado, feriados e suspensões considerados, marcos interruptivos, e a página de cada dado.
- O texto do alerta vem de template, não do modelo de linguagem.
- Fato faltante produz "verificar: fato não localizado", indicando onde o sistema procurou.
- Feriados, suspensões de prazo e tabelas de prescrição ficam em dados versionados, não em código.
- Cada validação declara os fatos de que depende e tem testes com processos sintéticos.

### 4.4 Chat sobre os autos

- Agente construído com o Claude Agent SDK, com ferramentas somente de leitura.
- Escopo permitido: localizar, extrair, resumir e relacionar informações dos autos, sempre com citação de página.
- Escopo vedado: valorar prova, tipificar fatos, concluir sobre aplicação de norma ou precedente, opinar sobre resultado. O agente recusa e explica o limite. A recusa é testada na suíte de regressão.
- Toda citação devolvida é conferida por código contra o texto real da página antes de aparecer na tela. Citação que não confere é descartada e registrada.
- Respostas aparecem em bloco rotulado como gerado por IA.

## 5. Arquitetura

Três camadas:

1. **Pipeline determinística.** Recebe o arquivo, lacra com hash, separa páginas, extrai texto ou faz OCR, separa e classifica peças, extrai eventos, grava o resultado estruturado. Sem modelo de linguagem nesta camada. Parsers de PDF e OCR rodam em processo isolado, sem rede e sem acesso ao banco.
2. **Agente com ferramentas.** O agente consulta o resultado estruturado. Ferramentas: listar peças, ler página estruturada, buscar texto, executar cálculo de prazo e prescrição (funções Python determinísticas). Como válvula de escape, uma ferramenta "ler página N do PDF original", somente leitura e com limite de páginas por consulta, para quando a pipeline falhou. Sem ferramentas de escrita, rede ou execução de código.
3. **Interface web.** Login, upload, dossiê, visualizador, chat, auditoria.

Decisões:

- Escopo do agente travado em um único processo por conversa. O montador de contexto só lê dados do par (gabinete, processo) da sessão, verificado em código.
- Prompts versionados; hash do template registrado por chamada.
- Modelo e versão registrados por chamada; troca de modelo exige rodar a suíte de regressão.
- Texto dos autos entra no contexto como dado delimitado e rotulado por origem (juízo, MP, defesa, terceiro), nunca como instrução. Controles de ingestão do `prompt-injection.md` (texto oculto, metadados, normalização Unicode, padrões suspeitos) são aplicados e as flags seguem até a tela.

## 6. Dados, armazenamento e criptografia

- Piloto na infraestrutura própria do fornecedor, com MinIO local como object storage (compatível com S3, para migração futura à AWS trocando endpoint e gerenciador de chaves).
- Fase 1: TLS 1.3 em todo tráfego entre navegador e servidor e entre serviços.
- Fase 2 (logo após): criptografia em repouso com chave por processo derivada de chave mestra por gabinete, usando a criptografia nativa do MinIO com chaves em Vault próprio. Texto extraído e índices também cifrados, não só o PDF. O arquivo é cifrado antes de qualquer parser abrir; um worker isolado decifra uma cópia só para processar. Exclusão do processo é feita pela destruição da chave.
- Objetivo declarado: impedir vazamento do servidor ou do storage. Criptografia de ponta a ponta está fora de escopo.
- Primeira versão aceita apenas processos públicos. Processo ou peça em segredo de justiça é identificado na ingestão e bloqueado.
- Nomes e identificadores pessoais são pseudonimizados na camada analítica, nos logs e nos prompts; a tabela de resolução fica separada e cifrada.
- O que vai ao modelo de linguagem sai em claro do worker dentro da conexão TLS. A proteção ali é pseudonimização e o contrato do fornecedor do modelo, que deve vedar uso dos dados para treinamento (art. 19, §3º, III da Res. 615/2025). Conferir nos termos da API antes do piloto.
- Nenhum dado de autos é usado para treinar ou ajustar modelos.

## 7. Auditoria

Objetivo: consulta fácil e rápida, como tela do produto, não como log de servidor.

Registrar, por evento: quem, quando, IP, localização aproximada derivada do IP, gabinete, processo, ação, objeto (página, fato, achado, pergunta), resultado, versão do modelo e do prompt quando houver chamada ao agente.

Eventos cobertos: login e falha de login, reset de senha ou MFA, criação e desativação de usuário, upload, abertura de processo, página visualizada, busca, pergunta ao chat, anotação, correção de fato, execução de validação, chamada ao modelo, acesso do administrador a conteúdo.

Regras:

- Armazenamento append-only com encadeamento de hash entre eventos.
- Logs nunca guardam conteúdo dos autos nem texto de perguntas e respostas; guardam identificadores e hashes.
- Retenção dos logs maior que a dos dados do processo.
- Relatório de uso por processo e por usuário exportável, para o magistrado cumprir o dever de informar ao tribunal (art. 19, §7º).

## 8. Documentação para os usuários

Guia em linguagem simples para assessores e desembargador cobrindo: o que a ferramenta faz e não faz; como ler um alerta e refazer a conta; como conferir uma citação na página; limites do chat; o que fica registrado em auditoria; como pedir correção de peça ou fato. Atualizado a cada versão.

## 9. Padrões de engenharia

- Python, PEP 8, clean code, docstrings no estilo Google.
- Tudo em contêineres; piloto com Docker Compose.
- Esquemas de entrada e saída validados (pydantic). Campo fora do esquema é rejeitado.
- Suíte de regressão obrigatória antes de qualquer deploy: processos sintéticos com gabarito, corpus de injeção por vetor, casos de recusa do chat. Metas: zero fato sem evidência, zero achado suprimido ou criado sob injeção, datas com precisão igual ou superior a 99%.
- Segredos em cofre, nunca em código ou variável de ambiente.

## 10. Fora de escopo da primeira versão

- Validações semânticas (teses enfrentadas, bis in idem, fundamentação da preventiva).
- Catálogo cível.
- Processos em segredo de justiça.
- Integração direta com Projudi ou DataJud.
- Sugestão de jurisprudência.
- Exportação de relatório para fora do sistema.
- Múltiplos gabinetes (a estrutura de dados prevê, a operação não).

## 11. TODO

- [ ] Anonimização na origem para permitir processos em segredo de justiça com LLM externo (art. 19, §3º, IV da Res. 615/2025).
- [ ] Criptografia em repouso (fase 2 da seção 6).
- [ ] Módulo de validações cíveis, começando por tempestividade em dias úteis.
- [ ] Política de retenção e descarte por processo, com gatilho definido pelo gabinete.
- [ ] Conferir termos de uso e retenção de dados da API do modelo.
- [ ] Revisar o acesso do administrador a conteúdo quando houver mais de um gabinete.

## 12. Próximos passos

1. Obter um processo público exportado do Projudi e examinar o formato: um PDF ou vários, índice de movimentações, proporção de páginas digitalizadas.
2. Desenhar a pipeline de ingestão a partir desse formato.
3. Definir os esquemas de dados: processo, arquivo, peça, página, evidência, fato, achado, usuário, evento de auditoria.
4. Construir a pipeline e as três validações com processos sintéticos.
5. Construir autenticação, papéis e auditoria.
6. Construir o agente e o chat com a suíte de recusa e injeção.
7. Interface web e visualizador.
8. Piloto com o processo real e conferência pelos assessores.
