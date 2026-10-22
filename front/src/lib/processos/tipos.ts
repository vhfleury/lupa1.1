// Formatos das respostas das rotas de processo (src/lupa/api/rotas/processos.py, pecas.py,
// achados.py, dossie.py e visualizador.py). Texto vindo da API é sempre exibido como texto.

export type Materia = 'criminal' | 'civel';

export type SituacaoIngestao =
  | 'sem_arquivos'
  | 'processando'
  | 'quarentena'
  | 'falho'
  | 'pendencias'
  | 'concluido';

export interface Processo {
  id: string;
  gabinete_id: string;
  numero_cnj: string;
  classe: string;
  materia: Materia;
  sigiloso: boolean;
  status: string;
  criado_em: string;
}

export interface ProcessoNaLista extends Processo {
  ingestao: {
    situacao: SituacaoIngestao;
    por_estado: Record<string, number>;
    ultimo_envio: string | null;
  };
}

export interface ArquivoProcesso {
  arquivo_id: string;
  nome: string;
  mime: string;
  tamanho_bytes: number;
  enviado_em: string;
  job_id: string | null;
  estado: string | null;
  motivo_quarentena: string | null;
  motivo_falha: string | null;
  total_paginas: number | null;
  finalizado_em: string | null;
}

export interface ArquivosDoProcesso {
  processo_id: string;
  status: string;
  situacao: SituacaoIngestao;
  arquivos: ArquivoProcesso[];
}

export interface RespostaEnvio {
  arquivo_id: string;
  job_id: string;
  estado: string;
  sha256: string;
  tamanho_bytes: number;
  mime: string;
  duplicado: boolean;
}

export interface PecaIndice {
  ordem: number;
  id: string;
  arquivo_id: string;
  tipo: string;
  origem: string;
  pagina_inicial: number;
  pagina_final: number;
  data: string | null;
  tipo_data: string | null;
  evidencia_data: { id: string; pagina_id: string; trecho: string } | null;
  confianca: number;
  metodo: string;
  resumo_flags: { peca: string[]; saneamento: Record<string, number[]>; total_saneamento: number };
}

export interface Indice {
  processo_id: string;
  pecas: PecaIndice[];
}

export interface Citacao {
  pagina_id: string;
  trecho: string;
}

export interface Dossie {
  versao_esquema: string;
  ficha: {
    processo_id: string;
    numero_cnj: string;
    classe: string;
    materia: string;
    status: string;
    reus: string[];
  };
  pecas: {
    ordem: number;
    peca_id: string;
    arquivo_id: string;
    tipo: string;
    origem: string;
    pagina_inicial: number;
    pagina_final: number;
    data: string | null;
    confianca: number;
    flags: Record<string, unknown>;
    resumo_peca: { rotulo: 'gerado'; texto: string; citacoes: Citacao[] } | null;
  }[];
  linha_do_tempo: {
    data: string;
    tipo: string;
    fato_id: string;
    status: string;
    pagina_id: string;
    pagina: number | null;
    trecho: string;
  }[];
  alertas: { pagina_id: string; arquivo_id: string; pagina: number; flags: string[] }[];
  achados: { achado_id: string; validacao: string; resultado: string; explicacao: string }[];
}

export interface EvidenciaFato {
  id: string;
  pagina_id: string;
  arquivo_id: string | null;
  pagina: number | null;
  trecho: string;
  inicio: number;
  fim: number;
}

export interface Fato {
  id: string;
  tipo: string;
  valor: unknown;
  status: 'automatico' | 'confirmado' | 'corrigido';
  confianca: number;
  extraido_por: string;
  substitui_fato_id: string | null;
  substituido_por: string | null;
  vigente: boolean;
  criado_em: string;
  evidencias: EvidenciaFato[];
}

export interface Achado {
  id: string;
  validacao: string;
  versao_catalogo: string;
  resultado: 'conforme' | 'atencao' | 'verificar';
  fatos_usados: string[];
  valores: Record<string, unknown>;
  explicacao: string;
  criado_em: string;
  vigente?: boolean;
}

export interface Anotacao {
  id: string;
  achado_id: string | null;
  fato_id: string | null;
  usuario_id: string;
  autor: string | null;
  texto: string;
  criado_em: string;
}

export interface Retangulo {
  x: number;
  y: number;
  largura: number;
  altura: number;
}

export interface BboxEvidencia {
  evidencia_id: string;
  arquivo_id: string;
  pagina: number;
  trecho: string;
  uniao: Retangulo | null;
  retangulos: Retangulo[];
}
