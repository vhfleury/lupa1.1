# Calibração com o processo real do Projudi (Etapa 4F.10)

21 de outubro de 2026 · roteiro pronto para executar; **o arquivo do Projudi ainda não existe**.

Este documento é o roteiro do dia em que o primeiro processo real chegar: o que rodar, o que medir,
o que comparar com a conferência manual do assessor e onde registrar. A seção final ("Registro")
fica vazia até lá; é ela que fecha o critério da 4F.10 ("o que acertou, o que errou e o que mudou").

## 0. Antes de começar

- O arquivo é dado real de processo: **nunca** entra no repositório, em `.sinteticos/`, em issue,
  em log nem em relatório versionado. Ele fica num diretório fora do projeto, montado só leitura
  no contêiner, e o relatório gerado fica dentro do contêiner (`/tmp`), lido por quem tem acesso
  ao gabinete.
- Processo sigiloso não entra no piloto (Etapa 1); confirmar antes.
- Banco e storage: rodar contra o ambiente de desenvolvimento (o script cria um gabinete de
  calibração próprio, isolado por RLS dos demais). Depois da conferência, apagar o gabinete de
  calibração e o objeto no storage (passo 6).
- Imagem atualizada e verificação verde: `docker compose up -d --build --wait` e
  `docker compose exec api bash scripts/verificar.sh`.

## 1. Disponibilizar o arquivo ao contêiner (sem copiar para o repositório)

Criar um `docker-compose.override.yml` **local, não versionado** que monta o diretório do
arquivo só leitura no `api`:

```yaml
services:
  api:
    volumes:
      - /caminho/fora/do/projeto/projudi:/dados/projudi:ro
```

`docker compose up -d --wait api` e conferir: `docker compose exec api ls -l /dados/projudi`.

## 2. Rodar a pipeline e gerar o relatório de diagnóstico

```bash
docker compose exec api python scripts/calibrar.py /dados/projudi/autos.pdf \
    --saida /tmp/calibracao --titulo "Projudi 1"
```

O script (`scripts/calibrar.py`, código em `lupa/ingestao/calibracao.py`):

1. cria o gabinete e o processo de calibração (`Gabinete de calibração xxxxxx`);
2. lacra o arquivo no storage e roda o worker (`processar_job`) sem fatiar: validação no
   sandbox, diagnóstico, páginas (roteador, texto nativo, OCR, fusão, saneamento), índice de
   peças, eventos e achados;
3. grava `/tmp/calibracao/relatorio.md` (para conferência) e `relatorio.json` (bruto).

Ler o relatório sem tirá-lo do contêiner: `docker compose exec api cat /tmp/calibracao/relatorio.md`
(ou abrir um shell no contêiner). Se for preciso entregar ao assessor, imprimir na máquina do
gabinete; não anexar a e-mail nem a ferramenta externa.

O relatório tem quatro seções, com a coluna **Confere?** em branco para o assessor:

| Seção | Conteúdo |
| --- | --- |
| 1. Diagnóstico e páginas | cenário (ZIP por peça, bookmarks, índice, liso), total de páginas, fronteiras da origem, páginas por tipo, abstidas, CER estimado, flags de saneamento, tempo e tempo por mil páginas |
| 2. Peças | uma linha por peça: páginas, tipo, origem, data e tipo da data, confiança, marcas (fronteira fraca, divergência, tipo ambíguo, origem desconhecida, data ausente) |
| 3. Eventos | um fato por linha: página, tipo, valor, confiança e o trecho literal da evidência |
| 4. Achados | as três validações com resultado e explicação |

## 3. Conferência manual do assessor

O assessor abre os autos no Projudi ao lado do relatório e preenche a coluna "Confere?" com
`sim`, `não (correto: ...)` ou `?`. Instruções a passar ao assessor:

1. **Diagnóstico**: o cenário bate com o que o Projudi exportou (um PDF por movimento em ZIP,
   PDF único com marcadores, PDF único com índice, PDF liso)? O total de páginas bate?
2. **Peças**: para cada linha, a peça começa nessa página? Falta alguma peça entre duas linhas
   (fronteira perdida)? O tipo e a origem estão certos? A data é a da assinatura, do protocolo ou
   da juntada, como dita a coluna "Tipo da data"?
3. **Eventos**: o valor está no trecho e o trecho é o lugar certo dos autos? Falta algum evento
   que o assessor encontra (recebimento da denúncia, publicação da sentença, intimações do
   defensor, do réu e do MP, interposição do recurso, decretação e revisões da preventiva, pena
   máxima, data do fato, nascimento do réu)? Anotar página e data dos que faltam.
4. **Achados**: o resultado de cada validação é o que o assessor concluiria? Se não, qual fato
   faltou ou está errado?

Tempo estimado: 1 a 2 horas para um processo de 300 a 500 páginas.

## 4. O que medir

A partir da planilha do assessor (as colunas "Confere?"):

