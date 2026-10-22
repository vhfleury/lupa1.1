# Relatório de conformidade geral — Etapas 0 a 7 e 8.1 a 8.2

21 de outubro de 2026 · revisor (atualizado após 8.1 e 8.2: fim do que é construível por agentes)

## 0.000 Atualização final: 8.1 (ambiente de piloto) e 8.2 (conformidade)

| Verificação | Resultado |
| --- | --- |
| Backend | 867 testes; cobertura 98,3% (ver revisão 8.1, §1.1) |
| E2E | 36 de 36 |
| Cofre selado | detectado pelo healthcheck do Vault e por `/saude` (503), provado pelo revisor |
| Perfil de produção | compose válido; só o proxy publica portas; backup e expurgo agendados; monitoramento em loopback com 4 alertas |
| Certificado | três modos validados; ACME e fornecido só TLS 1.3 com HSTS |
| Conformidade | seis minutas para revisão de advogado, com fundamentos confirmados na fonte e itens abertos listados |
| Checklist de segurança no dev (`conferir_piloto.py`) | 10 atendidos, 5 pendentes por serem de produção, 2 manuais (objetos órfãos, termos do fornecedor do modelo) |

**Estado do projeto:** a primeira versão está implementada, testada e documentada nas Etapas 0 a 7, com ambiente de piloto preparado (8.1) e conformidade minutada (8.2). As subetapas 8.3 a 8.10 são execução humana com o gabinete: usuários reais, processo do Projudi, gabarito, uso acompanhado, revisão de segurança externa, relatório e decisão de continuidade.

**Decisões do responsável técnico antes do primeiro processo real** (consolidadas de todas as revisões; também em `docs/conformidade/checklist-piloto.md`):

1. Pseudonimização de vítimas e testemunhas: estender (recomendado) ou aceitar a limitação com registro no aviso de tratamento (revisão 8.2, §3).
2. Chave da API da Anthropic, smoke test real do agente, e leitura dos termos vigentes quanto a treinamento e retenção.
3. Assinatura da decisão do object storage.
4. Apagar os 344 objetos sintéticos órfãos em claro no storage de desenvolvimento.
5. Vault em produção com três pessoas, certificado real, perfil de produção num servidor de verdade.
6. Revisão das minutas por advogado e aceite dos termos pelos usuários.
7. Confirmação dos dados jurídicos pelo gabinete: calendários, prazos, tabela do art. 109, tipos penais, regras de borda.
8. Conta na MaxMind para geolocalização por IP (opcional).

## 0.00 Atualização: Etapa 7 concluída (criptografia em repouso, backup, guias, operação)

| Verificação | Resultado |
| --- | --- |
| Backend | 860 testes; cobertura 98,3%; todos os passos do `verificar.sh` verdes (ver revisão 7.10, §1.1) |
| E2E | 36 de 36 com a cifra ativa |
| Backup | restauração em banco e bucket limpos conferida por hash; recusa por falta de espaço testada |
| Cifra | páginas, evidências, mensagens, identidades e objetos novos cifrados; conferido no banco e no storage; objetos legados de processos existentes recifrados |
| Vault | serviço real no compose com Transit e AppRole; ensaios de rotação, incidente de injeção e reinício com unseal registrados |
| Guias | assessor e desembargador com 11 capturas reais; leitor externo 10 de 10 |
| Operação | `docs/operacao.md` com instalação, atualização, Vault, certificado, backup, descarte, monitoramento, incidentes, relatório de uso e checklist de segurança |

Incidente de processo: a primeira execução encheu o disco por um backup de teste contra o banco e o bucket principais, derrubando Docker e WSL. Recuperado com autorização do responsável técnico; regras de disco adicionadas aos briefs e ao script de backup (estimativa e recusa). Registrado na revisão 7.1-7.9, §0.

