# Relatório da subetapa 6.10: acessibilidade, segurança do front e testes ponta a ponta

Inclui os itens herdados da revisão 6.4-6.9 (seção 5: itens 1, 2, 3, 6 e 7) e da revisão 6.1-6.3
(seção 6: itens 2, 4 e 5).

## 1. Cabeçalhos de segurança no proxy

`proxy/Caddyfile`, em todas as respostas (SPA, estáticos e `/api`):

- `Content-Security-Policy: default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-hashes' 'sha256-S8qMpvofolR8Mpjy4kQvEm7m1q8clzU4dfDH0AmvZjo='; img-src 'self'; font-src 'self'; connect-src 'self'; manifest-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'; object-src 'none'`
- `Strict-Transport-Security: max-age=31536000; includeSubDomains`. Só tem efeito em produção, com certificado válido; com o certificado autoassinado de desenvolvimento o navegador ignora o cabeçalho.
- `Permissions-Policy`: acelerômetro, autoplay, câmera, captura de tela, geolocalização, giroscópio, magnetômetro, microfone, MIDI, pagamento, publickey-credentials-get, screen-wake-lock, USB e XR desligados.
- `Cross-Origin-Opener-Policy: same-origin`, `Cross-Origin-Resource-Policy: same-origin`, `X-Permitted-Cross-Domain-Policies: none`.
- Continuam os de antes: `X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options` e a remoção de `Server`.

Nenhum script inline. O `<script>` de partida que o SvelteKit grava no `index.html` passa a ser o
arquivo `/inicio.js`, gerado no build por `front/scripts/externalizar-inicio.mjs`. Esse script
também aplica o tema salvo antes do primeiro desenho, e o build falha se sobrar no HTML algum
script inline, `<style>`, atributo `style` ou atributo `on*=`. No `app.html`,
`style="display: contents"` virou a classe `.raiz`. O zoom e o destaque do visualizador usam
diretivas `style:`, que escrevem pela API CSSOM (a CSP permite).

Única exceção de estilo: o anunciador de rota do próprio SvelteKit, uma `div aria-live` gerada
pelo framework com atributo `style` fixo. O E2E pegou a violação em todas as telas. Ela é liberada
só pelo hash SHA-256 desse texto exato, com `'unsafe-hashes'`. O hash foi conferido contra o fonte
do `@sveltejs/kit` 2.15.1; qualquer outro estilo inline continua bloqueado. Ao atualizar o
SvelteKit, é preciso conferir o hash de novo.

Varredura automática:
- `scripts/verificar_cabecalhos.py`, novo passo `== cabecalhos de seguranca ==` no `verificar.sh`
  (contêiner, `https://proxy:8443`) e no `verificar.ps1` (host, `https://localhost:8443`). Falha
  se faltar algum cabeçalho ou se a CSP afrouxar: `unsafe-inline`/`eval`, curinga,
  `data:`/`blob:`/http, origem externa em script ou estilo, hash diferente, falta de
  `frame-ancestors`, `form-action` etc. Com o proxy fora do ar só avisa, a menos que
  `LUPA_EXIGIR_CABECALHOS=1`. Testes em `tests/unit/test_verificar_cabecalhos.py` (18).
- `front/e2e/testes/seguranca.spec.ts`: cabeçalhos em 6 rotas, `index.html` sem nada inline e
  nenhuma violação de CSP (evento `securitypolicyviolation` e console) ao navegar por 9 telas.

Observação: o Caddyfile entra por bind mount de arquivo único. No Docker Desktop, editar o arquivo
não chega ao contêiner já em execução. Por isso `e2e.sh`/`.ps1` agora recriam o `proxy`.

## 2. Conteúdo dos autos só como texto

Auditoria dos componentes que mostram texto de páginas, trechos, citações, explicações e respostas
(`MensagemChat`, dossiê, validações, visualizador e auditoria): nenhum `{@html}` (a regra do ESLint
já existia), nenhum `innerHTML`, nenhum renderizador de Markdown e nenhuma linkificação. Os únicos
`href` montados pelo front usam ids.

Defeito encontrado e corrigido: a citação do chat apontava para `/processos/{id}/paginas/N`, rota
que não existe (caía no 404 da SPA; o E2E da 6.8 só conferia a URL), e levava o **trecho dos autos
na query string**, que acaba em histórico e logs do proxy. Agora o link é
`/processos/{id}/visualizador?arquivo=…&pagina=N`, só com ids e número.

Testes:
- unitário `front/src/lib/seguranca.test.ts`: mensagem com `<script>`, `[link](http://x)`,
  `http://exemplo` e `<img onerror>` sai literal, sem elemento criado e com um único link, o
  interno. Inclui a varredura das fontes (`{@html`, `innerHTML`, `document.write`, Markdown,
  linkify, `href` com texto, atributo `style`).
- E2E: `scripts/e2e_semear_chat.py` cria um processo sintético cuja certidão tem os três padrões.
  O teste pergunta no chat e confere que a citação mostra os padrões como texto, que
  `window.__lupaXss` continua indefinido, que não há `a[href^=http]` e que nada viola a CSP, também
  depois de recarregar a página.

