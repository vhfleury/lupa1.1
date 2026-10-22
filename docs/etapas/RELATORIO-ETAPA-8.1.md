# Relatório da Etapa 8.1 — ambiente de piloto

Data: 21/10/2026. Ambiente de prova: desenvolvimento (Windows 11, Docker Desktop). Sem servidor
nem domínio reais: a instalação ficou como sequência de comandos com variáveis; o que dependia do
ambiente foi provado no dev. Nenhum dado real, nenhuma cópia de contêiner para o host, sem git.
Disco conferido antes de cada build: 115–116 GB livres o tempo todo (nunca abaixo de 15 GB).
`docs/conformidade/**`, `front/**` e `src/lupa/migrations/**` não foram tocados; os 344 objetos
órfãos não foram apagados.

## 1. Correção do achado da 7.10 (cofre selado)

- `docker-compose.yml`, serviço `vault`: healthcheck `["CMD", "vault", "status"]` (sai com 0 só
  destravado, 2 selado, 1 fora). Consequência registrada no compose e no manual: depois de
  recriar ou reiniciar o `vault`, ele fica `unhealthy` e a `api`/`worker` (que dependem dele
  `service_healthy`) esperam o unseal; a ordem passa a ser `up -d vault` → `vault_inicializar` →
  `up -d --wait`.
- `src/lupa/seguranca/cofre.py`: constante `CHAVE_SAUDE = "lupa-saude"`.
- `src/lupa/api/saude.py`: `verificar_cofre` cifra e decifra um valor fixo pela chave
  `lupa-saude` (no cofre em memória, cria a chave); qualquer erro (selado, fora, sem AppRole, sem
  a chave) ou valor diferente → falso.
- `src/lupa/api/rotas/saude.py`: `GET /saude` ganha `"cofre"`; 503 se falhar.
- `vault/politicas/lupa.hcl`: o AppRole só pode `encrypt`/`decrypt` em `lupa-saude` (não cria nem
  apaga). `vault_inicializar.sh`/`.ps1` criam a chave com o token raiz.
- Testes: `tests/api/test_saude.py` (+4: 503 com cofre selado; memória ida e volta; cofre que
  falha ou decifra outra coisa; Vault inalcançável) e ajuste dos existentes.

**Prova no dev** (`docker compose restart vault`, `/saude` pela API, unseal, `/saude` pelo proxy):

    == antes: 2026-10-21T23:44:47Z
    {"api":"ok","db":"ok","minio":"ok","cofre":"ok"} HTTP 200
    Sealed          false
    == docker compose restart vault
     Container lupa-vault-1 Started 
    == depois do reinicio (selado): 2026-10-21T23:45:10Z
    Sealed             true
    vault status rc=2
    503 {"api":"ok","db":"ok","minio":"ok","cofre":"falha"}
    api healthy
    vault starting
    == unseal
    vault: unseal ok
    == depois do unseal: 2026-10-21T23:45:29Z
    {"api":"ok","db":"ok","minio":"ok","cofre":"ok"} HTTP 200
    api healthy
    vault healthy

A `api` só passou a `unhealthy` depois das 5 tentativas do healthcheck (≈50 s); o 503 do
`/saude` é imediato.

## 2. Perfil de produção (`docker-compose.prod.yml`)

Uso: `docker compose -f docker-compose.yml -f docker-compose.prod.yml ...` (ou
`COMPOSE_FILE=docker-compose.yml:docker-compose.prod.yml`). `config -q` válido.

- Portas: `api` e `minio` com `ports: !reset []` (`API_PORTA_HOST` ignorada); `proxy` com
  `!override` só `443→8443` e `80→8080` (IP em `LUPA_PROXY_IP`, padrão `0.0.0.0`). Conferido no
  `config --format json`: só o proxy publica.
- `restart: unless-stopped` e logs `json-file` (`max-size` 10m, `max-file` 5) em todos, por âncora
  `x-comum`; `minio-init` com `restart: "no"`.
- Limites de CPU e memória por serviço (api 2/2g, worker 6/6g, db 2/3g, minio 1/1g, demais
  menores), ajustáveis por variável.
