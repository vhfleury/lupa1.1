# Revisão — Etapa 4D (saneamento contra injeção, subetapas 4D.1 a 4D.10)

21 de outubro de 2026 · revisor

## 1. Verificação executada

Imagem reconstruída, banco de desenvolvimento migrado para `0005 (head)` e verificação completa:

```
docker compose up -d --build --wait
docker compose exec -T api alembic -c src/lupa/migrations/alembic.ini upgrade head
docker compose exec -T api bash scripts/verificar.sh
```

Resultado: ruff sem avisos, 165 arquivos formatados, mypy sem erros em 165 arquivos, 588 testes passaram, 1 pulado, 1 desmarcado, cobertura 98,66%, ponta a ponta da ingestão (1 passou), regressão de injeção sobre o corpus (2 passaram, 161 s) com métricas gravadas:

```
recall 1.0 (16 de 16 injeções textuais)   falso_positivo 0.0 (0 de 196 páginas de semente_01)
versões: saneamento 4d.1, homoglifos 1, padroes_instrucao 1, idiomas 1, densidade 1
```

Metas da 4D.5 (recall ≥ 90%, falso positivo ≤ 5%) atendidas com folga.

## 2. Critérios de saída por subetapa

| Subetapa | Resultado | Evidência |
| --- | --- | --- |
| 4D.1 texto oculto | ok | `oculto.py` separa texto branco, fonte pequena e fora da página em `trechos_ocultos`, fora de `pagina.texto`; flag `texto_oculto` |
| 4D.2 metadados e anotações | ok | hash dos valores em `diagnostico_arquivo.metadados_descartados`; instrução em XMP ou anotação nunca entra em `texto`; flag `metadado_suspeito` |
| 4D.3 normalização Unicode | ok | `texto_normalizado` com mapa de offsets recalculável; homóglifos em YAML; flag `homoglifos` |
| 4D.4 blocos codificados | ok | marcação sem remoção do original; heurística de rodapé tolerante a OCR corrigiu 53 falsos positivos iniciais |
| 4D.5 padrões de instrução | ok | YAML versionado pt/en por categoria; recall 100%, falso positivo 0% |
| 4D.6 idioma inesperado | ok | heurística por palavras funcionais; latim curto não marca; limitação de 8 palavras documentada |
| 4D.7 densidade anômala | ok | limiar por tipo em YAML |
| 4D.8 origem por trecho | ok | `origem_da_pagina` lê `peca.origem` com fallback `desconhecida` |
| 4D.9 hash por trecho | ok | consistente com `Evidencia.hash_trecho`; estável entre original e normalizado |
| 4D.10 painel e regressão | ok | rota `/alertas`, seção `saneamento` no relatório do job, passo no `verificar.sh` e `.ps1` |

## 3. Defeito encontrado na 4C, confirmado pelo revisor

O sinal `caracteres_invisiveis` em `sinais.py` compara `int(span["color"]) == 0xFFFFFF`. Conferido no contêiner com PyMuPDF 1.25.1: texto branco é reportado como `-0x1` (0xFFFFFFFF com sinal) e texto preto como `-0x1000000`. A comparação nunca é verdadeira para branco, então o roteador não leva ao OCR uma página nativa cujo único sinal suspeito é texto branco. O módulo `oculto.py` da 4D usa a máscara `& 0xFFFFFF` e funciona, então a injeção em texto branco é detectada e removida de `pagina.texto` mesmo assim. O efeito prático é só a perda da comparação de camadas nesses casos. Correção: aplicar a mesma máscara em `sinais.py`, reexecutar a matriz de confusão do roteador e registrar se algo mudou. Atribuída à Etapa 4E como primeira tarefa.

## 4. Decisões do executor endossadas

- Metadados descartados em `diagnostico_arquivo` porque `arquivo` é imutável por trigger. Correto.
- Mapa de offsets recalculado em vez de gravado: evita coluna grande e mantém `texto` como única fonte.
- Ajustes nos testes da 4C: texto oculto agora é tratado antes da fusão com o OCR, e os testes passaram a esperar `texto_oculto` em vez de `texto_divergente`. É a semântica certa.

## 5. Decisão

**Aprovado.** Etapa 4E liberada.

## 6. Itens para etapas seguintes

1. Corrigir `sinais.py` (seção 3) e reexecutar a calibração do roteador (4E, primeira tarefa).
2. `imagem_com_texto`: a instrução dentro de imagem em página nativa não gera texto nem alerta, porque a página não vai ao OCR. Decisão a registrar: ou toda imagem com área relevante numa página nativa passa por OCR só para detecção (custo), ou aceita-se que a instrução em imagem só importa quando a página inteira é digitalizada. Como o agente da Etapa 5 nunca vê imagens, o risco real é baixo; registrar no `docs/ingestao.md` e decidir na 4F.
3. Texto girado e fundo não branco não são tratados como ocultos. Limitação documentada.
4. Resumo de flags por peça depende da 4E.
5. A nota do executor sobre ter instalado `ruff` num venv temporário por PyPI para formatar no host: sem impacto no repositório, mas o fluxo recomendado é formatar dentro do contêiner.