## 3. Acessibilidade

- O axe (`@axe-core/playwright` 4.10.1, WCAG 2.1 A/AA) roda em 13 telas (login, início, processos,
  processo, dossiê, visualizador, validações, chat, auditoria do desembargador, usuários do
  desembargador, e gabinetes, usuários e auditoria do admin), nos temas claro e escuro.
  **Resultado: 0 violações sérias ou críticas nos dois temas**, já na primeira execução. Os tokens
  de cor da 6.1 já atendiam o contraste AA.
- Teclado:
  - o link "pular para o conteúdo" não movia o foco, porque o roteador do SvelteKit trata o
    `#conteudo` sem focar o destino. Corrigido no `+layout.svelte`: o foco agora vai para o `<main>`;
  - a ordem de tabulação do login, do cabeçalho e do menu foi conferida, com foco visível
    (contorno de 3 px) em cada elemento;
  - foi possível navegar até Processos só com Tab e Enter;
  - o visualizador responde ao teclado (zoom com + e −);
  - no diálogo de confirmação, o foco começa em "Cancelar" e Esc cancela.
- `aria-live`: o progresso do envio é anunciado em degraus de 10%, e os três "Carregando…" que não
  tinham papel ganharam `role="status"`. Erros já usavam `role="alert"`.
- Tema manual (claro, escuro ou do sistema): seletor rotulado no cabeçalho e no rodapé das telas
  sem moldura. Fica só em `localStorage` (`lupa.tema`), não vai em cookie e é aplicado por
  `/inicio.js` antes do primeiro desenho. O CSS cobre `[data-tema=escuro]` e
  `prefers-color-scheme` sem `[data-tema=claro]`.

## 4. Confirmações e sessão encerrada

- Desativar usuário e liberar revisão abrem `Confirmacao.svelte`, um `<dialog>` modal com título e
  descrição acessíveis.
- Marcador `lupa.sessao-anterior` em `sessionStorage`, sem nenhum dado da sessão:
  - é gravado quando a sessão é carregada;
  - é consumido pelo guarda de rotas;
  - na recarga completa sem sessão, leva a `/login?motivo=expirada` com "Sessão encerrada ou
    expirada";
  - "Sair" apaga o marcador, então quem sai de propósito não vê o aviso.
- Testes: unitários (`tema.test.ts`, `componentes.test.ts`) e E2E (`auditoria-admin.spec.ts`,
  `fluxos.spec.ts`, `chat-auditoria.spec.ts`).

## 5. Suíte E2E consolidada

- Dois projetos no `playwright.config.ts`:
  - `fluxos`: 6.1 a 6.9, mesma ordem de antes;
  - `finais`: segurança, acessibilidade e auditoria como admin; depende de `fluxos`.
- Fixture global (`testes/global-setup.ts` e `testes/credenciais.ts`): cada arquivo dono de uma
  conta guarda usuário, senha, segredo TOTP, último passo usado e o estado de sessão do navegador
  em `/tmp` do contêiner efêmero. Os testes finais reutilizam a sessão e só entram de novo se ela
  tiver caído.
- Admin na auditoria: vê eventos de mais de um gabinete, o filtro por gabinete funciona e a API
  aceita qualquer gabinete.
- `front/scripts/e2e.sh` usa `trap EXIT` (e INT/TERM) e, ao terminar, mesmo em falha, recria o
  serviço `api` sem `LUPA_AGENTE_CLIENTE=falso`. O `.ps1` faz o mesmo com `try/finally`.
  Conferido depois da execução: `LUPA_AGENTE_CLIENTE=sdk`.
- `verificar.ps1` (host) ganhou o passo opcional `== e2e ==`, ligado com `LUPA_VERIFICAR_E2E=1`.
  Não existe no contêiner. Documentado em `docs/front.md` e `.env.example`.
- Estabilização:
  - no teste do teto, a ordem entre pergunta e resposta empatadas no mesmo instante não é
    garantida; ele agora conta as respostas em vez de olhar a última;
  - o `Autenticador` do E2E usa só o passo TOTP corrente, sem adiantar um passo. Houve uma falha
    de login intermitente quando ele usava `atual+1`.

**Resultado final: `bash front/scripts/e2e.sh` com 36 testes passando** (22 anteriores e 14
novos), em 6,7 min. Na auditoria, a mediana da interface ficou em 149 ms.

## 6. Estabilidade dos testes de backend

`tests/conftest.py::logar` agora gera o código e o instante juntos (`codigo_totp_e_instante`) e
injeta esse instante no `relogio` da API durante o `/auth/mfa`. Assim o passo não vira entre a
geração e o uso. Se os passos da janela já foram gastos por logins anteriores do mesmo usuário, o
instante avança para o próximo passo livre em vez de falhar com "janela TOTP esgotada". Novo
utilitário `relogio_fixo`.

O mesmo padrão aparecia em `tests/acesso/test_login.py` (reuso de código, primeiro acesso com
`pyotp.now()` e flags do cookie) e foi corrigido também. Não há outro login real com TOTP nos
testes: os demais passam por `logar`.

