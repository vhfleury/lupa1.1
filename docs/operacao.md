# Manual de operação do Lupa

Para o responsável técnico. Diz o que fazer, em que ordem e o que conferir. Os detalhes de cada
mecanismo ficam nos documentos citados: [criptografia](criptografia.md), [backup](backup.md),
[auditoria](auditoria.md), [ingestão](ingestao.md), [agente](agente.md), [front](front.md).

Convenções: comandos rodam na raiz do projeto, no host com Docker. `docker compose exec api ...`
roda dentro do contêiner da API. Nos exemplos, `https://lupa.exemplo` é o endereço público (troque
pelo seu); em desenvolvimento é `https://localhost:8443`, e a API fica sob `/api`.

Sumário: 1. Pré-requisitos e dimensionamento · 2. Instalação do zero · 3. Atualização de versão ·
4. Vault · 5. Certificado e portas · 6. Backup e restauração · 7. Descarte de processo e rotação de
chave · 8. Dados sintéticos · 9. Monitoramento · 10. Resposta a incidente · 11. Relatório de uso
para o tribunal · 12. Checklist de segurança (seção 6 dos requisitos) · 13. Ensaios registrados.

---

## 1. Pré-requisitos e dimensionamento

**Software:** Docker Engine com Compose v2 (no Windows, Docker Desktop com WSL 2), `bash` (no
Windows, Git Bash) ou PowerShell 5.1, Python 3 no host só para os scripts do Vault e do backup. Nada
mais é instalado na máquina: tudo roda nos contêineres.

**Serviços:** `proxy` (Caddy, HTTPS), `front` (SPA), `api` (FastAPI), `worker` (ingestão, sem saída
de rede), `db` (PostgreSQL 16), `minio` (S3), `redis` (fila), `vault` (chaves), mais `minio-init`
(cria o bucket e sai) e `backup` (perfil `backup`, só quando chamado).

**Medidas que existem** (revisões 4C e 4F, relatório 4F.9; 1 worker, host com 12 CPUs, lotes de 8
páginas, 4 lotes por job, sandbox de 1024 MB e 60 s de CPU por lote, Tesseract com uma thread):

| Medida | Tempo por mil páginas |
| --- | --- |
| Página nativa (texto no PDF) | 35,8 s |
| Página digitalizada (OCR) | 882 s (4C, 4 lotes) a 912 s (4F) — cerca de 15 min |
| Processo misto real (85–94% OCR), do upload aos achados | 723 a 852 s |
| Mesmo arquivo enviado de novo (cache) | 9 a 26 s |
| Eventos e catálogo | cerca de 2,4 s |
| Cifra em repouso (7.5) | +0,1 a +0,3 s na gravação, +0,05 a +0,08 s na leitura |

Um processo de 5.000 folhas quase todo digitalizado leva cerca de 75 minutos. Os dez processos
sintéticos de referência (15.647 folhas) levaram cerca de 64 minutos de OCR. Diagnóstico de ZIP:
0,8 s por entrada.

**Disco:**

| O quê | Ordem de grandeza | Origem |
| --- | --- | --- |
| Originais no storage | ~100 MB por mil folhas | autos sintéticos: 4,7 GB para 3 × 15.647 folhas, maioria digitalizada |
| Cache do visualizador (PNG) | cresce com as páginas abertas | não medido |
| Banco, páginas cifradas | 6 a 8 KB por página nativa (6 a 8 MB por mil) | medido na base de desenvolvimento |
| Auditoria | ~1,1 GB por milhão de eventos | base de desenvolvimento com 1 milhão de eventos de carga |
| Backup | precisa de 2 × (banco + bucket) + 2 GB livres no destino | regra do script (7.8) |
| Imagens Docker e cache de build | 15 a 25 GB | `docker system df` na máquina de desenvolvimento |

**Recomendação para o piloto** (não medida em produção; deriva das medidas acima): 8 CPUs ou mais
para o worker (o OCR é o gargalo, cada lote usa uma CPU), 16 GB de RAM (4 lotes × 1 GB de sandbox
no worker, mais banco, MinIO e o resto), 200 GB de disco para dados e mais o mesmo tanto, em
**outro disco**, para backups. Pare e libere espaço abaixo de 15 GB livres (incidente da seção 10.4).

---

## 2. Instalação do zero

### 2.1 Arquivo `.env`

```bash
cp .env.example .env
chmod 600 .env
```

O `.env` nunca entra no git (`scripts/preparar_repositorio.md`). Troque **todos** os valores
fictícios. Variáveis (as marcadas **segredo** dão acesso a dados; guarde-as num cofre de senhas):

