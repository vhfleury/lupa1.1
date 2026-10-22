import { fireEvent, render, screen } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import type { Sessao } from '$lib/tipos';
import Cabecalho from './Cabecalho.svelte';
import Confirmacao from './Confirmacao.svelte';
import MenuLateral from './MenuLateral.svelte';
import QrCode from './QrCode.svelte';
import SeletorTema from './SeletorTema.svelte';
import SenhaTemporaria from './SenhaTemporaria.svelte';

const DESEMBARGADOR: Sessao = {
  usuario_id: '1',
  nome_usuario: 'des.silva',
  papel: 'desembargador',
  gabinete_id: 'g1',
  troca_senha_obrigatoria: false,
  permissoes: ['ver_processo', 'gerir_assessor', 'resetar_assessor'],
};

describe('Cabecalho', () => {
  it('mostra nome, papel e o botão sair', async () => {
    const aoSair = vi.fn();
    render(Cabecalho, { sessao: DESEMBARGADOR, aoSair });
    expect(screen.getByTestId('usuario-nome')).toHaveTextContent('des.silva');
    expect(screen.getByTestId('usuario-papel')).toHaveTextContent('Desembargador');
    await fireEvent.click(screen.getByRole('button', { name: 'Sair' }));
    expect(aoSair).toHaveBeenCalledOnce();
  });
});

describe('MenuLateral', () => {
  it('desembargador vê Usuários mas não Gabinetes; item atual marcado', () => {
    render(MenuLateral, { sessao: DESEMBARGADOR, caminho: '/usuarios' });
    const nav = screen.getByRole('navigation', { name: 'Menu principal' });
    expect(nav).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Usuários' })).toHaveAttribute('aria-current', 'page');
    expect(screen.queryByRole('link', { name: 'Gabinetes' })).toBeNull();
  });

  it('assessor só vê Início e Processos (6.4)', () => {
    render(MenuLateral, {
      sessao: { ...DESEMBARGADOR, papel: 'assessor', permissoes: ['ver_processo'] },
      caminho: '/',
    });
    expect(screen.getAllByRole('link').map((l) => l.textContent?.trim())).toEqual([
      'Início',
      'Processos',
    ]);
  });
});

describe('QrCode', () => {
  it('desenha um SVG acessível a partir da URI otpauth', () => {
    render(QrCode, {
      texto: 'otpauth://totp/Lupa:fulano?secret=JBSWY3DPEHPK3PXP&issuer=Lupa',
      rotulo: 'QR do autenticador',
    });
    const svg = screen.getByRole('img', { name: 'QR do autenticador' });
    const caminho = svg.querySelector('path')?.getAttribute('d') ?? '';
    expect(caminho.length).toBeGreaterThan(100);
    expect(svg.innerHTML).not.toContain('otpauth');
  });
});

describe('SenhaTemporaria', () => {
  it('exibe a senha e avisa que não aparece de novo', async () => {
    const aoFechar = vi.fn();
    render(SenhaTemporaria, { nomeUsuario: 'ana', senha: 'abc-def-ghi', aoFechar });
    expect(screen.getByTestId('senha-temporaria-valor')).toHaveTextContent('abc-def-ghi');
    expect(screen.getByText(/não será exibida de novo/)).toBeInTheDocument();
    await fireEvent.click(screen.getByRole('button', { name: /Já anotei/ }));
    expect(aoFechar).toHaveBeenCalledOnce();
  });
});

describe('Confirmacao (6.10)', () => {
  it('abre como diálogo rotulado, foca Cancelar e chama cada ação', async () => {
    const aoConfirmar = vi.fn();
    const aoCancelar = vi.fn();
    render(Confirmacao, {
      aberto: true,
      titulo: 'Desativar usuário?',
      mensagem: 'Perde o acesso.',
      rotuloConfirmar: 'Desativar',
      perigo: true,
      aoConfirmar,
      aoCancelar,
    });
    const dialogo = screen.getByTestId('confirmacao');
    expect(dialogo).toHaveAttribute('open');
    expect(dialogo).toHaveAccessibleName('Desativar usuário?');
    expect(screen.getByRole('button', { name: 'Cancelar' })).toHaveFocus();
    await fireEvent.click(screen.getByRole('button', { name: 'Desativar' }));
    expect(aoConfirmar).toHaveBeenCalledOnce();
    await fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }));
    expect(aoCancelar).toHaveBeenCalledOnce();
    await fireEvent(dialogo, new Event('cancel', { cancelable: true }));
    expect(aoCancelar).toHaveBeenCalledTimes(2);
  });

  it('fechado não aparece', () => {
    render(Confirmacao, {
      aberto: false,
      titulo: 'T',
      mensagem: 'M',
      rotuloConfirmar: 'OK',
      aoConfirmar: vi.fn(),
      aoCancelar: vi.fn(),
    });
    expect(screen.getByTestId('confirmacao')).not.toHaveAttribute('open');
  });
});

describe('SeletorTema (6.10)', () => {
  it('tem rótulo e troca o tema do documento', async () => {
    render(SeletorTema, { id: 'tema-teste' });
    const seletor = screen.getByLabelText('Tema');
    await fireEvent.change(seletor, { target: { value: 'escuro' } });
    expect(document.documentElement.dataset['tema']).toBe('escuro');
    await fireEvent.change(seletor, { target: { value: 'sistema' } });
    expect(document.documentElement.dataset['tema']).toBeUndefined();
  });
});
