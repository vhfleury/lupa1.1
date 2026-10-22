// Tela de auditoria (Etapa 6.9): formatos de src/lupa/auditoria/rotas.py e a montagem da query.
import { BASE_API, chamar } from '$lib/api';

export interface EventoAuditoria {
  id: string;
  sequencia: number;
  ocorrido_em: string;
  usuario_id: string | null;
  gabinete_id: string | null;
  processo_id: string | null;
  acao: string;
  objeto_tipo: string | null;
  objeto_id: string | null;
  ip: string | null;
  localizacao: string | null;
  resultado: string;
  versao_modelo: string | null;
  versao_prompt: string | null;
}

export interface PaginaEventos {
  eventos: EventoAuditoria[];
  proximo_cursor: string | null;
}

export interface Verificacao {
  gabinete_id: string | null;
  integra: boolean;
  total: number;
  primeiro_evento_quebrado: string | null;
  motivo: string | null;
}

export interface CustoModelo {
  modelo: string;
  tokens_entrada: number;
  tokens_saida: number;
  custo: string | null;
}

export interface CustoEstimado {
  total: string;
  moeda: string;
  versao_tabela: string;
  fonte: string;
  observacao: string;
  por_modelo: CustoModelo[];
}

export interface RelatorioUso {
  processo: string | null;
  usuario: string | null;
  contagem_por_acao: Record<string, number>;
  primeiro_acesso: string | null;
  ultimo_acesso: string | null;
  chamadas_modelo: { versao_modelo: string | null; versao_prompt: string | null; total: number }[];
  custo_estimado: CustoEstimado;
}

/** Filtros como digitados na tela (strings vazias não filtram). */
export interface Filtros {
  gabinete_id: string;
  usuario_id: string;
  processo_id: string;
  acao: string;
  inicio: string;
  fim: string;
  ip: string;
}

export const FILTROS_VAZIOS: Filtros = {
  gabinete_id: '',
  usuario_id: '',
  processo_id: '',
  acao: '',
  inicio: '',
  fim: '',
  ip: '',
};

/** Ações auditadas (src/lupa/auditoria/eventos.py), para o filtro. */
export const ACOES = [
  'login_ok',
  'login_falha',
  'login_bloqueado',
  'mfa_ok',
  'mfa_falha',
  'logout',
  'senha_trocada',
  'senha_resetada',
  'mfa_resetado',
  'usuario_criado',
  'usuario_desativado',
  'usuario_reativado',
  'gabinete_criado',
  'processo_criado',
  'arquivo_enviado',
  'processo_aberto',
  'pagina_vista',
  'busca',
  'pergunta_chat',
  'anotacao',
  'fato_corrigido',
  'peca_reclassificada',
  'validacao_executada',
  'chamada_modelo',
  'admin_acesso_conteudo',
  'auditoria_consultada',
  'auditoria_exportada',
  'processo_em_revisao',
  'revisao_liberada',
] as const;

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** Mensagem de erro do primeiro filtro inválido, ou null. */
export function validarFiltros(f: Filtros): string | null {
  for (const [campo, rotulo] of [
    ['usuario_id', 'usuário'],
    ['processo_id', 'processo'],
  ] as const) {
    const valor = f[campo].trim();
    if (valor && !UUID.test(valor)) return `O identificador de ${rotulo} não é válido.`;
  }
  if (f.inicio && f.fim && new Date(f.inicio) >= new Date(f.fim)) {
    return 'O início do intervalo deve ser anterior ao fim.';
  }
  return null;
}

/** Instante do campo datetime-local (hora local) em ISO UTC. */
function instante(valor: string): string {
  return new Date(valor).toISOString();
}

/** Query string dos filtros (só os preenchidos), mais os parâmetros extras. */
export function montarQuery(f: Filtros, extras: Record<string, string> = {}): string {
  const busca = new URLSearchParams();
  for (const campo of ['gabinete_id', 'usuario_id', 'processo_id', 'acao', 'ip'] as const) {
    const valor = f[campo].trim();
    if (valor) busca.set(campo, valor);
  }
  if (f.inicio) busca.set('inicio', instante(f.inicio));
  if (f.fim) busca.set('fim', instante(f.fim));
  for (const [chave, valor] of Object.entries(extras)) busca.set(chave, valor);
  const texto = busca.toString();
  return texto ? `?${texto}` : '';
}

/** Link de download da exportação (o navegador manda o cookie de sessão sozinho). */
export function linkExportacao(f: Filtros, formato: 'csv' | 'json'): string {
  return `${BASE_API}/auditoria/exportar${montarQuery(f, { formato })}`;
}

export function textoVerificacao(v: Verificacao): string {
  if (v.integra) return `Cadeia íntegra: ${v.total} evento(s) conferido(s), nenhum hash divergente.`;
  const onde = v.primeiro_evento_quebrado ?? 'desconhecido';
  return `Cadeia QUEBRADA a partir do evento ${onde}${v.motivo ? ` (${v.motivo})` : ''}.`;
}

export function formatarInstante(iso: string | null): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('pt-BR');
}

export function formatarDinheiro(valor: string, moeda: string): string {
  const numero = Number(valor);
  return new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: moeda,
    minimumFractionDigits: 2,
    maximumFractionDigits: 4,
  }).format(numero);
}

export const apiAuditoria = {
  consultar: (f: Filtros, cursor: string | null, limite = 50) =>
    chamar<PaginaEventos>(
      'GET',
      `/auditoria${montarQuery(f, { limite: String(limite), ...(cursor ? { cursor } : {}) })}`,
    ),
  verificar: (gabinete: string) =>
    chamar<Verificacao>('GET', `/auditoria/verificar${gabinete ? `?gabinete_id=${gabinete}` : ''}`),
  relatorio: (gabinete: string, tipo: 'processo' | 'usuario', id: string) => {
    const busca = new URLSearchParams({ [tipo]: id.trim() });
    if (gabinete) busca.set('gabinete_id', gabinete);
    return chamar<RelatorioUso>('GET', `/auditoria/relatorio-uso?${busca.toString()}`);
  },
};