- `read_only`: front, proxy (já eram), redis (+ tmpfs `/data`), backup-agendado, prometheus.
  Não: api/worker (uploads de até 512 MB e temporários em `/tmp`, tmpfs em memória seria pior),
  db, minio, vault (o entrypoint faz `setcap` no binário para o mlock).
- Vault: `cap_add: [IPC_LOCK]`, `vault/producao/lupa.hcl` com `disable_mlock = false`, sem
  `no-new-privileges` (anularia a capability de arquivo). Provado num contêiner descartável:
  `Mlock: supported: true, enabled: true`.
- Volumes `db-dados`, `minio-dados`, `vault-dados`, `caddy-dados`, `prometheus-dados`,
  `grafana-dados` como bind em `${LUPA_DADOS_DIR:-/srv/lupa/dados}/<nome>`.
- `backup-agendado`: definido no compose base (perfil `agendamento`) e ligado sempre no prod
  (`profiles: !reset []`). Imagem do próprio backup (`lupa-backup:local`, bases já fixadas por
  digest/versão), `crond` do BusyBox via `scripts/cron_backup.sh`: diário `fazer` (02:00 UTC) e
  semanal `expurgar` (dom 03:30 UTC), horários em `LUPA_BACKUP_CRON_DIARIO/_EXPURGO`, gravando em
  `LUPA_BACKUP_DIR` e `cron.log`. Não usei ofelia/supercronic: a imagem já tem `crond`, e evita
  dar o socket do Docker a um agendador. Prova (agenda a cada minuto, estimativa forçada para
  recusar, sem tocar no banco grande):

    cron_backup: agenda diario='* * * * *' expurgo='30 3 * * 0'
    --- cron.log
    backup: fazer banco=lupa bucket=lupa-autos estimativa_forcada=1 estimativa_bytes=1000000000000000 livre_bytes=124241321984 exigido_bytes=2000002147483648
    backup: fazer banco=lupa bucket=lupa-autos estimativa_forcada=1 RECUSADO: espaco livre insuficiente no destino
    backup: espaco livre insuficiente: livre=124241321984 exigido=2000002147483648 (2 x 1000000000000000 + 2 GB)
    healthy

## 3. Certificado e domínio

`proxy/Caddyfile` virou um snippet comum `(lupa_site)` (cabeçalhos e rotas) mais
`import modos/{$LUPA_TLS_MODO:interno}.caddy`; o compose monta a pasta `proxy/` inteira.
Globais: `http_port 8080`, `https_port 8443` (o desafio HTTP-01 entra pela 80 do host).

| Modo | Arquivo | Endereço | TLS | HSTS |
| --- | --- | --- | --- | --- |
| `interno` (padrão; dev) | `modos/interno.caddy` | `localhost:8443, proxy:8443`, `tls internal` | 1.2+1.3 | sim (ver abaixo) |
| `acme` (padrão do prod) | `modos/acme.caddy` | `{$LUPA_DOMINIO}`, `tls {$LUPA_ACME_EMAIL}` | só 1.3 | sim |
| `fornecido` | `modos/fornecido.caddy` | `{$LUPA_DOMINIO}`, `tls /certs/lupa.crt /certs/lupa.key` (de `LUPA_TLS_CERT`/`LUPA_TLS_CHAVE`) | só 1.3 | sim |

**Desvio registrado — HSTS em dev:** o pedido era "HSTS só com certificado real", mas o E2E
`front/e2e/testes/seguranca.spec.ts` (que não posso editar) e a varredura exigem o cabeçalho em
dev. Mantive-o no modo `interno`; o navegador ignora HSTS recebido com certificado não confiável,
então não fixa `localhost`. Para tirar, basta apagar a linha em `modos/interno.caddy` e afrouxar
os dois testes numa etapa que possa mexer no front.

`scripts/validar_caddyfile.sh` (contêiner `caddy:2.8.4-alpine`, certificado descartável gerado
dentro do contêiner para o modo fornecido): `Valid configuration` nos três; um modo inexistente
sai com 1. A varredura de cabeçalhos do `verificar.sh` continua `ok em 4 rotas` e o E2E passa.

## 4. Vault para produção

