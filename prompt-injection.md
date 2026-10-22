# Validações contra prompt injection

Oct 16, 2026 · @Victor Hugo

Autos criminais contêm texto escrito por partes com interesse no resultado: peças de defesa, mensagens de WhatsApp transcritas, e-mails, posts, documentos juntados pelo réu. Qualquer um desses trechos pode conter instruções ao modelo. A defesa não é um detector; é um conjunto de barreiras em cada etapa, de modo que uma instrução que passe por uma seja neutralizada pela seguinte.

## 1. Por onde a injeção entra

| Vetor | Exemplo em autos criminais | Quem controla o texto | Risco |
| --- | --- | --- | --- |
| Texto visível em peça | Trecho em razões de apelação ou memorial com instrução dirigida a "sistemas automatizados" | Parte ou advogado | Alto: chega íntegro ao modelo |
| Texto invisível no PDF | Fonte branca, tamanho 1, texto fora da página, camada oculta, anotações e metadados do PDF | Quem gerou o PDF | Alto: invisível ao assessor, visível ao extrator |
| Imagem com texto | Print de conversa, documento fotografado, marca d'água com instrução; passa pelo OCR | Quem juntou a imagem | Médio: OCR pode captar |
| Conteúdo citado | Mensagens de WhatsApp, e-mails e posts transcritos em laudo pericial ou depoimento | Terceiros (réu, vítima, testemunha) | Médio: aparece dentro de peça oficial |
| Nome de arquivo e metadados | Título do documento, autor, assunto, campos XMP | Quem subiu | Baixo, se o sistema não os usar no prompt |
| Homóglifos e codificação | Letras de outros alfabetos que parecem latinas, texto em base64, unicode de direção (RTL) | Quem gerou o texto | Médio: burla filtros por palavra |
| Instrução em outro idioma | Comandos em inglês ou outro idioma dentro de peça em português | Parte | Médio |
| Cadeia de documentos | Instrução em peça A que o modelo "lembra" ao processar peça B, se contexto for compartilhado | Parte | Baixo, se cada chamada for isolada |
| Dado do próprio sistema | Fato extraído com instrução embutida reaparece em prompt posterior (injeção de segundo estágio) | Sistema | Médio: contaminação interna |

O objetivo do atacante neste domínio é previsível: fazer o sistema omitir um achado (uma intempestividade, uma prescrição não ocorrida), inventar um achado favorável, ou expor dados de outro processo. As validações abaixo são desenhadas contra esses três resultados.

## 2. Camadas de defesa

```
Autos (texto não confiável)
  → 1. Ingestão (código): remove texto oculto e metadados, normaliza Unicode, marca padrões suspeitos, hash por trecho
  → 2. Montagem do prompt: uma peça por chamada, delimitadores aleatórios, rótulo de origem, dados pseudonimizados
  → 3. LLM local: sem ferramentas, sem rede, sem memória entre chamadas; só devolve JSON
  → 4. Validação da saída (código) [barreira decisiva]: esquema estrito, citação conferida por hash e regex, sem instrução refletida, sem dado de outro processo
  → 5. Relatório e interface: texto por template, página renderizada como imagem, alertas de injeção visíveis, nenhuma ação automática
```

As barreiras 1, 4 e 5 são código determinístico e não dependem do modelo se comportar; a barreira 4 é a decisiva, porque um fato só é gravado se a citação conferir com o texto real.

## 3. Validações na ingestão (antes do LLM)

Tudo aqui é código determinístico. O resultado é um conjunto de flags por página e por trecho, que seguem junto com o texto até o relatório.

| Validação | Como funciona | Ação quando dispara |
| --- | --- | --- |
| Texto oculto no PDF | Comparar texto extraído com texto renderizado: fonte < 4 pt, cor igual ao fundo, fora do MediaBox, opacidade zero, camadas (OCG) desligadas | Trecho marcado como oculto e excluído do prompt; página sinalizada no relatório |
| Anotações e metadados | Extrair anotações, campos de formulário, XMP, bookmarks; nunca incluir no texto da página | Descartados; registrados em log |
| Normalização Unicode | NFKC, remoção de caracteres de controle e de direção (U+202E etc.), mapeamento de homóglifos para ASCII equivalente | Texto normalizado; original preservado para evidência |
| Codificações embutidas | Detectar blocos base64, hex ou URL-encoded com tamanho acima de N caracteres | Bloco substituído por marcador `[bloco codificado removido]` |
| Divergência OCR × texto nativo | Em páginas com ambos, comparar; diferença grande indica camada de texto manipulada | Usar o OCR da imagem renderizada; página sinalizada |
| Padrões de instrução | Lista versionada de padrões (em português e inglês) que se dirigem a sistema, assistente, modelo, IA, ou que pedem para ignorar, esquecer, revelar, alterar resultado | Trecho mantido (pode ser conteúdo legítimo) mas marcado `suspeito`; nunca entra em prompt sem o marcador |
| Idioma inesperado | Detecção de idioma por parágrafo; trecho em outro idioma dentro de peça oficial | Marcado para revisão; incluído no prompt com marcador |
| Densidade de texto anômala | Página com volume de texto muito acima do padrão para seu tipo | Marcada |
| Separação por origem | Cada trecho carrega a classificação da peça (oficial do juízo, do MP, da defesa, de terceiro) | Trechos de defesa e de terceiros entram no prompt com rótulo de origem |
| Hash por trecho | Cada trecho extraído tem hash; o mesmo hash entra no prompt e volta na citação da saída | Permite provar que a saída cita texto real |

