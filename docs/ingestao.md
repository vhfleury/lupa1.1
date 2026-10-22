# Ingestão — fundações (Etapa 4A)

Tudo o que acontece entre o upload e o job em `validado`, antes de qualquer leitura de conteúdo.
Código em `src/lupa/ingestao/`; testes em `tests/ingestao/`.

## Fluxo

```
POST /processos/{id}/arquivos?nome=autos.pdf   (corpo binário, streaming)
  └─ recepcao.receber: SHA-256 em stream, limite de tamanho, tipo pelos bytes mágicos
  └─ recepcao.lacrar: objeto no storage (chave pelo hash), linha em `arquivo`, job `recebido`
  └─ evento `arquivo_enviado` (ok ou negado) na transação da requisição
  └─ depois do commit: job_id e gabinete_id na fila Redis (RQ)
worker (contêiner `worker`)
  └─ adquire lease (fencing token novo), baixa o objeto
  └─ PDF: 1 lote │ ZIP: inventário seguro, 1 lote por entrada, entradas gravadas no storage
  └─ cada lote: parser no sandbox → resultado gravado uma vez em `lote_ingestao`
  └─ job → `validado` (total de páginas + manifesto) │ `quarentena` (motivo) │ `falho` (motivo)
```

## Estados do job

`lupa/ingestao/estados.py` guarda a tabela de transições como dados e a função pura
`transicao(atual, novo)`; `repositorio.mudar_estado` a aplica sob o fencing token.

| De | Para |
|---|---|
| recebido | validado, falho, quarentena |
| validado | em_extracao, falho, quarentena |
| em_extracao | parcial, em_revisao, concluido, falho, quarentena |
| parcial | em_extracao, em_revisao, falho |
| em_revisao | em_extracao, concluido, falho |
| falho | recebido (nova tentativa manual) |
| concluido, quarentena | nenhum (finais) |

O banco reforça: `motivo_quarentena` é obrigatório se e somente se o estado é `quarentena`.

## Lease, heartbeat e fencing token

Colunas em `job_ingestao`: `lease_dono`, `lease_expira_em`, `heartbeat_em`, `fencing_token`,
`tentativas`. Adquirir é um `UPDATE ... WHERE lease vencido ou nulo` que incrementa o token.
Antes de cada lote o worker renova o lease (heartbeat); toda escrita (`gravar_lote`,
`mudar_estado`, `registrar_resultado`) trava a linha do job e confere o token, então um worker
que perdeu o lease recebe `LeasePerdidoError` e não grava nada. `lote_ingestao` é único por
`(job_id, numero)`: um worker que retoma o job reaproveita os lotes já gravados.

O varredor (`worker.varrer`, a cada volta do loop) reenfileira jobs `recebido` com lease
vencido ou nunca tomados há mais de 30 s; por isso a fila Redis pode ser volátil (sem
persistência) e uma falha de enfileiramento no upload não perde o job. Depois de
`LUPA_MAX_TENTATIVAS` aquisições o job vai para `falho` com `erro_interno`.

O worker conecta com o usuário da aplicação (`url_banco_aplicacao`), assume `lupa_app` e define
o gabinete do job em cada transação (RLS). Só o varredor usa a visão de administrador, para
listar jobs parados de todos os gabinetes.

## Sandbox de parsing

`sandbox.executar` roda `python -I` num subprocesso com:

- `RLIMIT_AS` (`LUPA_SANDBOX_MEMORIA_MB`), `RLIMIT_CPU` (`LUPA_SANDBOX_CPU_SEGUNDOS`),
  `RLIMIT_FSIZE = 0`, `RLIMIT_NOFILE = 64`, sem core dump;
- tempo de parede (`LUPA_SANDBOX_TEMPO_SEGUNDOS`), imposto pelo pai;
- ambiente mínimo (`PATH`, `HOME`, `LANG`, `TMPDIR`): nenhuma variável `LUPA_*`, logo nenhuma URL
  ou credencial de banco, storage ou Redis;
- criação de sockets desabilitada no próprio filho antes de abrir o PDF;
- resultado só por JSON em stdout; stderr descartado (nunca vai ao log).

