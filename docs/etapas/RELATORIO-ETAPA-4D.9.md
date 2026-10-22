# Relatório da Etapa 4D.9 — Hash por trecho

## O que foi feito

- `saneamento.hash_trecho(texto_original, inicio, fim)` = `calcular_hash(texto_original[inicio:fim])`, a mesma função de `Evidencia.hash_trecho`; `hash_trecho_normalizado` resolve offsets do normalizado para o original e devolve o hash do original.
- Cada trecho suspeito e cada trecho oculto grava `hash`; metadados gravam o hash do valor.

## Critério

| Critério | Evidência |
| --- | --- |
| Consistente com o domínio | `test_evidencia_sobre_o_normalizado_resolve_para_o_original_com_hash_do_dominio` (hash igual ao de `Evidencia`) |
| Estável entre execuções | função pura do texto; `test_bloco_base64_legivel...` confere contra o sha256 do original; a regressão extrai as mesmas páginas em processos filhos diferentes a cada execução do `verificar.sh` |
| Original × normalizado via mapa | mesmo teste: trecho com cirílico no original, ASCII no normalizado, hash do original |

## Comandos e saída

```
docker compose up -d --build --wait
docker compose exec api bash scripts/verificar.sh
```

Saída resumida (21/10/2026): ruff e `ruff format --check` limpos; `mypy --strict` sem erros em 165 arquivos; pytest **588 passed, 1 skipped** (o skip é anterior à 4D; eram 551 testes), cobertura **98,66%**; ponta a ponta 1 passed; regressão de injeção 2 passed (159 s), `recall 1.0`, `falso_positivo 0.0`.
