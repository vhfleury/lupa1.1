# Relatório da Etapa 2 — Motor de validações e as três validações do piloto

## O que foi feito

- `src/lupa/validacoes/`
  - `modelo.py`: esquemas de entrada `Evidencia`, `Fato` (mínimo 1 evidência) e de saída `Achado`,
    com os mesmos campos da tabela da Etapa 1; `ModeloProcesso` com `fato(tipo)` (lança
    `ConflitoDeFatosError` se houver valores divergentes), `fatos(tipo)`, `por_reu(reu_id)`, `reus()`.
  - `calendario.py`: `contar_prazo_corrido` (art. 798 CPP: exclui o dia do começo, pula
    suspensões, prorroga vencimento sem expediente) e `contar_prazo_util` (pronta para o cível);
    `somar_meses`, `idade_em`.
  - `dados.py`: carregadores YAML com validação pydantic; todo arquivo exige `versao` e `fonte`
    (`extra="forbid"`).
  - `dados/`: `feriados/nacionais.yaml`, `feriados/tjgo.yaml`, `suspensoes_prazo.yaml`,
    `prescricao_art109.yaml`, `prazos_recursos.yaml`, `preventiva.yaml`.
  - `criminal/tempestividade.py`, `criminal/prescricao.py`, `criminal/preventiva.py`: cada uma com
    `executar(modelo, referencia) -> Achado`, `FATOS_NECESSARIOS`, `NOME` e `BASE_LEGAL` (base
    legal também na docstring e nos YAML).
  - `catalogo.py` (registro por matéria `criminal`/`civel`, `VERSAO_CATALOGO = "2026.10.0"`,
    definida em `versao.py` para evitar import circular), `motor.py` (`executar_catalogo`,
    isola exceções em achado `verificar` e registra log sem conteúdo), `apoio.py` (leitura de
    datas, rastreio fato/evidência, `Coleta` de faltantes/conflitos, render de template).
  - `templates/*.txt`: um por validação e resultado (9) + `motor_erro.txt`, via `str.format`.
  - `__main__.py`: CLI `python -m lupa.validacoes --fatos ... --materia criminal --referencia ...`.
- `tests/validacoes/`: 72 testes (conftest próprio com fábrica de fatos e dados sintéticos).
- `docs/validacoes.md` (guia do assessor), `docs/exemplos/fatos.json` (processo sintético).
- Dependências: `pyyaml==6.0.2` (produção) e `types-PyYAML==6.0.12.20241230` (dev) em
  `pyproject.toml`, `requirements.in`, `requirements-dev.in`; regenerados com:

  ```
  pip-compile --allow-unsafe --generate-hashes --output-file=requirements.txt --strip-extras requirements.in
  pip-compile --allow-unsafe --generate-hashes --output-file=requirements-dev.txt --strip-extras requirements-dev.in
  ```

  Imagem reconstruída com `docker compose build api`.

## Decisões que o plano não previa

1. **Esquemas próprios em `validacoes/modelo.py`** porque a Etapa 1 corria em paralelo. Mesmos
   nomes de campo; a troca por `lupa.dominio.esquemas` é só mudar o import (documentado na
   docstring). Nada em `validacoes` importa de `lupa.dominio`.
2. **Formato de `valor`**: datas como string ISO; `tipo_recurso` como
   `{"tipo": ..., "recorrente": "defesa"|"mp"}` (a tabela da Etapa 1 não tem fato para quem
   recorre); pena em meses inteiros; fatos por réu como `{"valor": ..., "reu_id": ...}`.
3. **Dois YAML a mais** além dos listados: `prazos_recursos.yaml` e `preventiva.yaml`, para que
   nenhum prazo fique em `.py`. A redução do art. 115 (21/70 anos, divisor 2) fica em
   `prescricao_art109.yaml`.
4. **Injeção de dados**: cada `executar` aceita um terceiro argumento opcional com as tabelas
   (testes usam feriados sintéticos); sem ele, usa os YAML empacotados (cache `lru_cache`).
5. **Regras de borda** (a confirmar, listadas em `docs/validacoes.md`): intervalo igual ao prazo
   prescricional não prescreve (limite = início + prazo em meses de calendário); "maior de 70"
   = 70 completos; 90 dias exatos na preventiva é conforme; dias de suspensão não contam no prazo
   corrido; empate de datas de intimação escolhe a do réu.
6. **Validações extras de consistência** que geram `verificar`: marcos da prescrição fora de ordem
   ou posteriores à referência; revisão da preventiva anterior à decretação ou posterior à
   referência; recorrente não identificado.