- `scripts/vault_inicializar.sh` com `LUPA_AMBIENTE=producao`: `init -key-shares=3
  -key-threshold=2`; cada parte mostrada uma vez, numa tela limpa, para um portador; nada em disco;
  unseal pedindo duas partes sem eco; configuração com o token raiz só em memória e **revogação do
  token raiz** no fim; `--so-unseal` para reinícios. Em dev continua 1/1 com `.vault-dev/init.json`.
  O `.ps1` recusa produção e aponta para o `.sh`. O modo produção **não foi executado** (exige
  terminal interativo e três pessoas); a sintaxe foi conferida e os caminhos de dev rodaram.
- **Decisão: sem TLS entre API/worker e Vault no piloto** (registrada em `docs/operacao.md` 4.6 e
  no `vault/producao/lupa.hcl`). Rede interna de um único host, sem porta publicada; quem enxerga
  a ponte do Docker já é root e lê o `.env` e a memória; a CA interna traria renovação e mais um
  ponto de falha no reinício sem ganho real. Reavaliar se o Vault sair do host.
- Backup do Vault: o serviço de backup monta `vault-dados` só leitura e `backup_conteiner.sh fazer`
  põe `vault.tar` no `.age` do dia (com entrada no manifesto); `restaurar` o deixa em
  `LUPA_BACKUP_DIR/vault-<arquivo>.tar` para a reposição manual (passos em `operacao.md` 4.4).
  `scripts/backup.sh --vault-frio` para cópia fria (para e sobe o vault, que volta selado).
  **Teste de restauração no dev** (banco `lupa_bkp81` de 3 linhas e bucket `lupa-bkp81` de 1
  objeto, para não fazer backup do banco e do bucket grandes; tudo apagado ao fim): backup →
  restauração → volume novo com o `vault.tar` → Vault descartável → unseal com a chave de dev →
  as 44 chaves Transit presentes, iguais às do Vault em uso:

    backup: manifesto conferido
    backup: restaurando banco em lupa_bkp81_r
    backup: restaurando objetos em lupa-bkp81-r
    backup: armazenamento do vault em vault-lupa-2026-10-20261021T235335Z.tar (reposicao manual)
    backup: restaurado lupa-2026-10-20261021T235335Z.tar.age em banco=lupa_bkp81_r bucket=lupa-bkp81-r
    -rw-r--r-- 1 vh15f 197609 822272 Oct 21 20:53 vault-lupa-2026-10-20261021T235335Z.tar
    auth
    core
    logical
    sys
    Sealed          false
    Total Shares    1
    Keys
    ----
    lupa-gabinete-1c81f1f2-78d3-4695-8e33-8176ac7b892f
    lupa-gabinete-1c81f1f2-78d3-4695-8e33-8176ac7b892f-identidades
    lupa-gabinete-239c8e47-d3d8-4adf-98fc-83d5d50ff7f4
    chaves no vault restaurado: 44
    chaves no vault em uso:      44
    limpeza: conteiner, volume e tar extraido removidos
    banco restaurado: 3 linhas

O arquivo de teste `lupa-2026-10-20261021T235335Z.tar.age` (830 KB) ficou em `.backups/`.

## 5. Monitoramento

- Rota nova `GET /metricas/servico` (em `src/lupa/api/rotas/saude.py`): `Authorization: Bearer`
  comparado em tempo constante com `LUPA_METRICAS_TOKEN` (`config.py`); sem token configurado, 404;
  errado, 401. Motivo: `GET /metricas` exige sessão de administrador com TOTP, que o Prometheus
  não consegue manter, e `rotas/ingestao.py` estava fora do escopo. Devolve as métricas de
  ingestão de sempre mais `lupa_cofre_ok`, `lupa_modelo_chamadas_24h`,
  `lupa_modelo_tokens_24h{tipo}` e `lupa_auditoria_eventos_24h{acao}` (só contagens). Testes em
  `tests/api/test_metricas_servico.py` (3).
