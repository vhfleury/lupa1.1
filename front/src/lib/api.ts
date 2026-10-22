// Cliente da API, servida no mesmo origin em /api (o proxy remove o prefixo).
// Cookie de sessão HttpOnly/Secure/SameSite=Strict: o navegador o envia sozinho.

export const BASE_API = '/api';
const DETALHE_NAO_AUTENTICADO = 'não autenticado';
const DETALHE_TROCA_OBRIGATORIA = 'troca de senha obrigatória';
const MENSAGEM_MUITAS_TENTATIVAS = 'Muitas tentativas. Aguarde alguns minutos e tente novamente.';

export class ErroApi extends Error {
  readonly status: number;
  readonly detalhe: string;

  constructor(status: number, detalhe: string) {
    super(detalhe);
    this.name = 'ErroApi';
    this.status = status;
    this.detalhe = detalhe;
  }

  get sessaoExpirada(): boolean {
    return this.status === 401 && this.detalhe === DETALHE_NAO_AUTENTICADO;
  }

  get trocaObrigatoria(): boolean {
    return this.status === 403 && this.detalhe === DETALHE_TROCA_OBRIGATORIA;
  }
}

export interface Manipuladores {
  sessaoExpirada: () => void;
  trocaObrigatoria: () => void;
}

let manipuladores: Manipuladores = { sessaoExpirada: () => {}, trocaObrigatoria: () => {} };

/** Define o que fazer quando uma chamada descobre sessão expirada ou troca de senha pendente. */
export function configurarManipuladores(novos: Manipuladores): void {
  manipuladores = novos;
}

function detalheDe(corpo: unknown): string {
  if (typeof corpo === 'object' && corpo !== null && 'detail' in corpo) {
    const detalhe = (corpo as { detail: unknown }).detail;
    if (typeof detalhe === 'string') return detalhe;
  }
  return '';
}

export interface OpcoesChamada {
  /** Falso nas rotas de login: 401 ali é credencial errada, não sessão expirada. */
  tratarSessao?: boolean;
  fetch?: typeof fetch;
}

export async function chamar<T>(
  metodo: 'GET' | 'POST',
  caminho: string,
  corpo?: unknown,
  opcoes: OpcoesChamada = {},
): Promise<T> {
  const executar = opcoes.fetch ?? fetch;
  const cabecalhos: Record<string, string> = { Accept: 'application/json' };
  const init: RequestInit = { method: metodo, credentials: 'same-origin', headers: cabecalhos };
  if (corpo !== undefined) {
    cabecalhos['Content-Type'] = 'application/json';
    init.body = JSON.stringify(corpo);
  }
  const resposta = await executar(`${BASE_API}${caminho}`, init);
  if (resposta.status === 204) return undefined as T;
  const texto = await resposta.text();
  let json: unknown = null;
  try {
    json = texto ? JSON.parse(texto) : null;
  } catch {
    json = null;
  }
  if (!resposta.ok) {
    const erro = new ErroApi(resposta.status, detalheDe(json));
    if (opcoes.tratarSessao !== false) {
      if (erro.sessaoExpirada) manipuladores.sessaoExpirada();
      else if (erro.trocaObrigatoria) manipuladores.trocaObrigatoria();
    }
    throw erro;
  }
  return json as T;
}

/** Mensagem do primeiro passo; idêntica para usuário inexistente e senha errada. */
export function mensagemLogin(erro: unknown): string {
  if (erro instanceof ErroApi) {
    if (erro.status === 429) return MENSAGEM_MUITAS_TENTATIVAS;
    if (erro.status === 401 || erro.status === 422) return 'Usuário ou senha inválidos.';
  }
  return 'Não foi possível entrar agora. Tente novamente.';
}

/** Mensagem do segundo passo (código TOTP). */
export function mensagemCodigo(erro: unknown): string {
  if (erro instanceof ErroApi) {
    if (erro.status === 429) return MENSAGEM_MUITAS_TENTATIVAS;
    if (erro.status === 401 || erro.status === 422) {
      return 'Código inválido ou expirado. Confira o relógio do celular e use o código atual.';
    }
  }
  return 'Não foi possível conferir o código agora. Tente novamente.';
}

/** Mensagem geral das telas autenticadas (texto do servidor exibido só como texto). */
export function mensagemErro(erro: unknown): string {
  if (erro instanceof ErroApi) {
    if (erro.status === 403) return 'Ação não permitida para o seu papel.';
    if (erro.status === 404) return 'Registro não encontrado.';
    if (erro.detalhe) return `${erro.detalhe.charAt(0).toUpperCase()}${erro.detalhe.slice(1)}.`;
  }
  return 'Algo deu errado. Tente novamente.';
}
