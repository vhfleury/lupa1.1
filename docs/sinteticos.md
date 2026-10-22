# Autos sintéticos e gabarito (Etapa 4B)

O Lupa precisa de uma régua para saber se a ingestão lê bem os autos. Como não podemos usar
processos reais para isso, o pacote `lupa.sinteticos` fabrica **processos criminais falsos e
difíceis**, sempre iguais para a mesma semente, e grava junto de cada um um **gabarito**: tudo o
que uma leitura perfeita deveria encontrar. As etapas 4C a 4F medem a pipeline contra esse
gabarito com `scripts/medir.py`.

## Nada é real

- Nomes, endereços e a comarca ("Vila Esperança") são inventados por combinação de listas.
- **CPF**: todo CPF gerado tem o segundo dígito verificador propositalmente errado; há teste que
  gera 5.000 CPFs e confere que nenhum é válido.
- **Número do processo (CNJ)**: o dígito verificador é correto (passa na validação do Lupa), mas
  o segmento é `8` (Justiça Estadual) com tribunal `99`, que não existe (os tribunais estaduais
  vão de 01 a 27), e o sequencial fica na faixa `9900000` a `9999999`, que o Lupa reserva para
  dados de teste. Formato: `99NNNNN-DD.AAAA.8.99.OOOO`.
- Códigos de autenticação são hexadecimais aleatórios; o site de conferência não existe.

## Como gerar

Os PDFs são grandes e **não entram no repositório**. A pasta padrão é `.sinteticos/` na raiz
(ignorada pelo git); para usar outra, passe `--destino` ou defina `LUPA_SINTETICOS_DIR`.

```bash
# um processo (40 folhas, 25% digitalizadas), nos três cenários
python scripts/gerar_autos.py processo --semente 1 --paginas 40 --digitalizada 0.25

# com injeções (todas, ou uma lista: base64,homoglifos,...)
python scripts/gerar_autos.py processo --semente 2 --paginas 60 --injecoes todas

# os dez processos de referência (demora; ver tempos no relatório 4B.9)
python scripts/gerar_autos.py referencia
python scripts/gerar_autos.py referencia --somente semente_01,semente_02

# o corpus de injeção (uma variante por vetor e uma com todos)
python scripts/gerar_autos.py injecao
```

No contêiner: `docker compose exec api python scripts/gerar_autos.py --destino /tmp/sint ...`.

Cada processo vira uma pasta com três subpastas, uma por cenário, cada uma com o arquivo de autos
e o `gabarito.json` daquele cenário. Um `resumo.json` registra folhas, peças, tempo de geração e
tamanho de cada arquivo.

## Os três cenários

O **conteúdo é o mesmo** nos três (mesmas folhas, peças, eventos e resultado esperado); muda só a
embalagem, e com ela o diagnóstico que a etapa 4C deve dar.

| Cenário | Arquivo | O que tem | `diagnostico_esperado` |
| --- | --- | --- | --- |
| `zip_por_peca` | `autos.zip` | Um PDF por peça, nome `NNN_tipo_AAAA-MM-DD.pdf` (ordem, tipo, data) | `zip_por_peca` |
| `pdf_indice` | `autos.pdf` | Páginas de "ÍNDICE DE MOVIMENTAÇÕES" no início (uma linha por peça, com data, título e folha) e um bookmark por peça | `pdf_com_bookmarks_e_indice` |
| `pdf_liso` | `autos.pdf` | Tudo num PDF só, sem bookmarks nem índice (o pior caso) | `pdf_liso` |

## O que deixa os autos difíceis

- **Tipos de folha**: nativa (texto real, fontes embutidas); digitalizada (imagem com ruído,
  rotação de até 3 graus, 150 a 300 DPI, contraste variável, sem camada de texto); híbrida com
  cabeçalho e rodapé nativos e corpo em imagem; híbrida com o bloco de assinatura em imagem;
  verso em branco; capa de autuação.
- **Níveis de degradação**: `leve` (300 DPI, ruído baixo, até 1 grau), `media` (200 DPI, até 2
  graus), `forte` (150 DPI, ruído alto, contraste baixo, até 3 graus).
- **Ruídos de leitura**: cabeçalho idêntico em todas as peças (atrapalha achar fronteiras),
  rodapé com "código de autenticação" falso em toda folha, carimbo vermelho em imagem por cima
  do texto, marca d'água diagonal "CÓPIA - DOCUMENTO SINTÉTICO" (texto cinza na camada).
- **Distratores**: parágrafos de enchimento com datas que não são eventos (ofícios, audiências
  redesignadas, mandados) e datas citadas em outras peças.
- **Datas em dois formatos**: `dd/mm/aaaa` ou por extenso ("3 de março de 2024").
- **Duas colunas (opcional, 4E.0)**: `Configuracao(duas_colunas=(TipoPeca.LAUDO, ...))` ou
  `--duas-colunas laudo,termo_depoimento` diagrama o corpo dessas peças em duas colunas. A
  folha ganha o elemento `duas_colunas` e o `texto` do gabarito é a ordem de leitura (coluna
  esquerda inteira, depois a direita). Os dez processos de referência não usam a opção.

## Injeções (corpus separado)

