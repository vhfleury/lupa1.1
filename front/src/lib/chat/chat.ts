// Chat por processo (Etapa 6.8): formatos de src/lupa/api/rotas/chat.py e api/rotas/revisao.py,
// e as regras de exibição (rótulos, link da citação para o visualizador da 6.6).
import { chamar } from '$lib/api';

export type StatusMensagem =
  | 'pergunta'
  | 'respondida'
  | 'sem_evidencia'
  | 'recusa'
  | 'descartada'
  | 'teto';

export interface Citacao {
  pagina_id: string;
  trecho: string;
  hash_trecho: string;
  pagina_numero: number | null;
  arquivo_id: string | null;
}

export interface Mensagem {
  mensagem_id: string;
  papel: 'usuario' | 'agente';
  status: StatusMensagem;
  texto: string;
  citacoes: Citacao[];
  avisos: string[];
  citacoes_descartadas: number;
  rotulo: string | null;
  criado_em: string | null;
}

export interface Conversa {
  conversa_id: string;
  criada_em: string;
  encerrada: boolean;
  motivo_encerramento: string | null;
  citacoes_descartadas: number;
  mensagens: Mensagem[];
}

export interface Historico {
  processo_id: string;
  conversas: Conversa[];
}

export interface SituacaoRevisao {
  processo_id: string;
  status: string;
  em_revisao: boolean;
  motivo: string | null;
  aberta_em: string | null;
}

export const AVISO_IA = 'Conteúdo gerado por IA: confira na página citada antes de usar.';

/** Rótulo do desfecho da resposta do agente; null quando não há o que destacar. */
export function rotuloStatus(status: StatusMensagem): string | null {
  switch (status) {
    case 'sem_evidencia':
      return 'Sem citação válida: resposta não conferida nos autos';
    case 'recusa':
      return 'Pergunta fora do que o assistente pode responder';
    case 'descartada':
      return 'Resposta descartada pela conferência automática';
    case 'teto':
      return 'Limite de uso atingido';
    default:
      return null;
  }
}

export const MOTIVO_REVISAO: Record<string, string> = {
  instrucao_refletida: 'a resposta repetia uma instrução contida nos autos',
  outro_processo: 'a resposta citava identificador de outro processo',
};

export const MOTIVO_ENCERRAMENTO: Record<string, string> = {
  teto_conversa: 'limite de uso da conversa atingido',
  teto_processo: 'limite de uso do processo atingido',
};

/**
 * Destino do link da citação: o visualizador de páginas (6.6), na página citada.
 * 6.10: a rota antiga `/paginas/N` não existia (caía no 404 da SPA) e levava o trecho dos autos
 * na URL (histórico, logs). Agora só ids e número: `arquivo` desambigua processos com vários
 * arquivos; o trecho continua visível na própria citação.
 */
export function linkCitacao(processoId: string, citacao: Citacao): string | null {
  if (citacao.pagina_numero === null) return null;
  const busca = new URLSearchParams();
  if (citacao.arquivo_id) busca.set('arquivo', citacao.arquivo_id);
  busca.set('pagina', String(citacao.pagina_numero));
  return `/processos/${encodeURIComponent(processoId)}/visualizador?${busca.toString()}`;
}

/** Conversa em andamento (a última não encerrada), se houver. */
export function conversaAtual(historico: Conversa[]): Conversa | null {
  const ultima = historico.at(-1);
  return ultima && !ultima.encerrada ? ultima : null;
}

export function plural(n: number, singular: string, varios: string): string {
  return `${n} ${n === 1 ? singular : varios}`;
}

export const apiChat = {
  historico: (id: string) => chamar<Historico>('GET', `/processos/${id}/chat`),
  perguntar: (id: string, pergunta: string) =>
    chamar<Mensagem>('POST', `/processos/${id}/chat`, { pergunta }),
  revisao: (id: string) => chamar<SituacaoRevisao>('GET', `/processos/${id}/revisao`),
  liberar: (id: string) => chamar<SituacaoRevisao>('POST', `/processos/${id}/liberar-revisao`),
};
