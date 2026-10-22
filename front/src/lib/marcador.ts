// Marcador de "havia sessão neste separador" (6.10), só em sessionStorage e sem nenhum dado da
// sessão: serve para, numa recarga completa sem sessão válida, dizer "sessão encerrada ou
// expirada" em vez de mostrar o login como se fosse a primeira vez. Sair apaga o marcador.
export const CHAVE_MARCADOR = 'lupa.sessao-anterior';

function armazenamentoPadrao(): Storage | null {
  try {
    return typeof sessionStorage === 'undefined' ? null : sessionStorage;
  } catch {
    return null;
  }
}

export function marcarSessao(armazenamento: Storage | null = armazenamentoPadrao()): void {
  try {
    armazenamento?.setItem(CHAVE_MARCADOR, '1');
  } catch {
    // Sem armazenamento: só perde a mensagem de expiração após recarga.
  }
}

/** Devolve se havia marcador e o apaga (a mensagem aparece uma vez). */
export function consumirMarcador(armazenamento: Storage | null = armazenamentoPadrao()): boolean {
  try {
    const havia = armazenamento?.getItem(CHAVE_MARCADOR) === '1';
    armazenamento?.removeItem(CHAVE_MARCADOR);
    return havia;
  } catch {
    return false;
  }
}
