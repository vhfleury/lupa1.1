# Relatório da Etapa 4C.4 — Roteador de páginas

## O que foi feito

- `src/lupa/ingestao/roteador.py`: `rotear(sinais) -> TipoPagina | None`, função pura; None é abstenção (OCR integral + texto nativo guardado + fusão).
- Limiares em `src/lupa/ingestao/dados/roteador.yaml` (`versao: "1"`, `fonte` descrita). Regras: `vazia` (sem tinta, sem imagem opaca, ≤ 3 caracteres); `ocr` (imagem opaca ≥ 85% e ≤ 20 caracteres); `nativa` (imagem opaca ≤ 0,5%, ≥ 20 caracteres, fragmentação ≤ 0,5, U+FFFD ≤ 2%, nenhum caractere invisível); o resto se abstém.

## Decisões não previstas

- **Capa mapeada para `nativa`**, não `vazia`: o gabarito 4B marca a capa como `TipoPagina.NATIVA` (tem 400+ caracteres de camada de texto); rotear como vazia descartaria esse texto.
- **Digitalização em branco não é `vazia`**: na primeira calibração 53 páginas digitalizadas de contraste baixo saíram com tinta < limiar; agora `vazia` exige ausência de imagem opaca e a página vai ao OCR (que devolve `vazia` se não ler nada).

## Comandos e saída

```
docker compose run --rm api python scripts/medir_extracao.py roteador
```

## Matriz de confusão (dez processos, cenário `pdf_liso`, 15.647 folhas)

| Gabarito \ Roteador | nativa | ocr | vazia | abstenção | Total |
|---|---|---|---|---|---|
| nativa | **10.708** | 0 | 0 | 0 | 10.708 |
| capa | **10** | 0 | 0 | 0 | 10 |
| digitalizada | 0 | **3.426** | 0 | 0 | 3.426 |
| hibrida_corpo | 0 | 0 | 0 | **1.190** | 1.190 |
| hibrida_assinatura | 0 | 0 | 0 | **83** | 83 |
| vazia | 0 | 0 | **230** | 0 | 230 |

Corretos pelo mapeamento (nativa→nativa; digitalizada→ocr; híbrida→ocr ou abstenção; vazia→vazia; capa→nativa): **15.647/15.647**.

## Critério

| Critério | Evidência |
|---|---|
| Matriz nos dez processos | tabela acima |
| Falso negativo perigoso (digitalizada ou híbrida roteada nativa) < 1% | **0 de 4.699 (0,00%)** |

Limitação: os processos de referência não têm imagens opacas decorativas (logotipo em JPEG); num PDF real elas levam a página nativa à abstenção. Custo: OCR a mais, nunca conteúdo perdido. A calibração com o Projudi (4F.10) mede isso.
