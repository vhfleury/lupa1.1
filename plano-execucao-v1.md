# Lupa — Plano de execução das etapas independentes do processo real

20 de outubro de 2026 · Victor Hugo

Este plano detalha as quatro etapas que não dependem do formato de exportação do Projudi. Cada etapa será executada por um agente (Opus 5.5) e validada por um revisor separado. O agente executor entrega código, testes e um relatório curto; o revisor confere contra os critérios de aceite e devolve com aprovação ou lista de correções.

Documentos de referência obrigatórios para todo agente: `requisitos-v1.md` (decisões do produto), `prompt-injection.md` (controles de segurança), `catalogo-validacoes.md` (regras jurídicas).

## Regras comuns a todas as etapas

**Linguagem e estilo**

- Python 3.12. PEP 8 verificado por `ruff` com `line-length = 100`. Tipagem completa verificada por `mypy --strict`.
- Docstrings no estilo Google em todo módulo, classe e função pública, verificadas por `ruff` com a regra `D` e convenção `google`.
- Clean code: funções curtas com uma responsabilidade, nomes em português para conceitos jurídicos (`peca`, `achado`, `evidencia`) e em inglês para infraestrutura (`repository`, `session`, `handler`). Sem comentários explicando o que o código faz; o nome e a docstring fazem isso.
- Sem lógica em `__init__.py`. Sem imports circulares. Sem `print`; logging estruturado em JSON.

**Testes**

- `pytest` com cobertura mínima de 90% no pacote da etapa, medida por `pytest-cov`.
- Testes nomeados pelo comportamento: `test_apelacao_interposta_no_sexto_dia_e_intempestiva`.
- Fixtures sintéticas. Nenhum dado real de processo, pessoa ou tribunal entra no repositório.

**Contêineres**

- Tudo roda via `docker compose`. Nenhuma instrução de execução depende de instalação na máquina do desenvolvedor.
- Imagens com usuário não root, `python:3.12-slim` como base, dependências fixadas por `uv.lock` ou `requirements.txt` com hashes.

**Segurança**

- Segredos só por arquivo `.env` ignorado pelo git no piloto, com caminho claro para Vault depois. Nunca em código ou em imagem.
- Nenhum conteúdo de autos, senha, token ou texto de pergunta entra em log.

**Entrega de cada etapa**

- Código na estrutura definida na Etapa 0.
- `RELATORIO-ETAPA-N.md` na pasta `docs/etapas/` com: o que foi feito, decisões tomadas que o plano não previa, o que ficou de fora e por quê, comando para rodar os testes e saída resumida.
- O agente não altera arquivos de outras etapas sem registrar no relatório.

**Papel do revisor**

- Roda lint, tipagem e testes do zero em contêiner limpo.
- Confere cada critério de aceite da etapa.
- Confere que nenhuma regra comum foi violada.
- Devolve: aprovado, ou lista numerada de correções com o critério violado.

## Ordem e dependências

```
Etapa 0 (esqueleto)
   ├── Etapa 1 (esquemas de dados)
   │      └── Etapa 3 (autenticação, papéis, auditoria)
   └── Etapa 2 (validações)   [paralela à 1 e à 3]
```

Etapas 1 e 2 começam juntas assim que a 0 for aprovada. Etapa 3 começa quando a 1 for aprovada.

---

## Etapa 0 — Esqueleto do projeto

**Objetivo.** Repositório pronto para as próximas etapas: estrutura de pastas, ferramentas de qualidade, contêineres, CI local. Nenhuma regra de negócio.

**Estrutura de pastas a criar**