**Três execuções de `docker compose exec api bash scripts/verificar.sh`, todas com saída 0:**

| Execução | pytest | cobertura | demais passos |
| --- | --- | --- | --- |
| 1 | 828 passaram, 1 pulado (8 min 10 s) | 98,59% | ponta a ponta 1/1, injeção 2/2, front ok, cabeçalhos ok, agente 9/9 |
| 2 | 828 passaram, 1 pulado (8 min 16 s) | 98,59% | idem |
| 3 | 828 passaram, 1 pulado (8 min 11 s) | 98,59% | idem |

Front unitário: 56 testes (eram 41).

## 7. Limpeza do banco de desenvolvimento

`scripts/limpar_dev.py` seleciona os gabinetes cujo nome começa por um destes prefixos (sem
diferenciar maiúsculas): "Gabinete ponta a ponta", "Gabinete de calibração", "Gabinete E2E",
"Gabinete Processos E2E", "carga" e "e2e". Os nomes reais encontrados no banco eram "Gabinete E2E…"
e "Gabinete Processos E2E…", por isso esses prefixos entraram na lista.

Sem `--sim`, só simula. Com `--sim`, numa transação:
1. desliga a trava append-only de `evento_auditoria` (só o dono das tabelas consegue), apaga as
   cadeias inteiras desses gabinetes e religa a trava antes do commit;
2. apaga todas as linhas com `gabinete_id` deles, em ordem topológica;
3. apaga os gabinetes.

O script recusa rodar fora de `desenvolvimento`/`teste` e também se algum evento da cadeia global
apontar para esses usuários, porque apagá-lo quebraria a cadeia global. Não toca no MinIO. Testes:
`tests/auditoria/test_limpar_dev.py` (5): simulação, remoção, cascata de processo, a cadeia de
outro gabinete continua íntegra, a trava volta, as duas recusas e a CLI.

**Executado no banco de desenvolvimento ao final: 89 gabinetes e 1.002.271 eventos de auditoria
removidos**, além de 1.064 usuários, 83 processos, 49.362 páginas, 6.604 peças, 7.759 evidências,
1.201 fatos, 167 achados e 202 mensagens, entre outros. Ficaram 0 gabinetes e 244 eventos da
cadeia global. O próximo E2E recria a carga de 1 milhão de eventos.

## 8. Custo dos resumos do dossiê por usuário

`custo_estimado` por usuário agora soma, além das conversas dele, as chamadas sem conversa (os
resumos do dossiê) cujo evento `chamada_modelo` tem esse `usuario_id`. Novo teste em
`tests/auditoria/test_custo.py`, e o E2E confere o custo no relatório por usuário.

## Arquivos

- Front:
  - `front/src/lib/{tema,marcador}.ts`
  - `front/src/lib/componentes/{Confirmacao,SeletorTema}.svelte`
  - `front/src/lib/seguranca.test.ts`, `front/src/lib/tema.test.ts`
  - `front/scripts/externalizar-inicio.mjs`
  - ajustes em `app.html`, `app.css`, layout, login, usuários, chat, processo, dossiê, validações,
    `Visualizador.svelte`, `geometria.ts` e `chat.ts`
- E2E:
  - `front/e2e/testes/{global-setup,credenciais,acessibilidade.spec,seguranca.spec,auditoria-admin.spec}.ts`
  - config, `totp.ts` e os três specs antigos
  - `package.json` e `package-lock.json` (`@axe-core/playwright`)
- Proxy: `proxy/Caddyfile`
- Scripts:
  - `scripts/{verificar_cabecalhos,limpar_dev}.py`
  - `scripts/e2e_semear_chat.py`, `verificar.sh`, `verificar.ps1`
  - `front/scripts/e2e.{sh,ps1}`
- Compose: `docker-compose.yml` (variável `LUPA_E2E_HOSTIL_PROCESSO`)
- Backend: `src/lupa/auditoria/consulta.py`
- Testes de backend:
  - `tests/conftest.py`, `tests/acesso/test_login.py`, `tests/auditoria/test_custo.py`
  - `tests/auditoria/test_limpar_dev.py`, `tests/unit/test_verificar_cabecalhos.py`
- Documentação: `docs/front.md`, `README.md`, `.env.example`

## Fora do escopo ou pendente

- HSTS só vale de verdade com certificado real (produção, 7.10). Não foi pedido preload.
- O hash do anunciador do SvelteKit precisa ser revisto a cada atualização do framework. Se mudar,
  o E2E e a varredura acusam.
- O `limpar_dev.py` não remove objetos órfãos no MinIO.
- Destaque de evidência por caractere, retomada de upload e desfazer correção continuam para
  depois do piloto (revisão 6.4-6.9, itens 4 e 5).
- Incidente de processo: no editor do host, alguns arquivos meus ficaram com fim de linha CRLF e
  quebraram o `verificar.sh` no contêiner (`set -o pipefail` inválido). Foi corrigido convertendo
  para LF só os arquivos desta subetapa. Arquivos de outras etapas que já estavam em CRLF ficaram
  como estavam.
