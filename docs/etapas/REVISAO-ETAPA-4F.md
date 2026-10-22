# Revisão — Etapa 4F (eventos e ponta a ponta, subetapas 4F.1 a 4F.10)

21 de outubro de 2026 · revisor

## 1. Verificação executada

Imagem reconstruída, banco em `0006 (head)` (sem migração nova), verificação completa:

```
docker compose up -d --build --wait
docker compose exec -T api bash scripts/verificar.sh
```

Resultado: ruff sem avisos, 204 arquivos formatados, mypy sem erros em 204 arquivos, 697 testes passaram, 1 pulado, 1 desmarcado, cobertura 98,72%, ponta a ponta (1 passou), regressão de injeção (2 passaram, recall 1,0, falso positivo 0).

Reproduções do revisor:

- Medição de eventos em `semente_01/pdf_liso` a partir da extração do volume `lupa_medicao4e`: eventos com precisão 1,0 e recall 1,0 (23 de 23), datas 1,0 (20 de 20), zero fatos sem evidência, zero datas rejeitadas, 3 achados iguais ao esperado.
- `scripts/calibrar.py` sobre `semente_01/pdf_liso/autos.pdf`: gerou relatório Markdown e JSON com as quatro seções (diagnóstico e páginas, índice de peças, eventos com evidência, achados). O nome do réu não aparece no relatório; os réus aparecem como `REU-01`. O nome do defensor aparece no trecho de uma certidão de intimação, o que é esperado e documentado pelo executor.

## 2. Critérios de saída por subetapa

| Subetapa | Resultado | Evidência |
| --- | --- | --- |
| 4F.1 padrões de data | ok | `datas.py`; suíte de formatos; datas impossíveis rejeitadas; ano de 2 dígitos com pivô 50 e confiança 0,8 |
| 4F.2 extratores por tipo de peça | ok | `eventos/` com `eventos.yaml` e `tipos_penais.yaml` (marcado "a confirmar pelo gabinete") |
| 4F.3 evidência obrigatória | ok | 0 fatos sem evidência nos 30 arquivos; 0 trechos não literais |
| 4F.4 validação cruzada | ok | data inexistente na página rejeitada e logada sem conteúdo; conflitos viram `verificar` |
| 4F.5 réus e pseudonimização | ok | `REU-01` em fatos e achados; nome e CPF só em `reu_identidade`; trecho de evidência recortado para não conter nome ou CPF do réu; teste varre fatos, achados, auditoria e logs |
| 4F.6 gravação | ok | id por chave natural (processo, tipo, valor, evidência); reprocessar não duplica; fatos anotados ou corrigidos por pessoa são preservados |
| 4F.7 catálogo | ok | achados gravados ao fim da ingestão; `GET /processos/{id}/achados` auditada |
| 4F.8 cache | ok | segundo upload do mesmo arquivo em 4 a 47 s; cache por (sha256, versão do extrator) dentro do gabinete, nunca entre gabinetes |
| 4F.9 ponta a ponta | ok | datas 99,5% (399/401) pelo worker e 99,26% (807/813) nos 30 arquivos; eventos precisão 99,3% e recall 98,0%; achados iguais ao esperado 86,7% (90% só no resultado); tempo 35,8 s/mil nativo, 912 s/mil digitalizado |
| 4F.10 calibração | ok como roteiro | `docs/calibracao-projudi.md` e `scripts/calibrar.py` prontos e testados; execução real espera o arquivo do Projudi |

Metas do roteiro: datas ≥ 99% atendida; zero fato sem evidência atendida.

## 3. Leitura das métricas

- Todas as datas erradas e todos os achados divergentes vêm de páginas digitalizadas com degradação forte (sementes 04, 05 e 09). O erro de OCR está escrito no texto, então a reconferência literal não o pega. É a limitação prevista na 4C.6 e o motivo pelo qual o guia do assessor pede conferência manual de datas em páginas escaneadas.
- Achados iguais ao esperado em 86,7% parece baixo, mas o número compara resultado e valores completos; só no resultado é 90%, e as diferenças são datas com dígito trocado que levam a `verificar`, não a conclusão errada. Nenhum achado afirmou algo falso.
- Ponta a ponta com OCR real só em duas sementes; as demais reaproveitaram as páginas do volume da 4E, regravadas com a versão corrente do extrator para o cache aceitar. O executor documentou exatamente isso. Diagnóstico, índice, eventos e achados rodaram de verdade. Aceitável, mas a medição plena com OCR dos dez deve ser repetida antes do piloto, de preferência num worker dimensionado.

## 4. Decisões do executor endossadas

- OCR só de detecção nas imagens de páginas nativas com área acima de 2%, gerando flag sem entrar no texto. Fecha o item `imagem_com_texto` da revisão 4D com custo de 21 a 27 s por mil páginas. Subiu a versão do extrator de páginas para `4f.0`, o que invalida o cache antigo; correto.
- Trecho de evidência recortado para não conter nome nem CPF do réu. Mantém a rastreabilidade (a página continua apontada) e cumpre a pseudonimização nos derivados.
- Correção de `logging.py`: `configurar_logging` prendia o `sys.stdout` do momento. Resolve o problema de saída fechada na origem, como pedido.

## 5. Decisão

**Aprovado.** Etapa 4 (4A a 4F) concluída.

## 6. Itens para as etapas 5 a 8

1. Pena aplicada não é extraída porque não há `TipoFato` para ela. Entra quando o catálogo ganhar a prescrição pela pena aplicada (revisão 2, item 3).
2. Réu qualificado fora da denúncia, cache por entrada de ZIP e `bbox` da evidência ficaram de fora. O `bbox` é necessário para o visualizador da Etapa 6.6 destacar o trecho; a 6.6 deve pedir à ingestão a coordenada a partir dos blocos já gravados em `pagina`.
3. Upload pela rota HTTP não foi exercitado no ponta a ponta dos dez processos; a Etapa 6.4 cobre com Playwright.
4. O banco de desenvolvimento ficou com cinco gabinetes sintéticos das execuções. A seção 6 do roteiro de calibração descreve a limpeza; executar antes do piloto.
5. `tipos_penais.yaml` e `eventos.yaml` são dados jurídicos a confirmar pelo gabinete, como os calendários da Etapa 2.
