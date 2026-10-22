// Formatos das respostas da API (src/lupa/acesso/rotas.py).
export type Papel = 'assessor' | 'desembargador' | 'administrador';

export type Permissao =
  | 'ver_processo'
  | 'subir_processo'
  | 'anotar'
  | 'ver_auditoria'
  | 'gerir_assessor'
  | 'resetar_assessor'
  | 'gerir_desembargador'
  | 'gerir_gabinetes';

export interface Sessao {
  usuario_id: string;
  nome_usuario: string;
  papel: Papel;
  gabinete_id: string | null;
  troca_senha_obrigatoria: boolean;
  permissoes: Permissao[];
}

export interface Usuario {
  id: string;
  nome_usuario: string;
  papel: Papel;
  gabinete_id: string | null;
  ativo: boolean;
  mfa_confirmado: boolean;
  troca_senha_obrigatoria: boolean;
}

export interface UsuarioComSenha extends Usuario {
  senha_temporaria: string;
}

export interface Gabinete {
  id: string;
  nome: string;
}

export type RespostaLogin =
  | { etapa: 'mfa'; desafio: string }
  | { etapa: 'configurar_mfa'; desafio: string; segredo: string; uri_qr: string };

export interface RespostaMfa {
  troca_senha_obrigatoria: boolean;
}

export const ROTULO_PAPEL: Record<Papel, string> = {
  assessor: 'Assessor',
  desembargador: 'Desembargador',
  administrador: 'Administrador',
};
