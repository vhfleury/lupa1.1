# Revisão — Etapa 1 (esquemas de dados)

20 de outubro de 2026 · revisor

## 1. Verificação executada

A Etapa 2 estava em execução no mesmo diretório, então a imagem não foi reconstruída para não interferir. Os arquivos da Etapa 1 foram copiados para o contêiner `api` em execução e a verificação foi limitada ao escopo da etapa:

```
docker compose cp src/lupa/dominio api:/app/src/lupa/
docker compose cp src/lupa/migrations api:/app/src/lupa/
docker compose cp tests/dominio api:/app/tests/
docker compose cp tests/conftest.py api:/app/tests/conftest.py
docker compose exec -T api sh -c "ruff check ... && ruff format --check ... && mypy ... && pytest tests/dominio --no-cov"
```

Saída: ruff sem avisos, 16 arquivos formatados, mypy sem erros em 17 arquivos, 28 testes passaram (15 de esquema, 13 de banco contra o PostgreSQL do compose, incluindo RLS, triggers, migração e comparação migração × tabelas).

A verificação completa com `scripts/verificar.sh` e imagem reconstruída será feita na revisão da Etapa 2, quando não houver agente escrevendo no diretório.

## 2. Critérios de aceite

| Critério | Resultado | Evidência |
| --- | --- | --- |
| Fato sem evidência rejeitado pelo pydantic e pelo banco | ok | `min_length=1` em `Fato.evidencias`; constraint trigger adiado `fato_exige_evidencia`; teste de remoção da última evidência também passa |
| Número CNJ com dígito errado rejeitado | ok | `cnj.py` com módulo 97; testes de esquema e de processo |
| RLS isola gabinetes | ok | `test_rls_isola_gabinetes`, `test_rls_impede_gravar_em_outro_gabinete`, `test_rls_ativa_em_todas_as_tabelas_com_gabinete`; política com USING e WITH CHECK, FORCE ROW LEVEL SECURITY |
| Achado não pode ser atualizado | ok | trigger `achado_imutavel`; teste de UPDATE falhando |
| upgrade head cria tudo, downgrade base remove | ok | teste de ida e volta; execução da CLI relatada (15 → 1 → 15 tabelas) |
| Diagrama Mermaid coerente com o código | ok | `docs/modelo-de-dados.md`; `test_migracao_coincide_com_tabelas` garante migração = tabelas |
| Nome real só em ReuIdentidade e Usuario | ok | teste varre todas as colunas |

## 3. Regras comuns

- Estilo, docstrings, tipagem estrita: atendidos.
- Nenhuma dependência nova. Nenhum arquivo da Etapa 0 alterado além de `tests/conftest.py`, só com acréscimos.
- Segredos: `senha_hash` e `mfa_segredo` com `repr=False` no esquema.

## 4. Decisões do executor que o revisor endossa

- `gabinete_id` desnormalizado em todas as tabelas filhas com chaves compostas. Deixa a RLS barata e impede filho apontar para pai de outro gabinete.
- Enums como texto com CHECK. Estender tipo de fato ou de peça vira migração simples.
- Migração escrita à mão com teste que a compara ao modelo SQLAlchemy. É a melhor garantia possível de que as duas fontes não divergem.
- Papel `lupa_app` sem login com RLS forçada, porque superusuário ignora RLS.

## 5. Decisão

**Aprovado.** Etapa 3 liberada.

## 6. Pontos que a Etapa 3 precisa resolver (herdados desta etapa)

1. **Login sob RLS.** A tabela `usuario` está sob a política por gabinete. No login, o gabinete ainda não é conhecido, então a busca por `nome_usuario` precisa acontecer antes de assumir `lupa_app`, ou por uma política adicional que permita ler `usuario` por `nome_usuario`. Decidir e testar.
2. **Administrador.** Com `gabinete_id` nulo, o administrador não vê nada sob `lupa_app`. A Etapa 3 define como o admin opera: uma política que libera quando `current_setting('lupa.papel') = 'administrador'`, ou uma função que itera gabinetes. Em qualquer caso, o acesso do admin a conteúdo gera evento `admin_acesso_conteudo`.
3. **Eventos globais de auditoria.** `evento_auditoria` está sob RLS e eventos sem gabinete (login falho de usuário desconhecido, ações do admin) ficam invisíveis sob `lupa_app`. Mesma solução do item 2.
4. **Membership do papel.** `SET LOCAL ROLE lupa_app` só funciona se o usuário de conexão for membro de `lupa_app` ou superusuário. Nos testes a conexão é superusuário. A Etapa 3 deve criar um usuário de conexão sem superusuário, membro de `lupa_app`, e documentar isso para o compose e para produção.
5. **Grants para tabelas novas.** O `GRANT ... ON ALL TABLES` da migração 0001 só cobre tabelas existentes. Toda migração que criar tabela (ex.: `sessao`) precisa repetir o grant ou definir `ALTER DEFAULT PRIVILEGES`.

## 7. Observações menores, sem bloqueio

- `_salvar_evidencia` usa `on_conflict_do_nothing`. Se uma evidência com o mesmo id chegar com conteúdo diferente, a segunda é ignorada em silêncio. Aceitável agora; a ingestão (Etapa 4) deve garantir ids novos por extração.
- `Fato.valor` volta do banco como JSON, então datas chegam como string ISO. A Etapa 2 precisa converter na entrada do motor. Conferir na revisão da Etapa 2.
- `arquivo` ficou imutável por trigger, além de `achado`. Coerente com os requisitos, embora não fosse critério.