`--network none` não se aplica a subprocesso. O isolamento de rede vem do contêiner: o `worker`
fica só na rede `ingestao`, declarada `internal: true` no compose (sem rota para fora), onde
estão apenas `db`, `minio` e `redis`. Limitação conhecida: o filho ainda alcança esses três
serviços na rede interna, mas sem credenciais e sem sockets. Isolar o parser num contêiner
próprio sem rede fica para quando a decifragem por processo (fase 2 de `requisitos-v1.md` §6)
exigir um worker de decifragem separado.

Desfecho do sandbox: código de saída 3 (`MemoryError` ou erro de sistema do MuPDF) →
`limite_memoria`; `SIGXCPU`/`SIGKILL` → `limite_cpu`; tempo → `tempo_esgotado`; outro código
ou saída ilegível → `erro_parser`. Todos levam o job a `falho`, nunca a `concluido`.

## Quarentena

| Motivo | Quando |
|---|---|
| corrompido | PDF que não abre ou sem páginas; ZIP ilegível, CRC errado, compressão desconhecida |
| senha | PDF com senha de usuário; entrada de ZIP com bit de criptografia |
| truncado | PDF sem `%%EOF` nos últimos 1024 bytes |
| assinatura_invalida | há `/ByteRange` e nenhum cobre o arquivo inteiro (alterado depois de assinado); a validação criptográfica da assinatura fica fora |
| tipo_invalido | entrada de ZIP que não é PDF; ZIP sem arquivos |
| zip_malicioso | `..`, caminho absoluto ou com unidade, barra invertida, link simbólico, nomes repetidos, entradas demais, razão de compressão ou tamanho descomprimido acima do limite |

Texto legível de cada motivo: `quarentena.DESCRICOES`. Quarentena é estado final; só
`validado` entra na extração (`quarentena.pode_extrair`).

## Recepção

Corpo binário (`application/octet-stream`), nome em `?nome=`; não há multipart. Tipo pelos bytes
mágicos (`%PDF-`, `PK\x03\x04`); extensão `.pdf`/`.zip` que contradiz o conteúdo é recusada (415).
Vazio: 422. Acima de `LUPA_UPLOAD_LIMITE_BYTES`: 413, com o upload interrompido no limite.
Processo sigiloso: 403 (v1 só aceita processos públicos). Mesmo conteúdo no mesmo processo:
200 com `duplicado: true`, sem novo `arquivo`, objeto ou job.

## Object storage

`storage.ObjectStorage` (`gravar`, `ler`, `existe`, `apagar`, `listar`) com `ArmazenamentoS3`
(boto3, endpoint do MinIO; para a AWS basta trocar endpoint e credenciais) e
`ArmazenamentoMemoria`. Escolha por `LUPA_STORAGE_BACKEND` (`s3` ou `memoria`). Chave:
`gabinete/<id>/processo/<id>/<sha256>`; entradas de ZIP usam a mesma regra com o hash da entrada.

## Métricas

`GET /metricas` (texto Prometheus; só administrador), calculadas do banco a cada coleta:

| Métrica | Tipo | Rótulos |
|---|---|---|
| `lupa_ingestao_jobs` | gauge | estado |
| `lupa_ingestao_lotes` | gauge | estado |
| `lupa_ingestao_idade_fila_segundos` | gauge | — |
| `lupa_ingestao_paginas_total` | counter | — |
| `lupa_ingestao_paginas_por_segundo` | gauge (última hora) | — |
| `lupa_ingestao_retries_total` | counter | — |
| `lupa_ingestao_falhas_total` | counter | tipo (falho, quarentena), motivo |

Logs do worker: só `job_id`, número do lote, estado, motivo e tentativa. Nome de arquivo e texto
nunca entram; `tests/ingestao/test_observabilidade.py` prova com um texto sentinela.

## Configuração

| Variável | Padrão |
|---|---|
| `LUPA_STORAGE_BACKEND` | `s3` |
| `LUPA_REDIS_URL` | `redis://redis:6379/0` |
| `LUPA_UPLOAD_LIMITE_BYTES` | 536870912 (512 MB) |
| `LUPA_SANDBOX_MEMORIA_MB` / `_CPU_SEGUNDOS` / `_TEMPO_SEGUNDOS` | 1024 / 60 / 120 |
| `LUPA_ZIP_MAX_ENTRADAS` / `_MAX_RAZAO` / `_MAX_DESCOMPRIMIDO_BYTES` | 2000 / 100 / 4 GB |
| `LUPA_LEASE_SEGUNDOS` / `LUPA_MAX_TENTATIVAS` | 300 / 3 |