| Variável | Para quê | Segredo |
| --- | --- | --- |
| `LUPA_AMBIENTE` | `producao` no piloto (`desenvolvimento`/`teste` liberam scripts de teste e o cofre em memória) | não |
| `LUPA_LOG_LEVEL` | `INFO` | não |
| `POSTGRES_USER`, `POSTGRES_DB` | dono das tabelas e nome do banco | não |
| `POSTGRES_PASSWORD` | senha do dono das tabelas (migrações e scripts) | **sim** |
| `LUPA_DATABASE_URL` | URL do dono, usada por scripts e migrações (repete a senha) | **sim** |
| `LUPA_DB_USUARIO_APP` | usuário de conexão da API e do worker, sem superusuário | não |
| `LUPA_DB_SENHA_APP` | senha dele | **sim** |
| `LUPA_MINIO_ENDPOINT`, `LUPA_MINIO_BUCKET`, `LUPA_MINIO_SECURE` | endereço, bucket, TLS do S3 | não |
| `LUPA_MINIO_ACCESS_KEY` | usuário raiz do MinIO | **sim** |
| `LUPA_MINIO_SECRET_KEY` | senha raiz do MinIO | **sim** |
| `LUPA_TIMEOUT_SAUDE_SEGUNDOS` | tempo de cada checagem do `/saude` | não |
| `API_PORTA_HOST` | porta direta da API no host; **vazia em produção** (seção 5.3) | não |
| `MINIO_CONSOLE_PORTA_HOST` | console do MinIO em `127.0.0.1` | não |
| `PROXY_PORTA_HOST` | porta HTTPS do proxy (em produção, 443) | não |
| `REDE_BORDA_SUBREDE` | sub-rede de onde a API aceita `X-Forwarded-For` | não |
| `LUPA_GEOIP_CAMINHO` | base GeoLite2 (sem ela, local "desconhecida") | não |
| `LUPA_ADMIN_USUARIO` | nome do administrador inicial | não |
| `LUPA_ADMIN_SENHA` | senha inicial do administrador; **apague do `.env` depois do primeiro login** | **sim** |
| `LUPA_COFRE_BACKEND` | `vault` (o `memoria` é recusado em produção) | não |
| `LUPA_VAULT_ROLE_ID` | identificador do AppRole da aplicação | não (sozinho não abre nada) |
| `LUPA_VAULT_SECRET_ID` | credencial do AppRole: com o `role_id`, decifra qualquer processo | **sim** |
| `ANTHROPIC_API_KEY` | chave do modelo; **nunca** no `.env` versionado, só no ambiente | **sim** |
| `LUPA_MODELO`, `LUPA_AGENTE_*` | modelo e tetos do agente | não |
| `LUPA_STORAGE_BACKEND`, `LUPA_REDIS_URL`, `LUPA_UPLOAD_LIMITE_BYTES`, `LUPA_SANDBOX_*`, `LUPA_ZIP_*`, `LUPA_LEASE_SEGUNDOS`, `LUPA_MAX_TENTATIVAS` | limites da ingestão (padrões bons) | não |
| `LUPA_BUSCA_MAX_PAGINAS`, `LUPA_VAULT_*` | busca cifrada e conexão com o Vault | não |
| `LUPA_BACKUP_DIR` | pasta dos backups (outro disco) | não |
| `LUPA_BACKUP_CHAVES_DIR` | chaves `age` dos backups (fora da pasta de backup, de preferência outro disco ou cofre) | **sim** (a pasta) |
| `LUPA_BACKUP_RETENCAO_DIAS` | retenção dos backups (30) | não |
| `STORAGE_IMAGEM` | imagem do object storage (`docs/decisoes/object-storage.md`) | não |
| `LUPA_TLS_MODO`, `LUPA_DOMINIO`, `LUPA_ACME_EMAIL`, `LUPA_TLS_CERT`, `LUPA_TLS_CHAVE` | certificado do proxy (seção 5.1) | não (o arquivo da chave fornecida é: permissão 600) |
| `LUPA_DADOS_DIR` | pasta dos volumes no perfil prod (outro disco) | não |
| `LUPA_BACKUP_CRON_DIARIO`, `LUPA_BACKUP_CRON_EXPURGO` | horários do `backup-agendado` | não |
| `LUPA_METRICAS_TOKEN` | token do Prometheus em `GET /metricas/servico`; mesmo valor em `.segredos/metricas_token` | **sim** |
| `LUPA_API_CPUS`, `LUPA_API_MEMORIA`, `LUPA_WORKER_CPUS`, `LUPA_WORKER_MEMORIA`, `LUPA_DB_MEMORIA`, `LUPA_LOG_MAX_SIZE`, `LUPA_LOG_MAX_FILE` | limites do perfil prod | não |
| `LUPA_PROXY_URL`, `LUPA_EXIGIR_CABECALHOS`, `LUPA_VERIFICAR_E2E`, `LUPA_VERIFICAR_BACKUP`, `LUPA_BACKUP_ESTIMATIVA_BYTES` | só verificação e testes | não |

### 2.2 Ordem dos comandos

**Atalho (Etapa 8.1):** `bash scripts/instalar_piloto.sh` encadeia os passos abaixo em produção
(`--dev` para desenvolvimento; no Windows, `powershell -File scripts/instalar_piloto.ps1`, só
desenvolvimento). Ele cria o `.env` a partir do exemplo, pergunta domínio, modo do certificado,
pastas de dados e de backup, gera os segredos aleatórios sem mostrá-los, cria as pastas com o dono
de cada imagem, sobe o Vault e o inicializa, sobe o resto, migra, cria o usuário restrito e o
administrador e no fim roda `scripts/conferir_piloto.py`. É idempotente (rodar de novo só completa
o que falta) e pede confirmação antes de alterar um `.env` existente, criar pastas e apagar
`LUPA_ADMIN_SENHA`. `LUPA_SIM=1` responde "sim" às confirmações (não às perguntas de valor nem
às partes do Vault).

À mão, em produção (`export COMPOSE_FILE=docker-compose.yml:docker-compose.prod.yml` antes; em
desenvolvimento, sem a variável):

```bash
# 1. construir e subir só o Vault (ele fica "unhealthy" até o unseal, e a api espera por ele)
docker compose build
docker compose up -d vault

# 2. inicializar o Vault (produção: 3 partes, limiar 2, seção 4.1; desenvolvimento: 1 parte)
bash scripts/vault_inicializar.sh          # Windows (dev): powershell -File scripts/vault_inicializar.ps1

# 3. subir o resto
docker compose up -d --wait

# 4. migrar o banco
docker compose exec api alembic -c src/lupa/migrations/alembic.ini upgrade head
docker compose exec api alembic -c src/lupa/migrations/alembic.ini current   # deve mostrar (head)

# 5. usuário de banco restrito (LUPA_DB_USUARIO_APP / LUPA_DB_SENHA_APP)
docker compose exec api python scripts/criar_usuario_banco.py
docker compose up -d --wait api worker     # passam a conectar com ele

# 6. administrador (LUPA_ADMIN_USUARIO / LUPA_ADMIN_SENHA)
docker compose exec api python scripts/criar_admin.py
# depois: apague LUPA_ADMIN_SENHA do .env
```