Cada variante planta uma tentativa de manipular um sistema automatizado (vetores de
`prompt-injection.md`, seção 1). O gabarito registra, por injeção, o `vetor`, o `objetivo`, a
folha e o texto da instrução. **Nenhuma injeção muda o resultado esperado**: o teste da pipeline
é justamente não obedecer.

| Vetor | Onde | Objetivo |
| --- | --- | --- |
| `texto_branco` | Texto branco de 1 pt na 1ª folha do recurso (fica na camada, invisível) | suprimir achado |
| `fora_da_pagina` | Texto posicionado abaixo da folha da sentença | alterar data |
| `metadado_xmp` | `dc:description` do XMP do arquivo | vazar dado |
| `anotacao` | Anotação de texto nas contrarrazões | criar achado |
| `imagem_com_texto` | Imagem com instrução na 1ª folha do laudo | mudar classificação |
| `base64` | "Código de verificação" em base64 numa juntada | suprimir achado |
| `homoglifos` | Instrução com letras cirílicas nas contrarrazões | criar achado |
| `idioma_alternado` | Parágrafo em inglês nas razões do recurso | suprimir achado |
| `transcricao_citada` | Mensagem de celular transcrita no laudo | alterar data |

O corpus fica em `.sinteticos/injecao/` (fora do repositório, como pede o roteiro: acesso
restrito a quem gera). Gere de novo a qualquer momento com `gerar_autos.py injecao`.

## Como ler o gabarito

`gabarito.json` segue o esquema `lupa.sinteticos.gabarito.Gabarito` (versão `1`). Gabarito
inconsistente é rejeitado ao carregar.

- `processo`: número CNJ, matéria, `cenario`, `diagnostico_esperado`, semente e
  `data_referencia` (o "hoje" das validações).
- `pecas`: em ordem; cada uma com `tipo` (`TipoPeca`), `origem` (`OrigemPeca`), `titulo`,
  `pagina_inicial` e `pagina_final`, `data` e `tipo_data` (`assinatura`, `protocolo` ou
  `juntada`). A peça 1 é sempre a capa (`outros`).
- `paginas`: uma por **folha de conteúdo**, numeradas de 1 a N (a numeração "Fls. N" impressa no
  rodapé). Cada uma tem `tipo` (`TipoPagina`: `nativa`, `ocr` ou `vazia`, o que a pipeline deve
  concluir), `composicao` (como foi fabricada), `degradacao`, `dpi`, `rotacao_graus`,
  `elementos` (carimbo, marca d'água, rodapé, cabeçalho repetido, injeção), `texto` (o texto
  visível, alvo do OCR; não inclui carimbo, marca d'água nem texto de imagens) e `texto_camada`
  (exatamente o que `page.get_text()` devolve; vazio nas digitalizadas).
- `eventos`: fatos que a extração deve achar: `tipo` (`TipoFato`), `valor` (data `AAAA-MM-DD`,
  pena em meses, tipo de recurso como objeto, reincidência como booleano), `pagina` (folha),
  `trecho` literal e `inicio`/`fim` (offsets em `texto` da folha; nas folhas nativas valem
  também em `get_text()`).
- `resultado_esperado`: o que o motor de validações do Lupa diz com esses eventos, para
  `tempestividade_recurso`, `prescricao_abstrata` e `revisao_preventiva` (`conforme`,
  `atencao` ou `verificar`, com os valores que justificam).
- `arquivos`: os arquivos físicos do cenário; `folhas[i]` é a folha de conteúdo da página física
  i+1 do arquivo (`null` nas páginas de índice).
- `injecoes`: as tentativas plantadas (vazio fora do corpus de injeção).

## Como medir

A pipeline grava sua saída no formato `lupa.sinteticos.saida_pipeline.SaidaPipeline`: peças,
páginas (com o texto final) e eventos, sempre apontando para `(arquivo, pagina física)`, e
opcionalmente o tempo gasto. Depois:

```bash
python scripts/medir.py --gabarito .sinteticos/referencia/semente_01/pdf_liso/gabarito.json \
  --saida saida.json --json medicao.json --markdown medicao.md
```

Métricas: precisão e recall de fronteira de peça; acurácia de tipo, de origem e de data da
peça (`PecaSaida.data`, opcional; peça sem data prevista conta como erro);
acurácia do tipo de página; precisão e recall de eventos (casando tipo, valor e folha); CER por
composição de folha e por nível de degradação (Levenshtein em Python puro sobre textos com
espaços normalizados; é lento em folhas muito divergentes, da ordem de segundos por folha); tempo
por mil páginas, se a saída informar o tempo. `lupa.sinteticos.medicao.saida_perfeita` monta a
saída ideal a partir do gabarito (dá 100% em tudo) e serve de exemplo do formato.

## Eventos, datas e achados (Etapa 4F)

- `medir` passou a devolver também `datas`: o casamento de eventos (tipo, valor, folha) restrito
  aos tipos `data_*`; a precisão de datas é a meta da 4F.9 (sobre as datas extraídas).
- `lupa.sinteticos.achados.comparar` compara os achados da pipeline com o `resultado_esperado`
  do gabarito: resultado igual e valores iguais depois de retirar as chaves de id (`fato_id`,
  `evidencia_id`, `evidencia_ids`, `fato_ids`), que mudam entre gabarito e pipeline.