# Diagnóstico e páginas (Etapa 4C)

Do `validado` em diante, no mesmo worker. Código em `src/lupa/ingestao/`: `diagnostico.py`,
`sinais.py`, `roteador.py` (+ `dados/roteador.yaml`), `texto_nativo.py`, `ocr.py`,
`hibridas.py`, `extrator_paginas.py` (filho do sandbox), `extracao.py` (orquestração),
`qualidade.py`. Testes em `tests/ingestao/test_{diagnostico,paginas,ocr,hibridas,extracao,
worker_extracao}.py`.

## Fluxo

```
validado
  └─ diagnóstico (cenário + fronteiras de origem) gravado em diagnostico_arquivo
  └─ job → em_extracao; processo.status → em_ingestao
  └─ lotes de 8 páginas, cada um num filho do sandbox (um documento aberto por processo):
       sinais → roteador → texto nativo → OCR (rota ocr ou abstenção) → fusão e divergência
  └─ cada lote gravado em `pagina` assim que termina (upsert por arquivo+número)
  └─ a cada 400 páginas o job cede a vez (volta ao fim da fila, sem contar tentativa)
  └─ fim: relatório de qualidade no job; concluido | parcial | falho; processo.status → pronto
```

## Diagnóstico

| Cenário | Regra |
|---|---|
| `zip_por_peca` | ZIP com duas ou mais entradas PDF (ZIP com uma só é diagnosticado pelo PDF) |
| `pdf_com_bookmarks_e_indice` | sumário com entradas e índice de movimentações no início |
| `pdf_com_bookmarks` | só sumário |
| `pdf_com_indice` | só índice: primeiras páginas em que a maioria das linhas segue `Movimentação N - dd/mm/aaaa - título - fls. P` (aceita `evento`, `mov.`, `seq.`, `pág.`) |
| `pdf_liso` | nenhum dos dois |

`fronteiras_origem`: lista `{peca, titulo, data, arquivo, pagina, fonte}` com `fonte` em
`indice`, `bookmark` ou `manifesto` (no ZIP também `pagina_continua`). A página é a física no
arquivo, já contando as páginas do índice. Leitura: `GET /processos/{id}/arquivos/{arquivo_id}/
diagnostico` (auditada como `processo_aberto`, conteúdo).

## Sinais e roteador

Sinais por página (`pagina.sinais`): caracteres imprimíveis, U+FFFD, caracteres invisíveis
(fonte < 4 pt, branco, fora da página), cobertura de texto, área de imagem e área de imagem
opaca (sem máscara de transparência), quantidade de imagens e palavras, fragmentação, rotação
declarada, tinta (pixels escuros a 24 DPI) e `visualmente_vazia`.

`rotear(sinais)` devolve `vazia` (sem tinta, sem imagem opaca, até 3 caracteres), `ocr` (imagem
opaca em ≥ 85% da página e até 20 caracteres), `nativa` (imagem opaca ≤ 0,5%, ≥ 20 caracteres,
fragmentação ≤ 0,5, U+FFFD ≤ 2%, nenhum invisível) ou None (abstenção: OCR integral, texto
nativo guardado e fusão). Limiares em `dados/roteador.yaml` com `versao` e `fonte`.

## Texto, OCR e fusão

- Nativo: blocos do PyMuPDF, ordem de leitura por corte XY com detecção de colunas; linhas não
  horizontais no fim. Coordenadas em pontos, origem no canto superior esquerdo. `coordenadas`
  guarda blocos e linhas com offsets no texto.
- OCR: Tesseract 5.5.0 (Debian trixie, `tesseract-ocr=5.5.0-1+b1`, modelos `1:4.1.0-2`;
  `por.traineddata` sha256 `c4932b93…7deb`, conferido no build), chamado por subprocesso dentro
  do filho do sandbox, imagem por stdin, TSV por stdout, `OMP_THREAD_LIMIT=1`. Raster de 300 DPI
  em cinza; `--psm 0` (OSD) no mesmo raster; com confiança ≥ 2 a página é rasterizada já girada.
  Caixas em pixels convertidas para pontos pela matriz `pixel -> ponto` (registrada em
  `extracao.ocr.matriz_pixel_para_ponto`).