Restam a Etapa 8 (piloto) e as decisões listadas na revisão 7.10, §5: apagar 344 objetos órfãos sintéticos, endurecer o Vault para produção, certificado real, assinatura da decisão do storage, prazos de incidente nos documentos de conformidade. Achado a corrigir em 8.1: healthcheck do Vault e `/saude` não detectam cofre selado.

Cobre tudo que foi executado por agentes e revisado: Etapa 0 (esqueleto), 1 (esquemas de dados), 2 (validações), 3 (acesso e auditoria), 4A.1 (adaptador), 4A a 4F (ingestão completa), 5 (agente e chat) e 6 completa (interface web, subetapas 6.1 a 6.10).

## 0.0 Atualização: Etapa 6 concluída (6.4 a 6.10)

| Verificação | Resultado |
| --- | --- |
| Backend | 828 testes, 1 pulado; cobertura 98,59%; três execuções completas verdes pelo executor, mais a do revisor (seção 1.1 da revisão 6.10) |
| Front | 56 testes unitários; 36 de 36 testes Playwright contra a stack real, incluindo axe em 13 telas nos dois temas e varredura de cabeçalhos |
| Segurança do front | CSP sem script inline, HSTS, Permissions-Policy, COOP e CORP; nada dos autos renderizado como HTML ou link; PDF nunca chega ao navegador (página renderizada no servidor dentro do sandbox) |
| Banco | migração 0009 (head); banco de desenvolvimento limpo de dados sintéticos (89 gabinetes e 1 milhão de eventos removidos, cadeia global preservada) |

Requisitos atendidos nesta rodada: dossiê navegável com índice, ficha, linha do tempo e alertas; visualizador com evidência destacada; tela de validações com anotação e correção de fato com histórico; chat com citações clicáveis e estado "em revisão" após incidente; tela de auditoria com exportação, verificação da cadeia e relatório de uso com custo estimado; acessibilidade e cabeçalhos de segurança.

A interface web da primeira versão está completa. Restam as Etapas 7 (criptografia em repouso, guia do assessor, operação) e 8 (piloto).

## 0. Atualização: Etapa 5 e subetapas 6.1 a 6.3

| Verificação | Resultado |
| --- | --- |
| ruff, mypy --strict | limpos, 234 arquivos |
| pytest | 766 testes; três execuções completas, com uma falha intermitente do mesmo teste de observabilidade da 4A.9 (ver revisão 5, §1), nenhuma outra; cobertura 98,7% |
| Front | lint 0, typecheck 0, 18 testes unitários; 8 de 8 testes Playwright contra a stack real |
| Agente | recusa: recall 100% e falso positivo 0% em 60 perguntas; injeção: 14 execuções com modelo manipulado simulado, zero achado suprimido ou criado, zero vazamento, nenhuma ferramenta embutida executada |
| Banco | migração 0007 (head) |
| Stack | api, db, minio, redis, worker, front, proxy saudáveis; front em `https://localhost:8443` pelo proxy Caddy, API no mesmo origin |

Requisitos atendidos nesta rodada: chat de localização e extração com citação conferida por código e recusa de valoração, tipificação e conclusão jurídica (seção 4.4 dos requisitos); interface web com login por usuário e senha, MFA por aplicativo, reset manual e gestão de usuários pelos três papéis (seções 3 e 8); as duas correções obrigatórias da Etapa 3 (auditoria gravada antes da resposta; bloqueio progressivo e rate limit por IP).

**Condição registrada:** o smoke test com o modelo real (dois testes marcados `llm`) não rodou por falta de credencial neste ambiente. Deve ser executado pelo responsável técnico com `ANTHROPIC_API_KEY` no ambiente antes de qualquer uso real do chat. Até lá, a garantia de que o harness do Claude Agent SDK não executa ferramentas embutidas vem das opções do SDK e do hook de bloqueio, ambos testados sem rede.

Novas decisões pendentes de Victor: chave de API da Anthropic para o piloto; aprovação formal do contrato `docs/agente.md`. Cada etapa tem relatório do executor em `RELATORIO-ETAPA-*.md` e revisão independente em `REVISAO-ETAPA-*.md` nesta pasta.

