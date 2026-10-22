# Relatório da Etapa 4F.5 — Réus e pseudonimização

## O que foi feito

- `lupa/ingestao/eventos/reus.py`: réus pela qualificação na denúncia (nome, em caixa mista ou
  alta, seguido de vírgula e termo de qualificação: "brasileiro", "inscrito", "nascido",
  "vulgo"...), CPF até 250 caracteres depois, posição na página. Pseudônimo pela ordem
  (`REU-01`, `REU-02`).
- `repositorio_eventos.gravar_reus`: `reu` (só pseudônimo) e `reu_identidade` (nome e
  documento) separados, idempotente por pseudônimo.
- Fatos por réu (`data_nascimento_reu`, `data_intimacao_reu`) com
  `valor = {"valor": ..., "reu_id": "<uuid do reu>"}`: nascimento vai para o réu qualificado
  imediatamente antes; intimação, para o réu cujo nome está no trecho; com um réu, sempre ele.
  Com mais de um réu, o catálogo roda por réu (`ModeloProcesso.por_reu`) e o achado leva
  `valores.reu_id`.
- `reus.sem_nomes`: o trecho de evidência começa depois do último nome ou CPF de réu que caia
  dentro dele ("intimei pessoalmente o réu FULANO em 07/04/2016" → "em 07/04/2016").
- Logs da etapa só com ids e contagens.

## Decisões não previstas

- O nome continua no texto da página (aceito pelo roteiro). O recorte vale para o réu; nomes de
  defensor e testemunha ficam nos trechos (não são partes pseudonimizadas). Nos sintéticos, o
  defensor às vezes compartilha sobrenome com o réu; o teste confere o nome completo e o CPF.
- O `reu_id` em `valor` é o UUID do réu, não o pseudônimo, para a ligação não depender de ordem.

## O que ficou de fora

- Réu qualificado fora da denúncia (aditamento, termo de interrogatório) não é identificado.
- Cifragem de `reu_identidade` (fica para quando houver chave por gabinete, Etapa 1).

## Comandos e saída resumida

```
docker compose run --rm api python -m pytest tests/ingestao/test_eventos.py tests/ingestao/test_eventos_banco.py -k "reu or nome" --no-cov -q
3 passed
```

## Checklist

| Item | Evidência |
| --- | --- |
| Réus pela qualificação, pseudônimo e identidade separada | `test_reus_qualificados_recebem_pseudonimo_e_fatos_por_reu` (2 réus, CPF, nascimentos por `reu_id`) |
| Fatos por réu com `{"valor", "reu_id"}` | mesmo teste; banco: `test_worker_grava_reus_fatos_e_achados_sem_nome_real` |
| Nome não aparece em fato, achado, auditoria, log, `trechos_suspeitos` | `test_worker_grava_reus_fatos_e_achados_sem_nome_real`: varre `fato.valor`, trechos dos fatos, `achado.valores`/`explicacao`, `pagina.trechos_suspeitos`, `evento_auditoria` do processo e logs capturados (`structlog.testing.capture_logs`) |
| Recorte do trecho | `test_sem_nomes_recorta_o_trecho_depois_do_nome` |