- Abstenção: `texto_nativo` e `texto_ocr` guardados; `texto` é a fusão (linha do OCR coberta em
  50% ou mais por linhas nativas é descartada). Linha nativa com 8+ caracteres que o OCR lê com
  similaridade < 0,5 no mesmo lugar gera `texto_divergente` e entra em
  `extracao.divergencia.trechos`; a distância somada é o CER estimado da página.

## Gravação, idempotência e retry

`pagina` é única por `(arquivo_id, numero)`; o lote é gravado com upsert e `versao_extrator`.
Páginas já gravadas na versão corrente (`extrator_paginas.VERSAO_EXTRATOR`) são puladas;
mudar a versão refaz todas. ZIP: numeração contínua no arquivo, com `origem_arquivo` (entrada) e
`pagina_origem`.

| Desfecho da extração | Estado |
|---|---|
| todas as páginas gravadas | `concluido` |
| algumas páginas sem resultado (lote morto, OCR indisponível) | `parcial` (lista no relatório) |
| nenhuma página | `falho` com o motivo mais frequente |

Retry automático: `tempo_esgotado` e `erro_parser` voltam a `recebido` (lotes falhos de validação
apagados, job reenfileirado) até duas vezes (`LUPA_MAX_RETENTATIVAS`); `limite_memoria` e
`limite_cpu` nunca. `processo.status`: `em_ingestao` com job em andamento; `pronto` quando nenhum
está em andamento e algum terminou `concluido` ou `parcial`.

## Paralelismo e justiça

Lotes em processos filhos (o PyMuPDF não é compartilhado entre threads; no pai, threads só
esperam os filhos). Tetos: `LUPA_EXTRACAO_LOTES_POR_JOB` e `LUPA_EXTRACAO_LOTES_POR_GABINETE`
(semáforo por gabinete dentro do processo worker). Justiça entre jobs por round-robin de fatias:
depois de `LUPA_EXTRACAO_FATIA_PAGINAS` páginas o job solta o lease e volta ao fim da fila, então
um job pequeno de outro gabinete não espera um arquivo de 5.000 páginas inteiro.

## Relatório de qualidade

`job_ingestao.relatorio`: páginas por tipo e por rota, abstidas, faltando (com lista e motivo),
flags, CER estimado (páginas com texto nativo e OCR), confiança média do OCR, rotações corrigidas e
tempos (parede, soma por página, por mil páginas). `GET /processos/{id}/arquivos/{arquivo_id}/
relatorio` (auditada, sem conteúdo dos autos).

## Configuração nova

| Variável | Padrão |
|---|---|
| `LUPA_MAX_RETENTATIVAS` | 2 |
| `LUPA_EXTRACAO_PAGINAS_POR_LOTE` | 8 |
| `LUPA_EXTRACAO_LOTES_POR_JOB` / `_POR_GABINETE` | 4 / 4 |
| `LUPA_EXTRACAO_FATIA_PAGINAS` | 400 (0 = sem fatiar) |

## Medições

`scripts/medir_extracao.py` (dentro do contêiner `api`, que monta `.sinteticos` só leitura):
`diagnostico`, `roteador`, `ocr`, `tempo` e `extrair <processo>` (gera `saida.json` para
`scripts/medir.py` e o relatório de qualidade). Resultados em `docs/etapas/RELATORIO-ETAPA-4C.*`.

# Saneamento contra injeção (Etapa 4D)

Especificação: `prompt-injection.md`, seções 1, 3 e 7. Nenhum controle bloqueia o processamento:
cada um produz flags por página e trechos que seguem no banco até a tela. O original fica em
`pagina.texto`; o que vai ao modelo é o derivado `pagina.texto_normalizado`.

## Onde roda

Tudo dentro do filho do sandbox (`extrator_paginas.saneamento_da_pagina`), depois da extração
da página; os metadados do documento também são lidos na inspeção (`parser_pdf.inspecionar`).

