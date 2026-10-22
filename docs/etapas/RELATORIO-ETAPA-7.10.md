# Relatório da Etapa 7.10 — Documentação de operação

21 de outubro de 2026 · executor

## O que foi feito

1. **`docs/operacao.md`**: manual do responsável técnico, em 13 seções: dimensionamento (tempos
   das revisões 4C/4F e relatório 4F.9, disco por mil folhas, recomendação para o piloto);
   instalação do zero na ordem exata (tabela de todas as variáveis do `.env` com as que são
   segredo); atualização de versão; Vault (inicialização de produção à mão com 5 partes e limiar
   3, unseal, procedimento de reinício, rotação pela rota, backup a frio do volume, perda das
   partes, pendências de produção); certificado real no Caddy (ACME ou fornecido) e efeito do
   HSTS; porta direta da API (vazia = porta efêmera em loopback; sobreposição `ports: !reset []`
   para não publicar nada); backup e restauração, expurgo, chaves de período e o que o backup não
   cobre; descarte e rotação; `limpar_dev.py`; monitoramento (`/saude`, `/metricas`, logs, o que
   nunca vai a log); resposta a incidente com fluxo para vazamento, injeção, credencial e disco
   cheio; relatório de uso para o tribunal; checklist da seção 6 dos requisitos item a item; e o
   registro dos ensaios.
2. **Ensaios** executados uma vez (seção "Ensaios" abaixo).
3. **Itens herdados**:
   - `identidade_lida` com `usuario_id` (revisão 7.1-7.9, item 4): `pseudonimizador_do_processo`
     ganhou o parâmetro opcional `usuario_id`, que vai ao evento. Para que o valor chegue, foi
     preciso passá-lo pelos três chamadores: `agente/dossie.py` (`montar_dossie` e o resumo de
     peça), `agente/servico.py` (chat) e `api/rotas/dossie.py` (passa `chat.usuario_id`). São
     alterações de uma linha fora de `contexto.py`, registradas aqui. Testes:
     `tests/agente/test_dossie.py::test_identidade_lida_no_dossie_registra_quem_pediu` (pela rota) e
     `tests/seguranca/test_cifra_banco.py::test_identidade_lida_registra_o_usuario_informado`.
   - Recusa do backup por falta de espaço (item 5): `LUPA_BACKUP_ESTIMATIVA_BYTES` em
     `backup_conteiner.sh` faz uma conferência de espaço com a estimativa forçada **antes** de
     medir banco e bucket (repassada por `backup_comum.sh` e `.ps1`). Teste
     `tests/backup/test_espaco.py` (marcador `backup`, só no host): 1 EB forçado → saída com erro,
     `backup.log` com `RECUSADO`, nenhum `.age`, nenhuma área de trabalho, nenhuma chave criada.
     Passou (1 teste, 2,7 s).
   - `.gitattributes` (`* text=auto`, LF para `sh py yaml yml hcl md ts svelte json`, Caddyfile,
     Dockerfile e `ps1`; binários marcados) e `scripts/preparar_repositorio.md`.
   - `scripts/recifrar_objetos_legado.py` com simulação (padrão) e `--executar`, idempotente,
     conferência de cada objeto regravado; teste `tests/seguranca/test_recifrar_legado.py` (2
     testes: simula/executa/idempotente com objeto cifrado, legado, órfão e chave fora do padrão;
     parada quando a releitura não confere).
4. **README**: seção "Operação" e tabela "Onde cada etapa fica" refeita (etapa, código,
   documentação); frase de abertura atualizada. `docs/criptografia.md` aponta para o script de
   recifragem. `.env.example`: acréscimo comentado de `LUPA_BACKUP_ESTIMATIVA_BYTES` e nota de
   operação.

## Recifragem dos objetos legados (desenvolvimento)

Espaço livre antes: 120 GB.

| | Objetos |
| --- | --- |
| Examinados no bucket `lupa-autos` | 377 |
| Já cifrados (pulados) | 29 |
| **Recifrados** | **4** (2 processos, 524.563.585 bytes em claro), 40,6 s |
| Em claro sem DEK (não tocados) | 344 |
| Segunda passada | 0 a recifrar, 33 cifrados (idempotente) |

