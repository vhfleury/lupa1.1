// Reflexo da matriz de papéis (src/lupa/acesso/papeis.py) na interface: só esconde botões.
// O servidor reconfere tudo; esconder aqui nunca substitui a checagem de lá.
import type { Sessao, Usuario } from './tipos';

export interface AcoesSobre {
  gerir: boolean;
  resetar: boolean;
}

const NENHUMA: AcoesSobre = { gerir: false, resetar: false };

function noEscopo(s: Sessao, alvo: Usuario): boolean {
  if (s.papel === 'administrador') return true;
  return s.gabinete_id !== null && s.gabinete_id === alvo.gabinete_id;
}

/** Ações que a sessão pode executar sobre um usuário (ativar/desativar e resetar). */
export function acoesSobre(s: Sessao | null, alvo: Usuario): AcoesSobre {
  if (s === null || alvo.id === s.usuario_id || alvo.papel === 'administrador') return NENHUMA;
  if (!noEscopo(s, alvo)) return NENHUMA;
  if (alvo.papel === 'assessor') {
    return {
      gerir: s.permissoes.includes('gerir_assessor'),
      resetar: s.permissoes.includes('resetar_assessor'),
    };
  }
  const podeDesembargador = s.permissoes.includes('gerir_desembargador');
  return { gerir: podeDesembargador, resetar: podeDesembargador };
}

export type PapelCriavel = 'assessor' | 'desembargador';

/** Papéis que a sessão pode criar. */
export function papeisCriaveis(s: Sessao | null): PapelCriavel[] {
  if (s === null) return [];
  const papeis: PapelCriavel[] = [];
  if (s.permissoes.includes('gerir_desembargador')) papeis.push('desembargador');
  if (s.permissoes.includes('gerir_assessor')) papeis.push('assessor');
  return papeis;
}

export function gereUsuarios(s: Sessao | null): boolean {
  return papeisCriaveis(s).length > 0;
}
