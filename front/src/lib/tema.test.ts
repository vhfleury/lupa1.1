import { describe, expect, it } from 'vitest';
import { CHAVE_MARCADOR, consumirMarcador, marcarSessao } from './marcador';
import { aplicarTema, CHAVE_TEMA, escolherTema, lerTema } from './tema';

class Memoria implements Storage {
  private dados = new Map<string, string>();
  get length(): number {
    return this.dados.size;
  }
  clear(): void {
    this.dados.clear();
  }
  getItem(chave: string): string | null {
    return this.dados.get(chave) ?? null;
  }
  key(i: number): string | null {
    return [...this.dados.keys()][i] ?? null;
  }
  removeItem(chave: string): void {
    this.dados.delete(chave);
  }
  setItem(chave: string, valor: string): void {
    this.dados.set(chave, valor);
  }
}

class Quebrado extends Memoria {
  override getItem(): string | null {
    throw new Error('bloqueado');
  }
  override setItem(): void {
    throw new Error('bloqueado');
  }
}

describe('tema (6.10)', () => {
  it('padrão é o do sistema; valor desconhecido também', () => {
    const memoria = new Memoria();
    expect(lerTema(memoria)).toBe('sistema');
    memoria.setItem(CHAVE_TEMA, 'roxo');
    expect(lerTema(memoria)).toBe('sistema');
    expect(lerTema(null)).toBe('sistema');
    expect(lerTema(new Quebrado())).toBe('sistema');
  });

  it('escolher grava só no localStorage e marca o <html>', () => {
    const memoria = new Memoria();
    const raiz = document.createElement('html');
    escolherTema('escuro', memoria, raiz);
    expect(memoria.getItem(CHAVE_TEMA)).toBe('escuro');
    expect(raiz.dataset['tema']).toBe('escuro');
    expect(lerTema(memoria)).toBe('escuro');
    escolherTema('claro', memoria, raiz);
    expect(raiz.dataset['tema']).toBe('claro');
    escolherTema('sistema', memoria, raiz);
    expect(memoria.getItem(CHAVE_TEMA)).toBeNull();
    expect(raiz.dataset['tema']).toBeUndefined();
    expect(() => escolherTema('escuro', new Quebrado(), raiz)).not.toThrow();
    aplicarTema('sistema', raiz);
    expect(raiz.hasAttribute('data-tema')).toBe(false);
  });
});

describe('marcador de sessão anterior (6.10)', () => {
  it('marca, é consumido uma vez e tolera armazenamento bloqueado', () => {
    const memoria = new Memoria();
    expect(consumirMarcador(memoria)).toBe(false);
    marcarSessao(memoria);
    expect(memoria.getItem(CHAVE_MARCADOR)).toBe('1');
    expect(consumirMarcador(memoria)).toBe(true);
    expect(consumirMarcador(memoria)).toBe(false);
    expect(() => marcarSessao(new Quebrado())).not.toThrow();
    expect(consumirMarcador(new Quebrado())).toBe(false);
    expect(consumirMarcador(null)).toBe(false);
  });
});
