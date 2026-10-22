# Criptografia em repouso (Etapa 7)

Código em `src/lupa/seguranca/`; testes em `tests/seguranca/`. Objetivo: quem tiver o disco, um
dump do banco, uma cópia do bucket ou um backup não lê autos, trechos, conversas nem identidades.

## Hierarquia de chaves

```
Vault (Transit, nunca exporta chave)
 ├─ lupa-gabinete-<id>               chave do gabinete (aes256-gcm96, versionada)
 │    └─ envelopa a DEK de cada processo  → processo.chave_dados_cifrada  ("vault:v<n>:...")
 │          DEK (256 bits, gerada na aplicação, em claro só em memória)
 │           ├─ colunas de texto do processo            → "lupa1:<base64>"
 │           └─ objetos do storage (originais, entradas de ZIP, cache de PNG) → "LUPAOBJ" v1
 └─ lupa-gabinete-<id>-identidades   cifra direta de reu_identidade.nome/documento ("vault:v<n>:")
```

- **Cofre** (`cofre.py`): protocolo `Cofre` com `CofreVault` (HTTP via `httpx`, AppRole, Transit)
  e `CofreMemoria` (AES-GCM em memória, só testes; recusado em `producao`). Escolha por
  `LUPA_COFRE_BACKEND`. Token do AppRole renovado por novo login quando o Vault responde 403;
  `secret_id` nunca aparece em log nem em mensagem de erro.
- **Chaves do gabinete**: `criar_gabinete` cria as duas chaves (`criar_chaves_gabinete`); a de
  envelope também é criada sob demanda (idempotente) quando nasce o primeiro processo.
- **DEK por processo** (7.3): o evento `before_insert` de `ProcessoTabela` gera a DEK, cifra com a
  chave do gabinete e grava o token em `processo.chave_dados_cifrada`. A DEK em claro só existe no
  `ContextoCifra` do escopo (requisição, job ou script) e some com ele. Nunca vai a log.
- **Rotação** (`POST /gabinetes/{id}/rotacionar-chave`, só administrador, evento
  `chave_rotacionada`): nova versão da chave do gabinete e `rewrap` de cada DEK no próprio Vault
  (a DEK não sai em claro). Os dados não são recifrados: continuam com a mesma DEK.

## Formatos

**Campo** (`envelope.cifrar_campo`): `lupa1:` + base64(`processo_id[16] | nonce[12] |
AES-256-GCM(texto) | tag[16]`), AAD `lupa1|<tabela.coluna>|<processo_id>`. Copiar o valor para
outra coluna ou atribuí-lo a outro processo faz a tag falhar. O id no cabeçalho só diz qual DEK
pedir.

**Objeto** (`envelope.cifrar_stream`): cabeçalho `LUPAOBJ | 0x01 | tamanho_bloco[4] | sal[16]`;
subchave `HKDF-SHA256(DEK, sal, "lupa/objeto/v1")`; blocos de 64 KiB, cada um AES-256-GCM com
nonce = índice do bloco e AAD = cabeçalho | índice[8] | marca de último bloco. O sal novo por
objeto dá subchave nova, então o contador de nonce nunca se repete; a marca de último bloco
impede truncar o objeto numa fronteira de bloco. A gravação é em stream (`LeitorCifrado`), sem o
arquivo inteiro em memória.

## Onde a cifra acontece

| Dado | Como | Onde |
|---|---|---|
| `pagina.texto`, `texto_normalizado`, `texto_nativo`, `texto_ocr` | `TextoCifrado` | `dominio/tabelas.py` |
| `pagina.trechos_ocultos`, `trechos_suspeitos` (JSONB → texto) | `JsonCifrado` | idem |
| `evidencia.trecho`, `mensagem.texto` | `TextoCifrado` | idem |
| `reu_identidade.nome`, `documento` | Transit `...-identidades`, eventos `before_insert/update` | idem + `seguranca/chaves.py` |
| Originais, entradas de ZIP, PNG e medidas do visualizador | `StorageCifrado` sobre `ObjectStorage` | `ingestao/storage.py` |

`texto_nativo` e `texto_ocr` entraram além da lista do roteiro porque guardam o mesmo texto da
página (sem eles o dump ainda mostraria os autos). `hash_texto`/`hash_trecho` continuam em claro:
são SHA-256, necessários para conferir citações, e não revelam o texto.

- **Gravação**: a coluna cifra com a DEK do processo *ativo* do contexto (`dek_para_gravar`). O
  processo ativo é definido por `exige_processo` (toda rota de processo), pelo worker no início do
  job, ou pelo último processo criado no escopo. Sem processo ativo, a gravação falha (nunca grava
  em claro).
- **Leitura**: o processo vem do cabeçalho do campo; a DEK vem do cache do contexto ou do
  carregador `carregador_sql`, que chama `lupa_chave_processo(uuid)` (SECURITY DEFINER, 0010) numa
  conexão própria e abre a DEK no cofre. O carregador só é usado para campos que a sessão já leu
  sob a RLS, então não amplia o acesso.
- **API**: `cifra_middleware` (`api/cifra.py`) abre um contexto por requisição; o cofre é criado
  em `create_app` (`app.state.cofre`).
- **Worker**: `processar_job` roda dentro de `contexto_cifra(carregador_sql(...))` e ativa o
  processo do job; processo sem DEK (descartado) leva o job a `falho`.

## Originais no worker e no visualizador (7.4)

