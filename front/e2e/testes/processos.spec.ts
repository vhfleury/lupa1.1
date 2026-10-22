// Fluxos ponta a ponta das subetapas 6.4 a 6.7 contra a stack real (proxy, API, worker, MinIO).
// O assessor e o processo sintético vêm de scripts/e2e_processos.py (rodado por e2e.sh): o
// processo já está na fila do worker real quando o teste começa. O assessor faz o primeiro
// acesso pela tela (autenticador e troca de senha), como no uso real.
import { randomBytes } from 'node:crypto';
import { createWriteStream } from 'node:fs';
import { stat, unlink } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { expect, test, type BrowserContext, type Page } from '@playwright/test';
import { guardarConta, guardarSessao } from './credenciais';
import { Autenticador, segredoDaUri } from './totp';

const USUARIO = process.env['LUPA_E2E_PROC_USUARIO'] ?? '';
const SENHA_TEMPORARIA = process.env['LUPA_E2E_PROC_SENHA'] ?? '';
const PROCESSO = process.env['LUPA_E2E_PROC_ID'] ?? '';
const MEGABYTES_GRANDE = Number(process.env['LUPA_E2E_UPLOAD_MB'] ?? '500');
const ESTADOS_FINAIS = ['concluido', 'em_revisao', 'quarentena', 'falho', 'parcial'];

let processoNovo = '';

// Um único login na suíte: o primeiro acesso deixa a sessão no contexto compartilhado e os
// testes seguintes a reutilizam (menos logins vindos do mesmo IP do contêiner de E2E, que
// outros arquivos de teste também usam, inclusive provocando bloqueios de propósito).
let contexto: BrowserContext;
let page: Page;

/** Dígito verificador CNJ (módulo 97), para montar um número válido e um inválido. */
function numeroCnj(sequencial: number, valido: boolean): string {
  const seq = String(sequencial).padStart(7, '0');
  const base = BigInt(`${seq}2025809000100`);
  let digito = Number(98n - (base % 97n));
  if (!valido) digito = (digito + 1) % 100;
  return `${seq}-${String(digito).padStart(2, '0')}.2025.8.09.0001`;
}

