# Revisão — Etapa 4C (diagnóstico e páginas, subetapas 4C.1 a 4C.10)

21 de outubro de 2026 · revisor

## 1. Verificação executada

Imagem reconstruída e verificação completa:

```
docker compose up -d --build --wait
docker compose exec -T api bash scripts/verificar.sh
```

Resultado: ruff sem avisos, 154 arquivos formatados, mypy sem erros em 154 arquivos, 551 testes passaram, 1 pulado, 1 desmarcado (carga), cobertura 98,87%, ponta a ponta da ingestão até `concluido` (1 passou).

Conferências diretas na imagem:

- `tesseract 5.5.0` com idiomas `eng`, `osd`, `por`; SHA-256 do `por.traineddata` igual ao registrado no Dockerfile (`c4932b93…7deb`).
- Limiares do roteador em `ingestao/dados/roteador.yaml` com `versao` e `fonte`; `rotear` é função pura e conservadora (na dúvida, abstém).
- OCR roda pelo binário em subprocesso dentro do sandbox, com saída TSV, sem dependência Python nova.

Medições reproduzidas pelo revisor:

- OCR, amostra de 2 páginas por nível em cada processo, semente 7: nível `media` com CER 1,96% e 91,9% das datas encontradas literalmente (executor: 2,12% e 91,0%). Coerente.
- Diagnóstico dos dez processos nos três cenários: medição iniciada em segundo plano (a parte de ZIP leva cerca de 12 minutos); o executor relata 30/30 e a consistência de bookmarks e índice com o gabarito foi conferida na revisão da 4B. Resultado registrado em 1.1 quando concluir.

## 1.1 Diagnóstico reproduzido

Concluído: `scripts/medir_extracao.py diagnostico` nos dez processos e três cenários, 30 de 30 diagnósticos corretos, nenhum errado. Fronteiras do manifesto do ZIP e do índice batem com o gabarito (ex.: semente_01, 51 esperadas, 51 iguais). Tempo dominado pelo cenário ZIP (cerca de 30 s para 51 entradas no menor processo), confirmando o item 2 da seção 5.

## 2. Critérios de saída por subetapa

| Subetapa | Resultado | Evidência |
| --- | --- | --- |
| 4C.1 diagnóstico | ok | 30/30 nos dez processos; rota auditada de leitura |
| 4C.2 bookmarks e índice | ok | 2.825/2.825 fronteiras do índice batem com o gabarito após o deslocamento; ZIP 2.825/2.825 |
| 4C.3 sinais por página | ok | sinais no sandbox, coluna JSON na migração 0004 |
| 4C.4 roteador | ok | matriz de confusão 15.647/15.647; falso negativo perigoso 0 de 4.699 |
| 4C.5 texto nativo | ok | 10.718/10.718 páginas batem byte a byte com `texto_camada`; teste de duas colunas |
| 4C.6 OCR | ok | CER leve 1,65%, média 2,12%, forte 7,58%; datas literais 92,7%, 91,0%, 85,3%; metas definidas e registradas; fecha a pendência 4B.4 |
| 4C.7 híbridas | ok | fusão por bbox; `TEXTO_DIVERGENTE` disparada na camada manipulada; zero falsos positivos nas híbridas de referência |
| 4C.8 paralelismo | ok | processos filhos por lote, teto por job e por gabinete, revezamento a cada 400 páginas; teste de job pequeno terminando antes do grande |
| 4C.9 gravação | ok | idempotente por sha256 e versão do extrator; retry por motivo; `processo.status` atualizado |
| 4C.10 relatório de qualidade | ok | relatório em `job_ingestao.relatorio` e rota; dez processos sem página faltando; acurácia de tipo 100% no `medir.py` |

Itens herdados da revisão 4A: todos resolvidos (`verificar.ps1`, filtros de aviso, retry, `processo.status`).

## 3. Decisões do executor endossadas

- Correção de bug em `parser_pdf.py` da 4A: página sem stream de conteúdo mandava o PDF inteiro para quarentena. Afetava todos os processos de referência e foi pego pela medição. É exatamente para isso que o gabarito existe.
- Enum `CenarioArquivo.PDF_COM_BOOKMARKS_E_INDICE`, porque o cenário sintético tem os dois. Correto, e o diagnóstico continua distinguindo os casos só com um.
- `.sinteticos` montado só leitura e fora do contexto de build.

## 4. Decisão

**Aprovado.** Etapa 4D liberada.

## 5. Riscos e itens para etapas seguintes

1. **Tempo de OCR.** 882 segundos por mil páginas digitalizadas com 4 lotes de 8 páginas. Um processo de 5.000 páginas majoritariamente digitalizado leva cerca de 75 minutos. Aceitável no piloto, mas o dimensionamento do worker (quantidade de filhos, CPU) precisa de decisão antes do uso real; registrar em 4F.9.
2. **Diagnóstico de ZIP lento**: 0,8 s por entrada. Com 878 entradas, 12 minutos só para diagnosticar. Investigar na 4E (provavelmente abrir cada PDF inteiro para ler o cabeçalho; basta ler as primeiras páginas).
3. **Teto por gabinete vale por réplica de worker.** Com várias réplicas, precisa de semáforo no Redis. Fica para quando houver mais de um worker.
4. **Reprocessamento automático ao mudar a versão do extrator** e cache por sha256 entre processos ficam para 4F.8, como previsto.
5. **Imagens decorativas opacas** (logotipo JPEG) em páginas nativas levam à abstenção e custam OCR. Sem perda de conteúdo. A calibração com o Projudi (4F.10) mede a frequência.
6. **Texto fora da página e girado** só vão ao OCR; a marcação é da 4D.1.