7. **Primeiro acesso do administrador**, pelo navegador em `https://lupa.exemplo`: senha inicial →
   cadastro do autenticador (QR) → troca obrigatória de senha.
8. **Gabinete**: tela de administração → Gabinetes → novo (ou `POST /api/gabinetes`
   `{"nome": "..."}`). Isso cria as duas chaves do gabinete no Vault.
9. **Desembargador**: Usuários → novo, papel `desembargador`, gabinete do passo 8 (ou
   `POST /api/usuarios` `{"nome_usuario", "papel": "desembargador", "gabinete_id"}`). A senha
   temporária aparece **uma vez**; entregue pessoalmente. O desembargador cria os assessores.

Conferência final: `curl -k https://lupa.exemplo/api/saude` responde
`{"api":"ok","db":"ok","minio":"ok","cofre":"ok"}`; `docker compose ps` mostra os serviços
`healthy` (o `vault` só fica `healthy` destravado); `python scripts/conferir_piloto.py --url
https://lupa.exemplo` imprime o checklist da seção 12 item a item.

---

## 3. Atualização de versão

1. Faça um backup (seção 6) e confira que o arquivo saiu.
2. Atualize o código e o `.env` (compare com o `.env.example` novo: variáveis novas vêm comentadas
   com o padrão).
3. Reconstrua e suba. Se o contêiner do Vault for recriado (imagem ou configuração nova), ele
   volta **selado** e fica `unhealthy`, e a `api` espera por ele: faça o unseal (seção 4.2) e
   repita o `up`.
   ```bash
   docker compose build
   docker compose up -d vault && bash scripts/vault_inicializar.sh --so-unseal
   docker compose up -d --wait
   ```
4. Confira `curl -k https://lupa.exemplo/api/saude` com `"cofre":"ok"` antes do passo 5.
5. Migre e confira:
   ```bash
   docker compose exec api alembic -c src/lupa/migrations/alembic.ini upgrade head
   docker compose exec api alembic -c src/lupa/migrations/alembic.ini current
   ```
   Migrações que cifram dados existentes (como a 0010) precisam do cofre destravado.
6. Verifique:
   ```bash
   docker compose exec api bash scripts/verificar.sh   # lint, tipos, testes, cabeçalhos, injeção
   curl -k https://lupa.exemplo/api/saude
   ```
   Abra um processo no navegador e uma página no visualizador (prova que a API decifra).
7. Se algo falhar: `docker compose logs api worker --since 10m`. Para voltar: código anterior,
   `alembic downgrade <revisão anterior>` (as migrações têm downgrade) ou restauração do backup.

---

## 4. Vault

O Vault guarda as chaves dos gabinetes. Sem ele destravado, **nada** dos autos pode ser lido nem
gravado (a API responde erro 500 nas rotas de processo e 503 no `/saude`; login continua
funcionando).

### 4.1 Inicialização em produção

Com `LUPA_AMBIENTE=producao` no `.env`, o mesmo `scripts/vault_inicializar.sh` (só a versão bash;
o `.ps1` é só desenvolvimento) entra em modo produção:

```bash
docker compose up -d vault
bash scripts/vault_inicializar.sh
```

1. `vault operator init -key-shares=3 -key-threshold=2`. Cada uma das 3 partes aparece **uma vez**,
   numa tela limpa, para **uma pessoa diferente** (Victor e mais duas de confiança) guardar no
   próprio cofre de senhas; a tela é limpa antes da próxima. Nada é gravado em disco, nem em
   variável exportada. Com 2 partes o cofre abre; ninguém sozinho abre.
2. Unseal: dois portadores digitam a sua parte (sem eco).
3. Com o token raiz **só em memória**: Transit, AppRole, chave de verificação `lupa-saude`,
   política `lupa` e papel `lupa`; `role_id` e um `secret_id` novo vão para o `.env`.
4. O token raiz é **revogado** no fim. Um token raiz novo só nasce com
   `vault operator generate-root` e o quórum; o script, rodado de novo com o cofre já
   inicializado, pede um token desses (sem eco) para gerar um `secret_id` novo.

Endurecimento opcional do papel (à mão, com um token gerado pelo quórum):
`vault write auth/approle/role/lupa ... secret_id_bound_cidrs=<sub-rede interna>
token_bound_cidrs=<sub-rede interna>`.

Em produção o Vault roda com `vault/producao/lupa.hcl` (mlock ligado, `cap_add: IPC_LOCK`).

### 4.2 Unseal depois de reinício

**Qualquer** reinício do contêiner `vault` (reboot do host, reinício do Docker, atualização) sela o
cofre. Desde a 8.1 isso aparece sozinho:

- o healthcheck do `vault` é `vault status` (sai com 2 se selado): `docker compose ps` mostra
  `vault` como `unhealthy`;
- `GET /api/saude` responde **503** com `"cofre":"falha"` (o componente `cofre` cifra e decifra um
  valor de teste pela chave Transit `lupa-saude`); em seguida a `api` e o `proxy` ficam
  `unhealthy`;
- o alerta `LupaCofreSelado` do Prometheus dispara em 2 minutos (seção 9).

Unseal:

- Desenvolvimento: `bash scripts/vault_inicializar.sh --so-unseal` (sem a opção, também gera um
  `secret_id` novo).
- Produção: `bash scripts/vault_inicializar.sh --so-unseal` com dois portadores, cada um digitando
  a sua parte (sem eco). Equivalente manual: `docker compose exec vault vault operator unseal`
  duas vezes.

A API e o worker voltam a decifrar sozinhos (fazem login de novo com o AppRole se o token
expirou). Não é preciso reiniciá-los. Confira com `curl -k https://lupa.exemplo/api/saude`.

