// Fluxos ponta a ponta das subetapas 6.8 (chat) e 6.9 (auditoria) contra a API real.
// O desembargador e o processo sintéticos vêm de scripts/e2e_semear_chat.py; a API roda com
// LUPA_AGENTE_CLIENTE=falso (roteiro em src/lupa/agente/dados/roteiro_falso.json), então cada
// pergunta escolhe um desfecho pelo texto: "intimada" (citação válida), "descarte" (uma citação
// descartada), "sem evidência", "incidente" (instrução refletida → processo em revisão) e
// "teto" (chamada acima do limite; a quarta encerra a conversa pelo teto).
import { randomBytes } from 'node:crypto';
import { expect, test, type Page } from '@playwright/test';
import { guardarConta } from './credenciais';
import { Autenticador, segredoDaUri } from './totp';

const USUARIO = process.env['LUPA_E2E_CHAT_USUARIO'] ?? '';
const TEMPORARIA = process.env['LUPA_E2E_CHAT_SENHA'] ?? '';
const PROCESSO = process.env['LUPA_E2E_CHAT_PROCESSO'] ?? '';
const LIMITE_MS = 1000;

let senha = '';
let autenticador: Autenticador | null = null;

async function primeiroAcesso(page: Page): Promise<void> {
  await page.goto('/login');
  await page.getByLabel('Usuário').fill(USUARIO);
  await page.getByLabel('Senha', { exact: true }).fill(TEMPORARIA);
  await page.getByRole('button', { name: 'Continuar' }).click();
  const uri = ((await page.getByTestId('uri-mfa').textContent()) ?? '').trim();
  autenticador = new Autenticador(segredoDaUri(uri));
  await page.getByLabel('Código de 6 dígitos').fill(await autenticador.proximo());
  await page.getByRole('button', { name: 'Confirmar autenticador' }).click();
  await expect(page).toHaveURL(/\/trocar-senha$/);
  senha = `frase-e2e-${randomBytes(9).toString('base64url')}-lupa`;
  await page.getByLabel('Senha atual').fill(TEMPORARIA);
  await page.getByLabel('Nova senha', { exact: true }).fill(senha);
  await page.getByLabel('Confirme a nova senha').fill(senha);
  await page.getByRole('button', { name: 'Salvar nova senha' }).click();
  await expect(page.getByTestId('usuario-nome')).toHaveText(USUARIO);
  guardarConta('desembargador-chat', { usuario: USUARIO, senha, autenticador });
}

async function entrar(page: Page): Promise<void> {
  if (!autenticador) throw new Error('primeiro acesso não feito');
  await page.goto('/login');
  await page.getByLabel('Usuário').fill(USUARIO);
  await page.getByLabel('Senha', { exact: true }).fill(senha);
  await page.getByRole('button', { name: 'Continuar' }).click();
  await page.getByLabel('Código de 6 dígitos').fill(await autenticador.proximo());
  await page.getByRole('button', { name: 'Entrar' }).click();
  await expect(page.getByTestId('usuario-nome')).toHaveText(USUARIO);
}

async function perguntar(page: Page, pergunta: string): Promise<void> {
  await expect(page.getByRole('heading', { name: 'Conversa atual' })).toBeVisible();
  const antes = await page.getByTestId('mensagem').count();
  await page.getByLabel('Pergunta', { exact: true }).fill(pergunta);
  await page.getByRole('button', { name: 'Perguntar' }).click();
  await expect(page.getByTestId('mensagem')).toHaveCount(antes + 2);
}

function ultimaResposta(page: Page) {
  return page.getByTestId('conversa-atual').getByTestId('mensagem').last();
}