```
lupa/
├── pyproject.toml
├── docker-compose.yml
├── Dockerfile
├── .env.example
├── .gitignore
├── Makefile
├── README.md
├── docs/
│   └── etapas/
├── src/
│   └── lupa/
│       ├── __init__.py
│       ├── config.py            # leitura de configuração por pydantic-settings
│       ├── logging.py           # logger JSON sem conteúdo sensível
│       ├── dominio/             # Etapa 1: modelos e esquemas
│       ├── validacoes/          # Etapa 2: motor e catálogo
│       ├── acesso/              # Etapa 3: usuários, autenticação, papéis
│       ├── auditoria/           # Etapa 3: trilha de auditoria
│       ├── ingestao/            # futuro: pipeline (vazio por enquanto)
│       ├── agente/              # futuro: Claude Agent SDK (vazio por enquanto)
│       └── api/                 # FastAPI: app, rotas, dependências
│           ├── __init__.py
│           ├── app.py
│           └── rotas/
└── tests/
    ├── conftest.py
    └── (espelha src/lupa/)
```

**Tarefas**

1. `pyproject.toml` com dependências de produção (`fastapi`, `uvicorn`, `pydantic>=2`, `pydantic-settings`, `sqlalchemy>=2`, `alembic`, `psycopg[binary]`, `structlog`) e de desenvolvimento (`pytest`, `pytest-cov`, `pytest-asyncio`, `ruff`, `mypy`, `httpx`). Fixar versões.
2. Configuração de `ruff` (regras `E,F,I,N,D,UP,B,S`, convenção `google`), `mypy --strict`, `pytest` com `--cov=lupa --cov-fail-under=90`.
3. `Dockerfile` multi-stage, usuário não root, `uvicorn` como entrada.
4. `docker-compose.yml` com serviços: `api`, `db` (PostgreSQL 16 com volume), `minio` (com console e bucket inicial criado por um serviço `minio-init`). Healthchecks em todos. Rede interna; só `api` e o console do MinIO expostos ao host.
5. `.env.example` com todas as variáveis, valores fictícios, comentário de uma linha por variável.
6. `config.py`: classe `Settings` com validação; falha ao iniciar se faltar variável obrigatória.
7. `logging.py`: configuração de `structlog` em JSON com campos fixos (`timestamp`, `level`, `event`, `request_id`). Processador que rejeita chaves da lista `CAMPOS_PROIBIDOS = {"senha", "password", "token", "texto", "conteudo", "pergunta", "resposta"}` lançando erro em teste e removendo em produção.
8. `api/app.py`: aplicação FastAPI com rota `GET /saude` que verifica banco e MinIO. Middleware que gera `request_id` por requisição.
9. `Makefile` com alvos `up`, `down`, `test`, `lint`, `typecheck`, `format`, `migrate`.
10. `README.md`: como subir, rodar testes e onde cada etapa fica.
11. Script `scripts/verificar.sh` que roda lint, tipagem e testes em sequência e falha no primeiro erro. É o comando que o revisor usa.

**Critérios de aceite**

- [ ] `docker compose up` sobe os três serviços saudáveis em menos de dois minutos em máquina limpa.
- [ ] `GET /saude` responde 200 com `{"api": "ok", "db": "ok", "minio": "ok"}`.
- [ ] `scripts/verificar.sh` passa com zero avisos de lint, zero erros de tipagem.
- [ ] Teste prova que o logger rejeita uma chave proibida.
- [ ] Teste prova que a aplicação não inicia sem variável obrigatória.
- [ ] Nenhuma imagem roda como root (`docker compose exec api whoami` retorna usuário não root).
- [ ] `.env` está no `.gitignore` e `.env.example` não contém valor real.

---

## Etapa 1 — Esquemas de dados

**Objetivo.** Modelo de domínio completo da primeira versão, em dois níveis: esquemas pydantic (contratos de entrada e saída) e tabelas SQLAlchemy com migrações Alembic. Nenhuma lógica de ingestão; só o modelo que a ingestão, as validações e a interface vão compartilhar.

**Princípio central.** Nenhum fato existe sem evidência. Isso é imposto no esquema, não em convenção: `Fato` exige ao menos uma `Evidencia`, e a validação pydantic rejeita o contrário.

**Entidades e campos**