**Procedimento de reinício planejado** (atualização, manutenção do host): avise os usuários →
`docker compose stop` → manutenção → `docker compose up -d vault` → unseal com o quórum →
`docker compose up -d --wait` → `/api/saude`. Combine antes quem são os portadores disponíveis.

### 4.3 Rotação da chave do gabinete

```bash
curl -k -X POST -b <cookie do administrador> https://lupa.exemplo/api/gabinetes/<id>/rotacionar-chave
# {"gabinete_id": "...", "deks_recifradas": N}
```

Cria uma versão nova da chave do gabinete e reenvelopa (rewrap, dentro do Vault) a DEK de cada
processo do gabinete. Os dados **não** são recifrados: continuam com a mesma DEK. Use em rotina
(sugestão: a cada 12 meses) e em incidente (seção 10.3). Evento `chave_rotacionada` na auditoria.
As versões antigas continuam no Vault (o Transit decifra versões anteriores); para aposentá-las,
`vault write transit/keys/lupa-gabinete-<id>/config min_decryption_version=<n>` depois de conferir
que todas as DEKs estão na versão nova (`chave_dados_cifrada` começa com `vault:v<n>:`).

### 4.4 Backup do Vault

Desde a 8.1 o **armazenamento do Vault entra no `.age` diário** (`vault.tar` dentro do arquivo,
conferido pelo manifesto): o serviço de backup monta o volume `vault-dados` só leitura. O
conteúdo já é cifrado pela barreira do Vault: sem as partes de unseal, não serve. A cópia é a
quente (o Vault só grava ao criar, rotacionar ou apagar chave e ao emitir token, eventos raros);
para uma cópia **fria** garantida (antes de uma atualização, por exemplo):

```bash
bash scripts/backup.sh --vault-frio     # para o vault, faz o backup, sobe o vault (selado!)
bash scripts/vault_inicializar.sh --so-unseal
```

**Restaurar o Vault** (testado em desenvolvimento em 21/10/2026, relatório 8.1):

1. `restaurar.sh` deixa o armazenamento em `LUPA_BACKUP_DIR/vault-<arquivo>.tar` (não repõe
   sozinho);
2. `docker compose stop vault api worker`;
3. esvazie o volume e extraia o tar nele, com o dono do Vault (uid 100):
   `docker run --rm -v lupa_vault-dados:/v -v "<LUPA_BACKUP_DIR>":/b:ro alpine:3.20 sh -c
   'rm -rf /v/* && tar -C /v -xf /b/vault-<arquivo>.tar && chown -R 100:1000 /v'`;
4. `docker compose up -d vault` e unseal com as partes **da época do backup**;
5. `docker compose up -d --wait`; confira `/api/saude` e abra um processo;
6. apague o `vault-<arquivo>.tar` extraído.

Guarde as partes de unseal **separadas** dos backups.

### 4.5 Se perder as partes do unseal

Abaixo do limiar (menos de 3 de 5), o cofre não abre nunca mais e **todos os autos cifrados ficam
ilegíveis**, inclusive nos backups. Não há recuperação. O que fazer:

1. Se ainda há quórum: gere partes novas já (`vault operator rekey`) e redistribua.
2. Se não há quórum: trate como perda total dos dados cifrados. Comunique o gabinete, reinstale o
   Vault (seção 4.1), recrie os gabinetes e reenvie os autos a partir das cópias do tribunal. A
   trilha de auditoria (que não é cifrada com a DEK) continua legível.

### 4.6 Pendências e decisões para produção

| Item | Estado | Observação |
| --- | --- | --- |
| Partes divididas entre pessoas | **feito (8.1)** | 3 partes, limiar 2, `vault_inicializar.sh` em modo produção (4.1) |
| Auto-unseal com KMS/HSM | fora do piloto | sem KMS externo; o reinício exige dois portadores (4.2) |
| Procedimento de reinício | documentado (4.2) | combinar os portadores |
| Detectar cofre selado | **feito (8.1)** | healthcheck, `/saude` com `cofre`, alerta `LupaCofreSelado` |
| Token raiz revogado | **feito (8.1)** | o script revoga ao fim |
| mlock | **feito (8.1)** | `vault/producao/lupa.hcl`, `cap_add: IPC_LOCK` |
| Backup do Vault | **feito (8.1)** | dentro do `.age` diário (4.4) |
| `secret_id` com `bound_cidrs` | opcional | 4.1 |
| TLS no listener do Vault | **decidido: não no piloto** | ver abaixo |

**Decisão (8.1): sem TLS entre API/worker e Vault.** O Vault escuta só nas redes `interna` e
`ingestao` do compose, num único host, sem porta publicada; o tráfego não sai da ponte do Docker
do próprio host. Quem consegue observar essa ponte já é root no host e, então, lê também o `.env`
com o `secret_id` e a memória dos processos: o TLS não acrescentaria proteção real contra esse
atacante. O custo é concreto: uma CA interna para gerar, distribuir para a API e o worker e
renovar antes do vencimento (um certificado vencido deixa, na prática, todos os autos
ilegíveis), e mais um ponto de falha no reinício. Reavaliar se o Vault sair do host da aplicação
(Vault compartilhado do tribunal ou outro servidor): aí o TLS é obrigatório
(`tls_cert_file`/`tls_key_file` no `lupa.hcl`, `LUPA_VAULT_ENDERECO=https://...`, CA confiada pela
API e pelo worker).

---

## 5. Certificado e portas

### 5.1 Certificado do proxy (modos)

O `proxy/Caddyfile` escolhe o modo por `LUPA_TLS_MODO` (arquivos em `proxy/modos/`):

