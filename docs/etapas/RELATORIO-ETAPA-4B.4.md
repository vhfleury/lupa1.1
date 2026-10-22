# Relatório da Etapa 4B.4 — Renderização digitalizada

20 de outubro de 2026 · agente executor da 4B

## O que foi feito

- A folha é desenhada numa página auxiliar, rasterizada em cinza (`get_pixmap`) na resolução do
  nível, degradada (contraste, deslocamento de brilho, ruído gaussiano, rotação, desfoque leve de
  scanner) e inserida como JPEG numa folha sem camada de texto.
- Níveis: `leve` 300 DPI, ruído σ 6, até ±1°; `media` 200 DPI, σ 14, até ±2°; `forte` 150 DPI, σ 24,
  até ±3°, contraste 0,55–0,75. Proporção sorteada 40/40/20. Nível, DPI e rotação aplicada ficam
  no gabarito.
- Testes: digitalizadas sem texto e com imagem; DPI e rotação dentro do nível.

## Decisões não previstas

- Desempenho: o ruído vem de um campo pré-calculado por nível, recortado em posição sorteada
  (gerar ruído novo por folha custava três quartos do tempo); o JPEG usa qualidade 40–45 com
  desfoque de 0,7 px. Uma folha digitalizada pesa de 150 a 300 KB.
- `numpy` foi acrescentado às dependências (ruído), junto com `pymupdf` e `pillow`.

## O que ficou de fora

- **CER de OCR de referência por nível**: não há Tesseract no host nem na imagem (`which tesseract`
  vazio nos dois), e instalar pacote de sistema muda o `Dockerfile`, que não é desta etapa. O
  harness (4B.10) já mede CER por nível de degradação; a meta e a medição ficam para a 4C.6, que
  instala o Tesseract.

## Como rodar os testes

```bash
docker compose exec api bash scripts/verificar.sh
# só a 4B, no host:
.venv/Scripts/python -m pytest tests/sinteticos --confcutdir=tests/sinteticos -o addopts="" --cov=lupa.sinteticos
```

Saída resumida (host, venv): `93 passed`; cobertura de `lupa.sinteticos` 99% (1.235 instruções, 4 não
cobertas). `ruff check`, `ruff format --check` e `mypy --strict` limpos em `src/lupa/sinteticos` e
`tests/sinteticos`. Resultado do `verificar.sh` completo: ver RELATORIO-ETAPA-4B.10.md.
