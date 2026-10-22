# Lupa — Etapa 4 (ingestão) quebrada em seis etapas

20 de outubro de 2026 · Victor Hugo

Este documento substitui a tabela da Etapa 4 do `roteiro-etapas-4-8.md`. A ingestão vira seis etapas, 4A a 4F, cada uma com dez subetapas. Vale a mesma premissa: funcionar no pior caso (PDF único, páginas de todos os tipos, sem índice) e diagnosticar caso a caso para escolher o caminho mais barato. Cada subetapa é uma unidade de trabalho para um agente executor com revisão separada.

Legenda: **[S3]** depende da decisão sobre o object storage.

## Ordem

```
4A fundações ──┬── 4B autos sintéticos ──┐
               │                         ├── 4C diagnóstico e páginas ── 4D saneamento ── 4E fronteiras e índice ── 4F eventos e ponta a ponta
               └─────────────────────────┘
```

4A e 4B andam em paralelo. 4C precisa das duas. 4D, 4E e 4F são sequenciais, mas 4D pode começar quando 4C tiver as páginas gravadas, mesmo antes das medições finais.

---

## Etapa 4A — Fundações da ingestão

Objetivo: tudo que a pipeline precisa para receber, guardar e processar arquivos com segurança, antes de qualquer leitura de conteúdo.

| # | Subetapa | Entregável | Pronta quando |
| --- | --- | --- | --- |
| 4A.1 | Adaptador validações ↔ domínio | `lupa/validacoes/adaptador.py` com `para_modelo` e `para_dominio`; esquemas locais de `modelo.py` removidos | Ida e volta com `fabrica_fato` passa; `executar_catalogo` roda sobre fatos lidos do banco |
| 4A.2 | Esquemas da ingestão | Entidades novas no domínio: `JobIngestao` (estados: recebido, validado, em_extracao, parcial, em_revisao, concluido, falho, quarentena), `LoteIngestao`, `DiagnosticoArquivo`; migração 0003 | Transições de estado válidas impostas por código e testadas; estado nunca volta de `concluido` para `em_extracao` |
| 4A.3 | Fila e worker base | Redis e RQ (ou equivalente registrado) no compose; worker que consome jobs por lote; lease com expiração, heartbeat e fencing token | Worker morto no meio do lote tem o lease recuperado; lote reprocessado não duplica gravação |
| 4A.4 | Sandbox de parsing | Execução de qualquer parser de PDF em subprocesso com limite de memória, CPU e tempo, sem rede e sem acesso ao banco; resultado devolvido por JSON | PDF com stream descomprimido gigante é morto pelo limite; job marca `falho` com motivo, nunca `concluido` |
| 4A.5 | Cliente de object storage **[S3]** | `lupa/ingestao/storage.py`: cliente S3 com interface própria, implementação para o storage escolhido e implementação em memória para testes; chaves de objeto por gabinete e processo | Troca de implementação por configuração; teste de contrato roda nas duas |
| 4A.6 | Recepção e lacre | `lupa/ingestao/recepcao.py`: validação de tipo (PDF, ZIP) e tamanho, SHA-256 calculado em stream, gravação no storage, registro em `arquivo`, evento `arquivo_enviado` | Mesmo arquivo duas vezes não duplica; arquivo com extensão falsa é rejeitado pelo conteúdo, não pelo nome |
| 4A.7 | Inventário de ZIP | `lupa/ingestao/inventario.py`: extração segura (sem caminho `../`, sem link simbólico, limites de quantidade e de tamanho descomprimido), manifesto com ordem, nome e hash por entrada | ZIP malicioso rejeitado com motivo; zip bomb detectada pelo limite de razão de compressão |
| 4A.8 | Quarentena e falhas | Política de quarentena: arquivo corrompido, protegido por senha, truncado ou com assinatura inválida; registro do motivo; tela futura lê daqui | Cada tipo de falha tem teste e motivo legível; nada em quarentena entra na extração |
| 4A.9 | Observabilidade da pipeline | Métricas por job e por lote: idade da fila, páginas por segundo, retries, falhas por motivo; logs com ids opacos | Painel mínimo (Prometheus ou equivalente) exposto; teste prova que nenhum log carrega texto de autos |
| 4A.10 | Ponta a ponta da fundação | Upload de PDF e ZIP sintéticos até o job em estado `validado` com arquivo no storage e manifesto gravado | Fluxo roda em `scripts/verificar.sh` com marcador `integracao` |

---

## Etapa 4B — Autos sintéticos e gabarito

Objetivo: um gerador de processos falsos difíceis, com gabarito, que serve de régua para todas as etapas seguintes. Nenhum dado real.