/** PDF mínimo válido (uma página com texto), montado com os offsets corretos do xref. */
function pdfMinimo(texto: string): Buffer {
  const conteudo = `BT /F1 14 Tf 72 720 Td (${texto}) Tj ET`;
  const objetos = [
    '<< /Type /Catalog /Pages 2 0 R >>',
    '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
    '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
    '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
    `<< /Length ${conteudo.length} >>\nstream\n${conteudo}\nendstream`,
  ];
  let corpo = '%PDF-1.4\n';
  const offsets: number[] = [];
  objetos.forEach((objeto, i) => {
    offsets.push(Buffer.byteLength(corpo));
    corpo += `${i + 1} 0 obj\n${objeto}\nendobj\n`;
  });
  const xref = Buffer.byteLength(corpo);
  corpo += `xref\n0 ${objetos.length + 1}\n0000000000 65535 f \n`;
  for (const offset of offsets) corpo += `${String(offset).padStart(10, '0')} 00000 n \n`;
  corpo += `trailer\n<< /Size ${objetos.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return Buffer.from(corpo, 'latin1');
}

/** Arquivo sintético grande em disco: cabeçalho PDF e bytes aleatórios, sem `%%EOF`. */
async function arquivoGrande(megabytes: number): Promise<string> {
  const caminho = join(tmpdir(), `sintetico-${randomBytes(4).toString('hex')}.pdf`);
  const saida = createWriteStream(caminho);
  saida.write('%PDF-1.7\n');
  const bloco = randomBytes(1024 * 1024);
  for (let i = 0; i < megabytes; i++) {
    if (!saida.write(bloco)) await new Promise((r) => saida.once('drain', r));
  }
  await new Promise<void>((r) => saida.end(r));
  return caminho;
}

async function estadoFinal(page: Page, nome: string): Promise<string[]> {
  const linha = page.getByTestId('lista-arquivos').locator('tr', { hasText: nome });
  const vistos: string[] = [];
  await expect(async () => {
    const estado = (await linha.getByTestId('estado-arquivo').getAttribute('data-estado')) ?? '';
    if (vistos.at(-1) !== estado) vistos.push(estado);
    expect(ESTADOS_FINAIS).toContain(estado);
  }).toPass({ timeout: 120_000, intervals: [250] });
  return vistos;
}

test.describe.serial('Etapas 6.4 a 6.7', () => {
  test.beforeAll(async ({ browser }) => {
    contexto = await browser.newContext();
    page = await contexto.newPage();
    expect(USUARIO, 'rode via front/scripts/e2e.sh (prepara o processo)').not.toBe('');
    expect(SENHA_TEMPORARIA).not.toBe('');
    expect(PROCESSO).not.toBe('');
  });

  test.afterAll(async () => {
    await contexto.close();
  });

  test('primeiro acesso do assessor do processo sintético', async () => {
    await page.goto('/login');
    await page.getByLabel('Usuário').fill(USUARIO);
    await page.getByLabel('Senha', { exact: true }).fill(SENHA_TEMPORARIA);
    await page.getByRole('button', { name: 'Continuar' }).click();
    const uri = (await page.getByTestId('uri-mfa').textContent()) ?? '';
    const autenticador = new Autenticador(segredoDaUri(uri.trim()));
    await page.getByLabel('Código de 6 dígitos').fill(await autenticador.proximo());
    await page.getByRole('button', { name: 'Confirmar autenticador' }).click();
    await expect(page).toHaveURL(/\/trocar-senha$/);
    const senha = `frase-e2e-${randomBytes(9).toString('base64url')}-proc`;
    await page.getByLabel('Senha atual').fill(SENHA_TEMPORARIA);
    await page.getByLabel('Nova senha', { exact: true }).fill(senha);
    await page.getByLabel('Confirme a nova senha').fill(senha);
    await page.getByRole('button', { name: 'Salvar nova senha' }).click();
    await expect(page.getByTestId('usuario-nome')).toHaveText(USUARIO);
    // 6.10: conta e sessão ficam para os testes finais (acessibilidade nas telas do processo).
    guardarConta('assessor-processos', { usuario: USUARIO, senha, autenticador });
    await guardarSessao('assessor-processos', contexto);
  });

  test('6.4 lista mostra o processo sintético e o status acompanha a fila', async () => {
    await page.getByRole('navigation', { name: 'Menu principal' }).getByRole('link', { name: 'Processos' }).click();
    await expect(page).toHaveURL(/\/processos$/);
    const linha = page.locator(`tr[data-processo="${PROCESSO}"]`);
    await expect(linha).toBeVisible();
    await expect(linha.getByTestId('situacao')).toHaveText(/Concluído|Com pendências/, { timeout: 120_000 });
  });

  test('6.4 cria processo (CNJ validado), envia PDF e o status muda; quarentena legível', async () => {
    test.setTimeout(240_000);
    await page.goto('/processos');
    const sequencial = 1_000_000 + Math.floor(Math.random() * 8_000_000);
    await page.getByLabel('Número CNJ').fill(numeroCnj(sequencial, false));
    await page.getByLabel('Classe').fill('Apelação Criminal');
    await page.getByRole('button', { name: 'Criar processo' }).click();
    await expect(page.getByText('Dígito verificador não confere.')).toBeVisible();
    await page.getByLabel('Número CNJ').fill(numeroCnj(sequencial, true));
    await page.getByRole('button', { name: 'Criar processo' }).click();
    await expect(page.getByText(/Processo .* criado\./)).toBeVisible();
    await page.getByRole('link', { name: numeroCnj(sequencial, true) }).click();
    await expect(page).toHaveURL(/\/processos\/[0-9a-f-]{36}$/);
    processoNovo = page.url().split('/').at(-1) ?? '';

    await page.getByLabel(/Arquivo PDF ou ZIP/).setInputFiles({
      name: 'peca-e2e.pdf',
      mimeType: 'application/pdf',
      buffer: pdfMinimo(`Peca sintetica ${sequencial}`),
    });
    await page.getByRole('button', { name: 'Enviar' }).click();
    await expect(page.getByText(/peca-e2e\.pdf recebido/)).toBeVisible();
    const vistos = await estadoFinal(page, 'peca-e2e.pdf');
    expect(vistos.length, `estados vistos: ${vistos.join(' → ')}`).toBeGreaterThan(1);
    expect(vistos[0]).not.toBe(vistos.at(-1));
    expect(['concluido', 'em_revisao']).toContain(vistos.at(-1));

    await page.getByLabel(/Arquivo PDF ou ZIP/).setInputFiles({
      name: 'truncado.pdf',
      mimeType: 'application/pdf',
      buffer: Buffer.from('%PDF-1.7\n1 0 obj << >> endobj\n'),
    });
    await page.getByRole('button', { name: 'Enviar' }).click();
    expect(await estadoFinal(page, 'truncado.pdf')).toContain('quarentena');
    const linha = page.getByTestId('lista-arquivos').locator('tr', { hasText: 'truncado.pdf' });
    await expect(linha.getByTestId('motivo-quarentena')).toHaveText(/incompleto/);
  });

  test(`6.4 upload de ${MEGABYTES_GRANDE} MB com progresso sem travar a interface`, async () => {
    test.setTimeout(600_000);
    expect(processoNovo).not.toBe('');
    const caminho = await arquivoGrande(MEGABYTES_GRANDE);
    try {
      const tamanho = (await stat(caminho)).size;
        await page.goto(`/processos/${processoNovo}`);
      await page.getByLabel(/Arquivo PDF ou ZIP/).setInputFiles(caminho);
      const inicio = Date.now();
      await page.getByRole('button', { name: 'Enviar' }).click();
      const barra = page.getByTestId('progresso-envio').locator('progress');
      await expect(barra).toBeVisible();
      // Enquanto envia: a página continua desenhando quadros (maior intervalo entre quadros
      // medido no próprio navegador) e a barra avança.
      const maiorIntervalo = await page.evaluate(
        () =>
          new Promise<number>((resolver) => {
            let anterior = performance.now();
            let maior = 0;
            const fim = anterior + 2000;
            const quadro = (agora: number): void => {
              maior = Math.max(maior, agora - anterior);
              anterior = agora;
              if (agora < fim) requestAnimationFrame(quadro);
              else resolver(maior);
            };
            requestAnimationFrame(quadro);
          }),
      );
      expect(maiorIntervalo).toBeLessThan(500);
      await expect(async () => {
        const valor = Number(await barra.getAttribute('value'));
        expect(valor).toBeGreaterThan(0);
      }).toPass({ timeout: 60_000 });
      await expect(page.getByRole('link', { name: 'Dossiê e linha do tempo' })).toBeEnabled();
      await expect(page.getByText(/recebido \(/)).toBeVisible({ timeout: 540_000 });
      const segundos = (Date.now() - inicio) / 1000;
      test.info().annotations.push({
        type: 'upload',
        description: `${(tamanho / 1048576).toFixed(0)} MB em ${segundos.toFixed(1)} s; maior intervalo entre quadros ${maiorIntervalo.toFixed(0)} ms`,
      });
      console.log(`[6.4] upload ${(tamanho / 1048576).toFixed(0)} MB em ${segundos.toFixed(1)} s; maior intervalo entre quadros ${maiorIntervalo.toFixed(0)} ms`);
      expect(['quarentena', 'falho']).toContain((await estadoFinal(page, 'sintetico-')).at(-1));
    } finally {
      await unlink(caminho);
    }
  });

  test('6.5 dossiê: ficha, índice e clique no evento abre o visualizador na página certa', async () => {
    await page.goto(`/processos/${PROCESSO}/dossie`);
    await expect(page.getByTestId('ficha')).toContainText(/\d{7}-\d{2}\.\d{4}/);
    await expect(page.getByTestId('reus')).toContainText('REU-');
    await expect(page.getByTestId('indice-pecas').locator('tbody tr').first()).toBeVisible();
    const eventos = page.getByTestId('evento');
    expect(await eventos.count()).toBeGreaterThan(0);
    const total = Math.min(await eventos.count(), 4);
    for (let i = 0; i < total; i++) {
      await page.goto(`/processos/${PROCESSO}/dossie`);
      const evento = page.getByTestId('evento').nth(i);
      const pagina = await evento.getAttribute('data-pagina');
      await evento.click();
      await expect(page).toHaveURL(/\/visualizador\?evidencia=/);
      await expect(page.getByTestId('pagina-atual')).toHaveText(new RegExp(`^Página ${pagina}\\b`));
      await expect(page.getByTestId('destaque-evidencia').first()).toBeVisible();
      const largura = await page.getByTestId('imagem-pagina').evaluate((img) => (img as HTMLImageElement).naturalWidth);
      expect(largura).toBeGreaterThan(0);
    }
  });

  test('6.6 evidência de cada fato e achado abre na página e destaca o trecho', async ({ request }) => {
    test.setTimeout(240_000);
    await page.goto(`/processos/${PROCESSO}/validacoes`);
    await expect(page.getByTestId('achado').first()).toBeVisible();
    const links = await page.getByTestId('link-evidencia').evaluateAll((els) =>
      els.map((el) => ({ href: el.getAttribute('href') ?? '', texto: el.textContent?.trim() ?? '' })),
    );
    const unicos = [...new Map(links.map((l) => [l.href, l])).values()];
    expect(unicos.length).toBeGreaterThan(0);
    for (const link of unicos) {
      await page.goto(link.href);
      const pagina = link.texto.replace('fl. ', '');
      await expect(page.getByTestId('pagina-atual')).toHaveText(new RegExp(`^Página ${pagina}\\b`));
      await expect(page.getByTestId('trecho-evidencia')).not.toBeEmpty();
      await expect(page.getByTestId('destaque-evidencia').first()).toBeVisible();
      const caixa = await page.getByTestId('destaque-evidencia').first().boundingBox();
      const imagem = await page.getByTestId('imagem-pagina').boundingBox();
      expect(caixa && imagem).toBeTruthy();
      if (caixa && imagem) {
        expect(caixa.x).toBeGreaterThanOrEqual(imagem.x - 1);
        expect(caixa.y).toBeGreaterThanOrEqual(imagem.y - 1);
        expect(caixa.x + caixa.width).toBeLessThanOrEqual(imagem.x + imagem.width + 1);
      }
    }
    // A imagem é PNG privado; o cliente nunca recebe o PDF.
    const imagem = await page.getByTestId('imagem-pagina').getAttribute('src');
    const resposta = await page.request.get(imagem ?? '');
    expect(resposta.headers()['content-type']).toBe('image/png');
    expect(resposta.headers()['cache-control']).toMatch(/^private/);
    // Sem sessão, nada.
    expect((await request.get(imagem ?? '')).status()).toBe(401);
    // Teclado: seta para a direita avança a página.
    await page.getByTestId('moldura-pagina').focus();
    const antes = (await page.getByTestId('pagina-atual').textContent()) ?? '';
    const [, atual, total] = /Página (\d+) de (\d+)/.exec(antes) ?? [];
    await page.keyboard.press(atual === total ? 'ArrowLeft' : 'ArrowRight');
    await expect(page.getByTestId('pagina-atual')).not.toHaveText(antes);
    await page.keyboard.press('+');
    await expect(page.getByTestId('zoom')).toHaveText('125%');
  });

  test('6.7 corrigir fato gera fato novo ligado; achado antigo fica no histórico; anotar', async () => {
    await page.goto(`/processos/${PROCESSO}/validacoes`);
    const fatoDeData = page
      .getByTestId('achado')
      .getByTestId('fato')
      .filter({ hasText: /\d{2}\/\d{2}\/\d{4}/ })
      .filter({ has: page.getByRole('button', { name: 'Corrigir' }) })
      .first();
    await expect(fatoDeData).toBeVisible();
    const fatoId = await fatoDeData.getAttribute('data-fato');
    await fatoDeData.getByRole('button', { name: 'Corrigir' }).click();
    const campo = page.getByLabel('Valor corrigido');
    const atual = await campo.inputValue();
    expect(atual).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    const ano = Number(atual.slice(0, 4)) - 11;
    await campo.fill(`${ano}${atual.slice(4)}`);
    await page.getByRole('button', { name: 'Salvar correção' }).click();
    await expect(page.getByText(/Fato corrigido\. Validações reexecutadas/)).toBeVisible();
    await expect(page.getByTestId('status-fato').filter({ hasText: 'Corrigido' }).first()).toBeVisible();
    await expect(page.getByTestId('historico-fatos')).toContainText(String(ano));
    await expect(page.getByTestId('historico-achados').locator('tbody tr').first()).toBeVisible();
    expect(await page.locator(`[data-fato="${fatoId}"] button`, { hasText: 'Corrigir' }).count()).toBe(0);

    const achado = page.getByTestId('achado').first();
    await achado.getByRole('button', { name: 'Anotar' }).last().click();
    await achado.getByLabel('Anotação').fill('Conferir a certidão de intimação.');
    await achado.getByRole('button', { name: 'Salvar anotação' }).click();
    await expect(page.getByText('Anotação registrada.')).toBeVisible();
    await expect(achado.getByText('Conferir a certidão de intimação.')).toBeVisible();
  });
});