| Controle | Módulo | Saída | Flag |
| --- | --- | --- | --- |
| Texto oculto (4D.1) | `oculto.py`, `texto_nativo.ler_blocos` | `pagina.trechos_ocultos` (texto, bbox, motivo, hash, categorias); excluído de `texto` | `texto_oculto` |
| Metadados e anotações (4D.2) | `metadados.py` | `diagnostico_arquivo.metadados_descartados` (hash, nunca o valor); itens da página em `extracao.metadados_descartados` | `metadado_suspeito` (página da anotação; primeira página para XMP/Info/bookmark) |
| Unicode (4D.3) | `saneamento.py` + `dados/homoglifos.yaml` | `texto_normalizado`; mapa de offsets recalculável | `homoglifos` |
| Blocos codificados (4D.4) | `deteccao.py` | marcador `[bloco codificado removido]` no normalizado; trecho `bloco_codificado` | `bloco_codificado` |
| Padrões de instrução (4D.5) | `deteccao.py` + `dados/padroes_instrucao.yaml` | trechos suspeitos por categoria | `padrao_instrucao` |
| Idioma (4D.6) | `deteccao.py` + `dados/idiomas.yaml` | trecho categoria `idioma` | `idioma_inesperado` |
| Densidade (4D.7) | `deteccao.py` + `dados/densidade.yaml` | — | `densidade_anomala` |
| Origem (4D.8) | `origem.py` | campo `origem` em cada trecho (`desconhecida` até a 4E) | — |
| Hash por trecho (4D.9) | `saneamento.hash_trecho` | campo `hash` (sha256 do trecho original, igual a `Evidencia.hash_trecho`) | — |
| Painel (4D.10) | `qualidade.resumo_saneamento`, `repositorio.alertas_arquivo` | `job_ingestao.relatorio.saneamento`; `GET /processos/{id}/arquivos/{arquivo_id}/alertas` | — |

Trecho suspeito: `{inicio, fim}` no normalizado, `{inicio_original, fim_original}` no original,
`hash`, `categoria`, `padrao`, `origem`. Para levar uma posição do normalizado ao original:
`normalizar(pagina.texto).para_original(inicio, fim)` ou `hash_trecho_normalizado`.

## Versões

`VERSAO_EXTRATOR` passou a `4d.1` (páginas antigas são refeitas); na 4E, a `4e.0` (correção do texto branco em `sinais.py`). Cada YAML tem `versao`;
o relatório do job e as métricas da regressão registram as versões usadas (`versoes()`).
Mudou um padrão ou limiar: suba a versão e rode `pytest -m injecao` (passo próprio do
`scripts/verificar.sh`), que mede recall e falso positivo e grava as métricas em
`$LUPA_METRICAS_INJECAO`.

## Limitações conhecidas

- Fundo suposto branco: texto da cor de um retângulo colorido atrás dele não é detectado
  (a divergência OCR × nativo da 4C cobre parte do caso). Texto girado é visível e não é oculto.
- Imagem com texto numa página roteada como nativa não passa pelo OCR, então a instrução da
  imagem não chega a nenhum texto (nem é sinalizada). É o caso `imagem_com_texto` do corpus.
- Idioma por palavras funcionais: segmentos com menos de 8 palavras não são avaliados; espanhol
  tem pouca margem sobre o português.
- Exceção de rodapé dos blocos codificados documentada em `deteccao.py`.

# Fronteiras, peças e índice (Etapa 4E)

Ao fim da extração (job `concluido` ou `parcial`), o worker lê as páginas gravadas e monta o
índice do arquivo (`lupa.ingestao.indice.montar_indice`, função pura), grava as peças em
`peca` e os sinais em `pagina.sinais_fronteira`, e acrescenta ao relatório do job `indice`
(fonte, peças, fracas, versões) e `divergencias_fronteira`. Se o arquivo já tem peças (de uma
execução anterior ou corrigidas pelo assessor), nada é regravado.

## Sinais de fronteira (4E.1)

`sinais_fronteira.py`, a partir do texto e das caixas já gravados (nada reabre o PDF). Cabeçalho
e rodapé repetidos são descobertos no próprio arquivo (máscaras das três primeiras e três
últimas linhas presentes em 30% das páginas, com comparação aproximada para erro de OCR) e
saem do corpo. Por página: `titulo` (lista versionada `dados/titulos_peca.yaml`, com variações e
semelhança ≥ 0,86), `assinatura_fim` (linha "assinado eletronicamente por", tolerante a OCR,
nunca o rodapé "Código de autenticação"), `numero_folha` e `reinicio_numeracao`, `cabecalho`
(máscara das duas primeiras linhas), `protocolo_topo`, `altura_linha` (fonte dominante),
`margem_esquerda` e `colunas`.

