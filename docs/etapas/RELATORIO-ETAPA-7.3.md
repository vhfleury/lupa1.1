# Relatório da Etapa 7.3: chave de dados por processo

## O que foi feito

- **DEK por processo**: evento `before_insert` de `ProcessoTabela` (`dominio/tabelas.py`) gera
  256 bits na aplicação (`envelope.gerar_dek`), cifra com `lupa-gabinete-<id>` no cofre e grava o
  token em `processo.chave_dados_cifrada` (coluna nova, migração 0010). Vale para qualquer criação
  (rota, scripts, testes).
- **Contexto de cifra** (`seguranca/contexto.py`): as DEKs em claro vivem só num `ContextoCifra`
  por escopo (requisição, job, script); `__repr__` não mostra chave; nada é registrado em log.
  `cifra_middleware` (`api/cifra.py`) abre um por requisição; `exige_processo` chama
  `ativar_processo` (e devolve 404 para processo `descartado`); o worker abre um por job e ativa o
  processo do job. Campos de outro processo são abertos pelo `carregador_sql`, que lê o envelope por
  `lupa_chave_processo(uuid)` (SECURITY DEFINER) numa conexão própria.
- **Rotação**: `POST /gabinetes/{id}/rotacionar-chave` (administrador, evento `chave_rotacionada`)
  chama `seguranca/chaves.rotacionar_gabinete`: versão nova da chave e `rewrap` de cada DEK no
  Vault (a DEK não sai em claro); o conteúdo não é recifrado.

## Testes (`tests/seguranca/test_cifra_banco.py`)

- `test_dek_de_um_processo_nao_abre_outro`: o campo de A decifra com a DEK de A e falha com a de B.
- `test_destruir_chave_do_gabinete_torna_processos_ilegiveis`: dois processos do gabinete; sem a
  chave no cofre, nenhuma DEK abre e a leitura das páginas falha.
- `test_rotacao_da_chave_do_gabinete_recifra_as_deks`: assessor recebe 403; admin rotaciona, o
  envelope passa a `v2` e o texto continua legível; evento auditado.
- `test_sem_processo_ativo_nao_grava_e_sem_carregador_nao_le`: sem processo ativo a cifra recusa
  em vez de gravar em claro.

## O que ficou de fora

- Zerar a memória da DEK: em Python `bytes` é imutável; o contexto só descarta a referência.
- Nos testes antigos que criam vários processos numa sessão e depois gravam páginas, o processo
  ativo é o último criado (as páginas abrem normalmente; em produção o processo ativo é sempre o do
  caminho ou do job).