| # | Subetapa | Entregável | Pronta quando |
| --- | --- | --- | --- |
| 4B.1 | Esquema do gabarito | JSON versionado por processo: lista de peças (tipo, origem, páginas, data), tipo de cada página, eventos com página e trecho, resultado esperado das três validações | Esquema pydantic; gabarito inválido é rejeitado |
| 4B.2 | Textos por tipo de peça | Templates de texto sintético para denúncia, recebimento, decisão de prisão, laudo, termo de depoimento, sentença, certidões, recurso, contrarrazões, acórdão; nomes e CPFs gerados, nunca reais | Cada template produz texto variável por semente; conferência de que nenhum CPF gerado é válido |
| 4B.3 | Renderização nativa | PDF com texto real (fontes embutidas), cabeçalho com número do processo, numeração de página, assinatura eletrônica textual | Texto extraído por PyMuPDF bate com o gabarito, offsets incluídos |
| 4B.4 | Renderização digitalizada | Página renderizada em imagem com ruído, rotação leve, baixa resolução, contraste variável, e embutida no PDF sem camada de texto | OCR de referência atinge CER medido e registrado por nível de degradação |
| 4B.5 | Páginas híbridas e vazias | Cabeçalho nativo com corpo em imagem; assinatura ou tabela como imagem; páginas em branco e capas | Gabarito marca cada página com o tipo correto |
| 4B.6 | Carimbos, marcas e rodapés | Carimbos sobre texto, marca d'água, rodapé com autenticação, cabeçalhos repetidos que atrapalham fronteira | Casos presentes em todos os processos de referência |
| 4B.7 | Três cenários de empacotamento | O mesmo processo gerado como ZIP com um PDF por peça (nomes e datas), PDF único com bookmarks e índice, e PDF único liso | Os três artefatos têm gabarito idêntico de conteúdo e diagnóstico esperado distinto |
| 4B.8 | Injeções por vetor | Variantes com texto oculto, metadados com instrução, imagem com texto, base64, homóglifos, idioma alternado, instrução em transcrição citada; objetivo de cada injeção registrado | Corpus de injeção em repositório separado com acesso restrito |
| 4B.9 | Processos de referência | Dez processos gerados com sementes fixas, tamanhos de 200 a 5.000 páginas, misturas diferentes de tipos de página, nos três cenários | Repositório separado versionado; tempo de geração registrado |
| 4B.10 | Harness de medição | `scripts/medir.py`: compara saída da pipeline com o gabarito e produz métricas (precisão e recall de fronteira, acurácia de tipo, precisão de datas, CER por tipo de página, tempo por mil páginas) | Relatório em JSON e Markdown; usado por 4C a 4F como critério |

---

## Etapa 4C — Diagnóstico e páginas

Objetivo: descobrir o que o arquivo é, separar páginas por tipo e extrair texto com coordenadas de cada uma.

| # | Subetapa | Entregável | Pronta quando |
| --- | --- | --- | --- |
| 4C.1 | Diagnóstico do contêiner | `lupa/ingestao/diagnostico.py`: ZIP por peça, PDF com bookmarks, PDF com índice de movimentações no texto, PDF liso; resultado gravado em `DiagnosticoArquivo` | Três cenários sintéticos diagnosticados corretamente; diagnóstico visível no processo |
| 4C.2 | Leitura de bookmarks e índice | Extração de bookmarks do PDF e de índice textual (padrões de "movimentação", "evento", número e data) em lista de fronteiras candidatas | Fronteiras do índice batem com o gabarito no cenário com índice |
| 4C.3 | Sinais por página | Caracteres imprimíveis, caracteres de substituição, cobertura de texto, área de imagem, fragmentação de palavras, orientação, página visualmente vazia | Sinais gravados por página; reproduzíveis |
| 4C.4 | Roteador de páginas | Classificação nativa, digitalizada, híbrida ou vazia a partir dos sinais, com abstenção para ambíguas (vão para OCR integral) | Matriz de confusão nos dez processos; falso negativo perigoso (nativa com conteúdo em imagem) abaixo de 1% |
| 4C.5 | Texto nativo com coordenadas | PyMuPDF por página: texto, blocos, caixas em pontos PDF, ordem de leitura; `hash_texto` | Offsets reproduzíveis; teste de ordem de leitura em página com duas colunas |
| 4C.6 | OCR | Tesseract por-BR em subprocesso; detecção e correção de rotação; caixas convertidas do raster para pontos PDF com registro da transformação | CER por nível de degradação dentro da meta definida em 4B.4 |
| 4C.7 | Páginas híbridas | Texto nativo e OCR guardados; fusão com deduplicação geométrica; divergência grande gera flag `texto_divergente` | Caso de camada de texto manipulada é detectado |
| 4C.8 | Paralelismo e desempenho | Lotes de páginas em paralelo, documentos abertos por processo (não por thread), limite de páginas simultâneas por processo e por gabinete | Tempo por mil páginas registrado nativo e digitalizado; um PDF enorme não ocupa toda a capacidade |
| 4C.9 | Gravação de páginas | `pagina` gravada com tipo, texto, hash, coordenadas e sinais; idempotente por hash do arquivo e versão do extrator | Reprocessar não duplica; versão do extrator muda e reprocessa só o necessário |
| 4C.10 | Relatório de qualidade por arquivo | Resumo por job: páginas por tipo, páginas abstidas, CER estimado, tempo; gravado e exposto para o dossiê | Relatório gerado para os dez processos de referência |