| Entidade | Campos obrigatórios | Observações |
| --- | --- | --- |
| `Gabinete` | id, nome, criado_em | Tenant. Chave de criptografia futura referenciada aqui |
| `Processo` | id, gabinete_id, numero_cnj, classe, materia (`criminal`/`civel`), sigiloso (bool), status, criado_em, criado_por | `numero_cnj` validado pelo formato NNNNNNN-DD.AAAA.J.TR.OOOO com dígito verificador. `sigiloso=True` bloqueia ingestão na v1 |
| `Arquivo` | id, processo_id, sha256, tamanho_bytes, nome_original, mime, chave_storage, enviado_por, enviado_em | Imutável. Índice único em (processo_id, sha256) |
| `Peca` | id, arquivo_id, tipo, pagina_inicial, pagina_final, confianca, metodo (`regra`/`llm`/`manual`), origem (`juizo`/`mp`/`defesa`/`terceiro`/`desconhecida`) | `tipo` é enum extensível: denuncia, recebimento, decisao_prisao, sentenca, certidao, recurso, contrarrazoes, acordao, laudo, termo_depoimento, outros |
| `Pagina` | id, arquivo_id, numero, tipo (`nativa`/`ocr`/`vazia`), texto, hash_texto, flags (JSON) | `flags` guarda os marcadores de ingestão do `prompt-injection.md`: texto_oculto, bloco_codificado, padrao_instrucao, idioma_inesperado |
| `Evidencia` | id, pagina_id, trecho, hash_trecho, inicio, fim, bbox (JSON, opcional) | `hash_trecho = sha256(trecho)`. `inicio`/`fim` são offsets no `texto` da página |
| `Fato` | id, processo_id, tipo, valor (JSON), evidencias (lista, mínimo 1), extraido_por, versao_extrator, confianca, status (`automatico`/`confirmado`/`corrigido`), substitui_fato_id (opcional), criado_em | Tipos iniciais: data_fato, data_denuncia, data_recebimento_denuncia, data_sentenca, data_publicacao_sentenca, data_intimacao_defesa, data_intimacao_mp, data_intimacao_reu, data_interposicao_recurso, tipo_recurso, data_decretacao_preventiva, data_revisao_preventiva, pena_maxima_abstrata, data_nascimento_reu, reincidente |
| `Reu` | id, processo_id, pseudonimo | Nome real fica em `ReuIdentidade`, tabela separada |
| `ReuIdentidade` | reu_id, nome, documento | Tabela separada para cifrar depois; acesso só pela camada de apresentação |
| `Achado` | id, processo_id, validacao, versao_catalogo, resultado (`conforme`/`atencao`/`verificar`), fatos_usados (lista de ids), valores (JSON), explicacao, criado_em | Gerado só pelo motor. `valores` guarda tudo que o alerta precisa mostrar |
| `Anotacao` | id, achado_id ou fato_id, usuario_id, texto, criado_em | Não altera achado nem fato |
| `Usuario` | id, gabinete_id (nulo para admin), nome_usuario, papel, senha_hash, mfa_segredo, mfa_confirmado, ativo, troca_senha_obrigatoria, criado_em | Detalhado na Etapa 3; a tabela nasce aqui |
| `EventoAuditoria` | id, ocorrido_em, usuario_id, gabinete_id, processo_id, acao, objeto_tipo, objeto_id, ip, localizacao, resultado, versao_modelo, versao_prompt, hash_anterior, hash_evento | Detalhado na Etapa 3; a tabela nasce aqui |

**Tarefas**

