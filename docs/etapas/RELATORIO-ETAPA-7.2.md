# Relatório da Etapa 7.2: cofre de chaves (HashiCorp Vault)

## O que foi feito

- **Serviço `vault`** no compose: `hashicorp/vault:1.21.3@sha256:5f244d44...9e65` (a 1.22 não
  existe), servidor real com storage em arquivo (volume `vault-dados`), sem modo dev, config em
  `vault/lupa.hcl` (montada só leitura), só nas redes `interna` e `ingestao`, sem porta no host,
  `no-new-privileges`. Healthcheck confere só que o servidor responde (selado ou não) para não
  travar o `--wait`; `api` e `worker` dependem dele e recebem `LUPA_VAULT_ENDERECO`.
- **Scripts** `scripts/vault_inicializar.sh` e `.ps1` (idempotentes): init (1 parte) com chave de
  unseal e token raiz em `.vault-dev/init.json` (fora do repositório e da imagem: `.gitignore` e
  `.dockerignore`), unseal, Transit, AppRole, política mínima `vault/politicas/lupa.hcl` (só
  `transit/{keys,encrypt,decrypt,rewrap}/lupa-gabinete-*`) e papel `lupa` (token 1 h); grava
  `LUPA_COFRE_BACKEND`, `LUPA_VAULT_ROLE_ID` e `LUPA_VAULT_SECRET_ID` só no `.env`. Placeholders no
  `.env.example`. Os dois scripts rodaram duas vezes cada sem erro.
- **Código** (`src/lupa/seguranca/cofre.py`, do agente anterior, revisado e mantido): protocolo
  `Cofre`, `CofreMemoria` (AES-GCM, recusado em produção) e `CofreVault` (httpx + AppRole, novo login
  em 403). Correções: `destruir_chave` confere a existência antes (o Vault responde 400, não 404,
  ao configurar chave inexistente) e docstring duplicada de `criar_cofre`.
- **Chave por gabinete**: `criar_gabinete` (`acesso/servico.py`) cria `lupa-gabinete-<id>` e
  `lupa-gabinete-<id>-identidades` (`seguranca/chaves.criar_chaves_gabinete`).
- Dependências: `cryptography==50.0.2` e `httpx==0.28.1` declaradas em `requirements.in` e
  `pyproject.toml`; o `requirements.txt` já as tinha com hash (nada a regenerar).

## Testes

`tests/seguranca/test_cofre.py`: contrato do `Cofre` parametrizado nas duas implementações (a do
Vault real marcada `integracao`, usando o AppRole do contêiner; passou contra o Vault do compose),
escolha do backend e recusa da memória em produção, e o adaptador do Vault contra um transporte
falso (login preguiçoso, novo login após 403, chave ausente, token inválido, servidor fora, erro
500, `secret_id` fora das mensagens).

## O que ficou de fora

- TLS no listener, auto-unseal e repartição das chaves de unseal (produção; ver
  `docs/criptografia.md`). Reiniciar o Vault sela o cofre: rodar o script de novo.
