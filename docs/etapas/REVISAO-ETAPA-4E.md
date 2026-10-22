# Revisão — Etapa 4E (fronteiras, peças e índice, subetapas 4E.0 a 4E.10)

21 de outubro de 2026 · revisor

## 1. Verificação executada

Imagem reconstruída, banco em `0006 (head)`, verificação completa:

```
docker compose up -d --build --wait
docker compose exec -T api bash scripts/verificar.sh
```

Resultado: ruff sem avisos, 178 arquivos formatados, mypy sem erros em 178 arquivos, 616 testes passaram, 1 pulado, 1 desmarcado, cobertura 98,68%, ponta a ponta (1 passou), regressão de injeção (2 passaram, recall 1,0, falso positivo 0).

Reproduções do revisor:

- `sinais.py` corrigido: `int(span["color"]) & BRANCO == BRANCO`; teste `test_texto_branco_conta_como_invisivel_com_alfa_do_pymupdf` presente.
- Diagnóstico dos dez processos nos três cenários: 64 segundos no total, contra cerca de 15 minutos antes da correção do ZIP. Resultados idênticos.
- Medição de peças em `semente_01/pdf_liso` a partir da extração guardada no volume `lupa_medicao4e`: zero erros de fronteira, tipo, origem e data; 51 de 51 datas com evidência; 1 fronteira fraca; índice montado em 0,84 s.

## 2. Critérios de saída por subetapa

| Subetapa | Resultado | Evidência |
| --- | --- | --- |
| 4E.0 tarefas prévias | ok | máscara de alfa em `sinais.py`; matriz do roteador idêntica (15.647/15.647); diagnóstico de ZIP de 0,91 s para 0,042 s por entrada (inspeção em grupos de 32 num só filho do sandbox); layout em duas colunas no gerador com 16/16 páginas na ordem certa |
| 4E.1 sinais de fronteira | ok | `sinais_fronteira.py`, coluna `pagina.sinais_fronteira` na migração 0006 |
| 4E.2 classificador por regras | ok | precisão e recall 100% no `pdf_liso` dos dez processos (2.825 fronteiras); 22 fracas, todas corretas; meta ≥ 95% |
| 4E.3 uso do índice | ok | índice é a fonte quando existe; 22 divergências em 2.825 (0,78%), todas `origem_sem_sinal_forte` em fronteiras fracas; índice errado de propósito gera divergência dos dois lados |
| 4E.4 tipo da peça | ok | 100% nos três cenários; nenhuma peça inventada (2.825 = 2.825) |
| 4E.5 origem | ok | 99,6%; 12 erros são `terceiro → desconhecida` por assinatura perdida no OCR forte, nunca atribuição errada |
| 4E.6 data da peça | ok | 98,8% com evidência; 22 dígitos trocados pelo OCR e 12 ausentes; nenhuma data inventada |
| 4E.7 índice | ok | `indice.py`, uma linha por peça, `GET /processos/{id}/indice` auditada e isolada por gabinete |
| 4E.8 reclassificação manual | ok | tipo, origem, divisão e união com `substitui_peca_id`, `vigente`, evento `peca_reclassificada` |
| 4E.9 medição | ok | tabela por processo e cenário em `RELATORIO-ETAPA-4E.9.md`, conferida |
| 4E.10 índice na API | ok | resumo de flags por peça no índice (pendência da 4D fechada) |

## 3. Observações sobre as métricas

- Os dez processos não têm reinício de numeração nem cabeçalho novo entre peças; esses sinais estão implementados e testados só com páginas fabricadas. A calibração com o Projudi (4F.10) é onde eles serão exercitados de verdade.
- `tipo_data` coincide com o gabarito em 31%, porque o gabarito rotula como protocolo ou juntada datas que no texto só aparecem na assinatura. Não é critério; vale ajustar o gabarito na 4F ou aceitar a semântica do extrator.
- Os erros de data e origem vêm todos do nível forte de degradação do OCR. São os mesmos casos que o relatório da 4C.6 previu.

## 4. Decisão

**Aprovado.** Etapa 4F liberada.

## 5. Itens para a 4F

1. Decisão sobre `imagem_com_texto` em página nativa (revisão 4D, seção 6, item 2).
2. Testes de API da 4E reprocessam um PDF em cada um dos 4 testes, 45 s cada. Reaproveitar a extração numa fixture de módulo para encurtar a suíte, que já leva 7 minutos.
3. Um teste novo reconfigura o logging porque um teste anterior deixa a saída fechada. Encontrar o teste que fecha e corrigir na origem.
4. O volume `lupa_medicao4e` guarda a extração dos dez processos; a 4F pode reaproveitá-lo para a medição ponta a ponta sem refazer os 55 minutos de OCR.
