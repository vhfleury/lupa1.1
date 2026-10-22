# Lupa

Apoio à análise de processos judiciais. Etapas 0 a 7 concluídas (ingestão, validações, agente,
interface, criptografia em repouso, backup, guias e operação); a Etapa 8 é o piloto.

## Subir

```bash
cp .env.example .env        # troque os valores fictícios
docker compose up -d vault           # o vault so fica healthy destravado (Etapa 8.1)
bash scripts/vault_inicializar.sh   # init/unseal de dev, Transit, AppRole e chave lupa-saude
docker compose up -d --build --wait   # ou: make up
curl -k https://localhost:8443/api/saude   # {"api":"ok","db":"ok","minio":"ok","cofre":"ok"}
```

Instalação guiada (gera o `.env`, sobe, Vault, migra, usuário restrito, admin):
`bash scripts/instalar_piloto.sh` (produção) ou `--dev`; Windows: `scripts/instalar_piloto.ps1`.

Serviços: `api` (FastAPI, porta `API_PORTA_HOST`, padrão 8000), `db` (PostgreSQL 16, só na rede
interna), `minio` (console em `MINIO_CONSOLE_PORTA_HOST`, padrão 9001; API S3 só na rede interna) e
`minio-init` (cria o bucket `LUPA_MINIO_BUCKET` e sai). Todos expostos apenas em `127.0.0.1`.
Todos rodam sem root: `api` uid 10001, `db` uid 70 (`postgres`), `minio` e `minio-init` uid 10002.

A imagem do MinIO é o fork comunitário `pgsty/minio`, fixado por digest, porque as imagens
oficiais deixaram de estar disponíveis publicamente. **A escolha do object storage está em aberto.**

## Testes, lint e tipagem

```bash
docker compose exec api bash scripts/verificar.sh   # ou: make verificar
```

O script roda `ruff check`, `ruff format --check`, `mypy --strict` e `pytest` (cobertura mínima de
90% em `lupa`), parando no primeiro erro. Há equivalente para PowerShell em `scripts/verificar.ps1`.
Fora do compose, o teste marcado `integracao` é pulado se PostgreSQL ou MinIO estiverem inacessíveis.

Dependências fixadas com hashes em `requirements.txt` (produção) e `requirements-dev.txt`
(desenvolvimento), geradas por `pip-compile --generate-hashes` a partir dos arquivos `.in`.

## Acesso e auditoria (Etapa 3)

Login por usuário e senha (argon2id, mínimo 12 caracteres, fora das 10 mil senhas mais comuns),
seguido de código TOTP de aplicativo autenticador. Sem e-mail em nenhum fluxo. Papéis
`assessor`, `desembargador` e `administrador` (matriz em `src/lupa/acesso/papeis.py`).
O que a auditoria registra e como verificar a integridade: [`docs/auditoria.md`](docs/auditoria.md).

Primeira instalação, depois de `docker compose up -d --build --wait`:

```bash
docker compose exec api alembic -c src/lupa/migrations/alembic.ini upgrade head
docker compose exec api python scripts/criar_usuario_banco.py   # usa LUPA_DB_USUARIO_APP/SENHA_APP
docker compose exec api python scripts/criar_admin.py           # usa LUPA_ADMIN_USUARIO/SENHA
docker compose up -d api   # recria a API para ler as variáveis novas do .env
```

- **Usuário de conexão.** `LUPA_DATABASE_URL` (usuário `POSTGRES_USER`) é o dono das tabelas e
  só deve servir para migrações e scripts. A API conecta com `LUPA_DB_USUARIO_APP`, um papel
  com LOGIN, sem superusuário e sem BYPASSRLS, membro de `lupa_app`, criado por
  `scripts/criar_usuario_banco.py`. Em produção, o dono das tabelas precisa ser superusuário ou
  ter `BYPASSRLS` (as funções `SECURITY DEFINER` da migração 0002 dependem disso) e nunca é
  usado pela API. Sem as duas variáveis, a API usa `LUPA_DATABASE_URL` (aceitável só em
  desenvolvimento).