Nenhum desses controles bloqueia o processamento. Um advogado pode legitimamente escrever "o sistema deve considerar...". O que muda é como o trecho chega ao modelo e como ele aparece ao assessor.

## 4. Validações na construção do prompt

| Validação | Como funciona |
| --- | --- |
| Isolamento por chamada | Cada chamada recebe só o trecho da tarefa; sem histórico, sem memória entre peças, sem contexto de outro processo. Injeção em uma peça não alcança outra |
| Delimitação estrita | Texto dos autos entre marcadores únicos por chamada (gerados aleatoriamente, não previsíveis), e o prompt declara que tudo entre eles é dado a analisar, nunca instrução |
| Instrução depois do dado | Instrução de tarefa colocada após o texto dos autos, reafirmando o que fazer, para reduzir efeito de instruções embutidas no meio |
| Rótulo de origem | Cada trecho entra com cabeçalho: tipo de peça, autor (juízo, MP, defesa, terceiro), página, flags de ingestão |
| Tarefa fechada | O prompt pede uma extração ou comparação específica com esquema de saída fixo; nunca "analise e me diga o que achar" |
| Sem ferramentas | O modelo não tem acesso a funções, busca, código ou gravação; a única saída possível é texto JSON |
| Prompt versionado e assinado | Hash do template registrado por chamada; qualquer alteração passa por revisão e regressão |
| Dados pseudonimizados | Nomes reais substituídos antes do prompt; uma injeção que peça "revele o nome da vítima" não tem o que revelar |
| Tamanho limitado | Teto de tokens por chamada; trecho maior é dividido, nunca truncado silenciosamente |
| Sem dados de outros tenants | O montador de prompt só lê trechos com o mesmo (tenant, processo) da tarefa; verificado em código, não confiado ao chamador |

## 5. Validações na saída do LLM

Esta é a camada que mais importa: mesmo que o modelo seja manipulado, a saída precisa passar por filtros que não entendem linguagem, só verificam fatos.

| Validação | Como funciona | Ação quando falha |
| --- | --- | --- |
| Esquema estrito | Saída parseada contra esquema pydantic; campo extra, tipo errado ou texto fora do JSON é rejeitado | Chamada descartada; retry uma vez; depois marcada como falha |
| Citação obrigatória e verificável | Cada campo traz citação literal + hash do trecho; o sistema confere que a citação existe no trecho enviado e que o hash bate | Campo descartado |
| Datas conferidas por regex | Toda data retornada precisa existir literalmente (em qualquer formato aceito) no trecho citado | Campo descartado e evento logado |
| Números e artigos conferidos | Pena, fração, artigo de lei retornados precisam constar do trecho | Campo descartado |
| Faixa de valores | Datas dentro do intervalo do processo; penas dentro dos limites do tipo; frações válidas | Campo marcado `verificar` |
| Ausência de instrução refletida | Saída não pode conter texto dirigido ao usuário ou ao sistema ("ignore", "o sistema deve", URLs, pedidos) | Chamada descartada; trecho de entrada marcado como suspeito |
| Consistência com extração por regra | Quando regra e LLM extraem o mesmo campo, discordância vira `verificar`; concordância eleva confiança | Nunca sobrescreve a regra |
| Confiança declarada | Modelo informa confiança por campo; baixa confiança não entra como `conforme` | Campo entra como `verificar` |
| Semântica nunca conclui | Validações de classe S só produzem `atenção` ou `verificar`; o código impede `conforme` nessa classe | Resultado rebaixado |
| Determinismo | Mesma entrada, mesma versão, mesma saída; discrepância em reexecução de amostra dispara alerta | Modelo ou prompt suspeito |
| Ausência de dados de outro processo | Saída não pode conter identificadores (número CNJ, pseudônimo) que não pertencem à tarefa | Chamada descartada; incidente aberto |