## Classificador e índice de origem (4E.2, 4E.3)

`fronteiras.pontuar(anterior, atual)` soma os pesos de `dados/fronteiras.yaml` (versionado):
título 0,5; título que também é seção (razões de apelação) 0,25; assinatura no fim da página
anterior com texto 0,45; reinício de numeração 0,3; cabeçalho novo 0,15; protocolo no topo 0,1;
mudança de fonte e de layout 0,05 cada. Forte ≥ 0,8 começa peça; fraca ≥ 0,45 também começa,
mas com confiança baixa e a flag `fronteira_fraca` para o assessor. Versos em branco ficam
com a peça anterior; páginas do índice de movimentações não pertencem a peça.

Com fronteiras da origem (manifesto do ZIP, bookmarks ou índice, nessa prioridade), elas
mandam; o classificador roda e cada divergência entra em `divergencias_fronteira`
(`origem_sem_sinal_forte`, `sinal_forte_sem_origem`, `origens_discordam` entre bookmarks e
índice) e liga `divergencia_fronteira` na peça.

## Tipo, origem e data (4E.4 a 4E.6)

`classificacao.py` com `dados/classificacao.yaml`: tipo pelo título (3 pontos; 1 quando o
título não decide, como "DECISÃO") mais fórmulas das primeiras 18 linhas (1 ponto cada);
abaixo de 2 pontos ou com margem < 1 sobre o segundo, `outros` com confiança 0,3 e a flag
`tipo_ambiguo`. Origem pelo cargo na última assinatura (0,95), por cargo aproximado quando o
OCR estragou o nome do cargo (0,8), pelo vocabulário do início (0,7) ou `desconhecida`.
`data_peca.py`: protocolo, assinatura, local e data, juntada ou autuação, nessa ordem; a
evidência (literal, offsets na página, hash) vira linha de `evidencia`; sem data reconhecível,
`data_ausente` e nenhuma data.

## API (4E.7, 4E.8, 4E.10)

- `GET /processos/{id}/indice`: peças vigentes de todos os arquivos, em ordem, com tipo,
  origem, páginas, data e evidência, confiança, método, flags e `resumo_flags` (marcas da peça e
  páginas por flag de saneamento). Auditada como `processo_aberto` (conteúdo).
- `GET /processos/{id}/pecas/{peca_id}`: peça, classificação e histórico de versões. Auditada.
- `POST /processos/{id}/pecas/{peca_id}/reclassificar` com `tipo`, `origem`, `dividir_em`
  (página do arquivo em que começa a parte nova) ou `unir_com` (peça vizinha): linhas novas
  `manual`, anteriores não vigentes, evento `peca_reclassificada` por peça nova. Exige a
  permissão de anotar; 422 para pedido incoerente; 404 fora do gabinete.

## Diagnóstico de ZIP (4E.0)

As entradas de um ZIP são inspecionadas em grupos de 32 num único filho do sandbox
(`sandbox.inspecionar_pdfs`); se o grupo falhar, cada entrada é reinspecionada sozinha e o
motivo fica com a culpada. A partida do filho (≈ 0,8 s) era o custo dominante.

## Medição (4E.9)

`scripts/medir_extracao.py pecas --destino <pasta>` usa as páginas de `extrair` e mede
fronteira, tipo, origem e data nos três cenários; ver `docs/etapas/RELATORIO-ETAPA-4E.9.md`.

# Eventos e ponta a ponta (Etapa 4F)

Ao fim da extração, depois do índice, o worker roda `lupa.ingestao.eventos.etapa.processar_eventos`
num savepoint: identifica os réus, extrai os fatos datados das peças vigentes, grava fatos e
achados e acrescenta `eventos` ao relatório do job (só contagens). Falha nessa etapa fica em
`relatorio.eventos.erro` e não desfaz páginas nem peças. `Dependencias.eventos = False` desliga
(comportamento da 4E).

## Datas (4F.1)