---

## Etapa 4D — Saneamento contra injeção

Objetivo: os controles de ingestão do `prompt-injection.md`, aplicados a cada página e trecho, com flags que seguem até a tela. Nenhum controle bloqueia o processamento; eles marcam.

| # | Subetapa | Entregável | Pronta quando |
| --- | --- | --- | --- |
| 4D.1 | Texto oculto | Comparação texto extraído × texto renderizado: fonte menor que 4 pt, cor igual ao fundo, fora da área visível, opacidade zero, camadas desligadas; trecho marcado e excluído do que vai ao modelo | Variantes do corpus 4B.8 detectadas; página sinalizada |
| 4D.2 | Metadados e anotações | Anotações, campos de formulário, XMP, bookmarks com instrução: extraídos, nunca misturados ao texto da página, registrados em log por hash | Instrução em metadado não aparece no texto da página |
| 4D.3 | Normalização Unicode | NFKC, remoção de caracteres de controle e de direção, mapa de homóglifos; original preservado para evidência, normalizado para análise | Texto com homóglifos vira ASCII equivalente; evidência aponta para o original |
| 4D.4 | Blocos codificados | Detecção de base64, hex e URL-encoded acima de N caracteres; substituídos por marcador | Bloco codificado não chega ao texto de análise; página sinalizada |
| 4D.5 | Padrões de instrução | Lista versionada, em português e inglês, de padrões dirigidos a sistema, assistente, modelo ou IA, e de pedidos para ignorar, revelar ou alterar; trecho marcado `suspeito`, nunca removido | Recall ≥ 90% no corpus; falso positivo ≤ 5% em peças legítimas com frases imperativas |
| 4D.6 | Idioma inesperado | Detecção de idioma por parágrafo; trecho em outro idioma dentro de peça em português marcado | Instrução em inglês dentro de razões de apelação é marcada |
| 4D.7 | Densidade anômala | Página com volume de texto muito acima do padrão do seu tipo é marcada | Página com 50 mil caracteres é sinalizada |
| 4D.8 | Origem por trecho | Cada trecho carrega a origem da peça (juízo, MP, defesa, terceiro) herdada de 4E, com fallback `desconhecida` | Trecho de defesa nunca entra sem rótulo |
| 4D.9 | Hash por trecho | Cada trecho extraído recebe hash que o acompanha até a citação do agente | Hash estável entre execuções |
| 4D.10 | Painel de flags e regressão | Resumo de flags por página e por peça para o dossiê; suíte de regressão com o corpus 4B.8 no `scripts/verificar.sh` | Suíte roda com marcador próprio; metas de 4D.5 medidas por versão |

---

## Etapa 4E — Fronteiras, peças e índice

Objetivo: separar o PDF em peças, dizer o que cada uma é e montar o índice do processo, que é o que o dossiê mostra.