## 1. Estado verificado

Última verificação completa, com imagem reconstruída do zero:

| Verificação | Resultado |
| --- | --- |
| ruff check e ruff format | sem avisos, 204 arquivos |
| mypy --strict | sem erros, 204 arquivos |
| pytest | 697 passaram, 1 pulado, 1 desmarcado (carga), cobertura 98,72% |
| Ponta a ponta da ingestão (integração) | passou |
| Regressão de injeção sobre o corpus | recall 100% (16/16), falso positivo 0% (0/196) |
| Banco de desenvolvimento | migração 0006 (head) |
| Stack do compose | api, db, minio, redis, worker saudáveis; nenhum contêiner como root; worker sem saída de rede |

Evolução da suíte: 18 testes na Etapa 0, 46 na 1, 117 na 2, 210 na 3, 476 em 4A/4B, 551 em 4C, 588 em 4D, 616 em 4E, 697 em 4F.

## 2. Conformidade com os requisitos da primeira versão

| Requisito (`requisitos-v1.md`) | Situação | Onde |
| --- | --- | --- |
| Nenhum fato sem evidência (página, trecho, hash) | atendido, imposto no pydantic e no banco por trigger; 0 fatos sem evidência nos 30 arquivos | Etapas 1, 4F |
| Validações determinísticas com todos os valores e página de cada dado | atendido; alerta conclusivo com datas, prazo, base legal, feriados, marcos | Etapa 2 |
| Explicações por template, nunca por modelo | atendido, com testes de frase inteira | Etapa 2 |
| Usuário e senha sem e-mail, MFA obrigatório, reset manual | atendido | Etapa 3 |
| Três papéis com autorização no servidor; 404 fora do gabinete | atendido; matriz como dados; RLS forçada no banco | Etapas 1, 3 |
| Admin vê tudo e o acesso a conteúdo fica destacado | atendido (`admin_acesso_conteudo`) | Etapa 3 |
| Auditoria de tudo, com IP e localização, consulta rápida, append-only | atendido; cadeia de hash, 3 ms em 1 milhão de eventos; geolocalização depende da base MaxMind | Etapa 3 |
| Logs nunca com conteúdo de autos | atendido, com teste de sentinela no worker e filtro no logger | Etapas 0, 3, 4A |
| Pipeline determinística sem modelo de linguagem | atendido | Etapa 4 |
| Funciona no pior caso e diagnostica caso a caso | atendido: 30/30 diagnósticos; fronteiras 100% sem índice | Etapas 4C, 4E |
| Controles de injeção na ingestão como flags, sem bloquear | atendido | Etapa 4D |
| Pseudonimização de réus nos derivados | atendido; nome só em `reu_identidade` | Etapa 4F |
| Só processos públicos na primeira versão | atendido: sigiloso recebe 403 na ingestão | Etapa 4A |
| Parsers em sandbox sem rede e sem credenciais | atendido | Etapa 4A |
| TLS agora, criptografia em repouso depois | pendente por desenho (Etapa 7) | — |
| Chat e agente | não iniciado (Etapa 5) | — |
| Interface web | não iniciado (Etapa 6) | — |

## 3. Métricas de qualidade da ingestão (dez processos sintéticos, 15.647 páginas, 2.825 peças)

| Medida | Resultado | Meta |
| --- | --- | --- |
| Diagnóstico do contêiner | 30/30 | 30/30 |
| Roteador: falso negativo perigoso | 0 de 4.699 | < 1% |
| Texto nativo igual ao gabarito | 10.718/10.718 | — |
| OCR, CER leve / média / forte | 1,65% / 2,12% / 7,58% | 3% / 5% / 15% |
| Fronteira de peça, precisão e recall (sem índice) | 100% / 100% | ≥ 95% |
| Tipo de peça | 100% | ≥ 95% |
| Origem da peça | 99,6% | medir |
| Data da peça | 98,8%, nenhuma inventada | medir |
| Eventos, precisão / recall | 99,3% / 98,0% | — |
| Datas extraídas, precisão | 99,26% a 99,5% | ≥ 99% |
| Fatos sem evidência | 0 | 0 |
| Achados iguais ao esperado | 86,7% (90% no resultado); divergências só por OCR forte, nenhuma conclusão falsa | — |
| Tempo por mil páginas | 35,8 s nativo; 912 s digitalizado | registrar |