`lupa/ingestao/datas.py`: numérico (`dd/mm/aaaa`, `dd.mm.aaaa`, `dd-mm-aaaa`, e `dd/ mm/aaaa`
com espaço do OCR), por extenso (dia e ano em algarismos ou por extenso, `1º`), abreviado
(`15/mai/2014`, `15 mai. 2014`, `15 de mai. de 2014`), com ou sem dia da semana. Datas impossíveis
e anos fora de 1900–2100 são descartados. **Ano de dois dígitos**: século pelo pivô fixo 50
(`00`–`49` → 2000–2049; `50`–`99` → 1950–1999); a ocorrência sai marcada e a confiança do fato
cai para 80%. A busca é no texto normalizado (4D.3) dobrado para minúsculas sem acento, com o
mesmo comprimento do normalizado; os offsets voltam ao original pelo mapa do normalizado.

## Extratores por tipo de peça (4F.2)

Um módulo por tipo em `lupa/ingestao/eventos/` (`denuncia`, `recebimento`, `decisao_prisao`,
`sentenca`, `certidao`, `recurso`); peça `outros` passa só pelas regras do YAML que a admitem.
Padrões versionados em `ingestao/dados/eventos.yaml` (gatilho, janela até a data, tipos de peça,
confiança, `ultima`, `por_reu`) e tabela mínima de tipos penais em
`ingestao/dados/tipos_penais.yaml` (pena máxima do caput em meses, **a confirmar pelo gabinete**).
`fato.versao_extrator` = `<versão de eventos.yaml>+tp<versão de tipos_penais.yaml>`.

| Peça | Fatos |
| --- | --- |
| Denúncia | `data_fato`, `data_nascimento_reu` (por réu), `data_denuncia` (local e data no fim), `pena_maxima_abstrata` (pena transcrita; sem ela, tabela pelo artigo, confiança 0,6; divergência entre as duas, 0,5) |
| Recebimento | `data_recebimento_denuncia` |
| Decisão de prisão | `data_decretacao_preventiva` ("decreto a prisão preventiva", conversão do flagrante) ou `data_revisao_preventiva` ("mantenho a prisão preventiva") |
| Sentença | `data_sentenca`, `reincidente`; pena máxima pelo artigo só como reserva, sem pena da denúncia. Pena aplicada não é extraída (não há `TipoFato` para ela) |
| Certidão | `data_publicacao_sentenca`, `data_intimacao_defesa`, `data_intimacao_mp`, `data_intimacao_reu` (por réu) |
| Recurso | `tipo_recurso` `{"tipo", "recorrente"}` (recorrente pelo texto e, sem pista, pela origem da peça; sem recorrente não gera) e `data_interposicao_recurso` |

## Evidência, reconferência e conflitos (4F.3, 4F.4)

Todo fato nasce com `Evidencia(pagina_id, trecho, inicio, fim)` sobre o texto **original**
(`pagina.texto`), hash calculado pelo esquema. Sem trecho (vazio ou só espaço, inclusive depois
de recortado o nome do réu), o valor é descartado (`relatorio.eventos.sem_trecho`). Toda data é
reconferida por `datas.reconferir`, que escreve a data em todas as formas aceitas e procura no
trecho, sem reaproveitar as expressões de busca; data que não está literalmente no trecho é
rejeitada e vai para o log só com tipo, regra e id da página. Mesmo tipo e valor em mais de uma
página: um fato com várias evidências. Tipos que devem ser únicos (todos menos
`data_revisao_preventiva`) com valores diferentes: todos os fatos são gravados com a confiança
pela metade e o motor devolve `verificar`.

## Réus e pseudonimização (4F.5)

Réus pela qualificação na denúncia (nome seguido de vírgula e termo de qualificação; CPF até 250
caracteres depois). Cada réu vira `reu` com pseudônimo (`REU-01`, `REU-02`, na ordem em que
aparecem) e `reu_identidade` com nome e documento. Fatos por réu levam
`{"valor": ..., "reu_id": "<uuid>"}`; com mais de um réu, o catálogo roda por réu e o achado leva
`valores.reu_id`. O trecho de evidência é recortado para começar depois do nome e do CPF do réu
("intimei pessoalmente o réu FULANO em 07/04/2016" vira "em 07/04/2016"). O nome do réu continua
no texto da página (inevitável), mas não aparece em `fato.valor`, nos trechos dos fatos, em
`achado.valores`, nos eventos de auditoria, nos logs nem em `trechos_suspeitos` (teste em
`tests/ingestao/test_eventos_banco.py`). Nomes de outras pessoas (defensor, testemunha) ficam
nos trechos.

