# Primeiro commit do Lupa

O diretório ainda não é repositório git. Antes do primeiro commit:

1. Confira que `.gitattributes` e `.gitignore` estão na raiz. O `.gitattributes` fixa LF em
   scripts, Python, YAML, HCL, Markdown, TypeScript, Svelte e JSON (o `sh` dos contêineres quebra
   com `\r`); os `.ps1` também ficam em LF (o PowerShell 5.1 aceita).
2. `git init` e `git add --renormalize .` (aplica o fim de linha a tudo que já existe).
3. Rode `git status --ignored` e confira que estão como **ignorados** e nunca entram:
   - `.env` (senhas, `LUPA_VAULT_SECRET_ID`); só `.env.example`, com valores fictícios, entra;
   - `.sinteticos/` (autos sintéticos grandes, regeneráveis por `scripts/gerar_autos.py`);
   - `.backups/` (backups cifrados) e `.backup-chaves/` (chaves `age` dos períodos);
   - `.vault-dev/` (chave de unseal e token raiz do Vault de desenvolvimento);
   - `.venv/`, caches (`.pytest_cache`, `.mypy_cache`, `.ruff_cache`, `__pycache__`), `.coverage`;
   - `front/node_modules/`, `front/build/`, `front/.svelte-kit/`, resultados do Playwright.
4. Os PDFs e o DOCX da raiz (relatórios de pesquisa) não são código: decida um a um se entram.
   Nenhum documento com dado real de processo, pessoa ou tribunal entra no repositório.
5. Procure segredos antes de commitar:
   `git grep -nE "(SECRET_ID|PASSWORD|SENHA|API_KEY)=[^ ]" -- ':!.env.example'` deve voltar vazio
   (fora de valores fictícios documentados nos testes).
6. `git commit -m "Lupa v1: etapas 0 a 7"`.

Se um segredo entrar por engano: troque o segredo (não basta apagar o commit) e siga
`docs/operacao.md`, seção "Comprometimento de credencial".
