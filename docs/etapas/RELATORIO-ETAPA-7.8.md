# Relatório da subetapa 7.8: backup cifrado

## Entregas

- `scripts/backup_conteiner.sh` (roda no serviço `backup`): `fazer`, `restaurar`, `expurgar`,
  `listar`. `pg_dump` custom + `mc mirror` do bucket + metadados + manifesto SHA-256, num tar
  cifrado com `age` para a chave do mês (`chave-AAAA-MM.txt` em `LUPA_BACKUP_CHAVES_DIR`).
- Wrappers do host: `backup.sh/.ps1`, `restaurar.sh/.ps1`, `expurgar_backups.sh/.ps1`,
  `backup_comum.sh/.ps1`.
- Serviço `backup` no `docker-compose.yml` (perfil `backup`, imagem `lupa-backup:local`).
- `tests/backup/` (`test_restauracao.py`, `semear.py`, marcador `backup`); passo opcional
  `LUPA_VERIFICAR_BACKUP=1` no `scripts/verificar.ps1`; `docs/backup.md`; `.env.example` e
  `.gitignore` (`.backups/`, `.backup-chaves/`).

## Correções após o incidente do disco

O trabalho anterior rodou o backup contra `lupa`/`lupa-autos` (1 milhão de eventos) com a área de
trabalho em `/trabalho` na camada gravável de um contêiner `--rm`, e encheu o disco C:. Agora:

1. O teste só usa banco `lupa_bkp_o_<sufixo>` e bucket `lupa-bkp-o-<sufixo>` criados por ele
   (processo sintético de 12 páginas), apagados no `finally`.
2. Contêiner `backup` com `read_only: true` (e `tmpfs /tmp` de 16 MB só para a configuração do
   `mc`); a área de trabalho é `/backups/.trabalho-XXXXXX`, no bind mount `LUPA_BACKUP_DIR`
   (padrão `.backups/`), apagada por `trap` mesmo em falha. O conferidor de objetos do teste lê
   cada objeto em fluxo (`mc cat | sha256sum`), sem cópia em disco.
3. Antes de `fazer` e `restaurar`: estimativa (`pg_database_size` + `mc du`, ou o tamanho do
   `.age`) e recusa se livre < 2 × estimativa + 2 GB; estimativa, livre e exigido em
   `backup.log`.
4. Espaço livre conferido antes de cada execução (abaixo).

## Execução

| Momento | Livre em C: | `docker system df` |
| --- | --- | --- |
| início | 96 GB | imagens 16,2 GB, contêineres 6,7 GB, volumes 14,6 GB, cache 7,3 GB |
| antes do teste | 141 GB (limpeza externa) | igual |
| depois do teste | 141 GB | igual |

Backup de teste: banco 10.591.255 bytes + bucket 340.041 bytes (estimativa 10,9 MB; exigido
2,17 GB); arquivo `.age` de **514.872 bytes**. Teste `test_backup_cifrado_restaura_processo_em_ambiente_limpo`:
**1 passed em 29 s** (processo, páginas, fatos, achados e as demais tabelas idênticas por md5;
objetos idênticos por SHA-256; expurgo +31 dias apagou o backup, destruiu a chave e a linha do
log fecha o hash).

Comando: `LUPA_VERIFICAR_BACKUP=1 python -m pytest -m backup tests/backup --no-cov -q --confcutdir=tests/backup`
(`--confcutdir` porque o `tests/conftest.py` raiz importa a app inteira, e o venv do host estava
sem `prometheus_client`; o teste não usa fixtures da raiz).

**Reexecução posterior falhou por causa externa:** depois que o `e2e.sh`/`capturas.sh` reconstruiu
a imagem da API com o código em andamento da 7.1–7.7, a ingestão chama o Vault
(`lupa.seguranca.cofre`), e o serviço `vault` ainda não existe no compose
(`httpx.ConnectError`). Além disso, `docker compose config` passou a falhar
("yaml: line 3") por edição em andamento fora do meu escopo. Rodar de novo quando a 7.1–7.7
fechar.

## Vault

A restauração exige o Vault com as mesmas chaves (objetos e colunas cifrados pela 7.4 vão como
estão). Etapa de snapshot do Vault preparada e comentada em `backup_conteiner.sh`
(`LUPA_BACKUP_VAULT=1`), porque o serviço não existia ao fim desta subetapa.

## Fora de escopo / pendente

- Teste automático do caminho de recusa por falta de espaço (não há como simular disco cheio
  com bind mount sem tocar o host); conferido por leitura e pelo log.
- A imagem `lupa-backup:local` ainda cria `/trabalho` (inofensivo, não é mais usado); remover no
  próximo rebuild.
- Ligar o snapshot do Vault quando o serviço existir.
