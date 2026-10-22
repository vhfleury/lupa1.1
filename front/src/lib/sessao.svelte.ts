// Estado da sessão corrente, recarregado do servidor a cada navegação.
import { chamar, ErroApi, type OpcoesChamada } from './api';
import { marcarSessao } from './marcador';
import type { Permissao, Sessao } from './tipos';

let atual = $state<Sessao | null>(null);

export const sessao = {
  get atual(): Sessao | null {
    return atual;
  },
  definir(nova: Sessao | null): void {
    atual = nova;
  },
};

/** Busca a sessão no servidor; devolve null se não houver sessão válida. */
export async function carregarSessao(executar?: typeof fetch): Promise<Sessao | null> {
  const opcoes: OpcoesChamada = { tratarSessao: false };
  if (executar) opcoes.fetch = executar;
  try {
    const nova = await chamar<Sessao>('GET', '/auth/sessao', undefined, opcoes);
    atual = nova;
    marcarSessao();
    return nova;
  } catch (erro) {
    if (erro instanceof ErroApi && erro.status === 401) {
      atual = null;
      return null;
    }
    throw erro;
  }
}

export function tem(s: Sessao | null, permissao: Permissao): boolean {
  return s !== null && s.permissoes.includes(permissao);
}