1. Pacote `lupa/dominio/` com um módulo por entidade: `esquemas.py` (pydantic) e `tabelas.py` (SQLAlchemy) em cada submódulo, ou um módulo por entidade contendo ambos. Escolher e registrar no relatório.
2. Enums em `lupa/dominio/enums.py`, com docstring explicando cada valor.
3. Validadores pydantic: número CNJ com dígito verificador; `Fato.evidencias` com mínimo 1; `Peca.pagina_final >= pagina_inicial`; `Evidencia.fim > inicio`; `Achado.resultado` restrito ao enum.
4. Tabelas com índices: `(gabinete_id)` em tudo que pertence a um gabinete; `(processo_id, tipo)` em `Fato`; `(arquivo_id, numero)` único em `Pagina`.
5. Row Level Security no PostgreSQL por `gabinete_id` em todas as tabelas com esse campo, com política baseada em `current_setting('lupa.gabinete_id')`. Documentar como a camada de API define a variável por requisição.
6. Migração Alembic inicial gerada e revisada à mão (sem `autogenerate` cego no commit final).
7. Repositórios mínimos (`lupa/dominio/repositorios.py`): `salvar_fato`, `listar_fatos_por_processo`, `salvar_achado`, `listar_achados`. Só o necessário para as etapas 2 e 3 testarem contra banco real.
8. Fixtures em `tests/conftest.py`: banco PostgreSQL efêmero via `docker compose` de teste, gabinete e processo sintéticos, fábrica de fatos com evidência.

**Critérios de aceite**

- [ ] Teste prova que `Fato` sem evidência é rejeitado pelo pydantic e pelo banco (constraint ou trigger).
- [ ] Teste prova que número CNJ com dígito errado é rejeitado.
- [ ] Teste prova que, com RLS ativo e `lupa.gabinete_id` definido para o gabinete A, uma consulta não retorna linhas do gabinete B.
- [ ] Teste prova que `Achado` não pode ser atualizado após inserido (trigger que bloqueia `UPDATE`).
- [ ] `alembic upgrade head` em banco vazio cria todas as tabelas; `alembic downgrade base` remove.
- [ ] Diagrama das entidades em `docs/modelo-de-dados.md` (Mermaid), coerente com o código.
- [ ] Nenhuma tabela guarda nome real de pessoa fora de `ReuIdentidade` e `Usuario`.

---

## Etapa 2 — Motor de validações e as três validações do piloto

**Objetivo.** Motor que recebe os fatos de um processo e devolve achados, mais as três validações determinísticas, como funções puras, com tabelas jurídicas em dados versionados e testes exaustivos. Independente de PDF e de banco.

**Princípios**

- Toda validação é uma função pura: entra `ModeloProcesso` (fatos indexados por tipo), sai `Achado` com `valores` completos.
- O alerta pode concluir (`intempestivo`, `prescrito`), mas `valores` carrega tudo que o assessor precisa para refazer a conta: cada data com o id do fato e sua evidência, o prazo aplicado e sua base legal, feriados e suspensões considerados, marcos interruptivos usados.
- Fato faltante produz `verificar` com `valores.faltantes` listando os tipos de fato não encontrados.
- A explicação é montada por template de texto com os valores. Nunca por modelo de linguagem.
- Regras jurídicas citadas de memória no `catalogo-validacoes.md` devem ser confirmadas pelo gabinete. O código registra a base legal em cada regra para facilitar essa conferência.

**Estrutura**

```
lupa/validacoes/
├── motor.py            # executa catálogo sobre ModeloProcesso, versiona
├── modelo.py           # ModeloProcesso: índice de fatos por tipo, por réu
├── catalogo.py         # registro das validações disponíveis por matéria
├── calendario.py       # contagem de prazos: dias corridos/úteis, feriados, suspensões
├── criminal/
│   ├── tempestividade.py
│   ├── prescricao.py
│   └── preventiva.py
└── dados/
    ├── feriados/
    │   ├── nacionais.yaml
    │   └── tjgo.yaml
    ├── suspensoes_prazo.yaml
    └── prescricao_art109.yaml
```

**Validação 1: tempestividade do recurso (criminal)**

Fatos necessários: `tipo_recurso`, `data_intimacao_defesa` ou `data_intimacao_mp` (conforme quem recorre), `data_intimacao_reu` (quando a defesa recorre), `data_interposicao_recurso`.

Regras a implementar, com base legal registrada no código:

- Prazos: apelação 5 dias (art. 593 CPP), RESE 5 dias (art. 586), embargos de declaração 2 dias (art. 619). Tabela em dados.
- Contagem em dias corridos no processo penal (art. 798 CPP), excluindo o dia do começo e incluindo o do vencimento; vencimento em dia sem expediente prorroga para o próximo dia útil (art. 798 §3º).
- Quando a defesa recorre, o prazo conta da última intimação entre réu e defensor (art. 392 CPP; catálogo).
- Feriados nacionais e do TJGO e suspensões de prazo vêm de dados versionados.

Saída: `resultado` em `conforme` (tempestivo) ou `atencao` (intempestivo), com `valores`: data base, origem da data base, prazo em dias, base legal, data de vencimento calculada, feriados que deslocaram o vencimento, data de interposição, diferença em dias.

**Validação 2: prescrição pela pena em abstrato (criminal)**

Fatos necessários: `pena_maxima_abstrata` (em meses), `data_fato`, `data_recebimento_denuncia`, `data_publicacao_sentenca` (se houver), `data_nascimento_reu` (opcional, para art. 115).

Regras:

- Prazo prescricional pela tabela do art. 109 CP, em dados versionados (`prescricao_art109.yaml`), com faixas de pena máxima e prazo correspondente.
- Redução pela metade se o réu tinha menos de 21 anos na data do fato ou mais de 70 na data da sentença (art. 115 CP).
- Marcos interruptivos considerados nesta versão: recebimento da denúncia e publicação da sentença condenatória recorrível (art. 117, I e IV). Pronúncia e acórdão ficam para versão futura e devem aparecer como limitação na explicação.
- A validação calcula cada intervalo entre marcos (fato até recebimento; recebimento até sentença; sentença até hoje) e compara com o prazo.

Saída: `resultado` em `conforme`, `atencao` (algum intervalo supera o prazo) ou `verificar` (fato faltante). `valores` com: pena máxima, faixa do art. 109 aplicada, prazo em anos, redução do art. 115 aplicada ou não e por quê, cada intervalo com datas, dias e se superou o prazo, data de referência "hoje" usada.

**Validação 3: revisão da prisão preventiva em 90 dias (criminal)**

Fatos necessários: `data_decretacao_preventiva`, lista de `data_revisao_preventiva` (pode ser vazia), e a data de referência.

Regras:

- Art. 316, parágrafo único, CPP: necessidade da preventiva revisada a cada 90 dias, com decisão fundamentada.
- A validação ordena as datas (decretação e revisões), calcula cada intervalo consecutivo e o intervalo da última até a data de referência.

Saída: `conforme` se nenhum intervalo passou de 90 dias, `atencao` caso contrário, `verificar` se falta a decretação. `valores` com a cadeia completa de datas, cada intervalo em dias e qual estourou.

**Tarefas**

1. `modelo.py`: `ModeloProcesso` construído a partir de uma lista de `Fato` (esquema da Etapa 1). Métodos `fato(tipo)`, `fatos(tipo)`, `por_reu(reu_id)`. Conflito de valores para um tipo que deveria ser único gera `verificar` automático.
2. `calendario.py`: funções `contar_prazo_corrido(data_base, dias, feriados, suspensoes)` e `contar_prazo_util(...)`. A segunda já fica pronta para o módulo cível.
3. Carregadores de YAML com validação pydantic dos dados jurídicos. Cada arquivo tem campo `versao` e `fonte`.
4. As três validações, cada uma expondo `executar(modelo: ModeloProcesso, referencia: date) -> Achado` e um atributo `FATOS_NECESSARIOS`.
5. `catalogo.py`: registro por matéria (`criminal`, `civel`), com versão do catálogo (`"2026.10.0"`), que o motor grava em cada achado.
6. `motor.py`: `executar_catalogo(modelo, materia, referencia) -> list[Achado]`. Captura exceção de uma validação e transforma em achado `verificar` com a mensagem, sem derrubar as outras.
7. Templates de explicação em `lupa/validacoes/templates/*.txt` com `str.format`, um por validação e por resultado.
8. CLI mínima `python -m lupa.validacoes --fatos fatos.json --materia criminal --referencia 2026-10-20` que imprime os achados em JSON. Serve para conferência manual pelo gabinete.
9. Testes: para cada validação, ao menos os casos listados abaixo. Todos com datas fixas e feriados sintéticos para não depender do calendário real.