| Modo | Quando | Variáveis | HSTS | TLS |
| --- | --- | --- | --- | --- |
| `interno` (padrão do compose base) | desenvolvimento | nenhuma | enviado (o E2E exige), ignorado pelo navegador com certificado não confiável | 1.2 e 1.3 |
| `acme` (padrão do perfil prod) | domínio público | `LUPA_DOMINIO`, `LUPA_ACME_EMAIL` | sim | só 1.3 |
| `fornecido` | CA do órgão ou certificado comprado | `LUPA_DOMINIO`, `LUPA_TLS_CERT`, `LUPA_TLS_CHAVE` | sim | só 1.3 |

- **`acme`:** DNS do domínio apontando para o host e portas 80 e 443 abertas (o perfil prod
  publica `443→8443` e `80→8080`; a 80 serve o desafio HTTP-01 e o redirecionamento para HTTPS).
  O Caddy emite e renova sozinho; os dados do ACME ficam no volume `caddy-dados` (para não esbarrar
  nos limites de emissão a cada reinício).
- **`fornecido`:** `LUPA_TLS_CERT` (cadeia completa, PEM) e `LUPA_TLS_CHAVE` (PEM, permissão 600)
  são caminhos no host, montados só leitura em `/certs`. Renove antes do vencimento e rode
  `docker compose restart proxy`.

Validação dos três modos sem subir nada: `bash scripts/validar_caddyfile.sh` (`caddy validate` em
contêiner). Depois de subir: `python scripts/verificar_cabecalhos.py --url https://lupa.exemplo
--exigir` e `python scripts/conferir_piloto.py --url https://lupa.exemplo` (o item 2 confere que
só TLS 1.3 é aceito).

### 5.2 Efeito do HSTS

O proxy manda `Strict-Transport-Security: max-age=31536000; includeSubDomains`. Com certificado
válido, o navegador passa a recusar HTTP e certificado inválido para o domínio **e subdomínios**
por um ano. Antes de ligar em produção, confirme que todos os subdomínios do domínio têm HTTPS
válido. Com o certificado autoassinado de desenvolvimento o navegador ignora o HSTS.

### 5.3 Portas

O perfil prod (`docker-compose.prod.yml`) **não publica porta nenhuma além do proxy** (443 e 80):
a porta direta da API (`API_PORTA_HOST` é ignorada) e o console do MinIO deixam de existir. Motivo:
quem alcança a API sem passar pelo proxy pode forjar `X-Forwarded-For` (e com isso o IP da
auditoria). Prometheus e Grafana (perfil `monitoramento`) ficam em `127.0.0.1`; acesse por túnel
SSH (`ssh -L 3000:127.0.0.1:3000 host`). Em desenvolvimento a API continua numa porta de
`127.0.0.1`.

### 5.4 Perfil de produção

`docker compose -f docker-compose.yml -f docker-compose.prod.yml ...` (ou `COMPOSE_FILE`):
`restart: unless-stopped` em tudo, limites de CPU e memória por serviço (variáveis
`LUPA_*_CPUS`/`LUPA_*_MEMORIA`), logs `json-file` com rotação (10 MB × 5 por contêiner),
`read_only` em front, proxy, redis e backup-agendado (o prometheus também, no compose base), Vault
com mlock e volumes em `LUPA_DADOS_DIR/<volume>` (crie com o dono da imagem: db 70, minio 10002,
vault 100, caddy 10001, prometheus 65534, grafana 472; o `instalar_piloto.sh` faz). API, worker,
banco, MinIO e Vault não são `read_only`: gravam em `/tmp` (uploads de até 512 MB, temporários do
worker), em diretórios de execução da imagem ou, no Vault, no binário (setcap do mlock).

---

## 6. Backup e restauração

Detalhes em [backup.md](backup.md). Resumo operacional:

1. **Diário:** no perfil prod, o serviço `backup-agendado` (crond do BusyBox na imagem do backup)
   roda `backup_conteiner.sh fazer` às 02:00 UTC e `expurgar` aos domingos 03:30 UTC
   (`LUPA_BACKUP_CRON_DIARIO`/`_EXPURGO`), gravando em `LUPA_BACKUP_DIR` e registrando em
   `cron.log`. O `.age` leva banco, objetos e o armazenamento do Vault (4.4). Sem o perfil prod:
   cron do host,
   `0 2 * * * cd /caminho/Lupa1 && bash scripts/backup.sh && bash scripts/expurgar_backups.sh`.
2. **Conferir:** `tail .backups/backup.log` (estimativa, livre, exigido e `gravado ...`) e
   `docker compose --profile backup run --rm -T backup /scripts/backup_conteiner.sh listar`.
3. **Restaurar** (sempre em banco e bucket **novos**, e só com o Vault da mesma época destravado):
   ```bash
   LUPA_RESTAURAR_BANCO=lupa_restaurado LUPA_RESTAURAR_BUCKET=lupa-restaurado \
     bash scripts/restaurar.sh lupa-AAAA-MM-<carimbo>.tar.age
   ```
   Para pôr em uso: aponte `POSTGRES_DB`/`LUPA_DATABASE_URL` e `LUPA_MINIO_BUCKET` para os
   restaurados, recrie o usuário restrito (`criar_usuario_banco.py`), `docker compose up -d api
   worker`, abra um processo. Teste a restauração uma vez por mês (`LUPA_VERIFICAR_BACKUP=1`).
4. **Expurgo e chaves de período:** backups com mais de 30 dias saem; a chave `age` de um mês sem
   backup vivo é sobrescrita e apagada, com linha encadeada em `destruicoes.log`.
5. **Espaço:** o script recusa sem `2 × estimativa + 2 GB` livres no destino. Nunca rode backup de
   teste contra o banco e o bucket principais na mesma partição do sistema (incidente da 7.8).

**O que o backup não cobre:**

- **As partes de unseal.** O armazenamento do Vault vai no `.age` (seção 4.4), mas só abre com
  as partes da época.