| Medida | Como calcular | Referência sintética (4E.9 / 4F.9) |
| --- | --- | --- |
| Diagnóstico certo | sim/não | 30/30 |
| Fronteira: precisão | peças com início certo / peças do relatório | 100% |
| Fronteira: recall | peças com início certo / peças que o assessor contou | 100% |
| Tipo de peça | tipos certos / peças com início certo | 100% |
| Origem | origens certas / peças com início certo | 99,6% |
| Data da peça | datas certas / peças com início certo | 98,8% |
| Eventos: precisão | fatos certos (tipo, valor, página) / fatos do relatório | 99,3% |
| Eventos: recall | fatos certos / fatos que o assessor encontrou | 98,0% |
| Datas: precisão | só os fatos de data | 99,3% (meta ≥ 99%) |
| Achados iguais | achados com o mesmo resultado do assessor / 3 | 86,7% (90% no resultado) |
| Tempo por mil páginas | seção 1 do relatório | ver `RELATORIO-ETAPA-4F.9.md` |

Também registrar, sem conteúdo: quantidade de páginas nativas, digitalizadas e híbridas; páginas
abstidas; flags de saneamento por tipo; frequência de imagens decorativas opacas em páginas
nativas (risco 5 da revisão 4C); sinais de fronteira que dispararam (reinício de numeração,
cabeçalho novo, que os sintéticos não exercitam).

## 5. O que ajustar e como

Cada erro vira uma de três ações, sempre com versão nova e teste com texto **sintético** que
reproduz o padrão (nunca o trecho real):

| Erro | Onde ajustar | Versão a subir |
| --- | --- | --- |
| Fronteira perdida ou a mais | `ingestao/dados/fronteiras.yaml`, `titulos_peca.yaml` | `versao` do YAML |
| Tipo ou origem errados | `ingestao/dados/classificacao.yaml`, `titulos_peca.yaml` | `versao` do YAML |
| Data da peça errada | `ingestao/data_peca.py` (regras) | `indice.versoes()` |
| Evento faltando ou errado | `ingestao/dados/eventos.yaml` (gatilho, janela, tipos de peça) | `versao` de `eventos.yaml` |
| Formato de data novo | `ingestao/datas.py` (+ caso em `tests/ingestao/test_datas.py`) | `versao` de `eventos.yaml` |
| Pena de tipo penal ausente | `ingestao/dados/tipos_penais.yaml` (a confirmar pelo gabinete) | `versao` de `tipos_penais.yaml` |
| Roteamento de página | `ingestao/dados/roteador.yaml` | `VERSAO_EXTRATOR` |

Mudar só `eventos.yaml` ou `tipos_penais.yaml` reprocessa só os eventos (`processar_eventos`;
páginas e peças ficam). Depois de ajustar: `scripts/verificar.sh`, a medição sintética
(`scripts/medir_extracao.py eventos --destino /m` com o volume `lupa_medicao4e`) para garantir
que nada regrediu, e de novo o passo 2 com o arquivo real.

## 6. Limpeza

Depois de registrar: apagar os processos do gabinete de calibração (as chaves estrangeiras
compostas apagam em cascata arquivo, job, páginas, peças, evidências, fatos, achados e réus),
depois o usuário e o gabinete, o relatório e o objeto do storage, e remover o override do compose:

```bash
docker compose exec db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "
  DELETE FROM processo WHERE gabinete_id IN
    (SELECT id FROM gabinete WHERE nome LIKE 'Gabinete de calibração %');
  DELETE FROM usuario WHERE gabinete_id IN
    (SELECT id FROM gabinete WHERE nome LIKE 'Gabinete de calibração %');
  DELETE FROM gabinete WHERE nome LIKE 'Gabinete de calibração %';"
docker compose exec api rm -rf /tmp/calibracao
```

Conferir antes, com `SELECT count(*)` nas mesmas condições, que só o gabinete de calibração é
afetado.

O objeto no MinIO fica sob o prefixo do gabinete (`<gabinete_id>/...`); remover pelo console
do MinIO (porta 9001, só localhost).

## 7. Teste do roteiro com processo sintético

O roteiro foi executado com o processo sintético `semente_01` (cenário `pdf_indice`) em
21/10/2026; saída resumida em `docs/etapas/RELATORIO-ETAPA-4F.10.md`. O caminho de código é o
mesmo testado em `tests/ingestao/test_calibracao.py`.

## Registro (preencher no dia)

| Data | Arquivo (hash, sem nome) | Páginas | Diagnóstico | Fronteira P/R | Tipo | Origem | Data | Eventos P/R | Datas P | Achados | Tempo/mil |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| | | | | | | | | | | | |

### O que acertou

(preencher)

### O que errou

(preencher: página, tipo do erro, padrão sintético que o reproduz)

### O que mudou

(preencher: arquivo de regra, versão antiga → nova, teste acrescentado, efeito na medição
sintética)