**Casos de teste mínimos**

Tempestividade:
- Interposição no último dia do prazo: tempestivo.
- Interposição no dia seguinte ao último: intempestivo.
- Vencimento em sábado: prorroga para segunda; interposição na segunda é tempestiva.
- Vencimento em feriado do TJGO: prorroga.
- Defesa recorre, réu intimado depois do defensor: prazo conta da intimação do réu.
- Falta data de intimação: `verificar` com `faltantes`.
- Tipo de recurso desconhecido: `verificar`.

Prescrição:
- Cada faixa do art. 109 com pena na borda inferior e superior.
- Intervalo exatamente igual ao prazo: não prescrito (confirmar regra e registrar).
- Réu com 20 anos no fato: prazo pela metade.
- Réu com 71 anos na sentença: prazo pela metade.
- Sem sentença: só intervalos fato–recebimento e recebimento–hoje.
- Duas datas de sentença no modelo: `verificar` por conflito.

Preventiva:
- Decretação há 89 dias, sem revisão: conforme.
- Decretação há 91 dias, sem revisão: atenção.
- Revisões a cada 80 dias: conforme.
- Uma revisão com 100 dias no meio da cadeia: atenção apontando qual intervalo.
- Revisões fora de ordem na entrada: ordenadas antes do cálculo.

**Critérios de aceite**

- [ ] As três validações são funções puras: mesmos fatos e mesma data de referência produzem o mesmo achado, provado por teste que executa duas vezes e compara.
- [ ] Todo achado com resultado `atencao` ou `conforme` tem em `valores` todas as datas com id de fato e id de evidência.
- [ ] Nenhuma validação importa de `lupa.ingestao`, `lupa.agente` ou `lupa.api`.
- [ ] Dados jurídicos só em YAML com `versao` e `fonte`; nenhum número de prazo ou de feriado dentro de arquivo `.py`.
- [ ] Explicações geradas por template, com teste que confere a frase inteira para um caso de cada resultado.
- [ ] Motor sobrevive a exceção em uma validação e devolve as demais.
- [ ] CLI funciona com o `fatos.json` de exemplo em `docs/exemplos/`.
- [ ] `docs/validacoes.md` descreve cada validação em linguagem simples: fatos usados, regra, base legal, o que o assessor deve conferir à mão. Esse texto vai para o guia dos assessores.

---

## Etapa 3 — Autenticação, papéis e auditoria

**Objetivo.** Usuários, login com senha e MFA, três papéis com autorização no servidor, e trilha de auditoria append-only com encadeamento de hash e consulta rápida. Depende da Etapa 1.

**Decisões já tomadas (de `requisitos-v1.md`)**

- Usuário e senha, sem e-mail. MFA obrigatório por aplicativo autenticador (TOTP).
- Papéis: `assessor`, `desembargador`, `admin`. Admin é único, vê tudo, cria desembargadores. Desembargador gerencia assessores do próprio gabinete. Assessor só vê o próprio gabinete.
- Recuperação de senha e de MFA é manual, por quem tem permissão, com credencial temporária e troca obrigatória.
- Desativar não apaga. Todo acesso do admin a conteúdo fica destacado.
- Auditoria registra IP e localização aproximada; nunca conteúdo.

**Estrutura**

