// Envio de PDF/ZIP em stream para POST /processos/{id}/arquivos?nome= (corpo binário, sem
// multipart). Usa XMLHttpRequest só para ter o progresso do upload; o navegador lê o File do
// disco em partes, então um arquivo de centenas de MB não passa pela memória do JavaScript nem
// trava a interface.
import { BASE_API, ErroApi } from '$lib/api';
import type { RespostaEnvio } from './tipos';

export const LIMITE_BYTES = 512 * 1024 * 1024;
const EXTENSOES = ['.pdf', '.zip'];

export interface Progresso {
  enviados: number;
  total: number;
}

export interface EnvioEmCurso {
  promessa: Promise<RespostaEnvio>;
  cancelar: () => void;
}

/** Problema detectável antes de enviar (o servidor confere de novo pelo conteúdo). */
export function problemaArquivo(arquivo: { name: string; size: number }): string {
  const nome = arquivo.name.toLowerCase();
  if (!EXTENSOES.some((extensao) => nome.endsWith(extensao))) return 'Envie um arquivo PDF ou ZIP.';
  if (arquivo.size === 0) return 'O arquivo está vazio.';
  if (arquivo.size > LIMITE_BYTES) return 'O arquivo passa do limite de 512 MB.';
  return '';
}

function detalhe(texto: string): string {
  try {
    const corpo: unknown = JSON.parse(texto);
    if (typeof corpo === 'object' && corpo !== null && 'detail' in corpo) {
      const valor = (corpo as { detail: unknown }).detail;
      if (typeof valor === 'string') return valor;
    }
  } catch {
    // corpo não JSON
  }
  return '';
}

export function enviarArquivo(
  processoId: string,
  arquivo: File,
  aoProgredir: (p: Progresso) => void,
): EnvioEmCurso {
  const xhr = new XMLHttpRequest();
  const url = `${BASE_API}/processos/${encodeURIComponent(processoId)}/arquivos?nome=${encodeURIComponent(arquivo.name)}`;
  const promessa = new Promise<RespostaEnvio>((resolver, rejeitar) => {
    xhr.open('POST', url);
    xhr.withCredentials = true;
    xhr.setRequestHeader('Content-Type', 'application/octet-stream');
    xhr.setRequestHeader('Accept', 'application/json');
    xhr.upload.onprogress = (evento) => {
      aoProgredir({ enviados: evento.loaded, total: evento.lengthComputable ? evento.total : arquivo.size });
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolver(JSON.parse(xhr.responseText) as RespostaEnvio);
      } else {
        rejeitar(new ErroApi(xhr.status, detalhe(xhr.responseText)));
      }
    };
    xhr.onerror = () => rejeitar(new ErroApi(0, 'falha de rede durante o envio'));
    xhr.onabort = () => rejeitar(new ErroApi(0, 'envio cancelado'));
    xhr.send(arquivo);
  });
  return { promessa, cancelar: () => xhr.abort() };
}

export function formatarBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const unidades = ['KB', 'MB', 'GB'];
  let valor = bytes / 1024;
  let i = 0;
  while (valor >= 1024 && i < unidades.length - 1) {
    valor /= 1024;
    i++;
  }
  return `${valor.toFixed(valor < 10 ? 1 : 0)} ${unidades[i]}`;
}