- `docker-compose.yml`, perfil `monitoramento`: `prometheus` (v3.5.0 por digest, `read_only`,
  token por `secrets:` de `LUPA_METRICAS_TOKEN_ARQUIVO`, padrão `.segredos/metricas_token`) e
  `grafana` (12.1.1 por digest, senha do admin por `GF_SECURITY_ADMIN_PASSWORD__FILE`, sem
  cadastro nem anônimo, sem telemetria). Portas `127.0.0.1:9090` e `127.0.0.1:3000`.
- `monitoramento/prometheus/prometheus.yml` e `regras.yml` (`promtool check rules`: 4 regras):
  `LupaFilaParada` (> 30 min), `LupaFalhasDeIngestao` (> 3 em 1 h), `LupaCofreSelado`,
  `LupaApiFora`. Sem Alertmanager (notificação é decisão do responsável).
- Grafana provisionado (`monitoramento/grafana/`): fonte Prometheus e painel **Lupa — piloto**
  (cofre, idade da fila, chamadas e tokens do modelo, jobs por estado, falhas por motivo, eventos
  de auditoria por ação). Prova: alvo `up`, `lupa_cofre_ok 1`, regras `inactive`; captura em
  `docs/imagens/grafana.png` com os dados sintéticos do dev, tirada por
  `monitoramento/capturar_painel.cjs` na imagem do E2E (a senha do Grafana é lida do arquivo de
  segredo dentro do contêiner, sem passar pelo terminal).
- `.segredos/` (token e senha do Grafana) no `.gitignore`.

## 6. Instalação e conferência

- `scripts/instalar_piloto.sh` (produção; `--dev`) e `scripts/instalar_piloto.ps1` (Windows, só
  dev): pré-requisitos e disco (para abaixo de 15 GB) → `.env` (copia o exemplo, pergunta
  domínio/modo do certificado/pastas, gera senhas e tokens aleatórios sem mostrar, zera
  `API_PORTA_HOST` no prod) → pastas com o dono de cada imagem (`sudo install -d`) e
  `.segredos/` → build → Vault (sobe só ele, inicializa) → `up --wait` → `alembic upgrade head` →
  usuário restrito → admin → oferece apagar `LUPA_ADMIN_SENHA` → `conferir_piloto.py`. Idempotente
  (só completa o que falta); confirmação antes de mexer num `.env` existente, criar pastas e
  apagar a senha. **Não foi executado de ponta a ponta** (o dev já está instalado e o fluxo de
  produção precisa de terminal interativo e de `sudo`); sintaxe conferida (`bash -n`, parser do
  PowerShell) e cada comando que ele encadeia rodou nesta etapa.
- `scripts/conferir_piloto.py`: lê `docker compose ps/exec`, `/api/saude`, apertos de mão TLS 1.2
  e 1.3 e contagens no banco (páginas e identidades no formato cifrado); imprime cada item da
  seção 12 como atendido/pendente/manual, mais três extras. Saída no dev (os pendentes 2, 13, 14 e
  E2 são do perfil de desenvolvimento; o 3 é a decisão de não usar TLS interno):

    [atendido]  1. Infraestrutura própria, MinIO local compatível com S3: 8 serviços healthy; MinIO local fixado por digest (assinatura da imagem: docs/decisoes/object-storage.md)
    [pendente]  2. TLS 1.3 entre navegador e servidor: TLS 1.3 ok, mas TLS 1.2 aceito (modo `interno` de dev; acme e fornecido exigem 1.3)
    [pendente]  3. TLS entre serviços: decisão 8.1: redes internas de um host só, sem TLS entre contêineres (operacao.md 4.6)
    [atendido]  4. Criptografia em repouso com chaves no Vault próprio: backend vault; /api/saude cofre=ok (cifra e decifra com lupa-saude)
    [atendido]  5. Texto extraído e índices também cifrados: 306 páginas, todas com texto no formato cifrado (lupa1:)
    [atendido]  6. Arquivo cifrado antes de qualquer parser: por desenho (7.4) e testes de tests/seguranca; worker sem rede externa
    [atendido]  7. Exclusão pela destruição da chave: 7.7; backups guardam o envelope por até 30 dias
    [manual  ]  8. Objetos legados em claro: 344 órfãos em claro mantidos por decisão do responsável técnico
    [atendido]  9. Só processos públicos; sigilo identificado e bloqueado: sigiloso recebe 403 na ingestão (testes da Etapa 4A)
    [atendido] 10. Pseudonimização; tabela de identidades separada e cifrada: 10 identidades, todas cifradas no Transit; leitura auditada
    [manual  ] 11. Contrato do fornecedor do modelo veda treino: conferir os termos da API do modelo (decisão de Victor)
    [atendido] 12. Nenhum dado de autos usado para treinar modelo: não há treino nem ajuste no sistema
    [pendente] 13. Vault em produção (partes, unseal, reinício): destravado e healthcheck exige Sealed false, mas partes=1 limiar=1 (dev; produção: 3 partes, limiar 2)
    [pendente] 14. Porta direta da API e console do MinIO fechados: publicadas: api:127.0.0.1:18000, minio:127.0.0.1:9001 (o perfil prod não publica)
    [atendido] E1. /api/saude com componente cofre: {"api": "ok", "db": "ok", "minio": "ok", "cofre": "ok"}
    [pendente] E2. backup agendado: backup-agendado fora (o perfil prod o liga)
    [atendido] E3. monitoramento: prometheus e grafana healthy
    
    resumo: 10 atendidos, 5 pendentes, 2 manuais

