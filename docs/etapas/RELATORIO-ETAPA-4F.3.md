# Relatório da Etapa 4F.3 — Evidência obrigatória

## O que foi feito

- `lupa/ingestao/eventos/fatos.py`: todo candidato vira `Fato` só com
  `Evidencia(pagina_id, trecho, inicio, fim)` sobre o texto ORIGINAL da página
  (`pagina.texto`); os offsets dos extratores, calculados no dobrado, voltam ao original pelo mapa
  do normalizado. O hash do trecho é calculado pelo esquema `Evidencia`.
- Trecho vazio ou só de espaços (inclusive depois de recortar o nome do réu, 4F.5) descarta o
  valor; a contagem vai para `relatorio.eventos.sem_trecho` e o log `fato_sem_trecho` leva só o
  tipo e a regra.
- Mesmo tipo e valor em várias páginas: um fato com várias evidências.
- Ids de fato e evidência derivados da chave natural (`uuid5`), base da idempotência da 4F.6.

## Decisões não previstas

- O trecho começa no gatilho e termina no fim da data ("mantenho a prisão preventiva em
  07/10/2014"), para a evidência mostrar por que a data é aquele fato, não só a data solta.

## O que ficou de fora

- `bbox` da evidência não é preenchida (as coordenadas por linha estão em
  `pagina.coordenadas`; a tela da Etapa 6 pode calcular).

## Comandos e saída resumida

```
docker compose run --rm api python -m pytest tests/ingestao/test_eventos.py -k "trecho or evidencia" --no-cov -q
2 passed
```

Na medição da 4F.9: 0 fato sem evidência e 0 evidência cujo trecho difere de
`texto[inicio:fim]`, nos 30 arquivos.

## Checklist

| Item | Evidência |
| --- | --- |
| Fato com trecho literal, offsets, hash e página | `test_todo_fato_tem_evidencia_literal_no_texto_original` |
| Valor sem trecho é descartado | `test_valor_sem_trecho_e_descartado` (2 candidatos, 0 fatos, `sem_trecho == 2`) |
| Zero fato sem evidência nos processos de referência | `RELATORIO-ETAPA-4F.9.md`: 0 em 903 fatos (30 arquivos) |
