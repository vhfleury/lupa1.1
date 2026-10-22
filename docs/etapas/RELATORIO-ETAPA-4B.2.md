# Relatório da Etapa 4B.2 — Textos por tipo de peça

20 de outubro de 2026 · agente executor da 4B

## O que foi feito

- 16 templates `.txt` em `src/lupa/sinteticos/templates/` (denúncia, recebimento, decisão de prisão,
  revisão de prisão, laudo, termo de depoimento, sentença, certidões de publicação e de intimação
  do MP, da defesa e do réu, recurso, contrarrazões, acórdão, juntada e um banco de parágrafos de
  enchimento). Sintaxe: `string.Template` (`$var`), `[[a||b]]` para alternativas sorteadas e
  `{{tipo_fato:trecho}}` para marcar o trecho literal de um evento. Sem dependência nova.
- `textos.py` renderiza os templates e extrai as marcas com offsets; `roteiro.py` sorteia a linha do
  tempo (fato, denúncia, recebimento, preventiva e revisões, sentença, publicação, intimações,
  recurso, contrarrazões, acórdão, data de referência), crime e pena, partes e o volume de peças de
  enchimento; as datas formatadas no texto vêm das mesmas variáveis que vão para o gabarito.
- `identidades.py`: nomes por combinação, CPF sempre inválido, CNJ de teste, endereços, hash falso,
  datas em `dd/mm/aaaa` ou por extenso.
- Testes: mesma semente → mesmo texto, semente diferente → texto diferente; 5.000 CPFs gerados, todos
  inválidos; CNJ válido no dígito e na faixa reservada; toda data de evento aparece no trecho no
  formato impresso; nenhum CPF válido nas folhas.

## Decisões não previstas

- Números CNJ: segmento 8, tribunal 99 (inexistente) e sequencial 9900000–9999999, faixa que
  declaramos reservada a testes (documentado em `identidades.py` e `docs/sinteticos.md`).
- O roteiro escolhe o crime pela prescrição desejada (pena baixa quando o processo deve prescrever)
  e força intervalos entre revisões da preventiva acima de 90 dias quando o resultado pretendido é
  atenção. O resultado gravado é sempre o do motor, não o pretendido.
- Parágrafos de enchimento trazem datas distratoras (ofícios, audiências, mandados).

## O que ficou de fora

- Múltiplos réus e concurso de crimes (o gabarito suporta; o roteiro gera um réu e um crime).

## Como rodar os testes

```bash
docker compose exec api bash scripts/verificar.sh
# só a 4B, no host:
.venv/Scripts/python -m pytest tests/sinteticos --confcutdir=tests/sinteticos -o addopts="" --cov=lupa.sinteticos
```

Saída resumida (host, venv): `93 passed`; cobertura de `lupa.sinteticos` 99% (1.235 instruções, 4 não
cobertas). `ruff check`, `ruff format --check` e `mypy --strict` limpos em `src/lupa/sinteticos` e
`tests/sinteticos`. Resultado do `verificar.sh` completo: ver RELATORIO-ETAPA-4B.10.md.