7. Cada data rastreável em `valores` tem `data`, `tipo`, `fato_id`, `evidencia_id` (primeira) e
   `evidencia_ids` (todas). A data de referência aparece como `{"data", "tipo": "data_referencia"}`,
   sem fato, por não vir dos autos.
8. `docs/` não entra na imagem (Dockerfile da Etapa 0), então os testes usam
   `tests/validacoes/fatos_exemplo.json`, e um teste garante que é idêntico a
   `docs/exemplos/fatos.json` quando `docs/` existe.
9. Log do motor ao capturar exceção: só `validacao` e `erro_tipo` (mensagem fica no achado, não no
   log).

## O que ficou de fora e por quê

- Feriados do TJGO **reais**: não há portaria conferida; `tjgo.yaml` é provisório e marcado
  "a confirmar". Só 2026 está preenchido em `nacionais.yaml`.
- Pronúncia, acórdão e causas suspensivas da prescrição (fora do escopo da v1; aparecem como
  limitação na explicação e em `valores.limitacoes`).
- Súmula 310 STF (intimação na sexta), prazos especiais e exceções do recesso para réu preso:
  registrados como conferência manual.
- Execução por réu (`por_reu`) existe no modelo, mas o motor roda sobre o modelo recebido;
  quem chama decide recortar por réu.
- `README.md` não foi alterado (arquivo da Etapa 0, fora da lista permitida).

## Como rodar e saída resumida

Local (venv da Etapa 0, Git Bash):

```
PYTHON=.venv/Scripts/python bash scripts/verificar.sh
== ruff check ==            All checks passed!
== ruff format --check ==   formatado
== mypy --strict ==         Success: no issues found
== pytest ==                105 passed, 13 skipped
                            Total coverage: 89.12%  (FAIL no limiar de 90%)
```

A cobertura total local fica abaixo de 90% só por arquivos da Etapa 1 em andamento
(`migrations/*`, `dominio/repositorios.py`), cujos testes de banco são pulados fora do compose.
Cobertura do pacote desta etapa:

```
python -m pytest tests/validacoes -o addopts="" --cov=lupa.validacoes --cov-fail-under=90
71 passed — Total coverage: 99.62%
```

No contêiner (após `docker compose build api`):

```
docker compose exec api bash scripts/verificar.sh
ruff check: All checks passed! | ruff format: 55 files already formatted
mypy --strict: Success: no issues found in 55 source files
pytest: 117 passed, 1 skipped — Total coverage: 98.74%
```

CLI com o exemplo (`--referencia 2026-10-20`): tempestividade `conforme`, prescrição `conforme`,
preventiva `conforme`.

## Checklist dos critérios de aceite

| Critério | Status | Evidência |
| --- | --- | --- |
| Validações puras (executa duas vezes e compara) | ok | `test_validacoes_sao_puras_mesma_entrada_mesmo_achado` |
| Achado `atencao`/`conforme` tem todas as datas com id de fato e de evidência | ok | `test_achados_conclusivos_trazem_datas_com_fato_e_evidencia` |
| Nenhuma validação importa de `lupa.ingestao`, `lupa.agente`, `lupa.api` (nem `lupa.dominio`) | ok | `test_nenhuma_validacao_importa_camadas_proibidas` (AST) |
| Dados jurídicos só em YAML com `versao` e `fonte`; nenhum número de prazo/feriado em `.py` | ok | `test_todo_yaml_de_dados_exige_versao_e_fonte`, `test_arquivo_sem_versao_e_rejeitado`, `test_nenhum_numero_de_prazo_ou_data_em_arquivo_py` (AST: só 0, 1 e as constantes de calendário sábado/domingo/12 meses) |
| Explicações por template, frase inteira por resultado | ok | `test_explicacao_{conforme,atencao,verificar}_com_frase_inteira` nas três validações + mensagem do motor |
| Motor sobrevive a exceção e devolve as demais | ok | `test_motor_sobrevive_a_excecao_e_devolve_as_demais` |
| CLI funciona com `docs/exemplos/fatos.json` | ok | `test_cli_imprime_achados_do_exemplo`; execução manual local e no contêiner |
| `docs/validacoes.md` em linguagem simples | ok | `docs/validacoes.md` (fatos, regra, base legal, conferência manual, pontos a confirmar) |
| Casos mínimos de tempestividade, prescrição e preventiva | ok | `test_tempestividade.py`, `test_prescricao.py`, `test_preventiva.py` |
| Cobertura ≥ 90% no pacote da etapa | ok | 99,62% em `lupa.validacoes`; 98,74% total no contêiner |
| `scripts/verificar.sh` passa | ok no contêiner; local falha só no limiar total por arquivos da Etapa 1 | ver seção anterior |