O efeito prático: uma injeção bem-sucedida consegue, no máximo, fazer o modelo devolver lixo, que é descartado. Ela não consegue criar um fato sem evidência, porque o fato só nasce quando a citação confere.

## 6. Validações no relatório e na interface

| Validação | Como funciona |
| --- | --- |
| Relatório gerado por template | Texto do relatório vem de templates com os fatos preenchidos; nenhuma frase livre do LLM aparece sem rótulo "trecho gerado" |
| Trechos suspeitos sinalizados | Toda evidência vinda de trecho com flag de ingestão (oculto, codificado, padrão de instrução, idioma inesperado) aparece com aviso e link para a página |
| Painel de alertas de injeção | Seção própria do relatório lista páginas com texto oculto, metadados com instrução, blocos codificados; o assessor vê o que o PDF esconde |
| Sem execução de conteúdo | Texto dos autos exibido como texto puro; sem renderizar HTML, Markdown ou links clicáveis vindos dos autos |
| Evidência renderizada da imagem | O visualizador mostra a página renderizada (imagem), não o texto extraído; texto oculto não engana o assessor |
| Fatos descartados visíveis | Contador de campos descartados por falha de citação por peça; muitos descartes em uma peça é sinal de manipulação ou OCR ruim |
| Resumo gerado em área separada | Resumo narrativo (quando houver) fica em bloco rotulado, com parágrafos ancorados às peças e aviso de que é gerado |
| Nenhuma ação automática | Relatório não dispara nada: não altera autos, não envia e-mail, não cria tarefa. A única saída é leitura humana |

## 7. Suíte de testes de regressão e métricas

A suíte roda a cada mudança de prompt, modelo, extrator ou catálogo. Nenhuma versão sobe se um caso de injeção passar a produzir fato sem evidência ou a suprimir um achado.

**Corpus de testes**

- Processos sintéticos limpos (gabarito conhecido) como linha de base.
- Os mesmos processos com injeções inseridas por vetor: texto visível em razões, texto oculto, imagem com instrução, metadados, homóglifos, base64, idioma alternado, instrução em transcrição de WhatsApp, injeção de segundo estágio via fato extraído.
- Para cada injeção, um objetivo: suprimir achado, criar achado, vazar dado, alterar data, mudar classificação da peça.
- Casos de falso positivo: peças legítimas com frases como "o sistema processual deve", "ignora-se a tese", trechos em inglês citados, para garantir que não são bloqueados.

**Métricas por versão**

| Métrica | Meta |
| --- | --- |
| Fatos sem evidência válida gravados | 0 |
| Achados do gabarito suprimidos sob injeção | 0 |
| Achados inexistentes criados sob injeção | 0 |
| Vazamento de identificador de outro processo | 0 |
| Trechos suspeitos detectados na ingestão (recall sobre o corpus) | ≥ 90% |
| Falsos positivos de trecho suspeito em peças legítimas | ≤ 5% |
| Datas extraídas corretas (precisão) com e sem injeção | ≥ 99% |
| Diferença de resultado entre reexecuções da mesma entrada | 0 |

**Processo**

- Corpus de injeção mantido em repositório separado, com acesso restrito; novos padrões vistos em produção entram como casos.
- Reavaliação a cada troca de modelo e a cada 90 dias com amostra de processos reais já julgados (anonimizados), comparando achados com o acórdão.
- Teste de intrusão externo inclui injeção via autos como escopo explícito.

## 8. Resposta a incidente de injeção

| Gatilho | Resposta imediata | Investigação |
| --- | --- | --- |
| Saída com instrução refletida ou dado de outro processo | Chamada descartada; processo marcado `em revisão`; relatório bloqueado até análise | Reprocessar a peça com flags; identificar o trecho de origem; registrar o padrão no corpus |
| Texto oculto ou metadado com instrução detectado na ingestão | Relatório publicado com alerta destacado | Assessor decide se comunica ao desembargador; o fato de a peça conter instrução oculta pode ser relevante ao processo |
| Divergência entre regra e LLM em campo crítico (data, pena) | Campo entra como `verificar` | Amostragem para ver se é padrão sistemático |
| Muitos descartes de citação em uma peça | Peça marcada | Diferenciar OCR ruim de manipulação |
| Reexecução com resultado diferente | Versão de modelo/prompt suspeita; congelar deploy | Auditar mudança de infraestrutura ou modelo |

- Todo incidente gera registro na trilha de auditoria com hash do trecho, versão do prompt e do modelo, sem o conteúdo.
- Incidente que envolva vazamento entre tenants ou dado pessoal segue o plano LGPD (comunicação ao controlador em até 24 h).
- Lição aprendida vira caso de teste antes do próximo deploy.
