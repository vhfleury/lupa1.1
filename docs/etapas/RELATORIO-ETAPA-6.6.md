# Relatório da Etapa 6.6 — Visualizador de PDF com evidência

## O que foi feito

Decisão: a página chega ao navegador como IMAGEM renderizada pelo servidor; o cliente nunca
recebe o PDF cru nem o texto extraído (sem pdf.js). O roteiro citava pdf.js; a troca evita
entregar o arquivo inteiro ao navegador e evita que texto oculto do PDF seja exibido ou
selecionável.

API:

- `GET /processos/{id}/arquivos/{arquivo_id}/paginas/{numero}/imagem?zoom=` (`src/lupa/api/rotas/visualizador.py`):
  só para quem vê o processo (`exige_processo`, 404 com tentativa auditada), só para páginas
  gravadas pela ingestão (arquivo em quarentena não tem página: 404), auditada como
  `pagina_vista` (com `admin_acesso_conteudo` para o administrador). Responde `image/png` com
  `Cache-Control: private, max-age=3600`, `nosniff` e o tamanho da página em pontos nos
  cabeçalhos. Origem: o objeto do arquivo no storage; num ZIP, a entrada do manifesto
  (`origem_arquivo`/`pagina_origem`, guardada pelo hash). Falha de renderização: 503 sem
  conteúdo.
- Renderização (`src/lupa/ingestao/renderizacao.py`): roda no sandbox da ingestão (processo
  filho com limites de memória, CPU e tempo, sem rede e sem variáveis `LUPA_*`). Abre o PDF com
  PyMuPDF, DESLIGA todas as camadas opcionais (OCG; `set_layer` e as configurações de interface
  de camada), recorta à `CropBox` (`page.rect`) e não desenha anotações. O PNG e o tamanho da
  página vão para um cache no storage (`renderizacao/<versão>/<chave do original>/<página>-<zoom>.png`),
  então a segunda visualização não abre o PDF.
- `GET /processos/{id}/evidencias/{evidencia_id}/bbox`: cruza `[inicio, fim)` da evidência com as
  linhas gravadas em `pagina.coordenadas` (linhas dos blocos nativos; linhas de OCR ou da fusão
  híbrida), une as caixas (pontos PDF, origem no canto superior esquerdo) e devolve a união e
  um retângulo por linha em fração da página, com arquivo, página e trecho. Página sem
  coordenadas: `uniao: null` (a tela avisa). Fecha o item pendente da Revisão 4F (seção 6, item
  2): o `bbox` é calculado sob demanda a partir dos blocos já gravados, sem migração.

Front:

- `front/src/lib/visualizador/Visualizador.svelte`: imagem da página, retângulos de destaque
  posicionados em porcentagem sobre a imagem (`geometria.ts`), navegação anterior/próxima,
  zoom (50–300%), teclado com o foco na página (setas e PageUp/PageDown, Home/End, `+`/`-`).
- `/processos/[id]/visualizador?arquivo=&pagina=&evidencia=`: com `evidencia`, busca o bbox e
  abre na página dele com o trecho citado; troca de arquivo quando há mais de um; a URL acompanha
  a página.

## Limitação registrada (texto oculto)

A imagem mostra o que o PDF desenha, sem as camadas opcionais e só dentro da `CropBox`. Assim,
texto numa camada OCG ou fora da área visível não aparece. Texto branco sobre fundo branco ou em
fonte de 1 pt também não aparece visualmente (como para quem lê o papel). Mas conteúdo que o
próprio PDF desenha visível (por exemplo, uma instrução impressa no corpo, ou texto da mesma cor
de um retângulo colorido desenhado atrás dele) aparece normalmente: a imagem não é filtro de
injeção; os alertas de saneamento da 4D continuam sendo a fonte para isso. Anotações do PDF não
são desenhadas.

## Testes

- `tests/ingestao/test_visualizador.py`: PNG privado, tamanho coerente com o zoom, evento
  `pagina_vista`, cache (segunda resposta idêntica), zoom fora do limite (422); página
  inexistente, arquivo de outro processo e usuário de outro gabinete (404, tentativa auditada);
  origem ausente (503); bbox de TODA evidência de fato do processo sintético dentro da página;
  caixas por offset em blocos nativos e linhas de OCR; renderização com OCG (a imagem com texto
  numa camada opcional é idêntica à imagem sem ele) e tamanho da `CropBox`; PDF ilegível e
  página inexistente; sandbox + cache + falha sem origem.
- `front/src/lib/processos/processos.test.ts`: geometria do destaque, zoom e navegação.
- E2E `6.6 evidência de cada fato e achado abre na página e destaca o trecho`: para cada link de
  evidência da tela de validações (todos os fatos de todos os achados), abre o visualizador,
  confere a página, o trecho e que o destaque está dentro da imagem; a imagem é `image/png` com
  `Cache-Control: private`; sem sessão, 401; teclado troca a página e `+` aumenta o zoom.

## Critério de aceite

Evidência de cada fato e achado abre na página e destaca o trecho: passando no E2E sobre o
processo sintético ingerido.

## Fora do escopo

Seleção ou cópia de texto na página (de propósito); miniaturas; destaque com precisão de
caractere dentro da linha (o retângulo cobre a linha inteira atingida); invalidação do cache de
PNG quando a versão de renderização muda (a versão está na chave; versões antigas ficam até
limpeza manual do prefixo).