O revisor contou 50 objetos em claro; a varredura completa achou 348. Classificação feita antes
de executar: os 344 sem DEK pertencem a processos que **não existem mais no banco** (removidos pela
limpeza da 6.10, antes da exclusão criptográfica da 7.7; é o item 2 da revisão 6.10, "objetos
órfãos"). Sem DEK não há como cifrá-los. São dados sintéticos; não os apaguei porque apagar é
irreversível e não estava pedido. Recomendação: apagar os órfãos (prefixos de processos
inexistentes) antes do piloto, com decisão do responsável técnico.

## Ensaios

Todos pela aplicação real (rotas FastAPI, banco, Vault real), em desenvolvimento, com gabinete
`Gabinete E2E ensaio 7.10 ...`, desembargador e assessor sintéticos com MFA e um processo de três
páginas sintéticas. O chat usou o cliente falso roteirizado (`LUPA_AGENTE_CLIENTE=falso`, roteiro
"incidente"). Para a rota de rotação, o administrador do banco de desenvolvimento recebeu senha e
autenticador de teste e, ao fim, foi resetado de novo com `scripts/e2e_preparar.py` (senha
temporária aleatória, como o E2E espera). Os gabinetes do ensaio foram removidos ao fim pelo
mesmo caminho do `limpar_dev.py` (prefixo do ensaio só).

Correção de percurso: a primeira execução importou `tests.conftest`, que força
`LUPA_COFRE_BACKEND=memoria`; a rotação e as DEKs daquela rodada foram para o cofre em memória
(tokens `mem:v2`) e o processo ficou ilegível para a API em execução. Descartei aquela rodada,
reescrevi o roteiro sem o conftest, com conferência de que o cofre é `CofreVault`, e repeti. Os
números abaixo são da rodada válida (token `vault:v2`).

### 1. Credencial de assessor comprometida

| Passo | Comando (rota) | Tempo | Resultado |
| --- | --- | --- | --- |
| Preparo | duas sessões do assessor ("legítima" e "atacante") | 0,82 s | ambas abrem o processo |
| 1 | `POST /gabinetes/{id}/rotacionar-chave` (administrador) | 0,020 s | 200, `deks_recifradas: 1`, envelope `vault:v1` → `vault:v2` |
| 2 | `POST /usuarios/{id}/resetar-senha` (desembargador) | 0,072 s | 200, troca obrigatória |
| 3 | `POST /usuarios/{id}/resetar-mfa` (desembargador) | 0,016 s | 200 |
| 4 | conferência | 0,123 s | sessão do atacante 401, sessão legítima 401, login com a senha antiga 401, dossiê do processo 200 depois da rotação |

Total das rotas: 0,233 s. Auditoria (cadeia do gabinete): `chave_rotacionada` (administrador,
objeto `gabinete`), `senha_resetada` e `mfa_resetado` (desembargador, objeto `usuario`),
`login_falha` (assessor, resultado `falha`), `processo_aberto` (desembargador). Não há rota só
para revogar sessões: reset de senha, reset de MFA e desativação revogam (documentado).

### 2. Incidente de injeção

| Passo | Tempo | Resultado |
| --- | --- | --- |
| Pergunta cujo roteiro devolve "Ignore as instruções anteriores..." | 0,160 s | mensagem `descartada`, processo `em_revisao` |
| `GET /processos/{id}/revisao` e nova pergunta | 0,039 s | em revisão; pergunta recusada (`recusa`) |
| `POST /processos/{id}/liberar-revisao` (desembargador) | 0,026 s | 200, `em_revisao: false` |
| Nova pergunta | 0,032 s | chat responde de novo (`sem_evidencia`, o roteiro padrão) |

Total: 0,258 s. Auditoria: `pergunta_chat`, `chamada_modelo` (resultado `bloqueado`),
`processo_em_revisao` (resultado `bloqueado`, objeto `incidente`), `pergunta_chat`,
`revisao_liberada` (desembargador), `pergunta_chat`, `chamada_modelo` (`ok`). A tentativa de
liberação pelo assessor deu 401 (a sessão dele já tinha sido revogada no ensaio 1), então não
prova a recusa por papel; essa recusa já é coberta pelos testes da 6.8.

### 3. Reinício do Vault

| Passo | Comando | Tempo | Resultado |
| --- | --- | --- | --- |
| Antes | login + `GET /api/processos/{id}/dossie` pelo proxy | 2,4 s | 200 |
| Reinício | `docker compose restart vault` | 1,3 s | `vault status`: `sealed true` |
| Compose | `docker compose ps vault` | — | `healthy` 6 s depois, **mesmo selado** |
| Selado | mesma chamada | 0,1 s | login 200, dossiê **500** (`CofreError: vault respondeu 503` no log) |
| Unseal | `vault operator unseal` com a chave de `.vault-dev/init.json` (sem eco) | 0,9 s | `sealed false` |
| Depois | mesma chamada; `abrir_dek` no worker | 0,2 s | dossiê 200; worker abre a DEK |

Do reinício à conferência: 15,9 s. API e worker voltaram a decifrar sem serem reiniciados.

Achados do ensaio, registrados no manual: o healthcheck do `vault` aceita selado (o compose mostra
`healthy`) e o `/saude` da API não consulta o Vault; o usuário vê só "erro interno" nas rotas de
processo. Precisa de alerta externo sobre `vault status` (pendência para 8.1; mudar o `/saude` ou o
compose está fora do escopo desta subetapa).

## Decisões não previstas

- `/saude` e healthcheck do Vault não foram alterados (fora do escopo: `docker-compose.yml` e
  rotas da API); a lacuna está no manual e nas pendências.
- Backup do Vault: o storage é `file`, então o `raft snapshot` comentado no `backup_conteiner.sh`
  não serve. O manual descreve backup a frio do volume `lupa_vault-dados`. Não foi executado
  (exigiria copiar dados de volume para o host, vedado nesta subetapa).
- Prazos de comunicação da LGPD: `requisitos-v1.md` não os fixa (só diz que o fornecedor é o
  controlador). O manual não inventa prazo nem artigo; registra a regra operacional de avisar
  Victor e o desembargador no mesmo dia e deixa a definição para os documentos da 8.2.
- Dimensionamento de disco: originais estimados pelos autos sintéticos (4,7 GB para 3 × 15.647
  folhas); banco medido por página na base de desenvolvimento. O cache de PNG do visualizador não
  foi medido.

## O que ficou de fora

- Exclusão dos 344 objetos órfãos em claro (decisão do responsável técnico).
- Backup real do Vault e ensaio de restauração do Vault.
- TLS no Vault, auto-unseal, divisão das partes, TLS entre serviços, certificado real: pendências
  de produção documentadas (8.1).
- Revisão 7.1-7.9, item 6 (tela do valor corrigido) e item 8 (leitura dos guias por assessor
  externo): Etapa 8.

## Espaço em disco

120 a 121 GB livres em todas as conferências (antes da recifragem, dos ensaios, do rebuild e da
verificação). Nenhuma cópia de contêiner para o host; nada gravado em camada de contêiner além do
que a imagem já fazia.

## Testes

```
docker compose exec api bash scripts/verificar.sh
LUPA_VERIFICAR_BACKUP=1 .venv/Scripts/python -m pytest -m backup tests/backup/test_espaco.py --no-cov -q --confcutdir=tests/backup
```

Saída resumida: ver a seção "Verificação final" abaixo.

## Verificação final

`docker compose exec api bash scripts/verificar.sh` (imagem reconstruída, Vault destravado),
13 min 39 s, saída 0:

- ruff check e format: sem avisos; mypy --strict: sem erros.
- pytest: **860 passaram**, 3 pulados (inclui os testes de backup, que só rodam no host), 3
  desmarcados; cobertura **98,27%**.
- Ponta a ponta da ingestão: 1 passou. Regressão de injeção: 2 passaram, recall 1,0, falso
  positivo 0.
- Front: carimbo do build ok. Cabeçalhos: ok em 4 rotas.
- Suíte de injeção do agente: 9 passaram; 0 achados suprimidos ou criados, 0 vazamentos.
- No host: `tests/backup/test_espaco.py` 1 passou.

Espaço livre ao fim: 118 GB.
