import { describe, expect, it, vi } from 'vitest';
import { chamar, configurarManipuladores, ErroApi, mensagemCodigo, mensagemLogin } from './api';

function respostaFalsa(status: number, corpo: unknown): typeof fetch {
  return vi.fn(async () => new Response(corpo === null ? null : JSON.stringify(corpo), { status }));
}

describe('chamar', () => {
  it('prefixa /api e envia JSON com credenciais do mesmo origin', async () => {
    const executar = vi.fn(async () => new Response('{"ok":true}', { status: 200 }));
    const resultado = await chamar<{ ok: boolean }>('POST', '/auth/login', { a: 1 }, { fetch: executar });
    expect(resultado.ok).toBe(true);
    const [url, init] = executar.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe('/api/auth/login');
    expect(init.credentials).toBe('same-origin');
    expect(init.body).toBe('{"a":1}');
  });

  it('204 devolve undefined', async () => {
    const executar = vi.fn(async () => new Response(null, { status: 204 }));
    await expect(chamar('POST', '/auth/logout', undefined, { fetch: executar })).resolves.toBeUndefined();
  });

  it('401 de sessão chama o manipulador de sessão expirada', async () => {
    const sessaoExpirada = vi.fn();
    configurarManipuladores({ sessaoExpirada, trocaObrigatoria: vi.fn() });
    const executar = respostaFalsa(401, { detail: 'não autenticado' });
    await expect(chamar('GET', '/usuarios', undefined, { fetch: executar })).rejects.toBeInstanceOf(ErroApi);
    expect(sessaoExpirada).toHaveBeenCalledOnce();
  });

  it('nas rotas de login o 401 não é tratado como sessão expirada', async () => {
    const sessaoExpirada = vi.fn();
    configurarManipuladores({ sessaoExpirada, trocaObrigatoria: vi.fn() });
    const executar = respostaFalsa(401, { detail: 'usuário ou senha inválidos' });
    await expect(
      chamar('POST', '/auth/login', {}, { fetch: executar, tratarSessao: false }),
    ).rejects.toMatchObject({ status: 401 });
    expect(sessaoExpirada).not.toHaveBeenCalled();
  });

  it('403 de troca obrigatória chama o manipulador de troca', async () => {
    const trocaObrigatoria = vi.fn();
    configurarManipuladores({ sessaoExpirada: vi.fn(), trocaObrigatoria });
    const executar = respostaFalsa(403, { detail: 'troca de senha obrigatória' });
    await expect(chamar('GET', '/usuarios', undefined, { fetch: executar })).rejects.toBeInstanceOf(ErroApi);
    expect(trocaObrigatoria).toHaveBeenCalledOnce();
  });
});

describe('mensagens de login', () => {
  it('usuário inexistente e senha errada recebem a mesma mensagem', () => {
    const inexistente = new ErroApi(401, 'usuário ou senha inválidos');
    const senhaErrada = new ErroApi(401, 'usuário ou senha inválidos');
    expect(mensagemLogin(inexistente)).toBe(mensagemLogin(senhaErrada));
    expect(mensagemLogin(inexistente)).toBe('Usuário ou senha inválidos.');
  });

  it('bloqueio não revela se o usuário existe', () => {
    expect(mensagemLogin(new ErroApi(429, 'qualquer'))).toMatch(/Muitas tentativas/);
    expect(mensagemLogin(new ErroApi(429, 'qualquer'))).not.toMatch(/usuário/i);
  });

  it('código errado tem mensagem própria', () => {
    expect(mensagemCodigo(new ErroApi(401, 'código inválido'))).toMatch(/Código inválido/);
  });
});
