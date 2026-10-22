# Relatório da Etapa 7.7: exclusão criptográfica

## O que foi feito

- `POST /processos/{id}/descartar` (`api/rotas/descarte.py`, desembargador do gabinete ou
  administrador): `seguranca/descarte.descartar` chama `lupa_descartar_processo` (SECURITY DEFINER,
  confere gabinete/papel; apaga conteúdo inclusive em tabelas sem DELETE para `lupa_app`, zera a
  DEK cifrada, status `descartado`), esquece a DEK do contexto, apaga originais, entradas e cache
  do visualizador no storage e registra `processo_descartado` na cadeia de hash com o SHA-256 da
  DEK cifrada apagada. Processo descartado responde 404 em todas as rotas; worker leva job de
  processo sem chave a `falho`.
- `POST /gabinetes/{id}/rotacionar-chave` (7.3) no mesmo módulo.
- `scripts/limpar_dev.py`: cada processo dos gabinetes sintéticos passa por
  `lupa_descartar_processo` antes da remoção; com `--sim`, apaga os objetos e destrói as duas
  chaves Transit do gabinete. Recusa fora de desenvolvimento/teste antes de criar cofre/storage.

## Testes

- `test_descarte_apaga_tudo_e_nada_e_recuperavel`: assessor 403; desembargador 200; storage vazio;
  tombstone sem DEK; nenhuma linha em arquivo, página, conversa, réu, fato, achado, chamada;
  evento com o hash; `dek_de` falha mesmo com a chave do gabinete ainda no cofre; a "cópia de
  backup" do objeto é só `LUPAOBJ`; repetir dá 404.
- `tests/auditoria/test_limpar_dev.py` passando com o caminho novo.

## O que ficou de fora

- Backups do banco anteriores ao descarte ainda guardam o envelope da DEK (a política de
  retenção da 7.8 decide quando somem).
- A listagem do cache de renderização percorre o prefixo `renderizacao/` inteiro (aceitável no piloto).

## Verificação final das subetapas 7.1 a 7.7

- Disco: 138 GB livres no início da retomada, 123 GB no fim (`docker system df`: imagens 16,7 GB,
  contêineres 6,2 GB, volumes 14,3 GB, cache de build 7,3 GB). Única imagem nova: Vault.
- `docker compose up -d --build --wait` com o Vault inicializado por `scripts/vault_inicializar.sh`;
  `alembic upgrade head` no banco de desenvolvimento (0010, 30/30 páginas cifradas com o Vault).
- `docker compose exec api bash scripts/verificar.sh`: ruff, format e mypy limpos; **856 passed,
  2 skipped**, cobertura **98,27%**; ponta a ponta, injeção (recall 1,0), carimbo do front,
  cabeçalhos e suíte do agente (0 vazamentos) passando.
- `bash front/scripts/e2e.sh`: **36 passed**.
