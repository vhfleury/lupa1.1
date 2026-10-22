# Revisão — Subetapa 6.10 (acessibilidade, segurança do front e testes ponta a ponta)

21 de outubro de 2026 · revisor

## 1. Verificação executada

Stack reconstruída (api, db, minio, redis, worker, front, proxy):

```
curl -D - https://localhost:8443/login
   Content-Security-Policy: default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-hashes'
   'sha256-S8qM…'; img/font/connect/manifest 'self'; form-action 'self'; frame-ancestors 'none';
   base-uri 'none'; object-src 'none'
   Strict-Transport-Security, Permissions-Policy, COOP e CORP same-origin, X-Frame-Options DENY,
   nosniff, Referrer-Policy no-referrer
docker compose exec api python scripts/verificar_cabecalhos.py   -> ok em 4 rotas
bash front/scripts/e2e.sh                                         -> 36 de 36 testes, 7,9 min
docker compose exec api sh -c 'echo $LUPA_AGENTE_CLIENTE'         -> sdk (restaurado após o E2E)
docker compose exec api bash scripts/verificar.sh                 -> ver seção 1.1
```

## 1.1 Verificação do backend

Executada pelo revisor após a suíte E2E completa: ruff e mypy limpos; 828 testes passaram, 1 pulado, 3 desmarcados, cobertura 98,59%; ponta a ponta da ingestão (1), regressão de injeção da ingestão (2), front, cabeçalhos de segurança (ok em 4 rotas) e suíte de injeção do agente (9) todos verdes. Código de saída 0.

## 2. Critérios de saída por item

| Item | Resultado | Evidência |
| --- | --- | --- |
| 1 cabeçalhos | ok | CSP sem script inline (script de partida externalizado no build, com falha de build se sobrar inline); única exceção é um hash de estilo da `div aria-live` do SvelteKit, conferido no fonte do framework; varredura automatizada no `verificar.sh` e em `seguranca.spec.ts` |
| 2 conteúdo dos autos como texto | ok | sem `{@html}`, `innerHTML` ou Markdown; teste unitário com `<script>`, link Markdown e URL; E2E com página hostil semeada; defeito real corrigido: citação do chat apontava para rota inexistente e levava trecho dos autos na URL, agora só ids |
| 3 acessibilidade | ok | axe em 13 telas nos dois temas, sem violação séria ou crítica; foco no `<main>` ao pular, `role="status"` nos carregamentos, progresso anunciado, seletor de tema em `localStorage` |
| 4 confirmações e sessão | ok | diálogo modal para desativar usuário e liberar revisão; aviso de sessão expirada na recarga com marcador em `sessionStorage` |
| 5 suíte E2E consolidada | ok | projetos `fluxos` e `finais`, contas compartilhadas por fixture global, admin vendo todos os gabinetes; `e2e.sh` e `.ps1` recriam a `api` ao terminar mesmo em falha |
| 6 estabilidade | ok | `logar` do `tests/conftest.py` injeta o relógio e avança o passo TOTP; mesmo padrão corrigido em três testes de login; três execuções completas do executor com 828 testes verdes |
| 7 limpeza do banco | ok | `scripts/limpar_dev.py` só simula sem `--sim`, recusa fora de desenvolvimento e recusa quando quebraria a cadeia global; executado: 89 gabinetes e 1.002.271 eventos removidos, cadeia global preservada |
| 8 custo dos resumos | ok | resumos do dossiê entram no relatório de uso por usuário |

Contagens: backend de 804 para 828 testes; front unitário de 41 para 56; E2E de 22 para 36.

## 3. Decisões do executor endossadas

- Hash de estilo em vez de `unsafe-inline`: a exceção é mínima e explícita, e a varredura acusa se o hash mudar numa atualização do SvelteKit.
- Recriação do proxy pelo `e2e.sh`: o Caddyfile entra por bind mount e a edição não chega ao contêiner em execução. Documentado.
- Fins de linha: as edições pelo host gravaram CRLF e quebraram o `verificar.sh` no contêiner; o executor converteu seus arquivos para LF e devolveu os demais ao estado anterior. Vale um `.gitattributes` com `* text=auto eol=lf` para scripts, quando o repositório for iniciado no git.

## 4. Decisão

**Aprovado.** Etapa 6 concluída.

## 5. Itens para a Etapa 7

1. HSTS só tem efeito com certificado real; `docs/operacao.md` (7.10) descreve a emissão.
2. Objetos órfãos no MinIO não são removidos pela limpeza; a exclusão criptográfica da 7.7 cobre.
3. `.gitattributes` para fixar LF em scripts e YAML antes do primeiro commit.
4. Itens 4 e 5 da revisão 6.4-6.9 (precisão do destaque, retomada de upload, desfazer correção, filtros por nome) ficam para depois do piloto.