## 7. Documentação

`docs/operacao.md`: 2.1 (variáveis novas), 2.2 (atalho do instalador e ordem nova com o Vault
primeiro), 3 (atualização com o Vault selado), 4 (intro), 4.1 (produção pelo script, 3/2), 4.2
(selado agora detectado; `--so-unseal`), 4.4 (Vault dentro do `.age`, restauração testada), 4.6
(tabela de decisões, TLS interno), 5.1 (três modos), 5.3 (portas), 5.4 (perfil prod), 6 (backup
agendado), 9 (Prometheus/Grafana/alertas, `/saude` com cofre), 12 (checklist atualizado e ligado
ao `conferir_piloto.py`). `README.md` (subida nova, seção "Ambiente de piloto"), `.env.example`
(bloco 8.1), `.gitignore` (`.segredos/`).

## 8. Verificação final

| Verificação | Resultado |
| --- | --- |
| `docker compose up -d --build --wait` (perfil padrão) | 8 serviços `healthy` (+ prometheus e grafana do perfil `monitoramento`, deixados no ar) |
| `docker compose -f docker-compose.yml -f docker-compose.prod.yml config -q` | válido |
| `docker compose exec api bash scripts/verificar.sh` | ok: ruff, format, mypy strict (274 arquivos), **867 passed**, 3 skipped, cobertura **98,28%**; ponta a ponta 1, injeção 2, front (carimbo), cabeçalhos ok em 4 rotas, agente 9 |
| `bash front/scripts/e2e.sh` | **36 passed** |
| `bash scripts/validar_caddyfile.sh` | três modos válidos |
| `promtool check rules` | 4 regras |

Testes de backend: 860 → 867 (+4 em `test_saude.py`, +3 em `test_metricas_servico.py`).

## 9. Fora do escopo ou pendente

- Execução real em servidor: domínio, ACME, certificado fornecido, `instalar_piloto.sh` de ponta a
  ponta, Vault 3/2 com três pessoas e o perfil prod com `LUPA_DADOS_DIR` em outro disco. Só
  validados por `config -q`, `caddy validate`, `bash -n` e um Vault descartável com mlock.
- TLS 1.2 desligado só nos modos `acme`/`fornecido`; em dev continua aceito.
- HSTS mantido em dev (desvio da seção 3, por causa do E2E que não posso editar).
- TLS entre serviços: não adotado (decisão da seção 4).
- Auto-unseal (KMS/HSM): não há KMS; reinício exige dois portadores.
- Notificação de alertas (Alertmanager, e-mail): não configurada.
- Cópia do Vault no backup diário é a quente (escritas raras); a fria fica em `--vault-frio`.
- Itens manuais do checklist: 8 (344 órfãos, decisão do responsável) e 11 (termos do fornecedor
  do modelo).
- `ruff` no host acusa 5 linhas longas em scripts antigos (`medir_extracao.py` etc.), fora do
  `verificar.sh` (que cobre `src` e `tests`); não mexi.
