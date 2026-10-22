# Revisão — Etapa 7, subetapas 7.1 a 7.9 (criptografia em repouso, backup e guias)

21 de outubro de 2026 · revisor

## 0. Incidente e retomada

A primeira execução desta etapa foi interrompida: o agente da 7.8 rodou um backup de teste contra o banco e o bucket principais (1 milhão de eventos de carga e autos sintéticos), gravando dentro da camada de um contêiner, e encheu o disco C:. Docker e WSL travaram; a sessão caiu; os dois agentes foram perdidos. Recuperação: `wsl --shutdown` com autorização do responsável técnico, Docker Desktop relançado, stack recriada íntegra (volumes nomeados preservados, banco em 0009), espaço liberado pelo responsável técnico. Os dois agentes foram relançados com disciplina de disco no brief: nada grande em camada de contêiner, backup de teste só contra banco e bucket pequenos, estimativa de tamanho e recusa sem o dobro de espaço livre, parada abaixo de 15 GB. Pastas vazias `src;C`, `scripts;C` e `.sinteticos;C`, artefatos de cópia com caminho mal interpretado, foram removidas.

## 1. Verificação executada

Stack com oito serviços saudáveis (api, db, minio, redis, worker, front, proxy, vault), `docker compose config` válido, banco em `0010 (head)`, Vault inicializado e aberto.

```
docker compose exec -T api bash scripts/verificar.sh
   ruff e mypy limpos; 856 testes passaram, 2 pulados, 3 desmarcados; cobertura 98,27%;
   ponta a ponta, injeção (recall 1,0), front, cabeçalhos (4 rotas), suíte do agente (9): ok
bash front/scripts/e2e.sh                                   -> 36 de 36 (8,9 min)
pytest tests/backup -m "integracao and backup"              -> 1 passou (29 s)
bash front/scripts/capturas.sh                              -> 25 passaram; 11 PNGs em docs/imagens
```

Provas diretas da cifra, feitas pelo revisor:

- `pagina.texto` e `texto_normalizado` começam com `lupa1:`; zero páginas em claro entre as existentes; `reu_identidade.nome` começa com `vault:v1:`; todos os 8 processos têm `chave_dados_cifrada`.
- Processo sintético novo ingerido pela pipeline real: os objetos gravados no storage começam com o cabeçalho `LUPAOBJ\x01`, não com `%PDF`. Os 50 objetos anteriores à 7.4 continuam em claro, como legado documentado.
- Após o E2E, a API voltou ao cliente de modelo real. Diretórios `.backups/` e `.backup-chaves/` vazios ao final. Disco com 121 GB livres.

## 2. Critérios de saída por subetapa