- **Administrador.** `scripts/criar_admin.py` cria o único administrador se ainda não existir.
  No primeiro login ele cadastra o autenticador (a resposta de `/auth/login` traz o segredo e a
  URI `otpauth://` do QR) e é obrigado a trocar a senha. Remova `LUPA_ADMIN_SENHA` do `.env`
  depois.
- **Reset.** Senha e autenticador são reiniciados por quem tem permissão
  (`/usuarios/{id}/resetar-senha`, `/usuarios/{id}/resetar-mfa`); a senha temporária aparece uma
  única vez na resposta e a troca é obrigatória no acesso seguinte.
- **Localização por IP (GeoLite2).** A base gratuita da MaxMind exige conta: crie em
  <https://www.maxmind.com/en/geolite2/signup>, aceite a licença, baixe "GeoLite2 City" (formato
  `.mmdb`), coloque o arquivo fora do git (por exemplo `./geoip/GeoLite2-City.mmdb`), monte no
  contêiner da API (`volumes: ["./geoip:/app/geoip:ro"]`) e defina
  `LUPA_GEOIP_CAMINHO=/app/geoip/GeoLite2-City.mmdb`. Atualize o arquivo manualmente (a MaxMind
  publica versões semanais). Sem a base, IPs públicos ficam "desconhecida"; IPs privados são
  sempre "rede interna".
- **Proxy reverso.** O IP auditado é o da conexão. Atrás de proxy, rode o uvicorn com
  `--proxy-headers --forwarded-allow-ips=<ip do proxy>`.
- **Teste de carga** (1 milhão de eventos, fora da suíte padrão por levar cerca de 1 minuto):
  `docker compose exec api python -m pytest -m carga --no-cov -s`.

## Ingestão — fundações (Etapa 4A)

Upload de PDF ou ZIP do processo, lacre por SHA-256, object storage, fila e worker isolado até o
job em `validado`. Detalhes: [`docs/ingestao.md`](docs/ingestao.md).

```bash
docker compose exec api alembic -c src/lupa/migrations/alembic.ini upgrade head   # revisão 0003
curl -X POST "https://.../processos/<id>/arquivos?nome=autos.pdf"      -H "Content-Type: application/octet-stream" --data-binary @autos.pdf     # com cookie de sessão
```

Serviços novos: `redis` (fila RQ, sem persistência e sem porta no host) e `worker`
(`python -m lupa.ingestao.worker`), este só na rede interna `ingestao`, sem saída para fora.
Os parsers rodam em subprocesso com limites de memória, CPU e tempo, sem variáveis `LUPA_*`.
Métricas Prometheus em `GET /metricas` (administrador).

## Onde cada etapa fica

| Etapa | Código | Documentação |
|---|---|---|
| 0. Esqueleto | `src/lupa/config.py`, `logging.py`, `api/` | este README |
| 1. Modelo de dados | `src/lupa/dominio/` | `docs/modelo-de-dados.md` |
| 2. Validações | `src/lupa/validacoes/` | `docs/validacoes.md`, `catalogo-validacoes.md` |
| 3. Acesso e auditoria | `src/lupa/acesso/`, `src/lupa/auditoria/` | `docs/auditoria.md` |
| 4A–4F. Ingestão | `src/lupa/ingestao/` | `docs/ingestao.md`, `docs/calibracao-projudi.md` |
| 4B. Autos sintéticos | `src/lupa/sinteticos/`, `scripts/gerar_autos.py` | `docs/sinteticos.md` |
| 5. Agente e chat | `src/lupa/agente/` | `docs/agente.md`, `prompt-injection.md` |
| 6. Interface web | `front/`, `proxy/Caddyfile` | `docs/front.md` |
| 7.1–7.7. Criptografia em repouso | `src/lupa/seguranca/`, `vault/` | `docs/criptografia.md`, `docs/decisoes/object-storage.md` |
| 7.8. Backup | `scripts/backup*.sh`, `restaurar.*`, `expurgar_backups.*` | `docs/backup.md` |
| 7.9. Guias dos usuários | `docs/imagens/` | `docs/guia-assessor.md`, `docs/guia-desembargador.md` |
| 7.10. Operação | `scripts/recifrar_objetos_legado.py`, `scripts/preparar_repositorio.md` | `docs/operacao.md` |
| Testes | `tests/` (espelha `src/lupa/`) | — |
| Relatórios e revisões | — | `docs/etapas/` |

