# Relatório da Etapa 4B.5 — Páginas híbridas, vazias e capas

20 de outubro de 2026 · agente executor da 4B

## O que foi feito

- `hibrida_corpo`: cabeçalho e rodapé nativos, corpo em imagem degradada (sem rotação).
- `hibrida_assinatura`: texto nativo, bloco de assinatura eletrônica em imagem (só em folhas que
  têm assinatura; nas outras vira `hibrida_corpo`).
- `vazia`: verso em branco ao fim de algumas peças (chance configurável), pertencente à peça.
- `capa`: autuação (peça 1, tipo `outros`) com número, classe, partes, assunto e data.
- O gabarito marca cada folha com `tipo`, `composicao` e elementos; o teste exige todas as
  composições no processo de teste e confere imagem e camada de cada uma.

## O que ficou de fora

- Tabela como imagem (a assinatura cobre o caso de bloco localizado em imagem).

## Como rodar os testes

```bash
docker compose exec api bash scripts/verificar.sh
# só a 4B, no host:
.venv/Scripts/python -m pytest tests/sinteticos --confcutdir=tests/sinteticos -o addopts="" --cov=lupa.sinteticos
```

Saída resumida (host, venv): `93 passed`; cobertura de `lupa.sinteticos` 99% (1.235 instruções, 4 não
cobertas). `ruff check`, `ruff format --check` e `mypy --strict` limpos em `src/lupa/sinteticos` e
`tests/sinteticos`. Resultado do `verificar.sh` completo: ver RELATORIO-ETAPA-4B.10.md.