| # | Subetapa | Entregável | Pronta quando |
| --- | --- | --- | --- |
| 4E.1 | Sinais de fronteira | Por página: cabeçalho novo, título de peça, reinício de numeração, assinatura digital no fim da anterior, mudança de layout, padrão de protocolo, mudança de fonte dominante | Sinais gravados por página |
| 4E.2 | Classificador de fronteira por regras | Pontuação combinada dos sinais com limiar; fronteira forte, fraca ou nenhuma; fraca vai ao assessor | Precisão e recall ≥ 95% no cenário liso dos dez processos |
| 4E.3 | Uso do índice quando existe | No cenário com ZIP por peça, bookmarks ou índice, as fronteiras vêm de lá; o classificador confere e marca divergências | Índice errado de propósito no sintético gera divergência marcada |
| 4E.4 | Tipo da peça por regras | Padrões textuais estáveis por tipo (denúncia, sentença, certidão, recurso...), com confiança; ambíguo fica `outros` com confiança baixa | Acurácia de tipo ≥ 95%; nenhuma peça inventada |
| 4E.5 | Origem da peça | Juízo, MP, defesa ou terceiro, por assinatura, cabeçalho e vocabulário; alimenta 4D.8 | Acurácia medida; `desconhecida` quando incerto |
| 4E.6 | Data da peça | Data de assinatura, protocolo ou juntada extraída por regra, com evidência e tipo de data (assinatura, protocolo, publicação) | Datas com evidência; data ausente não é inventada |
| 4E.7 | Construção do índice | `lupa/ingestao/indice.py`: lista ordenada de peças com tipo, origem, páginas, data, confiança, flags de saneamento; é o índice do processo quando a origem não trouxe um | Índice gerado para os dez processos; exportável em JSON |
| 4E.8 | Reclassificação manual | Assessor pode mudar tipo, origem ou fronteira; nova versão da peça ligada à anterior com registro em auditoria | Histórico preservado; índice reflete a correção |
| 4E.9 | Medição contra gabarito | `scripts/medir.py` estendido para fronteira, tipo, origem e data da peça, nos três cenários | Relatório por processo e por cenário |
| 4E.10 | Índice no modelo e na API | Índice persistido e exposto por endpoint de leitura para o dossiê e para as ferramentas do agente | Endpoint respeita RLS e gera evento de auditoria |

---

## Etapa 4F — Eventos e ponta a ponta

Objetivo: extrair os fatos datados que as validações consomem, com evidência, e fechar o fluxo do upload até os achados.

| # | Subetapa | Entregável | Pronta quando |
| --- | --- | --- | --- |
| 4F.1 | Padrões de data | Reconhecimento de datas em todos os formatos usuais (numérico, por extenso, abreviado), com normalização para ISO e evidência | Suíte de formatos com 100% de acerto |
| 4F.2 | Extratores por tipo de peça | Para cada tipo de peça, quais fatos procurar e com quais padrões: recebimento da denúncia, publicação e intimação na certidão, interposição no recurso, decretação e revisão na decisão de prisão, pena máxima na denúncia ou sentença | Cada extrator com testes nos textos sintéticos do tipo |
| 4F.3 | Evidência obrigatória | Cada fato com trecho literal, offsets, hash e página; fato sem evidência não é gerado | Teste prova que valor sem trecho é descartado |
| 4F.4 | Validação cruzada | Toda data extraída é reconferida contra o texto da página por expressão independente; conflito entre peças (duas datas de sentença) marcado | Data que não existe literalmente na página é rejeitada e logada |
| 4F.5 | Réus e pseudonimização | Identificação de réus por qualificação na denúncia; pseudônimo gerado; nome e documento só em `reu_identidade`; fatos por réu com `reu_id` | Nome real não aparece em `fato`, `pagina.texto` de análise nem em log |
| 4F.6 | Gravação de fatos | Uso de `salvar_fato` em transação por lote; status `automatico`; versão do extrator registrada | Reprocessar com a mesma versão não duplica |
| 4F.7 | Execução do catálogo | Ao fim da ingestão, `executar_catalogo` via adaptador de 4A.1; achados gravados com `salvar_achado` | Achados dos dez processos batem com o resultado esperado do gabarito |
| 4F.8 | Cache e reprocessamento | Resultado intermediário (páginas, peças) cacheado por hash do arquivo e versão; reprocessar uma peça não reprocessa o processo | Segundo upload do mesmo arquivo custa quase zero; troca de versão de extrator reprocessa só a etapa afetada |
| 4F.9 | Ponta a ponta nos processos de referência | Upload até achados nos dez processos, nos três cenários, com o harness de 4B.10 | Datas com precisão ≥ 99%; zero fato sem evidência; tempo por mil páginas registrado; relatório versionado |
| 4F.10 | Calibração com o processo real | Quando o arquivo do Projudi existir: rodar, comparar diagnóstico, fronteiras, tipos e datas com conferência manual de um assessor; ajustar regras e registrar | `docs/calibracao-projudi.md` com o que acertou, o que errou e o que mudou |

---

## Contagem

Seis etapas, sessenta subetapas. Com 4A a 4F no lugar da antiga Etapa 4, o caminho completo fica: Etapas 0 a 3 (feitas ou em andamento), 4A a 4F, 5, 6, 7 e 8. São 100 subetapas até o fim do piloto.
