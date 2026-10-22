# Relatório da Etapa 7.6: identidades dos réus

## O que foi feito

- `reu_identidade.nome` e `documento` cifrados direto no Transit com a chave
  `lupa-gabinete-<id>-identidades` (`seguranca/chaves.cifrar_identidade`), por eventos
  `before_insert`/`before_update` de `ReuIdentidadeTabela`: qualquer caminho de gravação cifra.
- Decifrados só ao montar o pseudonimizador (`agente/contexto.pseudonimizador_do_processo`), que
  registra `identidade_lida` (processo e quantidade de réus, sem nome) na cadeia do gabinete.
- Ações novas no enum `AcaoAuditoria`: `identidade_lida`, `processo_descartado`,
  `chave_rotacionada` (só acréscimo; não há CHECK no banco).
- Migração 0010 leva as identidades existentes ao Transit (e o downgrade as decifra).

## Testes

- `test_identidade_do_reu_cifrada_no_banco_e_lida_com_auditoria`: consulta direta devolve
  `mem:v1:`/`vault:v1:` sem o nome; pseudonimização funciona; um evento `identidade_lida`.
- `test_worker_grava_reus_fatos_e_achados_sem_nome_real` (ajustado): decifra a identidade antes de
  conferir que o nome não vaza no texto nem nos logs.

## O que ficou de fora

- `identidade_lida` sem `usuario_id` (o pseudonimizador não recebe o ator); o processo e o
  instante identificam a requisição na trilha.