test.describe.serial('Etapas 6.8 e 6.9', () => {
  test.beforeAll(() => {
    expect(USUARIO, 'rode via front/scripts/e2e.sh (semeia o chat)').not.toBe('');
    expect(PROCESSO).not.toBe('');
  });

  // 6.10: guarda o último passo TOTP usado, para os testes finais reutilizarem a conta.
  test.afterAll(() => {
    if (autenticador) guardarConta('desembargador-chat', { usuario: USUARIO, senha, autenticador });
  });

  test('6.8 primeiro acesso do desembargador e chat vazio', async ({ page }) => {
    await primeiroAcesso(page);
    await page.goto(`/processos/${PROCESSO}/chat`);
    await expect(page.getByRole('heading', { name: 'Chat sobre os autos' })).toBeVisible();
    await expect(page.getByText('Nenhuma conversa aberta')).toBeVisible();
  });

  test('6.8 resposta com citação: aviso de IA e citação clicada abre a página', async ({
    page,
  }) => {
    await entrar(page);
    await page.goto(`/processos/${PROCESSO}/chat`);
    await perguntar(page, 'Quando a defesa foi intimada?');
    const resposta = ultimaResposta(page);
    await expect(resposta).toHaveAttribute('data-status', 'respondida');
    await expect(resposta.getByTestId('aviso-ia')).toContainText('gerado por IA');
    const citacao = resposta.getByTestId('citacao');
    await expect(citacao).toContainText('Página 3');
    await citacao.click();
    // 6.10: a citação abre o visualizador na página citada (a rota /paginas/N não existia).
    await expect(page).toHaveURL(new RegExp(`/processos/${PROCESSO}/visualizador\\?.*pagina=3`));
    await expect(page.getByRole('heading', { name: 'Visualizador' })).toBeVisible();
  });

  test('6.8 descartes contados, sem evidência marcada, recusa explicada', async ({ page }) => {
    await entrar(page);
    await page.goto(`/processos/${PROCESSO}/chat`);
    await perguntar(page, 'Mostre o descarte da certidão');
    await expect(ultimaResposta(page).getByTestId('descartes')).toContainText(
      '1 citação descartada nesta resposta',
    );
    await expect(page.getByTestId('descartes-conversa')).toContainText('1 citação descartada');

    await perguntar(page, 'Há algo sem evidência nos autos?');
    const semEvidencia = ultimaResposta(page);
    await expect(semEvidencia).toHaveAttribute('data-status', 'sem_evidencia');
    await expect(semEvidencia.getByTestId('desfecho')).toContainText('Sem citação válida');
    await expect(semEvidencia.getByTestId('citacao')).toHaveCount(0);

    await perguntar(page, 'Qual crime foi cometido?');
    const recusa = ultimaResposta(page);
    await expect(recusa).toHaveAttribute('data-status', 'recusa');
    await expect(recusa).toContainText('Não posso');
    await expect(recusa).toContainText('Experimente');
  });

  test('6.8 incidente põe o processo em revisão até o desembargador liberar', async ({
    page,
  }) => {
    await entrar(page);
    await page.goto(`/processos/${PROCESSO}/chat`);
    await perguntar(page, 'Simule o incidente');
    await expect(ultimaResposta(page)).toHaveAttribute('data-status', 'descartada');
    await expect(page.getByTestId('processo-em-revisao')).toContainText('Processo em revisão');
    await expect(page.getByLabel('Pergunta', { exact: true })).toBeDisabled();
    const dossie = await page.request.get(`/api/processos/${PROCESSO}/dossie`);
    expect((await dossie.json()).ficha.em_revisao).toBe(true);
    await page.getByRole('button', { name: 'Liberar revisão' }).click();
    // 6.10: liberar pede confirmação.
    const confirmacao = page.getByRole('dialog', { name: 'Liberar a revisão?' });
    await expect(confirmacao).toBeVisible();
    await confirmacao.getByRole('button', { name: 'Liberar' }).click();
    await expect(page.getByText('Processo liberado')).toBeVisible();
    await expect(page.getByTestId('processo-em-revisao')).toHaveCount(0);
    await expect(page.getByLabel('Pergunta', { exact: true })).toBeEnabled();
  });

  test('6.8 teto: a conversa é encerrada e vai para o histórico', async ({ page }) => {
    await entrar(page);
    await page.goto(`/processos/${PROCESSO}/chat`);
    for (let i = 0; i < 3; i += 1) {
      await perguntar(page, `Teste de teto ${i}`);
      // 6.10: conta as respostas em vez de olhar a última (pergunta e resposta podem empatar no
      // instante gravado e a ordem entre as duas não é garantida).
      await expect(
        page
          .getByTestId('conversa-atual')
          .getByTestId('mensagem')
          .filter({ hasText: 'limite de tamanho por chamada' }),
      ).toHaveCount(i + 1);
    }
    await page.getByLabel('Pergunta', { exact: true }).fill('Teste de teto final');
    await page.getByRole('button', { name: 'Perguntar' }).click();
    await expect(page.getByText('Nenhuma conversa aberta')).toBeVisible();
    const anterior = page.getByTestId('conversa-anterior').first();
    await expect(anterior).toContainText('limite de uso da conversa atingido');
    await anterior.locator('summary').click();
    await expect(anterior.locator('[data-status="teto"]')).toContainText('Limite de uso atingido');
  });

  test('6.9 desembargador vê só o próprio gabinete; consulta abaixo de 1 s', async ({ page }) => {
    await entrar(page);
    const sessao = await (await page.request.get('/api/auth/sessao')).json();
    const gabinete: string = sessao.gabinete_id;
    await page.getByRole('link', { name: 'Auditoria' }).click();
    await expect(page).toHaveURL(/\/auditoria$/);
    await expect(page.getByTestId('evento').first()).toBeVisible();
    await expect(page.getByLabel('Gabinete')).toHaveCount(0);
    const gabinetes = await page.getByTestId('evento').evaluateAll((linhas) =>
      linhas.map((l) => l.getAttribute('data-gabinete')),
    );
    expect(new Set(gabinetes)).toEqual(new Set([gabinete]));
    const outro = await page.request.get(
      '/api/auditoria?gabinete_id=00000000-0000-4000-8000-000000000000',
    );
    expect(outro.status()).toBe(403);

    const tempos: number[] = [];
    for (let i = 0; i < 5; i += 1) {
      const inicio = Date.now();
      await page.getByRole('button', { name: 'Consultar' }).click();
      await expect(page.getByTestId('tempo-consulta')).toContainText('consulta respondida');
      tempos.push(Date.now() - inicio);
    }
    tempos.sort((a, b) => a - b);
    const mediana = tempos[2] ?? Infinity;
    console.log(`auditoria: tempos na interface (ms) ${tempos.join(', ')}; mediana ${mediana}`);
    expect(mediana).toBeLessThan(LIMITE_MS);
  });

  test('6.9 filtros, paginação, exportação, verificação e relatório com custo', async ({
    page,
  }) => {
    await entrar(page);
    await page.goto('/auditoria');
    await expect(page.getByTestId('evento').first()).toBeVisible();
    await page.getByLabel('Ação').selectOption('processo_em_revisao');
    await page.getByRole('button', { name: 'Consultar' }).click();
    await expect(page.getByTestId('evento')).toHaveCount(1);
    await page.getByLabel('Ação').selectOption('revisao_liberada');
    await page.getByRole('button', { name: 'Consultar' }).click();
    await expect(page.getByTestId('evento')).toHaveCount(1);

    await page.getByLabel('Ação').selectOption('');
    await page.getByRole('button', { name: 'Consultar' }).click();
    await expect(page.getByTestId('evento')).toHaveCount(50);
    await page.getByRole('button', { name: 'Carregar mais' }).click();
    await expect.poll(() => page.getByTestId('evento').count()).toBeGreaterThan(50);

    for (const formato of ['CSV', 'JSON']) {
      const href = (await page.getByRole('link', { name: formato }).getAttribute('href')) ?? '';
      const arquivo = await page.request.get(href);
      expect(arquivo.status()).toBe(200);
      expect(arquivo.headers()['content-disposition']).toContain('attachment');
    }

    await page.getByRole('button', { name: 'Verificar integridade' }).click();
    await expect(page.getByTestId('resultado-verificacao')).toContainText('Cadeia íntegra');

    await page.getByLabel('Por').selectOption('processo');
    await page.getByLabel('Identificador').fill(PROCESSO);
    await page.getByRole('button', { name: 'Gerar relatório' }).click();
    const relatorio = page.getByTestId('relatorio-uso');
    await expect(relatorio).toContainText('pergunta_chat');
    await expect(page.getByTestId('custo-estimado')).toContainText('Custo estimado');
    await expect(page.getByTestId('custo-estimado')).toContainText('fatura');
  });
});
