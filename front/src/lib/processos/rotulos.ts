// Rótulos legíveis para estados, motivos e enumerações vindos da API.

export const ESTADO_JOB: Record<string, string> = {
  recebido: 'Na fila',
  validado: 'Validado',
  em_extracao: 'Extraindo páginas',
  parcial: 'Parcial',
  em_revisao: 'Concluído com pendências',
  concluido: 'Concluído',
  falho: 'Falhou',
  quarentena: 'Em quarentena',
};

export const SITUACAO: Record<string, string> = {
  sem_arquivos: 'Sem arquivos',
  processando: 'Processando',
  quarentena: 'Em quarentena',
  falho: 'Falhou',
  pendencias: 'Com pendências',
  concluido: 'Concluído',
};

export const MOTIVO_QUARENTENA: Record<string, string> = {
  corrompido: 'O arquivo está corrompido e não pôde ser aberto.',
  senha: 'O arquivo está protegido por senha. Envie uma versão sem senha.',
  truncado: 'O PDF está incompleto (o envio ou a cópia foi interrompido).',
  assinatura_invalida: 'A assinatura digital não cobre o documento inteiro.',
  tipo_invalido: 'O conteúdo não é PDF (ou o ZIP tem arquivo que não é PDF).',
  zip_malicioso: 'O ZIP foi recusado por segurança (caminho perigoso, link ou tamanho excessivo).',
};

export const MOTIVO_FALHA: Record<string, string> = {
  limite_memoria: 'O processamento passou do limite de memória.',
  limite_cpu: 'O processamento passou do limite de tempo de CPU.',
  tempo_esgotado: 'O processamento demorou demais.',
  erro_parser: 'Erro ao ler o PDF.',
  arquivo_ausente: 'O arquivo não foi encontrado no armazenamento.',
  erro_interno: 'Erro interno no processamento.',
};

export const RESULTADO: Record<string, string> = {
  conforme: 'Conforme',
  atencao: 'Atenção',
  verificar: 'Verificar',
};

export const STATUS_FATO: Record<string, string> = {
  automatico: 'Automático',
  confirmado: 'Confirmado',
  corrigido: 'Corrigido',
};

export const ESTADOS_FINAIS = new Set(['concluido', 'falho', 'quarentena', 'em_revisao', 'parcial']);

/** Texto legível de um identificador em snake_case (`tempestividade_recurso`). */
export function legivel(chave: string): string {
  const texto = chave.replace(/_/g, ' ');
  return texto.charAt(0).toUpperCase() + texto.slice(1);
}

export function motivoQuarentena(motivo: string | null): string {
  if (!motivo) return 'Arquivo recusado.';
  return MOTIVO_QUARENTENA[motivo] ?? `Arquivo recusado (${legivel(motivo)}).`;
}

export function motivoFalha(motivo: string | null): string {
  if (!motivo) return 'Falha no processamento.';
  return MOTIVO_FALHA[motivo] ?? `Falha no processamento (${legivel(motivo)}).`;
}

export function formatarData(iso: string | null): string {
  if (!iso) return '—';
  const so = /^\d{4}-\d{2}-\d{2}$/.test(iso);
  const data = new Date(so ? `${iso}T12:00:00` : iso);
  if (Number.isNaN(data.getTime())) return iso;
  return so
    ? data.toLocaleDateString('pt-BR')
    : data.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' });
}

/** Valor de fato sem o envelope do réu. */
export function valorDoFato(valor: unknown): unknown {
  if (typeof valor === 'object' && valor !== null && 'reu_id' in valor && 'valor' in valor) {
    return (valor as { valor: unknown }).valor;
  }
  return valor;
}

export function textoDoValor(valor: unknown): string {
  const v = valorDoFato(valor);
  if (typeof v === 'string') return /^\d{4}-\d{2}-\d{2}$/.test(v) ? formatarData(v) : v;
  if (typeof v === 'number' || typeof v === 'boolean') return String(v);
  return JSON.stringify(v);
}

export const DATA_ISO = /^\d{4}-\d{2}-\d{2}$/;

/** Datas ISO encontradas (recursivamente) nos valores de um achado, com o caminho da chave. */
export function datasDosValores(valores: unknown, caminho = ''): { chave: string; data: string }[] {
  if (typeof valores === 'string') return DATA_ISO.test(valores) ? [{ chave: caminho, data: valores }] : [];
  if (Array.isArray(valores)) {
    return valores.flatMap((v, i) => datasDosValores(v, `${caminho}[${i}]`));
  }
  if (typeof valores === 'object' && valores !== null) {
    return Object.entries(valores).flatMap(([k, v]) =>
      datasDosValores(v, caminho ? `${caminho}.${k}` : k),
    );
  }
  return [];
}
