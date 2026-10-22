# Revisão — Etapa 4B (autos sintéticos e gabarito, subetapas 4B.1 a 4B.10)

21 de outubro de 2026 · revisor

## 1. Verificação executada

Com nenhum agente escrevendo no diretório, imagem reconstruída e verificação completa:

```
docker compose up -d --build --wait
docker compose exec -T api bash scripts/verificar.sh
```

Resultado: ruff sem avisos, 137 arquivos formatados, mypy sem erros em 137 arquivos, 476 testes passaram, 1 pulado, 1 desmarcado (carga), cobertura 99,11%, mais o passo ponta a ponta da ingestão (1 passou, sem skip). Isso cobre as Etapas 0 a 3, 4A.1, 4A e 4B juntas.

Conferência direta dos processos de referência (`.sinteticos/referencia/semente_01`):

- Três cenários presentes: `zip_por_peca/autos.zip`, `pdf_indice/autos.pdf`, `pdf_liso/autos.pdf`, cada um com seu `gabarito.json`.
- Gabarito: 51 peças, 196 páginas, 23 eventos; composição com 168 digitalizadas, 14 híbridas de corpo, 7 vazias, 4 nativas, 2 híbridas de assinatura, 1 capa.
- PDF liso: 196 páginas, zero bookmarks. PDF com índice: 198 páginas (índice no início), 51 bookmarks, um por peça. Diagnóstico esperado distinto, conteúdo igual.
- Offsets do primeiro evento conferidos: `texto[inicio:fim] == trecho`.
- `resultado_esperado` traz os três achados com os mesmos `valores` que o motor produz, calculados pelo próprio motor a partir dos eventos do gabarito. O processo 01 tem tempestividade e prescrição `conforme` e revisão da preventiva `atencao` (intervalo de 145 dias).
- `.sinteticos/` está no `.gitignore`. Pasta com 4,7 GB.

## 2. Critérios de saída por subetapa

| Subetapa | Resultado | Evidência |
| --- | --- | --- |
| 4B.1 esquema do gabarito | ok | pydantic com `versao_esquema`, `processo`, `pecas`, `paginas`, `eventos`, `resultado_esperado`, `arquivos`, `injecoes` |
| 4B.2 textos por tipo de peça | ok | 16 templates; datas dos textos são as do gabarito |
| 4B.3 renderização nativa | ok | teste de `get_text()` contra gabarito e offsets |
| 4B.4 digitalizada | ok com ressalva | ruído, rotação, resolução e contraste em três níveis; CER de referência por OCR não medido porque não há Tesseract na imagem; fica para 4C.6 |
| 4B.5 híbridas e vazias | ok | enum `Composicao` com seis valores, gabarito por página |
| 4B.6 carimbos e marcas | ok | presentes em todos os dez processos |
| 4B.7 três cenários | ok | conferido no processo 01 |
| 4B.8 injeções por vetor | ok | 10 variantes em `.sinteticos/injecao/`, uma por vetor mais uma combinada, cada uma com objetivo e vetor |
| 4B.9 dez processos de referência | ok | 196 a 4.988 folhas, misturas de 86% digitalizado a 89% nativo, 12 minutos de geração no total |
| 4B.10 harness de medição | ok | `scripts/medir.py` com JSON e Markdown; testes com saída igual e com erros injetados |

## 3. Decisões do executor endossadas

- Enum `Composicao` separado de `TipoPagina`: o gabarito precisa distinguir híbrida de corpo e de assinatura, e capa de vazia, enquanto o roteador da 4C só decide entre nativa, OCR e vazia. É a separação correta entre "o que a página é" e "o que fazer com ela".
- Dois textos por página: o visível, onde os offsets apontam, e o que `get_text()` devolve. Permite medir o roteador e o saneamento de texto oculto.
- CPFs inválidos pelo dígito e CNJ em tribunal inexistente com faixa reservada: garante que nenhum dado sintético colide com dado real.
- Resultado esperado calculado pelo motor: evita manter duas lógicas; o gabarito testa a extração, não o motor, que já tem seus testes.

## 4. Decisão

**Aprovado.** Etapa 4C liberada.

## 5. Itens para etapas seguintes

1. **Tesseract na imagem** (4C.6) e, com ele, a medição do CER de referência por nível de degradação que ficou pendente em 4B.4.
2. **Múltiplos réus e concurso de crimes** não são gerados, embora o gabarito suporte. Fica para a rodada do catálogo que precisar disso.
3. **Tabelas como imagem, vetor RTL, injeção cruzada entre documentos e layout em duas colunas** ficaram de fora. O layout em duas colunas afeta a ordem de leitura e deve entrar antes da 4E (fronteiras); os demais podem esperar.
4. **Variantes pequenas saem com 50 a 60 páginas** quando há muitas revisões de preventiva. Sem impacto nas medições.

## 6. Pendência para Victor

A pasta `.sinteticos/` tem 4,7 GB e está dentro do OneDrive, então vai sincronizar e consumir cota. Duas opções: excluir a pasta da sincronização nas configurações do OneDrive, ou definir `LUPA_SINTETICOS_DIR` para um caminho fora do OneDrive e regerar com `python scripts/gerar_autos.py referencia` (12 minutos). Sem decisão, fica como está.