- **O `.env` e `.segredos/`.** Ficam nos cofres de senha das pessoas.
- **Processos descartados dentro da janela.** Um backup feito antes de um descarte ainda tem o
  envelope da DEK do processo. Enquanto esse backup existir (até 30 dias) e a chave do gabinete
  daquela versão existir no Vault, o processo descartado pode ser recuperado dele. O descarte só é
  definitivo para os backups quando eles expiram e a chave do período é destruída. Se o descarte
  precisar ser imediato também nos backups, apague os backups anteriores a ele e registre.
- **Cópias fora de `LUPA_BACKUP_DIR`** (cópias manuais, sincronização em nuvem): ficam por sua conta.

---

## 7. Descarte de processo e rotação de chave

- **Descarte** (exclusão criptográfica): `POST /api/processos/<id>/descartar`, desembargador do
  gabinete ou administrador (na interface: processo → Descartar). Apaga conteúdo, a DEK cifrada e
  os objetos do storage; o processo vira tombstone `descartado` e some das rotas. Evento
  `processo_descartado` com o SHA-256 do envelope apagado. Irreversível, salvo pela janela de
  backup da seção 6.
- **Rotação da chave do gabinete:** seção 4.3. Rotação não substitui descarte: quem já tinha a DEK
  aberta em memória ou um backup antigo continua tendo o que tinha.
- **Objetos legados em claro** (gravados antes da 7.4): `docker compose exec api python
  scripts/recifrar_objetos_legado.py` simula; com `--executar` recifra com a DEK do processo e
  confere cada objeto. Idempotente. Objetos em claro de processos que não existem mais no banco
  aparecem como `sem DEK` e não são tocados: são órfãos, apague-os depois de conferir.

---

## 8. Dados sintéticos

Nunca há dado sintético em produção. No ambiente de desenvolvimento (ou num piloto que tenha usado
processos sintéticos de treinamento):

```bash
docker compose exec api python scripts/limpar_dev.py         # mostra o que sairia
docker compose exec api python scripts/limpar_dev.py --sim   # remove
```

Recusa fora de `desenvolvimento`/`teste`. Remove os gabinetes cujo nome começa por um prefixo
sintético (calibração, ponta a ponta, carga, E2E), seus eventos de auditoria, descarta cada
processo pelo caminho da 7.7, apaga os objetos e destrói as chaves Transit do gabinete. Antes do
piloto, rode e confira que não sobrou gabinete de teste (`GET /api/gabinetes`).

---

## 9. Monitoramento

- **`GET /api/saude`** (sem login): `{"api","db","minio","cofre"}`; 503 se algum falhar. O
  `cofre` só é `ok` se o Vault responde e decifra o valor de teste (chave `lupa-saude`). Não
  checa o Redis (o healthcheck do worker faz).
- **Prometheus e Grafana** (perfil `monitoramento`):
  `docker compose --profile monitoramento up -d` (no prod, com o `COMPOSE_FILE` do perfil).
  - O Prometheus raspa `GET /metricas/servico` da API, direto na rede interna, a cada 30 s, com
    `Authorization: Bearer` lido do arquivo de segredo `LUPA_METRICAS_TOKEN_ARQUIVO` (padrão
    `.segredos/metricas_token`, mesmo valor de `LUPA_METRICAS_TOKEN` no `.env`). Sem o token
    configurado, a rota responde 404. Ela devolve as métricas de ingestão abaixo e mais
    `lupa_cofre_ok`, `lupa_modelo_chamadas_24h`, `lupa_modelo_tokens_24h{tipo}` e
    `lupa_auditoria_eventos_24h{acao}` (só contagens; nenhum id, nome ou texto). O token é de
    serviço, não de usuário: o Prometheus não faz login com senha e TOTP.
  - Grafana em `http://127.0.0.1:3000` (usuário `admin`, senha em `.segredos/grafana_senha`),
    painel provisionado **Lupa — piloto**: cofre, idade da fila, chamadas e tokens do modelo,
    jobs por estado, falhas por motivo, eventos de auditoria por ação
    ([captura](imagens/grafana.png)).
  - Alertas (`monitoramento/prometheus/regras.yml`, visíveis em `http://127.0.0.1:9090/alerts`):
    `LupaFilaParada` (job em `recebido` há mais de 30 min), `LupaFalhasDeIngestao` (mais de 3
    falhas ou quarentenas em 1 h), `LupaCofreSelado` (2 min), `LupaApiFora` (5 min). Não há
    Alertmanager no piloto: ligar notificação (e-mail, chat) é decisão do responsável técnico.
- **`GET /api/metricas`** (administrador logado, formato Prometheus): só a ingestão,
  `lupa_ingestao_jobs{estado}`, `lupa_ingestao_lotes{estado}`, `lupa_ingestao_idade_fila_segundos`,
  `lupa_ingestao_paginas`, `lupa_ingestao_paginas_por_segundo`, `lupa_ingestao_retries`,
  `lupa_ingestao_falhas{tipo,motivo}`.
- **`docker compose ps`**: todos `healthy` (o `vault` só destravado).
- **Disco:** `df -h` e `docker system df`; alarme abaixo de 15 GB.
- **Logs:** JSON por linha (`docker compose logs api worker`), campos `event`, `level`,
  `timestamp`, ids (`job_id`, `processo_id`, lote, estado, motivo). No perfil prod, rotação de
  10 MB × 5 arquivos por contêiner. Avisos úteis: `objeto_legado_em_claro`, `CofreError` (Vault
  selado ou fora), falhas de job.
- **Nunca aparece em log** (e se aparecer é incidente): texto dos autos, nome ou CPF de réu,
  texto de pergunta ou resposta do chat, senha, token, segredo TOTP, `secret_id`, DEK, chave de
  API. O logger recusa os campos `senha`, `password`, `token`, `texto`, `conteudo`, `pergunta`,
  `resposta`; a auditoria guarda só identificadores e hashes.