## 4. Correções obrigatórias antes do piloto

Registradas nas revisões, não bloqueantes para as próximas etapas:

1. Auditoria automática de leitura gravada depois da resposta (revisão 3, §6.1). Gravar na transação da requisição. Etapa 6.
2. Bloqueio de login por nome permite negação de serviço (revisão 3, §6.2). Rate limit por IP e bloqueio progressivo. Etapa 6.
3. Repetir o ponta a ponta com OCR real dos dez processos num worker dimensionado (revisão 4F, §3).
4. Limpar os gabinetes sintéticos do banco de desenvolvimento (revisão 4F, §6.4).

## 5. Decisões pendentes de Victor

| Decisão | Contexto | Prazo |
| --- | --- | --- |
| Object storage | MinIO não é mais mantido; fork `pgsty/minio` fixado por hash em uso. Alternativas: Chainguard, Garage, RustFS. O código só fala S3 | antes de 7.1 |
| Base GeoLite2 | conta gratuita na MaxMind; sem ela a localização fica `desconhecida` | antes do piloto |
| Dimensionamento do worker | 1 worker, 12 CPUs, 4 lotes de 8 páginas: 15 minutos por mil páginas digitalizadas | antes do piloto |
| Pasta `.sinteticos` no OneDrive | 4,7 GB sincronizando; excluir da sincronização ou mover com `LUPA_SINTETICOS_DIR` | quando quiser |
| Dados jurídicos a confirmar pelo gabinete | calendários (`feriados`, `suspensoes`), `prazos_recursos`, `prescricao_art109`, `tipos_penais`, `eventos.yaml`; regras de borda listadas em `docs/validacoes.md` | antes do piloto |
| Valores reais das variáveis de produção | `LUPA_DB_*`, `LUPA_ADMIN_*`, chaves do MinIO | ambiente do piloto |

## 6. Limitações declaradas e aceitas

- Prescrição após a sentença usa a pena em abstrato (nunca gera alarme falso; pode deixar de apontar). Pena aplicada não é extraída. Próxima rodada do catálogo.
- Súmula 310 do STF, prazos especiais, pronúncia e acórdão como marcos, causas suspensivas: não aplicados; documentados no guia.
- Assinatura digital conferida só pela estrutura, sem validação criptográfica.
- Texto girado e fundo não branco não são tratados como ocultos.
- Detecção de idioma por heurística de palavras funcionais, só para parágrafos com 8 palavras ou mais.
- `bbox` da evidência não gravado; o visualizador da Etapa 6 deriva dos blocos da página.
- Calibração com o Projudi espera o arquivo real; roteiro e script prontos.

## 7. Incidentes de processo e regras adotadas

- Um agente copiou arquivos do contêiner para o host e sobrescreveu por dois minutos o trabalho de outro (Etapa 3). Regra desde então: fluxo só host → contêiner. Cumprida nas etapas seguintes.
- Dois bugs de etapas anteriores foram encontrados por etapas seguintes graças ao gabarito sintético: página sem conteúdo mandando o PDF à quarentena (4A, achado na 4C) e comparação de cor sem máscara de alfa (4C, achado na 4D). Ambos corrigidos na origem com teste.

## 8. Próximos passos

Etapas 5 (agente e chat), 6 (interface web), 7 (criptografia em repouso e guia) e 8 (piloto), conforme `roteiro-etapas-4-8.md`. As subetapas 5.1, 5.2 e 6.1 a 6.3 podem começar em paralelo; a decisão sobre o object storage (7.1) deve vir antes de qualquer gravação de autos reais.