```
lupa/acesso/
├── senhas.py          # hash e verificação (argon2id)
├── mfa.py             # geração de segredo, QR, verificação TOTP com janela
├── sessoes.py         # sessão server-side em tabela, cookie HttpOnly/Secure/SameSite=Strict
├── papeis.py          # enum de papéis e matriz de permissões
├── autorizacao.py     # dependências FastAPI: exige_papel, exige_gabinete, exige_processo
├── servico.py         # casos de uso: criar usuário, login, trocar senha, resetar, desativar
└── rotas.py           # endpoints
lupa/auditoria/
├── eventos.py         # enum de ações e esquema do evento
├── registrador.py     # grava evento com hash encadeado
├── geoip.py           # localização aproximada por IP (base offline)
├── consulta.py        # filtros e paginação
└── rotas.py           # endpoints de consulta e exportação
```

**Tarefas: acesso**

1. Senhas com `argon2-cffi` (argon2id, parâmetros documentados). Política mínima: 12 caracteres; rejeitar as 10 mil senhas mais comuns (lista embutida). Sem exigência de caracteres especiais.
2. MFA com `pyotp`: segredo gerado no primeiro login, exibido como QR e texto, confirmado com um código válido antes de ativar. Janela de tolerância de 1 passo. Códigos já usados dentro da janela são rejeitados (replay).
3. Sessões em tabela `sessao` (id aleatório de 256 bits, usuario_id, criada_em, expira_em, ip_criacao, revogada). Cookie `HttpOnly`, `Secure`, `SameSite=Strict`. Expiração absoluta de 8 horas e por inatividade de 30 minutos. Logout revoga. Troca de senha revoga todas as sessões do usuário.
4. Rate limit de login: 5 falhas por usuário em 15 minutos bloqueia por 15 minutos; registrado em auditoria. Resposta de erro idêntica para usuário inexistente e senha errada.
5. Fluxo de login em dois passos: senha, depois TOTP. Sessão só é criada após o TOTP. Se `troca_senha_obrigatoria`, a única rota permitida é a de troca.
6. Matriz de permissões em `papeis.py`, como dados, não como `if` espalhado:

| Ação | assessor | desembargador | admin |
| --- | --- | --- | --- |
| ver processo do próprio gabinete | sim | sim | sim (todos) |
| subir processo | sim | sim | sim |
| anotar, corrigir fato | sim | sim | sim |
| ver auditoria do gabinete | não | sim | sim (todos) |
| criar/desativar assessor | não | sim (próprio gabinete) | sim |
| resetar senha/MFA de assessor | não | sim (próprio gabinete) | sim |
| criar/desativar desembargador | não | não | sim |
| gerir gabinetes | não | não | sim |

7. `autorizacao.py`: dependências FastAPI que carregam a sessão, o usuário, e verificam papel e gabinete. A dependência `exige_processo` carrega o processo e confere `processo.gabinete_id == usuario.gabinete_id` ou `admin`. Define `lupa.gabinete_id` na conexão do banco para a RLS da Etapa 1.
8. Endpoints: `POST /auth/login`, `POST /auth/mfa`, `POST /auth/logout`, `POST /auth/trocar-senha`, `POST /auth/mfa/confirmar`, `GET /usuarios` (por gabinete), `POST /usuarios`, `POST /usuarios/{id}/desativar`, `POST /usuarios/{id}/reativar`, `POST /usuarios/{id}/resetar-senha`, `POST /usuarios/{id}/resetar-mfa`, `POST /gabinetes` (admin).
9. Script `scripts/criar_admin.py` que cria o único admin a partir de variáveis de ambiente, só se não existir.

**Tarefas: auditoria**

