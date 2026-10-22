import { describe, expect, it } from 'vitest';
import { acoesSobre, gereUsuarios, papeisCriaveis } from './permissoes';
import type { Permissao, Sessao, Usuario } from './tipos';

const GAB = 'gab-a';

function sessaoDe(papel: Sessao['papel'], permissoes: Permissao[], gabinete: string | null): Sessao {
  return {
    usuario_id: `eu-${papel}`,
    nome_usuario: papel,
    papel,
    gabinete_id: gabinete,
    troca_senha_obrigatoria: false,
    permissoes,
  };
}

const ASSESSOR = sessaoDe('assessor', ['ver_processo', 'subir_processo', 'anotar'], GAB);
const DESEMBARGADOR = sessaoDe(
  'desembargador',
  ['ver_processo', 'subir_processo', 'anotar', 'ver_auditoria', 'gerir_assessor', 'resetar_assessor'],
  GAB,
);
const ADMIN = sessaoDe(
  'administrador',
  [
    'ver_processo',
    'subir_processo',
    'anotar',
    'ver_auditoria',
    'gerir_assessor',
    'resetar_assessor',
    'gerir_desembargador',
    'gerir_gabinetes',
  ],
  null,
);

function usuario(papel: Usuario['papel'], gabinete: string | null, id = `u-${papel}`): Usuario {
  return {
    id,
    nome_usuario: id,
    papel,
    gabinete_id: gabinete,
    ativo: true,
    mfa_confirmado: true,
    troca_senha_obrigatoria: false,
  };
}

describe('matriz de permissões na interface', () => {
  it('assessor não gere ninguém', () => {
    expect(gereUsuarios(ASSESSOR)).toBe(false);
    expect(acoesSobre(ASSESSOR, usuario('assessor', GAB))).toEqual({ gerir: false, resetar: false });
  });

  it('desembargador gere assessor do próprio gabinete, não de outro, nem desembargador', () => {
    expect(papeisCriaveis(DESEMBARGADOR)).toEqual(['assessor']);
    expect(acoesSobre(DESEMBARGADOR, usuario('assessor', GAB))).toEqual({ gerir: true, resetar: true });
    expect(acoesSobre(DESEMBARGADOR, usuario('assessor', 'gab-b'))).toEqual({ gerir: false, resetar: false });
    expect(acoesSobre(DESEMBARGADOR, usuario('desembargador', GAB))).toEqual({ gerir: false, resetar: false });
  });

  it('ninguém age sobre si mesmo nem sobre o administrador', () => {
    expect(acoesSobre(ADMIN, usuario('administrador', null, ADMIN.usuario_id))).toEqual({ gerir: false, resetar: false });
    expect(acoesSobre(DESEMBARGADOR, usuario('desembargador', GAB, DESEMBARGADOR.usuario_id))).toEqual({
      gerir: false,
      resetar: false,
    });
  });

  it('administrador cria desembargador e assessor e gere ambos em qualquer gabinete', () => {
    expect(papeisCriaveis(ADMIN)).toEqual(['desembargador', 'assessor']);
    expect(acoesSobre(ADMIN, usuario('desembargador', 'gab-b'))).toEqual({ gerir: true, resetar: true });
    expect(acoesSobre(ADMIN, usuario('assessor', 'gab-c'))).toEqual({ gerir: true, resetar: true });
  });

  it('sem sessão nada aparece', () => {
    expect(papeisCriaveis(null)).toEqual([]);
    expect(acoesSobre(null, usuario('assessor', GAB))).toEqual({ gerir: false, resetar: false });
  });
});
