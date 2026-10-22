// Contas compartilhadas entre arquivos de teste (6.10; revisão 6.4-6.9, item 6). Cada arquivo dos
// fluxos é dono do primeiro acesso de uma conta e a guarda aqui; os testes finais a reutilizam.
// O último passo TOTP usado também é guardado: o servidor recusa código de passo já usado.
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { expect, type Browser, type BrowserContext, type Page } from '@playwright/test';
import { Autenticador } from './totp';

export const DIRETORIO_ESTADO = process.env['LUPA_E2E_ESTADO'] ?? '/tmp/lupa-e2e-estado';

export type Papel = 'admin' | 'desembargador-chat' | 'assessor-processos';

export interface Conta {
  usuario: string;
  senha: string;
  autenticador: Autenticador;
}

interface ContaSalva {
  usuario: string;
  senha: string;
  segredo: string;
  ultimo: number;
}

function arquivoConta(papel: Papel): string {
  return join(DIRETORIO_ESTADO, `${papel}.json`);
}

function arquivoSessao(papel: Papel): string {
  return join(DIRETORIO_ESTADO, `${papel}.sessao.json`);
}

export function guardarConta(papel: Papel, conta: Conta): void {
  const salva: ContaSalva = {
    usuario: conta.usuario,
    senha: conta.senha,
    segredo: conta.autenticador.segredo,
    ultimo: conta.autenticador.ultimoPasso,
  };
  writeFileSync(arquivoConta(papel), JSON.stringify(salva), { mode: 0o600 });
}

export function lerConta(papel: Papel): Conta {
  const caminho = arquivoConta(papel);
  if (!existsSync(caminho)) throw new Error(`conta ${papel} não guardada (o fluxo dono falhou?)`);
  const salva = JSON.parse(readFileSync(caminho, 'utf8')) as ContaSalva;
  return {
    usuario: salva.usuario,
    senha: salva.senha,
    autenticador: new Autenticador(salva.segredo, salva.ultimo),
  };
}

/** Guarda o estado de sessão (cookie) do contexto, para outro arquivo reaproveitar o login. */
export async function guardarSessao(papel: Papel, contexto: BrowserContext): Promise<void> {
  await contexto.storageState({ path: arquivoSessao(papel) });
}

/** Login completo (senha + TOTP) pela tela, com a conta guardada; atualiza o passo TOTP. */
export async function entrarComo(page: Page, papel: Papel): Promise<Conta> {
  const conta = lerConta(papel);
  await page.goto('/login');
  await page.getByLabel('Usuário').fill(conta.usuario);
  await page.getByLabel('Senha', { exact: true }).fill(conta.senha);
  await page.getByRole('button', { name: 'Continuar' }).click();
  await page.getByLabel('Código de 6 dígitos').fill(await conta.autenticador.proximo());
  guardarConta(papel, conta);
  await page.getByRole('button', { name: 'Entrar' }).click();
  await expect(page.getByTestId('usuario-nome')).toHaveText(conta.usuario);
  return conta;
}

/**
 * Contexto já autenticado no papel: reaproveita a sessão guardada se ainda valer; senão entra
 * pela tela e guarda a nova sessão. Poucos logins = longe do limite de falhas por IP.
 */
export async function contextoComo(
  browser: Browser,
  papel: Papel,
  opcoes: { tema?: 'claro' | 'escuro' } = {},
): Promise<{ contexto: BrowserContext; page: Page }> {
  const sessao = arquivoSessao(papel);
  const contexto = await browser.newContext(existsSync(sessao) ? { storageState: sessao } : {});
  if (opcoes.tema) {
    await contexto.addInitScript((tema) => window.localStorage.setItem('lupa.tema', tema), opcoes.tema);
  }
  const page = await contexto.newPage();
  const atual = await page.request.get('/api/auth/sessao');
  if (atual.status() !== 200) {
    await entrarComo(page, papel);
    await guardarSessao(papel, contexto);
  }
  return { contexto, page };
}
