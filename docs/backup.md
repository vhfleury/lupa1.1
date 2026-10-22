# Backup cifrado (Etapa 7.8)

## O que é copiado

Um backup é um único arquivo `lupa-AAAA-MM-<carimbo>.tar.age`, cifrado com `age`, que contém:

| Item | Como | Observação |
| --- | --- | --- |
| `banco.dump` | `pg_dump --format=custom` do banco | restaurado com `pg_restore` |
| `objetos/` | `mc mirror` do bucket | bytes **como estão**: se a 7.4 cifrou os objetos, o backup leva o objeto cifrado |
| `metadados.txt` | carimbo, período, banco, bucket, versão do `pg_dump` | |
| `manifesto.sha256` | SHA-256 de cada arquivo acima | conferido antes de restaurar |

## Chaves do período

- Uma chave `age` por mês (`chave-AAAA-MM.txt`), gerada na primeira vez em que o mês é usado,
  em `LUPA_BACKUP_CHAVES_DIR` (padrão `.backup-chaves/`), **fora** do diretório de backup.
  Em produção, aponte a variável para outro disco ou cofre; quem tem só os backups não lê nada.
- O backup é cifrado para a chave pública do mês; para restaurar é preciso a chave privada.

## Onde fica cada coisa (e a regra do disco)

- Tudo roda no serviço `backup` do compose (perfil `backup`, imagem `lupa-backup:local`:
  `pg_dump` 16, `age`, `mc`). A raiz do contêiner é **somente leitura**: nenhum dado de backup
  vai para a camada gravável do contêiner nem para volume do Docker.
- `LUPA_BACKUP_DIR` (padrão `.backups/`, ignorado pelo git) é montado por bind mount em
  `/backups`. Lá ficam os `.age`, o `backup.log` e, só durante a execução, a área de trabalho
  `.trabalho-XXXXXX` (permissão 700, apagada ao fim, mesmo em falha) com o dump e o espelho em
  claro antes de cifrar.
- **Conferência de espaço:** antes de começar, o script estima o tamanho
  (`pg_database_size` do banco + soma dos objetos do bucket por `mc du`) e **recusa** se o
  espaço livre no destino for menor que `2 × estimativa + 2 GB`. A estimativa, o livre e o
  exigido vão para `backup.log`. A restauração faz a mesma conferência com o tamanho do `.age`.

## Comandos (host)

```bash
bash scripts/backup.sh                 # ou: powershell scripts/backup.ps1
LUPA_RESTAURAR_BANCO=lupa_restaurado LUPA_RESTAURAR_BUCKET=lupa-restaurado \
  bash scripts/restaurar.sh lupa-2026-10-20261021T020000Z.tar.age
bash scripts/expurgar_backups.sh       # retenção
```

Variáveis: `LUPA_BACKUP_BANCO`/`LUPA_BACKUP_BUCKET` (origem; padrão `POSTGRES_DB` e
`LUPA_MINIO_BUCKET`), `LUPA_RESTAURAR_BANCO`/`LUPA_RESTAURAR_BUCKET` (destino, obrigatórios),
`LUPA_RESTAURAR_SOBRESCREVER=1` (aceita apagar um banco de destino com tabelas),
`LUPA_BACKUP_RETENCAO_DIAS` (padrão 30). Agendamento diário sugerido (cron do host):
`0 2 * * * cd /caminho/Lupa1 && bash scripts/backup.sh && bash scripts/expurgar_backups.sh`.

A restauração: confere o espaço, decifra, confere o manifesto (recusa backup corrompido), cria
o banco de destino (recusa banco com tabelas, salvo `SOBRESCREVER`), `pg_restore`, cria o bucket
e espelha os objetos de volta.

## Retenção e destruição da chave

`expurgar_backups.sh` apaga os backups com mais de 30 dias e, para cada chave de mês que **não é
o mês corrente e não tem mais nenhum backup vivo**, sobrescreve o arquivo com bytes aleatórios e o
remove. Cada destruição vira uma linha em `LUPA_BACKUP_CHAVES_DIR/destruicoes.log`:

```
2026-11-21T02:00:00Z destruida periodo=2026-10 impressao=<sha256 da chave pública> motivo=sem_backup_vivo retencao_dias=30 anterior=<hash> hash=<hash>
```

`hash = sha256(anterior + "|" + linha)`: as linhas formam uma corrente (como a auditoria); alterar
ou remover uma linha rompe a corrente. A impressão digital prova qual chave foi destruída sem
guardar a chave. Com a chave destruída, os backups daquele mês (já apagados) ficam ilegíveis em
qualquer cópia esquecida.

## Criptografia em repouso (7.1 a 7.7) e o Vault

O backup copia os objetos **como estão**. Se a 7.4 cifrou objetos e colunas com chaves do Vault,
**a restauração só serve com o Vault contendo as mesmas chaves**: restaure (ou mantenha) o Vault
antes de subir a API sobre o banco restaurado. O `backup_conteiner.sh` já traz a etapa de
snapshot do Vault preparada e **comentada** (`vault operator raft snapshot save`, ligada por
`LUPA_BACKUP_VAULT=1` com token só de snapshot em `VAULT_TOKEN`, nunca em arquivo): quando esta
subetapa terminou, o serviço `vault` ainda não existia no compose. Ao ligá-la, a imagem do
backup precisa do binário `vault` e o snapshot entra no manifesto e no mesmo `.age`.

## Teste de restauração

`tests/backup/test_restauracao.py` (marcadores `integracao` e `backup`), só no host com Docker:

```powershell
$env:LUPA_VERIFICAR_BACKUP = "1"; powershell scripts/verificar.ps1   # passo == backup ==
# ou só ele:
$env:LUPA_VERIFICAR_BACKUP = "1"; python -m pytest -m backup tests/backup --no-cov -q --confcutdir=tests/backup
```

Ele **nunca** usa o banco `lupa` nem o bucket `lupa-autos`: cria um banco `lupa_bkp_o_<sufixo>`
e um bucket `lupa-bkp-o-<sufixo>`, aplica as migrações e ingere um processo sintético de 12
páginas pelo worker real (`tests/backup/semear.py`, no contêiner da API); faz o backup pelo
script documentado num diretório temporário do pytest; confere que o arquivo é `age`, que não há
`PGDMP` em claro, que só sobraram o `.age` e o `backup.log` (área de trabalho apagada) e que a
estimativa foi registrada; apaga banco e bucket; restaura em banco e bucket **novos**; compara
contagem e md5 de todas as linhas de `processo`, `arquivo`, `pagina`, `peca`, `evidencia`, `fato`,
`achado` e `reu` e o SHA-256 de cada objeto (lido em fluxo, sem cópia em disco); por fim roda o
expurgo com o relógio 31 dias à frente (`LUPA_BACKUP_AGORA`) e confere que o backup saiu, a chave
foi destruída e a linha do log fecha o hash. Tudo de teste é apagado no `finally`.
