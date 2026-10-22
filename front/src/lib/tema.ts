// Alternância manual de tema (6.10): claro, escuro ou o do sistema. A escolha fica só no
// localStorage deste navegador (nada vai ao servidor); /inicio.js a aplica antes do primeiro
// desenho e este módulo a troca em tempo de execução.
export type Tema = 'claro' | 'escuro' | 'sistema';

export const CHAVE_TEMA = 'lupa.tema';
export const TEMAS: readonly { valor: Tema; rotulo: string }[] = [
  { valor: 'sistema', rotulo: 'Do sistema' },
  { valor: 'claro', rotulo: 'Claro' },
  { valor: 'escuro', rotulo: 'Escuro' },
];

function armazenamentoPadrao(): Storage | null {
  try {
    return typeof localStorage === 'undefined' ? null : localStorage;
  } catch {
    return null;
  }
}

export function lerTema(armazenamento: Storage | null = armazenamentoPadrao()): Tema {
  try {
    const valor = armazenamento?.getItem(CHAVE_TEMA);
    return valor === 'claro' || valor === 'escuro' ? valor : 'sistema';
  } catch {
    return 'sistema';
  }
}

export function aplicarTema(tema: Tema, raiz: HTMLElement = document.documentElement): void {
  if (tema === 'sistema') delete raiz.dataset['tema'];
  else raiz.dataset['tema'] = tema;
}

export function escolherTema(
  tema: Tema,
  armazenamento: Storage | null = armazenamentoPadrao(),
  raiz: HTMLElement = document.documentElement,
): void {
  aplicarTema(tema, raiz);
  try {
    if (tema === 'sistema') armazenamento?.removeItem(CHAVE_TEMA);
    else armazenamento?.setItem(CHAVE_TEMA, tema);
  } catch {
    // Sem armazenamento: o tema vale só até recarregar.
  }
}
