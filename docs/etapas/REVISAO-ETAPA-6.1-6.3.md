# Revisão — Subetapas 6.1 a 6.3 (interface web: esqueleto, login e MFA, gestão de usuários)

21 de outubro de 2026 · revisor

## 1. Verificação executada

Com os dois agentes (Etapa 5 e front) encerrados, stack reconstruída:

```
docker compose up -d --build --wait        -> api, db, minio, redis, worker, front, proxy saudáveis
bash front/scripts/e2e.sh                  -> 8 de 8 testes Playwright contra a stack real
curl https://localhost:8443/api/saude      -> 200 pelo proxy, mesmo origin
curl -D - https://localhost:8443/login     -> X-Frame-Options DENY, nosniff, Referrer-Policy no-referrer
```

A suíte do backend (`scripts/verificar.sh`) é avaliada na revisão da Etapa 5, que rodou junto.

O navegador embutido do revisor recusou o certificado autoassinado do Caddy, então a conferência visual ficou pelos testes Playwright, que cobrem os fluxos de ponta a ponta.

## 2. Critérios de saída

| Subetapa | Resultado | Evidência |
| --- | --- | --- |
| 6.1 esqueleto | ok | SvelteKit 2 com Svelte 5, SPA estática, TypeScript estrito, avisos de acessibilidade como erro; serviços `front` (Caddy estático, usuário 10001, somente leitura) e `proxy` (Caddy, `tls internal`); rota protegida redireciona ao login; `/api/*` no mesmo origin |
| 6.2 login e MFA | ok | E2E: primeiro acesso com QR desenhado no cliente, código errado recusado, troca obrigatória, sessão expirada com aviso, mensagens idênticas para usuário inexistente e senha errada, bloqueio após 5 falhas sem revelar existência |
| 6.3 gestão de usuários | ok | E2E: admin cria gabinete e desembargador com senha temporária exibida uma vez; desembargador cria, desativa, reativa e reseta assessor; papel errado recebe 403 no servidor; assessor não vê telas de gestão |

Lint 0 avisos, typecheck 0 erros, 18 testes unitários (Vitest).

## 3. Correções herdadas da Etapa 3

| Correção | Implementação | Teste |
| --- | --- | --- |
| Auditoria gravada antes da resposta | evento gravado antes do corpo sair do middleware; falha vira 500 sem conteúdo | `test_falha_ao_gravar_auditoria_vira_500_e_o_conteudo_nao_sai` |
| Bloqueio progressivo e rate limit por IP | 1, 5 e 15 minutos na 5ª, 10ª e 15ª falha; 20 falhas por IP em 15 minutos; tudo auditado | cinco testes em `tests/acesso/test_login.py` |

## 4. Decisões do executor endossadas

- Proxy reverso removendo o prefixo `/api` em vez de `root_path` na API: mantém `api/app.py` intocado e o cookie `Secure`/`SameSite=Strict` funciona sem CORS.
- API com `--proxy-headers` restrita à sub-rede do proxy, para a auditoria registrar o IP do cliente e não o do proxy. Conferido pelo executor com o contêiner de E2E.
- `scripts/e2e_preparar.py` fora da lista inicial: necessário porque a senha do admin de desenvolvimento não é conhecida. Recusa rodar fora de desenvolvimento ou teste e reseta o admin com senha aleatória só em memória. Aceito.

## 5. Decisão

**Aprovado.** Subetapas 6.4 a 6.10 liberadas.

## 6. Itens para as subetapas seguintes

1. O passo `== front ==` dentro do contêiner da API só confere o carimbo de verificação gerado no build da imagem; não detecta fonte alterada sem rebuild. No host, `verificar.ps1` reconstrói o estágio de verificação. Documentado; aceitável.
2. CSP e HSTS ficam para 6.10, com varredura de cabeçalhos.
3. Sem `API_PORTA_HOST`, o compose publica a API numa porta efêmera em loopback. Em produção a porta direta não deve ser publicada, porque permitiria forjar `X-Forwarded-For` a partir da sub-rede do proxy. Registrar no `docs/operacao.md` (7.10).
4. Na recarga completa sem sessão, o front não distingue expiração de "nunca entrou". Melhoria de interface para 6.10.
5. Confirmação antes de desativar usuário e alternância manual de tema: 6.10.