- **Auditoria:** tela Auditoria → Verificar cadeia (ou `GET /api/auditoria/verificar`), uma vez
  por semana e depois de qualquer incidente.

---

## 10. Resposta a incidente

Regra geral para todos: (1) conter, (2) preservar evidência (não apague logs nem eventos; exporte
a auditoria do período em CSV), (3) corrigir, (4) verificar a cadeia de auditoria, (5) registrar em
`docs/incidentes/AAAA-MM-DD-<tipo>.md` (o que, quando, quem, o que foi feito, horários).

**Comunicação (LGPD).** O fornecedor é o controlador dos dados pessoais dos autos perante a LGPD
(`requisitos-v1.md`, seção 2). Os requisitos **não fixam** prazos nem a forma de comunicar
incidente à autoridade nacional e aos titulares. Até que Victor defina isso com o jurídico (entra
nos documentos da subetapa 8.2), a regra operacional é: incidente com dado pessoal confirmado ou
provável → avisar Victor e o desembargador do gabinete **no mesmo dia**, com o registro acima, para
que a comunicação legal seja feita no prazo que a norma vigente exigir.

### 10.1 Vazamento suspeito (disco, dump, bucket, backup ou log)

1. Identifique o que saiu: banco (colunas de autos cifradas com DEK; identidades cifradas no
   Vault; auditoria e metadados em claro), bucket (objetos `LUPAOBJ`; confira se havia legado em
   claro com `recifrar_objetos_legado.py`), backup (cifrado com `age`), log (não deve ter conteúdo).
2. Se só saiu dado cifrado e o Vault e o `.env` estão íntegros: o conteúdo não é legível. Ainda
   assim troque as credenciais que estavam na mesma máquina (10.3) e rotacione as chaves dos
   gabinetes afetados.
3. Se saiu o `.env`, o `secret_id` ou uma parte de unseal junto com os dados: trate como vazamento
   de conteúdo. Revogue o `secret_id` (10.3), rotacione as chaves, avalie o descarte e o reenvio
   dos processos afetados e siga a comunicação acima.
4. Exporte a auditoria do período e verifique a cadeia.

### 10.2 Incidente de injeção (processo em revisão)

Quando a conferência bloqueia uma resposta do modelo (instrução refletida ou dado de outro
processo), o processo vai para `em_revisao` sozinho: chat e resumos ficam suspensos e a tela avisa.

1. Tela Auditoria, filtro pelo processo: eventos `chamada_modelo` com resultado `bloqueado` e
   `processo_em_revisao` (quem, quando).
2. Desembargador abre o processo, lê o aviso, localiza a página com o texto suspeito (o relatório
   de qualidade da ingestão mostra as flags de injeção por página) e decide.
3. Se for falso alarme ou o texto estiver identificado: **Liberar revisão** (desembargador do
   gabinete ou administrador; `POST /api/processos/<id>/liberar-revisao`). Evento `revisao_liberada`.
4. Se houver indício de ataque dirigido (peça plantada nos autos): mantenha em revisão, avise
   Victor, guarde o hash do arquivo (`arquivo.sha256`) e o número da página; nada do texto vai
   para log ou e-mail.

### 10.3 Comprometimento de credencial

**Usuário (assessor, desembargador):**

1. `POST /api/usuarios/<id>/resetar-senha` — senha temporária nova e **revoga todas as sessões**
   do usuário (não há rota só para revogar sessão: o reset de senha, o de MFA e a desativação
   revogam).
2. `POST /api/usuarios/<id>/resetar-mfa` — apaga o autenticador; o próximo login cadastra outro.
   Se não houver como entregar a senha nova com segurança agora, use `.../desativar`.
3. Rotacione a chave do gabinete (4.3) se a credencial pode ter sido usada para ler autos.
4. Auditoria do usuário no período (`GET /api/auditoria/relatorio-uso?usuario=<id>` e a tela com
   filtro por usuário): o que foi aberto, de que IP.

**Administrador:** outro portador com acesso ao banco reseta via script de instalação só em último
caso; prefira manter dois administradores nominais no piloto. Revise eventos `admin_acesso_conteudo`.

**Segredos de infraestrutura:**

| Segredo | Como trocar |
| --- | --- |
| `LUPA_VAULT_SECRET_ID` | `vault write -f auth/approle/role/lupa/secret-id` (novo), atualize o `.env`, `docker compose up -d api worker`, depois destrua o antigo com `vault write auth/approle/role/lupa/secret-id-accessor/destroy secret_id_accessor=<accessor>` (liste com `vault list auth/approle/role/lupa/secret-id`) |
| `LUPA_DB_SENHA_APP` | troque no `.env`, `criar_usuario_banco.py` (atualiza a senha), `docker compose up -d api worker` |
| `POSTGRES_PASSWORD` | `ALTER ROLE` no banco, atualize `.env` e `LUPA_DATABASE_URL` |
| Chaves do MinIO | troque no `.env` e recrie `minio`, `minio-init`, `api`, `worker` |
| Chave `age` de backup | apague backups do período e gere chave nova (a próxima execução cria) |
| Parte de unseal | `vault operator rekey` com o quórum |
| `ANTHROPIC_API_KEY` | revogue no console do fornecedor e gere outra |

### 10.4 Disco cheio (incidente da Etapa 7.8)

O que aconteceu: um backup de teste contra o banco principal (1 milhão de eventos) e o bucket
cheio gravou dentro da camada de um contêiner e encheu o disco C:. Docker e WSL travaram.

Sequência que funcionou (Windows com Docker Desktop):

1. Pare quem estiver escrevendo (backup, ingestão grande), se ainda responder.
2. `wsl --shutdown` (PowerShell; derruba o Docker Desktop e libera a VM).
3. Libere espaço **fora** dos volumes do Docker (downloads, pastas temporárias, `.sinteticos`
   sincronizando no OneDrive).