## Gravação, catálogo e API (4F.6, 4F.7)

`repositorio_eventos`: réus idempotentes por pseudônimo; fatos com id derivado da chave natural
(processo, tipo, valor, evidências), gravados com `salvar_fato` só quando novos (`status =
automatico`, `extraido_por = "regra"`); fatos automáticos de outra versão do extrator são
apagados antes, exceto os anotados e os substituídos por correção humana. O catálogo da matéria
do processo roda pelo adaptador da 4A.1 (`para_modelo` → `executar_catalogo` → `para_dominio`)
com a data de hoje (`deps.relogio`); um achado só é gravado quando difere do último da mesma
validação (achados são imutáveis). `processo.status` fica `pronto`. `GET /processos/{id}/achados`
devolve o último achado de cada validação, auditado como `processo_aberto` com conteúdo.

## Cache e reprocessamento (4F.8)

Antes de extrair, o worker procura outro arquivo **do mesmo gabinete** com o mesmo SHA-256 e
todas as páginas na versão corrente do extrator de páginas (`lupa.ingestao.cache`); achando,
copia as páginas (em blocos de 500) e pula a extração; o índice é recalculado (determinístico,
segundos) e as correções manuais de peça não passam para o outro processo. O filtro por gabinete é
explícito, além da RLS. Mudar só `eventos.yaml` ou `tipos_penais.yaml` não toca páginas nem peças:
`processar_eventos` regrava só os fatos e os achados.

## Decisão: `imagem_com_texto` em página nativa (revisão 4D, seção 6, item 2)

Implementado o OCR **só de detecção** (`lupa/ingestao/imagem_nativa.py`, extrator de páginas
`4f.0`): em página roteada como nativa, cada imagem com área acima de 2% da página é rasterizada
a 300 DPI e lida pelo Tesseract; o texto lido não entra em `texto`, `texto_normalizado` nem no que
vai ao modelo. Se casar com os padrões de instrução (4D.5), a página recebe `padrao_instrucao` e
`extracao.imagens_nativas` registra caixa, categorias e hash do texto lido (sem o texto). Custo
medido: 21 a 27 s por mil páginas nativas (12% delas têm imagem acima do limiar, quase sempre
carimbo), contra ~880 s por mil páginas digitalizadas; a injeção do corpus é detectada. A
limitação "imagem com texto numa página nativa não é sinalizada" (seção 4D acima) deixa de valer
a partir do extrator `4f.0`.

## Dimensionamento do worker (revisão 4C, seção 5, item 1)

Configuração usada nas medições da 4F.9: um worker, `LUPA_EXTRACAO_PAGINAS_POR_LOTE=8`,
`LOTES_POR_JOB=4`, `LOTES_POR_GABINETE=4`, sandbox de 1024 MB e 60 s de CPU por lote, Tesseract
com `OMP_THREAD_LIMIT=1`, sem fatiar. Tempos por mil páginas, nativo e digitalizado, em
`docs/etapas/RELATORIO-ETAPA-4F.9.md`. Recomendação para o piloto: uma réplica com 4 lotes
simultâneos por job; mais réplicas só depois do semáforo por gabinete no Redis (risco 3 da
revisão 4C).

## Medição e calibração (4F.9, 4F.10)

- `scripts/medir_extracao.py eventos --destino <volume>`: eventos e achados nos três cenários
  dos dez processos sobre as páginas já extraídas (sem banco); mede precisão e recall de eventos
  e de datas e compara os achados com o `resultado_esperado` (`lupa.sinteticos.achados`).
- `scripts/ponta_a_ponta.py`: upload pelo código do worker (storage e banco configurados) até os
  achados, com `--volume` para reaproveitar as páginas da 4E pelo cache e `--repetir` para medir o
  segundo upload.
- `scripts/calibrar.py <arquivo>`: relatório Markdown para conferência manual; roteiro em
  `docs/calibracao-projudi.md`.