## Autos sintéticos (Etapa 4B)

Processos criminais falsos, com gabarito, que servem de régua para a ingestão. Detalhes em
[`docs/sinteticos.md`](docs/sinteticos.md).

```bash
docker compose exec api python scripts/gerar_autos.py --destino /tmp/sinteticos processo --semente 1 --paginas 40
docker compose exec api python scripts/gerar_autos.py referencia     # dez processos de referência
docker compose exec api python scripts/gerar_autos.py injecao        # corpus de injeção
docker compose exec api python scripts/medir.py --gabarito G --saida S --json m.json --markdown m.md
```

Os arquivos gerados são grandes e ficam fora do repositório (padrão `.sinteticos/`, ignorada pelo
git; outra pasta com `--destino` ou `LUPA_SINTETICOS_DIR`).

## Interface web (Etapa 6)

Depois de `docker compose up -d --build --wait`, abra **https://localhost:8443** (porta em
`PROXY_PORTA_HOST`). O certificado é autoassinado: aceite o aviso do navegador no primeiro
acesso. O proxy (Caddy) serve o front em `/` e a API em `/api`, no mesmo origin.

- Primeiro acesso de qualquer usuário: senha temporária → cadastro do autenticador (QR code ou
  chave em texto) → troca de senha obrigatória.
- Testes do front: `docker build --target verificacao front` (lint, typecheck, unitários) e
  `bash front/scripts/e2e.sh` (Playwright contra a stack real; **reseta o admin do banco de
  desenvolvimento**).
- Segurança e acessibilidade (6.10): CSP sem nada inline, HSTS, Permissions-Policy e COOP no
  proxy (`python scripts/verificar_cabecalhos.py --url https://localhost:8443`); varredura axe nas
  telas; tema claro/escuro/sistema escolhido no cabeçalho. Limpeza dos dados sintéticos do banco
  de desenvolvimento: `docker compose exec api python scripts/limpar_dev.py --sim`.
- Detalhes, decisões e comandos: `docs/front.md`.

## Agente e chat (Etapa 5)

Contrato em [`docs/agente.md`](docs/agente.md). O agente usa o Claude Agent SDK (`claude-agent-sdk`,
que embute o binário do Claude Code) atrás da interface `ClienteAgente`
(`src/lupa/agente/cliente.py`); só as ferramentas somente leitura do Lupa ficam disponíveis, travadas
no processo da requisição. Toda citação é conferida por código antes de aparecer; pergunta de
valoração de prova, tipificação, conclusão jurídica, opinião sobre o resultado ou minuta é recusada
por regras antes de chamar o modelo.

- `POST /processos/{id}/chat` `{"pergunta": "..."}`: resposta com citações conferidas, recusa ou
  aviso de teto. `GET /processos/{id}/chat`: histórico do usuário no processo.
- `GET /processos/{id}/dossie` (`?resumos=true` pede ao modelo os resumos curtos, rotulados `gerado`).
- Credencial: nunca no repositório. O SDK usa `ANTHROPIC_API_KEY` do ambiente ou o login do Claude
  Code da máquina. Toda a suíte roda com um cliente falso roteirizado; o smoke do cliente real fica
  fora da suíte padrão e é pulado sem credencial (dentro do contêiner não há credencial):

```
docker compose exec api python -m pytest -m llm --no-cov tests/agente/test_smoke_llm.py
```

- Suíte de injeção do agente (passo próprio no `scripts/verificar.sh`, marcador `agente`).
- Tetos e modelo: `LUPA_MODELO`, `LUPA_AGENTE_*` (ver `.env.example`).

## Backup cifrado e guias (Etapas 7.8 e 7.9)