4. Relance o Docker Desktop e espere ficar pronto.
5. `docker compose up -d --wait` — os volumes nomeados (`db-dados`, `minio-dados`,
   `vault-dados`) são preservados.
6. **Unseal do Vault** (4.2) — o reinício selou o cofre.
7. Confira: `docker compose ps` (todos `healthy`), `alembic current`, abrir um processo, verificar
   a cadeia de auditoria.
8. Só então limpe espaço do Docker sem tocar em volumes: `docker builder prune`,
   `docker image prune`. **Nunca** `docker volume prune` nem `docker system prune --volumes`.

Prevenção: o backup recusa sem espaço; nada grande em camada de contêiner; alarme abaixo de 15 GB.

---

## 11. Relatório de uso para o tribunal

O magistrado tem de informar ao tribunal o uso da ferramenta (Res. CNJ 615/2025, art. 19, §7º,
conforme os requisitos). Como gerar:

- **Pela interface** (desembargador ou administrador): Auditoria → Relatório de uso → Por processo
  ou por usuário → identificador → Gerar. Mostra contagem por ação, primeiro e último acesso,
  versões do modelo e do prompt e custo estimado. Ver `guia-desembargador.md`, seções 5 e 6.
- **Pela API:** `GET /api/auditoria/relatorio-uso?processo=<id>` (ou `?usuario=<id>`; o
  administrador informa também `gabinete_id`) devolve JSON. Para anexar os eventos:
  `GET /api/auditoria/exportar?formato=csv&processo_id=<id>` (ou `formato=json`). A própria
  exportação vira evento.

Nada disso traz conteúdo dos autos nem texto de pergunta ou resposta. Guarde cada exportação
enviada e combine a periodicidade com o tribunal.

---

## 12. Checklist de segurança (seção 6 dos requisitos), estado em 21/10/2026 (Etapa 8.1)

Conferível no ambiente em execução por `python scripts/conferir_piloto.py` (item a item:
atendido, pendente ou manual). Estado abaixo para o **perfil prod**; em desenvolvimento os itens
2, 13 e 14 aparecem pendentes por desenho (TLS 1.2 aceito no modo `interno`, Vault com 1 parte,
portas de dev em `127.0.0.1`). Saída em desenvolvimento no relatório da 8.1.

| # | Item da seção 6 | Estado | Observação |
| --- | --- | --- | --- |
| 1 | Piloto em infraestrutura própria, MinIO local compatível com S3 | atendido (pronto para instalar) | perfil prod e `instalar_piloto.sh`; imagem do storage pendente de assinatura (`docs/decisoes/object-storage.md`) |
| 2 | TLS 1.3 entre navegador e servidor | atendido no perfil prod | modos `acme`/`fornecido` só TLS 1.3, HSTS; `interno` (dev) aceita 1.2 |
| 3 | TLS entre serviços | não adotado (decisão 8.1) | rede interna de um host só; justificativa em 4.6 |
| 4 | Criptografia em repouso, chave por processo derivada da chave do gabinete, chaves em Vault próprio | atendido | DEK por processo envelopada pela chave do gabinete no Vault Transit; `/saude` confere o cofre |
| 5 | Texto extraído e índices também cifrados | atendido | texto das páginas, trechos, evidências, mensagens, cache do visualizador; hashes SHA-256 em claro |
| 6 | Arquivo cifrado antes de qualquer parser; worker decifra cópia só para processar | atendido | 7.4 |
| 7 | Exclusão pela destruição da chave | atendido, com limite | 7.7; backups anteriores guardam o envelope por até 30 dias (seção 6) |
| 8 | Objetos legados em claro | manual | 344 órfãos em claro de processos já removidos do banco, mantidos por decisão do responsável técnico |
| 9 | Só processos públicos; sigilo identificado e bloqueado | atendido | sigiloso recebe 403 na ingestão |
| 10 | Pseudonimização; tabela de resolução separada e cifrada | atendido | `reu_identidade` cifrada no Transit |
| 11 | Contrato do fornecedor do modelo veda treino (art. 19, §3º, III) | manual | conferir termos da API antes do piloto (decisão de Victor) |
| 12 | Nenhum dado de autos usado para treinar ou ajustar modelo | atendido por desenho | |
| 13 | Vault em produção (unseal, reinício, partes) | atendido no perfil prod | 3 partes / limiar 2, mlock, selado detectado (healthcheck, `/saude`, alerta); sem auto-unseal |
| 14 | Porta direta da API e console do MinIO fechados | atendido no perfil prod | só o proxy publica portas |

---

## 13. Ensaios registrados (Etapa 7.10, 21/10/2026, ambiente de desenvolvimento)

Executados uma vez pela aplicação real (rotas, banco, Vault real), com gabinete, usuários e
processo sintéticos; detalhes e saídas em `docs/etapas/RELATORIO-ETAPA-7.10.md`.

| Ensaio | Passos | Tempo | Resultado |
| --- | --- | --- | --- |
| Credencial de assessor comprometida | rotacionar chave (admin) → resetar senha → resetar MFA → conferir | 0,23 s de execução das rotas | chave do gabinete `v1`→`v2` com 1 DEK reenvelopada; as duas sessões do assessor (a "legítima" e a do "atacante") passaram a 401; senha antiga recusada; dossiê do processo continuou abrindo depois da rotação |
| Injeção | pergunta que provoca resposta com instrução → bloqueio → processo em revisão → nova pergunta recusada → liberação pelo desembargador → chat volta | 0,26 s | auditoria: `chamada_modelo` bloqueado, `processo_em_revisao`, `revisao_liberada` |
| Reinício do Vault | `docker compose restart vault` → selado → API com erro 500 nas rotas de processo → unseal → API decifra | 15,9 s do reinício à conferência (reinício 1,3 s, unseal 0,9 s) | API e worker voltaram a decifrar sem reinício; `docker compose ps` mostrou o Vault `healthy` mesmo selado |