| Subetapa | Resultado | Evidência |
| --- | --- | --- |
| 7.1 decisão do storage | ok como documento | `docs/decisoes/object-storage.md` compara pgsty, Chainguard, Garage e RustFS; recomenda manter `pgsty/minio` por digest com `STORAGE_IMAGEM` como variável; Chainguard não tem `mc` e quebraria healthcheck, init e backup; assinatura pendente do responsável técnico |
| 7.2 cofre | ok | serviço `vault` 1.21.3 por digest, servidor real com storage em arquivo, Transit, AppRole com política mínima; `scripts/vault_inicializar.sh/.ps1` idempotentes; `Cofre` com implementação Vault e em memória, teste de contrato nas duas |
| 7.3 chave por processo | ok | DEK de 256 bits em envelope pela chave Transit do gabinete; `test_dek_de_um_processo_nao_abre_outro`, `test_destruir_chave_do_gabinete_torna_processos_ilegiveis`, `test_rotacao_da_chave_do_gabinete_recifra_as_deks` |
| 7.4 cifra dos originais | ok | `StorageCifrado`, formato `LUPAOBJ` v1 em blocos de 64 KiB com subchave HKDF e AAD contra truncamento; cifra na recepção após o hash; worker decifra em temporário 0600 apagado mesmo em falha (teste); cache de PNG cifrado; conferido no storage |
| 7.5 cifra de colunas | ok | `TextoCifrado`/`JsonCifrado` em texto, normalizado, nativo, OCR, trechos ocultos e suspeitos, evidência e mensagens; migração 0010 idempotente e reversível com conversão dos dados existentes; `test_dump_logico_nao_contem_sentinelas_em_claro`; busca do agente em memória com teto |
| 7.6 identidades | ok | chave Transit própria por gabinete; evento `identidade_lida`; conferido no banco |
| 7.7 exclusão criptográfica | ok | `POST /processos/{id}/descartar` e `POST /gabinetes/{id}/rotacionar-chave`; `test_descarte_apaga_tudo_e_nada_e_recuperavel`; `limpar_dev.py` pelo mesmo caminho |
| 7.8 backup cifrado | ok | `age` com chave por mês fora do diretório de backup; estimativa de tamanho e recusa sem espaço; contêiner somente leitura com `/tmp` em memória; restauração em banco e bucket limpos conferida por md5 e SHA-256; expurgo destrói a chave com registro em corrente de hash |
| 7.9 guias | ok | `guia-assessor.md` (336 linhas) e `guia-desembargador.md` com exemplos numéricos das três validações e regra da sexta-feira; leitor externo (Sonnet) 10 de 10 após correções; 11 capturas reais de telas com dados sintéticos |

Custo da cifra medido pelo executor: gravar mil páginas de 0,38 s para 0,45 a 0,70 s; ler de 0,015 s para 0,06 a 0,09 s; objeto de 1 MB em 0,5 a 1,2 ms. Desprezível diante do OCR.

## 3. Decisões dos executores endossadas

- Cifra na aplicação, não no servidor de storage: é o que torna o MinIO substituível por configuração.
- Cifrar também `texto_nativo` e `texto_ocr`, além da lista do roteiro: sem isso o dump ainda mostraria os autos. Correto.
- Busca do agente em memória por processo com teto, em vez de índice HMAC: aceitável no piloto porque a busca é sempre por um processo; registrado.
- Backup copia bytes cifrados como estão e a restauração exige o Vault com as mesmas chaves; snapshot do Vault preparado e comentado no script.
- Captura de telas sem reduzir o upload para 5 MB, porque a redução quebrava o teste de progresso; correção só no script e no spec de capturas.

## 4. Decisão

**Aprovado.** Subetapa 7.10 liberada.

## 5. Itens para a 7.10 e para o piloto

1. Vault em produção: TLS, auto-unseal (ou divisão das partes da chave de unseal entre pessoas) e procedimento de reinício, porque reiniciar o Vault sela o cofre. Documentar em `docs/operacao.md`.
2. Objetos anteriores à 7.4 continuam em claro no storage de desenvolvimento; antes do piloto, descartar os processos sintéticos ou recifrar com um script de migração de objetos.
3. Backups anteriores a um descarte ainda guardam o envelope da DEK; a retenção de 30 dias da 7.8 limita a janela. Registrar como limitação no guia de operação.
4. Evento `identidade_lida` sai sem `usuario_id`; corrigir na 7.10 ou na Etapa 8.
5. Não há teste automático da recusa por falta de espaço no backup; adicionar um teste com estimativa forçada.
6. Observação na captura do dossiê: um fato corrigido pelo E2E mostra valor 03/11/2008 com evidência "no dia 03/11/2019". A correção manual mantém a evidência original por desenho (o assessor corrigiu o valor), mas a tela deveria deixar claro que o valor corrigido não está no trecho citado. Melhoria de interface para a Etapa 8.
7. `.gitattributes` com LF para scripts e YAML antes do primeiro commit (revisão 6.10).
8. Leitura dos guias por um assessor humano de fora do projeto fica para o piloto (8.3).