- Backup: `bash scripts/backup.sh` (ou `.ps1`), `restaurar.sh`, `expurgar_backups.sh`; serviço
  `backup` do compose (perfil `backup`), saída por bind mount em `LUPA_BACKUP_DIR` (padrão
  `.backups/`), chaves por mês em `LUPA_BACKUP_CHAVES_DIR` (padrão `.backup-chaves/`). Recusa sem
  espaço livre de 2× a estimativa + 2 GB. Detalhes em `docs/backup.md`; teste com
  `LUPA_VERIFICAR_BACKUP=1` no `scripts/verificar.ps1`.
- Guias para usuários: `docs/guia-assessor.md` e `docs/guia-desembargador.md`; capturas em
  `docs/imagens/` geradas por `bash front/scripts/capturas.sh` (processos sintéticos).

## Criptografia em repouso (Etapas 7.1 a 7.7)

Autos, trechos, conversas e originais ficam cifrados com uma chave por processo (DEK), envelopada
pela chave do gabinete no HashiCorp Vault (Transit); identidades dos réus vão direto ao Transit com
chave própria. Detalhes, formatos e limites em [docs/criptografia.md](docs/criptografia.md);
decisão de object storage (pendente de assinatura) em
[docs/decisoes/object-storage.md](docs/decisoes/object-storage.md).

```bash
docker compose up -d vault
bash scripts/vault_inicializar.sh       # Windows: powershell -File scripts/vault_inicializar.ps1
docker compose up -d --build --wait     # a API e o worker leem o .env com o AppRole
docker compose exec api alembic -c src/lupa/migrations/alembic.ini upgrade head
```

Reiniciar o contêiner `vault` sela o cofre: o healthcheck do `vault` fica `unhealthy` e o
`GET /saude` responde 503 com `"cofre":"falha"` até o unseal (`bash scripts/vault_inicializar.sh
--so-unseal`). Exclusão criptográfica de um
processo: `POST /processos/{id}/descartar` (desembargador ou administrador); rotação da chave de um
gabinete: `POST /gabinetes/{id}/rotacionar-chave` (administrador).

## Operação (Etapa 7.10)

Manual do responsável técnico em [`docs/operacao.md`](docs/operacao.md): dimensionamento,
instalação do zero, atualização, Vault (unseal, rotação, backup, pendências de produção),
certificado real e portas, backup e restauração, descarte, limpeza de sintéticos, monitoramento,
resposta a incidente, relatório de uso para o tribunal e checklist de segurança.

- Objetos anteriores à 7.4 ainda em claro no storage:
  `docker compose exec api python scripts/recifrar_objetos_legado.py [--executar]`.
- Antes do primeiro commit: `scripts/preparar_repositorio.md` (`.gitattributes` fixa LF).

## Ambiente de piloto (Etapa 8.1)

- **Produção:** `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d` (só o
  proxy publica portas, 443 e 80; `restart`, limites, rotação de logs, Vault com mlock, dados em
  `LUPA_DADOS_DIR`, backup diário pelo serviço `backup-agendado`).
- **Certificado:** `LUPA_TLS_MODO` = `interno` (dev), `acme` (`LUPA_DOMINIO`, `LUPA_ACME_EMAIL`) ou
  `fornecido` (`LUPA_TLS_CERT`, `LUPA_TLS_CHAVE`); `bash scripts/validar_caddyfile.sh` valida os três.
- **Vault de produção:** `LUPA_AMBIENTE=producao bash scripts/vault_inicializar.sh` (3 partes,
  limiar 2, mostradas uma vez, nada em disco; token raiz revogado no fim).
- **Monitoramento:** `docker compose --profile monitoramento up -d` (Prometheus em
  `127.0.0.1:9090`, Grafana em `127.0.0.1:3000`, painel "Lupa — piloto", alertas em
  `monitoramento/prometheus/regras.yml`).
- **Conferência:** `python scripts/conferir_piloto.py` (checklist da seção 12 do manual).
- Relatório: [`docs/etapas/RELATORIO-ETAPA-8.1.md`](docs/etapas/RELATORIO-ETAPA-8.1.md).
"# lupa1.1" 