A recepção calcula o SHA-256 em stream sobre o claro (o `arquivo.sha256` e a chave do objeto
continuam os do claro), e só então `lacrar` grava no storage, cifrando em stream. Nenhum parser
toca o arquivo antes disso. O worker decifra o original para `original` dentro do diretório
efêmero do job (`TemporaryDirectory`, 0700, arquivo criado com `O_EXCL` e modo 0600), que é
apagado ao fim do job, inclusive em exceção (teste
`test_worker_decifra_em_temporario_0600_e_apaga_mesmo_em_falha`). As entradas de ZIP e o cache de
PNG/medidas do visualizador passam pelo mesmo `StorageCifrado`. A renderização grava o PDF num
temporário 0600 que some ao fim da chamada. Objeto legado em claro (anterior à 7.4) ainda é lido,
com aviso `objeto_legado_em_claro` no log.

## Busca do agente (7.5)

Com o texto cifrado, `ILIKE` no banco não serve. `buscar_texto` percorre as páginas do processo na
ordem dos autos, em blocos de 200 (`yield_per`), decifrando sob demanda e comparando em minúsculas,
até 20 acertos ou `LUPA_BUSCA_MAX_PAGINAS` páginas lidas (padrão 5000). O mesmo vale para a
contagem de trechos ocultos do relatório de qualidade (antes `jsonb_array_length`).

## Identidades (7.6)

`reu_identidade.nome` e `documento` vão ao banco já como token do Transit (chave própria
`lupa-gabinete-<id>-identidades`); uma consulta direta devolve só `vault:v1:...`. São decifrados
só para montar o pseudonimizador (a "apresentação" ao agente), que registra `identidade_lida`
(processo e quantidade de réus, sem nome) na cadeia de auditoria.

## Exclusão criptográfica (7.7)

`POST /processos/{id}/descartar` (desembargador do gabinete ou administrador):

1. `lupa_descartar_processo(uuid)` (SECURITY DEFINER, confere `lupa.gabinete_id`/`lupa.papel` da
   transação) apaga mensagens, chamadas ao modelo, conversas, revisões, anotações, achados,
   fatos, réus e identidades, peças, diagnósticos, lotes, jobs, arquivos e, em cascata, páginas e
   evidências; zera `chave_dados_cifrada` e põe `status = 'descartado'` (tombstone);
2. a DEK sai do contexto de cifra;
3. os objetos do processo (originais, entradas de ZIP, cache do visualizador) são apagados;
4. o evento `processo_descartado` entra na cadeia de hash do gabinete com o SHA-256 da DEK
   cifrada apagada (`objeto_tipo = dek_sha256`).

Depois disso, qualquer cópia remanescente (backup, réplica, versão antiga no bucket) é ilegível:
o único envelope da DEK foi apagado, então nem a chave do gabinete abre o conteúdo. O processo
some de todas as rotas (404). `scripts/limpar_dev.py` passa pelo mesmo caminho para cada processo
dos gabinetes sintéticos e, com `--sim`, apaga os objetos e destrói as chaves Transit do gabinete.

Limite: backups do banco feitos antes do descarte ainda contêm o envelope da DEK; o descarte só é
definitivo para eles quando a chave do gabinete correspondente ao período for destruída ou o
backup expirar (política da 7.8).

## Vault no compose (7.2)

Serviço `vault` (`hashicorp/vault:1.21.3` por digest), servidor real com storage em arquivo
(volume `vault-dados`), sem modo dev, só nas redes `interna` e `ingestao`, sem porta no host.
Configuração em `vault/lupa.hcl`; política mínima em `vault/politicas/lupa.hcl` (só
`transit/{keys,encrypt,decrypt,rewrap}/lupa-gabinete-*`).

```
docker compose up -d --build --wait
bash scripts/vault_inicializar.sh        # ou: powershell -File scripts/vault_inicializar.ps1
docker compose up -d api worker          # relê o .env com o AppRole
```

O script é idempotente: na primeira vez faz `operator init` (1 parte, limiar 1) e guarda a chave de
unseal e o token raiz em `.vault-dev/init.json` (fora do repositório, modo 600); depois faz unseal,
habilita Transit e AppRole, grava a política e o papel `lupa` (token de 1 h) e escreve
`LUPA_COFRE_BACKEND`, `LUPA_VAULT_ROLE_ID` e `LUPA_VAULT_SECRET_ID` só no `.env`. **Reiniciar o
Vault sela o cofre**: rode o script de novo. Em produção: TLS no listener, auto-unseal (KMS/HSM),
chaves de unseal repartidas entre pessoas, token raiz revogado e `secret_id` com TTL e
`bound_cidr_list`.

## Migração 0010

Adiciona `processo.chave_dados_cifrada`, aceita `descartado` no status, troca os trechos de JSONB
para texto e cria `lupa_chave_processo`/`lupa_descartar_processo`. Dados existentes: cada processo
ganha DEK; textos, trechos, evidências e mensagens são cifrados em lotes de 500 e as identidades vão
ao Transit. Idempotente (valor já `lupa1:` ou `vault:` é pulado) e reversível (o downgrade
decifra). Precisa do cofre configurado quando há dados. Objetos já gravados em claro no storage
continuam legíveis; para cifrá-los, rode `scripts/recifrar_objetos_legado.py` (7.10, simula sem
`--executar`, idempotente), reenvie o arquivo ou descarte o processo. Operação do Vault em
produção: `docs/operacao.md`, seção 4.

## Desempenho

Medido no contêiner da API (ver `docs/etapas/RELATORIO-ETAPA-7.5.md`): custo da cifra por mil
páginas sintéticas, gravação e leitura pelo ORM, e objeto de 1 MB.
