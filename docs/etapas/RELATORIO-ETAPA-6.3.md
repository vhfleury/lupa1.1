# Relatório da Etapa 6.3 — Gestão de usuários

## O que foi feito

- `/usuarios` (`front/src/routes/usuarios/+page.svelte`):
  - Desembargador: lista os usuários do próprio gabinete; cria assessor (o formulário não
    oferece outro papel nem outro gabinete); desativa, reativa, reseta senha e reseta
    autenticador de assessores. Nenhum botão sobre si mesmo.
  - Administrador: lista todos os usuários com o nome do gabinete; cria desembargador ou assessor
    escolhendo o gabinete; gere desembargadores e assessores. Nenhum botão sobre o próprio admin.
  - Senha temporária (criação e reset) exibida uma única vez (`SenhaTemporaria.svelte`), com
    aviso; ao fechar, o valor sai do estado da página e não volta (nem em recarga).
- `/gabinetes` (só administrador): lista e cria gabinetes; cria desembargadores.
- Matriz refletida na interface (`front/src/lib/permissoes.ts`), a partir das permissões que
  `GET /api/auth/sessao` devolve de `papeis.py`: o menu mostra "Usuários" só para quem gere
  usuários e "Gabinetes" só para quem tem `gerir_gabinetes`; botões por linha seguem
  `gerir_assessor`, `resetar_assessor` e `gerir_desembargador` no escopo do gabinete. Quem abrir a
  URL sem permissão vê um aviso, sem formulário.
- API: `GET /gabinetes` (só administrador, `exige_papel(Permissao.GERIR_GABINETES)`), com
  `servico.listar_gabinetes`. Testes em `tests/acesso/test_sessao_e_gabinetes.py`.

## Testes

Unitários: `permissoes.test.ts` (assessor não gere ninguém; desembargador só assessor do próprio
gabinete; ninguém age sobre si mesmo nem sobre o admin; admin gere tudo) e `componentes.test.ts`
(menu por papel, senha temporária).

E2E (`front/e2e/testes/fluxos.spec.ts`):

| Teste | Cobre |
| --- | --- |
| `6.3 admin cria gabinete e desembargador; senha temporária aparece uma única vez` | cria gabinete e desembargador pela interface; senha some ao fechar e após recarga; admin vê botões sobre o desembargador e nenhum sobre si |
| `6.2/6.3 desembargador: primeiro acesso e gestão completa de assessor` | sem menu Gabinetes; formulário sem escolha de papel; cria assessor; desativa, reativa, reseta senha (nova senha diferente) e autenticador; nenhum botão sobre si |
| `6.3 matriz reconfirmada no servidor…` | desembargador: tela `/gabinetes` sem formulário; `POST /api/gabinetes`, `GET /api/gabinetes` e `POST /api/usuarios` com papel desembargador → **403** |
| `6.2/6.3 assessor: … sem telas de gestão; servidor nega` | menu só com Início; `/usuarios` com aviso; `GET` e `POST /api/usuarios` → **403** |

## Critério de aceite

Ponta a ponta com Playwright para desembargador e admin: passando (8/8 na suíte). Matriz da
Etapa 3 refletida na interface e reconfirmada no servidor com chamadas diretas que recebem 403.

## Fora do escopo

Editar nome de usuário ou mudar papel (a API não oferece); listar sessões ativas; confirmação
antes de desativar (a ação é reversível pela reativação e auditada).