10. Enum de ações em `eventos.py`: `login_ok`, `login_falha`, `login_bloqueado`, `mfa_ok`, `mfa_falha`, `logout`, `senha_trocada`, `senha_resetada`, `mfa_resetado`, `usuario_criado`, `usuario_desativado`, `usuario_reativado`, `gabinete_criado`, `processo_criado`, `arquivo_enviado`, `processo_aberto`, `pagina_vista`, `busca`, `pergunta_chat`, `anotacao`, `fato_corrigido`, `validacao_executada`, `chamada_modelo`, `admin_acesso_conteudo`, `auditoria_consultada`, `auditoria_exportada`.
11. `registrador.py`: `registrar(evento)` calcula `hash_evento = sha256(hash_anterior + campos canônicos em JSON ordenado)` e grava. `hash_anterior` é o do último evento do mesmo gabinete (ou global para eventos sem gabinete). Gravação em transação com `SELECT ... FOR UPDATE` do último evento para evitar corrida. Trigger no banco bloqueia `UPDATE` e `DELETE` na tabela.
12. Middleware que registra `processo_aberto`, `pagina_vista`, `busca` automaticamente a partir das rotas, e marca `admin_acesso_conteudo` quando o usuário é admin e a rota devolve conteúdo de autos.
13. `geoip.py`: resolução de IP para país, estado e cidade com base offline (ex.: GeoLite2, respeitando a licença, baixada no build e atualizada manualmente). IP privado resolve para `"rede interna"`. Falha na resolução não impede o registro do evento.
14. `consulta.py`: filtros por gabinete, usuário, processo, ação, intervalo de datas, IP; paginação por cursor; ordenação por `ocorrido_em`. Índices compostos para essas consultas. Meta: consulta com filtros responde em menos de 200 ms com 1 milhão de eventos sintéticos.
15. `GET /auditoria` com os filtros; `GET /auditoria/exportar` em CSV e JSON, com o próprio ato de exportar registrado. `GET /auditoria/verificar` percorre a cadeia de um gabinete e devolve se o encadeamento está íntegro e, se não, o primeiro evento quebrado.
16. Relatório de uso `GET /auditoria/relatorio-uso?processo=...` ou `?usuario=...`: contagem por ação, primeiro e último acesso, chamadas ao modelo com versões. É o material para o magistrado informar o tribunal.

**Critérios de aceite**

- [ ] Teste: login com senha certa e TOTP errado não cria sessão.
- [ ] Teste: código TOTP reutilizado dentro da janela é rejeitado.
- [ ] Teste: 5 falhas bloqueiam e geram evento `login_bloqueado`.
- [ ] Teste: assessor do gabinete A recebe 404 (não 403) ao acessar processo do gabinete B, e o evento de tentativa é registrado.
- [ ] Teste: desembargador não consegue criar assessor em outro gabinete.
- [ ] Teste: usuário com `troca_senha_obrigatoria` só acessa a rota de troca.
- [ ] Teste: troca de senha revoga as demais sessões.
- [ ] Teste: `UPDATE` ou `DELETE` em `evento_auditoria` falha no banco.
- [ ] Teste: alterar um campo de um evento no meio da cadeia faz `GET /auditoria/verificar` apontar exatamente aquele evento.
- [ ] Teste: dois registros concorrentes no mesmo gabinete produzem cadeia válida (sem hash_anterior duplicado).
- [ ] Teste: nenhum evento contém chave de `CAMPOS_PROIBIDOS` (reaproveita o processador da Etapa 0).
- [ ] Teste de carga: 1 milhão de eventos sintéticos; consulta filtrada por usuário e intervalo responde em menos de 200 ms.
- [ ] Teste: acesso de admin a rota de conteúdo gera `admin_acesso_conteudo` além do evento normal.
- [ ] `docs/auditoria.md` explica em linguagem simples o que é registrado, o que nunca é registrado, e como verificar a integridade da cadeia.

---

## O que o revisor entrega ao fim de cada etapa

`docs/etapas/REVISAO-ETAPA-N.md` com:

1. Comando executado e saída resumida de `scripts/verificar.sh`.
2. Tabela de critérios de aceite com `ok` ou `falhou` e evidência (nome do teste ou observação).
3. Violações das regras comuns, se houver.
4. Decisão: aprovado, ou lista numerada de correções.
5. Riscos observados que não eram critério, para registro.

## Fora deste plano

Pipeline de ingestão, agente, chat, interface web e visualizador de PDF. Entram em plano próprio quando o processo exportado do Projudi estiver disponível.
