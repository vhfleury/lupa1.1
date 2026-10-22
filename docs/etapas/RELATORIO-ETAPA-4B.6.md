# Relatório da Etapa 4B.6 — Carimbos, marcas e rodapés

20 de outubro de 2026 · agente executor da 4B

## O que foi feito

- Carimbo vermelho "JUNTADA / Fls. N" em PNG com transparência, girado, sobre o corpo: na primeira
  folha do recebimento (garante presença em todo processo) e em cerca de 12% das demais folhas.
- Marca d'água diagonal "CÓPIA - DOCUMENTO SINTÉTICO" (texto cinza claro, 45°) em laudos, juntadas
  e termos; nas folhas com imagem ela vai dentro da imagem.
- Rodapé com "Documento assinado digitalmente. Código de autenticação: <40 hex>" em toda folha.
- Cabeçalho idêntico em todas as peças (teste confere que a primeira linha da primeira folha de
  todas as peças é a mesma).
- Elementos marcados por folha em `elementos`; presença nos dez processos de referência conferida
  no relatório 4B.9.

## Decisões não previstas

- A marca d'água fica na camada de texto (no fim de `get_text()`), não em `texto`: é ruído que a
  extração precisa ignorar.

## Como rodar os testes

```bash
docker compose exec api bash scripts/verificar.sh
# só a 4B, no host:
.venv/Scripts/python -m pytest tests/sinteticos --confcutdir=tests/sinteticos -o addopts="" --cov=lupa.sinteticos
```

Saída resumida (host, venv): `93 passed`; cobertura de `lupa.sinteticos` 99% (1.235 instruções, 4 não
cobertas). `ruff check`, `ruff format --check` e `mypy --strict` limpos em `src/lupa/sinteticos` e
`tests/sinteticos`. Resultado do `verificar.sh` completo: ver RELATORIO-ETAPA-4B.10.md.
